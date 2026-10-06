"""Production iOS device bridge using libimobiledevice-style toolchain.

Security and architecture invariants:
- Fixed executables resolved internally; no arbitrary command strings or paths.
- All subprocess operations use argument arrays (shell=False) through run_command.
- Subprocess timeouts and output caps are strictly enforced.
- UDIDs are validated before passing to any command.
- Raw UDID is internal/transient and is never logged or exposed in public exceptions.
- Data minimization: only allowlisted keys (ProductType, ProductVersion, BuildVersion,
  DeviceClass) and the com.apple.mobile.battery domain may be queried. Full unfiltered
  'ideviceinfo' and DeviceName queries are strictly prohibited.
- Explicit pairing consent: pairing is never triggered automatically from discovery or scans.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from vector_agent.core.config import AgentSettings, get_settings
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceIdentity,
    PairingState,
    Platform,
)
from vector_agent.security.subprocess_policy import run_command
from vector_agent.security.validation import validate_ios_udid

from .parsers import (
    parse_battery_telemetry,
    parse_developer_mode_output,
    parse_disk_usage_output,
    parse_gasgauge_plist,
    parse_idevice_id_output,
    parse_ideviceinfo_key_value,
    parse_ioreg_battery_plist,
    parse_nand_plist,
    parse_pairing_pair_output,
    parse_pairing_validate_output,
)

logger = get_logger(__name__)


class IOSToolchainStatus(StrEnum):
    """Availability of the local iOS device-service toolchain."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class IOSCommandStatus(StrEnum):
    """Execution status of an iOS device-service command."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    MALFORMED = "MALFORMED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class IOSTelemetryResult:
    """Typed result of a telemetry query (supports tuple unpacking for backward compatibility)."""

    status: IOSCommandStatus
    data: dict[str, Any] | None = None
    error: str | None = None

    def __iter__(self) -> Iterator[Any]:
        return iter((self.data, self.error))


@dataclass(frozen=True)
class IOSDeveloperModeResult:
    """Typed result of Developer Mode status query."""

    status: IOSCommandStatus
    state: str = "UNKNOWN"
    message: str | None = None

    def __iter__(self) -> Iterator[Any]:
        return iter((self.state, self.message))


@dataclass(frozen=True)
class IOSPairValidationResult:
    """Typed result of pairing validation."""

    connection_state: ConnectionState
    authorization_state: DeviceAuthorizationState
    message: str
    status: IOSCommandStatus = IOSCommandStatus.SUCCESS

    def __iter__(self) -> Iterator[Any]:
        return iter((self.connection_state, self.authorization_state, self.message))


@dataclass(frozen=True)
class IOSDiscoveryResult:
    """Typed result of iOS device discovery via idevice_id."""

    udids: list[str]
    status: IOSToolchainStatus
    error: str | None = None


class IOSDiscoveryError(Exception):
    """Raised when iOS device discovery fails due to tool error or timeout."""


# Explicit allowlist of safe device-info keys
_ALLOWLISTED_METADATA_KEYS = frozenset(
    {
        "ProductType",
        "ProductVersion",
        "BuildVersion",
        "DeviceClass",
        "HardwareModel",
        "CPUArchitecture",
    }
)

# Explicit allowlist of safe IORegistry entries (ASPStorage removed per L4)
_ALLOWLISTED_IOREG_ENTRIES = frozenset(
    {
        "AppleSmartBattery",
        "AppleARMPMUCharger",
    }
)


class IOSDeviceBridge:
    """Production bridge for iOS devices communicating via legitimate USB device services."""

    def __init__(
        self,
        settings: AgentSettings | None = None,
        *,
        idevice_id_path: str | None = None,
        idevicepair_path: str | None = None,
        ideviceinfo_path: str | None = None,
        idevicediagnostics_path: str | None = None,
        idevicedevmodectl_path: str | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._idevice_id_path = idevice_id_path or cfg.idevice_id_path
        self._idevicepair_path = idevicepair_path or cfg.idevicepair_path
        self._ideviceinfo_path = ideviceinfo_path or cfg.ideviceinfo_path
        self._idevicediagnostics_path = idevicediagnostics_path or cfg.idevicediagnostics_path
        self._idevicedevmodectl_path = idevicedevmodectl_path or cfg.idevicedevmodectl_path
        self._default_timeout = cfg.ios_timeout_seconds

    def is_tool_available(self, tool_name: str) -> bool:
        """Check whether a specific iOS executable is available on the host."""
        path_map = {
            "idevice_id": self._idevice_id_path,
            "idevicepair": self._idevicepair_path,
            "ideviceinfo": self._ideviceinfo_path,
            "idevicediagnostics": self._idevicediagnostics_path,
            "idevicedevmodectl": self._idevicedevmodectl_path,
        }
        target_path = path_map.get(tool_name)
        if not target_path:
            return False
        return shutil.which(target_path) is not None

    def get_available_tools(self) -> dict[str, bool]:
        """Return map of tool availability across all recognized iOS CLI utilities."""
        tools = [
            "idevice_id",
            "idevicepair",
            "ideviceinfo",
            "idevicediagnostics",
            "idevicedevmodectl",
        ]
        return {tool: self.is_tool_available(tool) for tool in tools}

    def get_toolchain_status(self) -> IOSToolchainStatus:
        """Check if basic required iOS command-line tools are available on host PATH."""
        try:
            has_id = shutil.which(self._idevice_id_path) is not None
            has_pair = shutil.which(self._idevicepair_path) is not None
            has_info = shutil.which(self._ideviceinfo_path) is not None

            if has_id and has_pair and has_info:
                return IOSToolchainStatus.AVAILABLE
            return IOSToolchainStatus.UNAVAILABLE
        except Exception as exc:
            logger.warning("Error checking iOS toolchain availability: %s", type(exc).__name__)
            return IOSToolchainStatus.ERROR

    def is_available(self) -> bool:
        """Return True if the iOS toolchain is installed and accessible."""
        return self.get_toolchain_status() == IOSToolchainStatus.AVAILABLE

    def discover_devices_result(self, timeout: float | None = None) -> IOSDiscoveryResult:
        """Discover connected iOS device identifiers returning typed discovery status."""
        if not self.is_tool_available("idevice_id"):
            return IOSDiscoveryResult(
                udids=[],
                status=IOSToolchainStatus.UNAVAILABLE,
                error="idevice_id tool unavailable on host",
            )

        t = timeout if timeout is not None else self._default_timeout
        cmd = [self._idevice_id_path, "-l"]

        try:
            result = run_command(cmd, timeout=t)
            if result.return_code != 0:
                logger.warning(
                    "iOS device discovery exited with non-zero code (%d)",
                    result.return_code,
                )
                return IOSDiscoveryResult(
                    udids=[],
                    status=IOSToolchainStatus.ERROR,
                    error=f"idevice_id exited with code {result.return_code}",
                )
            udids = parse_idevice_id_output(result.stdout)
            return IOSDiscoveryResult(udids=udids, status=IOSToolchainStatus.AVAILABLE)
        except (ADBCommandTimeoutError, TimeoutError):
            logger.warning("iOS device discovery timed out")
            return IOSDiscoveryResult(
                udids=[],
                status=IOSToolchainStatus.ERROR,
                error="idevice_id discovery timed out",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning(
                "iOS discovery tool missing or permission denied (%s)", type(exc).__name__
            )
            return IOSDiscoveryResult(
                udids=[],
                status=IOSToolchainStatus.UNAVAILABLE,
                error=f"idevice_id {type(exc).__name__}",
            )
        except Exception as exc:
            logger.warning("iOS device discovery failed (%s)", type(exc).__name__)
            return IOSDiscoveryResult(
                udids=[],
                status=IOSToolchainStatus.ERROR,
                error=f"idevice_id {type(exc).__name__}",
            )

    def discover_devices(self, timeout: float | None = None) -> list[str]:
        """Discover connected iOS device identifiers via 'idevice_id -l'.

        Returns:
            List of validated raw UDIDs (internal only).
        Raises:
            IOSDiscoveryError: If discovery tool is unavailable or failed.
        """
        res = self.discover_devices_result(timeout=timeout)
        if res.status != IOSToolchainStatus.AVAILABLE:
            raise IOSDiscoveryError(res.error or "iOS device discovery failed")
        return res.udids

    def validate_pairing(
        self,
        udid: str,
        timeout: float = 10.0,
    ) -> IOSPairValidationResult:
        """Check whether the host is paired and trusted with the device.

        Uses 'idevicepair -u <udid> validate'.
        Never triggers pairing.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicepair_path, "-u", valid_udid, "validate"]

        try:
            result = run_command(cmd, timeout=timeout)
            conn_state, auth_state, msg = parse_pairing_validate_output(
                result.return_code,
                result.stdout,
                result.stderr,
            )
            return IOSPairValidationResult(
                connection_state=conn_state,
                authorization_state=auth_state,
                message=msg,
                status=IOSCommandStatus.SUCCESS,
            )
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSPairValidationResult(
                connection_state=ConnectionState.UNKNOWN,
                authorization_state=DeviceAuthorizationState.UNKNOWN,
                message="Pairing validation timed out.",
                status=IOSCommandStatus.TIMEOUT,
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Pairing tool unavailable (%s)", type(exc).__name__)
            return IOSPairValidationResult(
                connection_state=ConnectionState.UNKNOWN,
                authorization_state=DeviceAuthorizationState.UNKNOWN,
                message="Pairing tool is unavailable on host.",
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
            )
        except Exception as exc:
            logger.warning("Pairing validation encountered error (%s)", type(exc).__name__)
            return IOSPairValidationResult(
                connection_state=ConnectionState.UNKNOWN,
                authorization_state=DeviceAuthorizationState.UNKNOWN,
                message="Pairing validation failed.",
                status=IOSCommandStatus.ERROR,
            )

    def pair_device(
        self,
        udid: str,
        timeout: float = 15.0,
    ) -> tuple[PairingState, str]:
        """Perform an explicit user-initiated pairing attempt.

        Uses 'idevicepair -u <udid> pair'.
        This must only be called as a result of an explicit user request.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicepair_path, "-u", valid_udid, "pair"]

        try:
            result = run_command(cmd, timeout=timeout)
            return parse_pairing_pair_output(
                result.return_code,
                result.stdout,
                result.stderr,
            )
        except (ADBCommandTimeoutError, TimeoutError):
            return (
                PairingState.ERROR,
                "Pairing operation timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Pairing tool unavailable (%s)", type(exc).__name__)
            return (
                PairingState.ERROR,
                "Pairing tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("Explicit pairing encountered error (%s)", type(exc).__name__)
            return (
                PairingState.ERROR,
                "Pairing operation encountered an error.",
            )

    def get_metadata_field(
        self,
        udid: str,
        key: str,
        timeout: float = 5.0,
    ) -> str | None:
        """Query a single allowlisted key from ideviceinfo.

        Args:
            udid: Validated iOS UDID.
            key: Name of the key to query (must be in allowlist).
            timeout: Subprocess timeout in seconds.

        Raises:
            ValueError: If key is not in _ALLOWLISTED_METADATA_KEYS.
        """
        if key not in _ALLOWLISTED_METADATA_KEYS:
            raise ValueError(f"Querying metadata key '{key}' is prohibited by privacy allowlist.")

        valid_udid = validate_ios_udid(udid)
        cmd = [self._ideviceinfo_path, "-u", valid_udid, "-k", key]

        try:
            result = run_command(cmd, timeout=timeout)
            if result.return_code != 0:
                return None
            return parse_ideviceinfo_key_value(result.stdout)
        except (ADBCommandTimeoutError, TimeoutError, FileNotFoundError, PermissionError):
            raise
        except Exception as exc:
            logger.debug("Failed to query metadata key %s (%s)", key, type(exc).__name__)
            return None

    def get_identity(
        self,
        udid: str,
        timeout: float = 10.0,
    ) -> DeviceIdentity | None:
        """Query allowlisted metadata to populate DeviceIdentity for a trusted device.

        Shares a single monotonic timeout budget across individual key queries.
        Never retrieves DeviceName, SerialNumber, or account information.
        """
        valid_udid = validate_ios_udid(udid)
        start_mono = time.monotonic()
        deadline = start_mono + timeout

        def get_remaining() -> float:
            return deadline - time.monotonic()

        try:
            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            product_type = self.get_metadata_field(valid_udid, "ProductType", timeout=rem)

            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            product_version = self.get_metadata_field(valid_udid, "ProductVersion", timeout=rem)

            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            build_version = self.get_metadata_field(valid_udid, "BuildVersion", timeout=rem)

            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            device_class = self.get_metadata_field(valid_udid, "DeviceClass", timeout=rem)

            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            hardware_model = self.get_metadata_field(valid_udid, "HardwareModel", timeout=rem)

            rem = get_remaining()
            if rem <= 0:
                raise ADBCommandTimeoutError("get_identity", timeout)
            cpu_architecture = self.get_metadata_field(valid_udid, "CPUArchitecture", timeout=rem)
        except (FileNotFoundError, PermissionError, TimeoutError, ADBCommandTimeoutError):
            raise

        # If we couldn't even retrieve product_type or product_version, return None
        if not product_type and not product_version:
            return None

        return DeviceIdentity(
            platform=Platform.IOS,
            manufacturer="Apple Inc.",
            model=product_type or device_class or "Unknown",
            marketing_name=None,
            android_version=None,
            android_sdk_level=None,
            build_fingerprint=None,
            brand="Apple",
            device_codename=None,
            ios_version=product_version,
            product_type=product_type,
            build_version=build_version,
            device_class=device_class,
            hardware_model=hardware_model,
            cpu_architecture=cpu_architecture,
            serial=None,  # NEVER raw serial
            udid=None,  # NEVER raw UDID
            discovered_at=datetime.now(UTC),
        )

    def get_battery_telemetry(
        self,
        udid: str,
        timeout: float = 10.0,
    ) -> IOSTelemetryResult:
        """Query battery domain telemetry using 'ideviceinfo -u <udid> -q com.apple.mobile.battery'.

        Returns:
            IOSTelemetryResult with status and parsed data.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._ideviceinfo_path, "-u", valid_udid, "-q", "com.apple.mobile.battery"]

        try:
            result = run_command(cmd, timeout=timeout)
            facts, err = parse_battery_telemetry(result.stdout, result.return_code)
            if err:
                status = (
                    IOSCommandStatus.MALFORMED
                    if facts is None and result.return_code == 0
                    else IOSCommandStatus.ERROR
                )
            else:
                status = IOSCommandStatus.SUCCESS
            return IOSTelemetryResult(status=status, data=facts, error=err)
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSTelemetryResult(
                status=IOSCommandStatus.TIMEOUT,
                error="Battery telemetry collection timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Battery query tool unavailable (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
                error="Battery query tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("Battery telemetry query failed (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.ERROR,
                error="Failed to query battery domain.",
            )

    def get_gasgauge_telemetry(
        self,
        udid: str,
        timeout: float = 15.0,
    ) -> IOSTelemetryResult:
        """Query GasGauge diagnostics via 'idevicediagnostics -u <udid> diagnostics GasGauge'.

        Returns:
            IOSTelemetryResult with status and parsed data.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicediagnostics_path, "-u", valid_udid, "diagnostics", "GasGauge"]

        try:
            result = run_command(cmd, timeout=timeout)
            facts, err = parse_gasgauge_plist(result.stdout, result.return_code)
            if err:
                status = (
                    IOSCommandStatus.MALFORMED
                    if facts is None and result.return_code == 0
                    else IOSCommandStatus.ERROR
                )
            else:
                status = IOSCommandStatus.SUCCESS
            return IOSTelemetryResult(status=status, data=facts, error=err)
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSTelemetryResult(
                status=IOSCommandStatus.TIMEOUT,
                error="GasGauge diagnostics collection timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("GasGauge tool unavailable (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
                error="Diagnostics tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("GasGauge diagnostics query failed (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.ERROR,
                error="Failed to query GasGauge diagnostics.",
            )

    def get_ioreg_entry(
        self,
        udid: str,
        entry_name: str,
        timeout: float = 15.0,
    ) -> IOSTelemetryResult:
        """Query a specific allowlisted IORegistry entry.

        Security guard:
        Only entries in _ALLOWLISTED_IOREG_ENTRIES are allowed.
        Broad plane dumps and mutating actions (shutdown, restart, sleep) are strictly rejected.
        """
        if entry_name not in _ALLOWLISTED_IOREG_ENTRIES:
            raise ValueError(f"IORegistry entry '{entry_name}' is not allowlisted.")

        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicediagnostics_path, "-u", valid_udid, "ioregentry", entry_name]

        try:
            result = run_command(cmd, timeout=timeout)
            facts, err = parse_ioreg_battery_plist(result.stdout, result.return_code)
            if err:
                status = (
                    IOSCommandStatus.MALFORMED
                    if facts is None and result.return_code == 0
                    else IOSCommandStatus.ERROR
                )
            else:
                status = IOSCommandStatus.SUCCESS
            return IOSTelemetryResult(status=status, data=facts, error=err)
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSTelemetryResult(
                status=IOSCommandStatus.TIMEOUT,
                error=f"IORegistry entry '{entry_name}' collection timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("IORegistry tool unavailable (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
                error="Diagnostics tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("IORegistry query for %s failed (%s)", entry_name, type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.ERROR,
                error=f"Failed to query IORegistry entry '{entry_name}'.",
            )

    def get_disk_usage_telemetry(
        self,
        udid: str,
        timeout: float = 15.0,
    ) -> IOSTelemetryResult:
        """Query filesystem storage accounting via 'ideviceinfo -u <udid> -q com.apple.disk_usage'.

        Returns:
            IOSTelemetryResult with status and parsed data.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._ideviceinfo_path, "-u", valid_udid, "-q", "com.apple.disk_usage"]

        try:
            result = run_command(cmd, timeout=timeout)
            facts, err = parse_disk_usage_output(result.stdout, result.return_code)
            if err:
                status = (
                    IOSCommandStatus.MALFORMED
                    if facts is None and result.return_code == 0
                    else IOSCommandStatus.ERROR
                )
            else:
                status = IOSCommandStatus.SUCCESS
            return IOSTelemetryResult(status=status, data=facts, error=err)
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSTelemetryResult(
                status=IOSCommandStatus.TIMEOUT,
                error="Storage accounting collection timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Disk usage tool unavailable (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
                error="Storage query tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("Disk usage query failed (%s)", type(exc).__name__)
            return IOSTelemetryResult(
                status=IOSCommandStatus.ERROR,
                error="Failed to query storage accounting domain.",
            )

    def get_developer_mode_state(
        self,
        udid: str,
        timeout: float = 10.0,
    ) -> IOSDeveloperModeResult:
        """Query Developer Mode state via 'idevicedevmodectl -u <udid> list'.

        Read-only query only. Mutating actions (enable, arm, confirm, reveal) are strictly prohibited.
        """
        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicedevmodectl_path, "-u", valid_udid, "list"]

        try:
            result = run_command(cmd, timeout=timeout)
            state, msg = parse_developer_mode_output(
                result.return_code, result.stdout, result.stderr, target_udid=valid_udid
            )
            return IOSDeveloperModeResult(
                status=IOSCommandStatus.SUCCESS,
                state=state,
                message=msg,
            )
        except (ADBCommandTimeoutError, TimeoutError):
            return IOSDeveloperModeResult(
                status=IOSCommandStatus.TIMEOUT,
                state="UNKNOWN",
                message="Developer Mode query timed out.",
            )
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Developer mode tool unavailable (%s)", type(exc).__name__)
            return IOSDeveloperModeResult(
                status=IOSCommandStatus.TOOL_UNAVAILABLE,
                state="UNKNOWN",
                message="Developer Mode tool is unavailable on host.",
            )
        except Exception as exc:
            logger.warning("Developer Mode query failed (%s)", type(exc).__name__)
            return IOSDeveloperModeResult(
                status=IOSCommandStatus.ERROR,
                state="UNKNOWN",
                message="Failed to query Developer Mode status.",
            )

    def get_nand_telemetry(
        self,
        udid: str,
        timeout: float = 15.0,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Query NAND diagnostics via 'idevicediagnostics -u <udid> diagnostics NAND' (investigation)."""
        valid_udid = validate_ios_udid(udid)
        cmd = [self._idevicediagnostics_path, "-u", valid_udid, "diagnostics", "NAND"]

        try:
            result = run_command(cmd, timeout=timeout)
            return parse_nand_plist(result.stdout, result.return_code)
        except (ADBCommandTimeoutError, TimeoutError):
            return None, "NAND diagnostics collection timed out."
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("NAND tool unavailable (%s)", type(exc).__name__)
            return None, "Diagnostics tool is unavailable on host."
        except Exception as exc:
            logger.warning("NAND diagnostics query failed (%s)", type(exc).__name__)
            return None, "Failed to query NAND diagnostics."
