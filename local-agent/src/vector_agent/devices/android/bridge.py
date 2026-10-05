"""Android device bridge using ADB subprocess calls.

Security invariants (enforced throughout):
- All ADB commands use argument arrays (shell=False, no string interpolation).
- Device serial numbers are validated before use.
- Output is bounded and decoded safely.
- Timeouts are mandatory on all calls.
- No user-supplied strings are passed to ADB without allowlist validation.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.capabilities import parse_pm_features
from vector_agent.models.device import DeviceCapabilityProfile
from vector_agent.security.subprocess_policy import run_command
from vector_agent.security.validation import validate_device_serial

logger = get_logger(__name__)


# ============================================================
# Enumerations
# ============================================================


class AdbDeviceState(StrEnum):
    """Observed ADB connection state for a device entry."""

    DEVICE = "DEVICE"  # authorized and ready
    UNAUTHORIZED = "UNAUTHORIZED"
    OFFLINE = "OFFLINE"
    NO_DEVICE = "NO_DEVICE"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    ERROR = "ERROR"


# ============================================================
# Data structures
# ============================================================


@dataclass(frozen=True)
class AdbDeviceEntry:
    """A single entry from 'adb devices -l' output."""

    serial: str
    state: AdbDeviceState
    qualifiers: dict[str, str]  # e.g. {"model": "...", "device": "..."}


@dataclass(frozen=True)
class AndroidDiscoveryResult:
    """Result of ADB device discovery."""

    state: AdbDeviceState
    devices: list[AdbDeviceEntry]
    message: str
    adb_available: bool


@dataclass(frozen=True)
class AndroidIdentity:
    """Basic identity properties retrieved from a connected Android device."""

    serial: str  # internal use only — not exposed raw in API
    manufacturer: str | None
    model: str | None
    device_codename: str | None
    android_version: str | None
    sdk_level: int | None
    brand: str | None
    retrieved_at: datetime


@dataclass(frozen=True)
class BatteryTelemetry:
    """Battery telemetry collected from 'adb shell dumpsys battery'."""

    level: int | None
    scale: int | None
    status: str | None
    health: str | None
    plugged: str | None
    voltage_mv: int | None
    temperature_tenths_c: int | None
    technology: str | None
    present: bool | None
    raw_output: str
    collected_at: datetime

    @property
    def temperature_celsius(self) -> float | None:
        """Convert Android tenths-of-degree Celsius to Celsius."""
        if self.temperature_tenths_c is None:
            return None
        return self.temperature_tenths_c / 10.0

    @property
    def voltage_volts(self) -> float | None:
        """Convert millivolts to volts."""
        if self.voltage_mv is None:
            return None
        return self.voltage_mv / 1000.0


@dataclass(frozen=True)
class BatteryTelemetryResult:
    """Result of battery telemetry collection, including evidence metadata."""

    telemetry: BatteryTelemetry | None
    status: str  # "PASS" | "INCONCLUSIVE" | "ERROR"
    confidence: float  # 0.0–1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


# ============================================================
# Constants
# ============================================================

_BATTERY_STATUS_MAP: dict[str, str] = {
    "1": "Unknown",
    "2": "Charging",
    "3": "Discharging",
    "4": "Not Charging",
    "5": "Full",
}

_BATTERY_HEALTH_MAP: dict[str, str] = {
    "1": "Unknown",
    "2": "Good",
    "3": "Overheat",
    "4": "Dead",
    "5": "Over Voltage",
    "6": "Unspecified Failure",
    "7": "Cold",
}

_BATTERY_PLUGGED_MAP: dict[str, str] = {
    "0": "Unplugged",
    "1": "AC",
    "2": "USB",
    "4": "Wireless",
}

# Properties to retrieve for device identity — ordered, minimal set.
_IDENTITY_PROPS: list[tuple[str, str]] = [
    ("ro.product.manufacturer", "manufacturer"),
    ("ro.product.model", "model"),
    ("ro.product.device", "device_codename"),
    ("ro.build.version.release", "android_version"),
    ("ro.build.version.sdk", "sdk_level"),
    ("ro.product.brand", "brand"),
]


# ============================================================
# AndroidDeviceBridge
# ============================================================


class AndroidDeviceBridge:
    """Safe ADB-backed bridge for Android device operations.

    All methods enforce the subprocess security policy:
    - shell=False, argument arrays only
    - validated serial numbers
    - bounded timeouts and output sizes

    No raw shell strings accepted from callers.
    """

    def __init__(self, adb_path: str = "adb") -> None:
        self._adb_path = adb_path

    # ----------------------------------------------------------
    # ADB availability
    # ----------------------------------------------------------

    def is_adb_available(self) -> bool:
        """Returns True if the adb executable is present on PATH."""
        return shutil.which(self._adb_path) is not None

    def _require_adb(self) -> str:
        """Resolve adb path or raise if not available."""
        resolved = shutil.which(self._adb_path)
        if not resolved:
            raise FileNotFoundError(
                f"ADB executable '{self._adb_path}' not found on PATH. "
                "Install Android Platform Tools before using Android device discovery."
            )
        return resolved

    # ----------------------------------------------------------
    # Device discovery
    # ----------------------------------------------------------

    def discover_devices(self) -> AndroidDiscoveryResult:
        """Enumerate connected Android devices using 'adb devices -l'.

        Returns an AndroidDiscoveryResult with the state and device list.
        Never raises; error conditions are returned as typed results.
        """
        try:
            adb = self._require_adb()
        except FileNotFoundError as exc:
            logger.warning("ADB not available: %s", exc)
            return AndroidDiscoveryResult(
                state=AdbDeviceState.ERROR,
                devices=[],
                message=(
                    "Android Platform Tools are required before VECTOR can discover an Android device. "
                    "Install ADB and ensure it is on PATH."
                ),
                adb_available=False,
            )

        try:
            result = run_command([adb, "devices", "-l"], timeout=10.0)
        except Exception as exc:
            logger.error("ADB devices command failed: %s", exc)
            return AndroidDiscoveryResult(
                state=AdbDeviceState.ERROR,
                devices=[],
                message=f"ADB device enumeration failed: {exc}",
                adb_available=True,
            )

        return _parse_devices_output(result.stdout)

    # ----------------------------------------------------------
    # Device identity
    # ----------------------------------------------------------

    def get_identity(self, serial: str) -> AndroidIdentity:
        """Retrieve basic identity properties from an authorized Android device.

        Args:
            serial: Validated ADB serial number.

        Returns:
            AndroidIdentity with real device properties.

        Raises:
            ValueError: If serial validation fails.
            FileNotFoundError: If ADB is not available.
            RuntimeError: If ADB command fails.
        """
        validated_serial = validate_device_serial(serial)
        adb = self._require_adb()

        props: dict[str, Any] = {}
        for prop_key, field_name in _IDENTITY_PROPS:
            value = self._getprop(adb, validated_serial, prop_key)
            props[field_name] = value

        sdk_raw = props.get("sdk_level")
        sdk_int: int | None = None
        if sdk_raw:
            try:
                sdk_int = int(sdk_raw.strip())
            except ValueError:
                logger.warning("Could not parse SDK level: %r", sdk_raw)

        return AndroidIdentity(
            serial=validated_serial,
            manufacturer=_clean_prop(props.get("manufacturer")),
            model=_clean_prop(props.get("model")),
            device_codename=_clean_prop(props.get("device_codename")),
            android_version=_clean_prop(props.get("android_version")),
            sdk_level=sdk_int,
            brand=_clean_prop(props.get("brand")),
            retrieved_at=datetime.now(UTC),
        )

    def _getprop(self, adb: str, serial: str, prop: str) -> str | None:
        """Execute 'adb -s <serial> shell getprop <prop>' safely.

        The serial has already been validated. prop is a fixed constant from
        _IDENTITY_PROPS — never a user-supplied string.
        """
        try:
            result = run_command(
                [adb, "-s", serial, "shell", "getprop", prop],
                timeout=8.0,
            )
            if result.return_code == 0:
                value = result.stdout.strip()
                return value if value else None
            logger.debug("getprop %s returned rc=%d", prop, result.return_code)
            return None
        except Exception as exc:
            logger.warning("getprop %s failed: %s", prop, exc)
            return None

    # ----------------------------------------------------------
    # Capability discovery
    # ----------------------------------------------------------

    def discover_capabilities(self, serial: str, device_id: str) -> DeviceCapabilityProfile:
        """Discover runtime hardware capabilities from an authorized Android device.

        Uses 'adb shell pm list features' with strict subprocess safety:
        - fixed argument list, shell=False
        - bounded timeout (10.0s) and bounded output
        - validated internal serial (never returned in profile, logs, or error text)

        Level 1 Runtime Detection only.
        """
        try:
            validated_serial = validate_device_serial(serial)
        except Exception:
            raise ValueError(f"Invalid internal device serial for device {device_id}") from None

        adb = self._require_adb()

        try:
            result = run_command(
                [adb, "-s", validated_serial, "shell", "pm", "list", "features"],
                timeout=10.0,
            )
        except (ADBCommandTimeoutError, TimeoutError) as exc:
            logger.warning("pm list features timed out for device %s", device_id)
            raise TimeoutError(
                f"ADB capability discovery timed out for device {device_id}"
            ) from exc
        except Exception as exc:
            logger.warning("pm list features failed for device %s", device_id)
            raise RuntimeError(f"ADB capability discovery failed for device {device_id}") from exc

        if result.return_code != 0:
            safe_stderr = result.stderr.replace(validated_serial, "<SERIAL_REDACTED>")
            logger.warning(
                "pm list features returned exit code %d for device %s (stderr: %s)",
                result.return_code,
                device_id,
                safe_stderr[:100],
            )
            raise RuntimeError(f"pm list features failed with exit code {result.return_code}")

        return parse_pm_features(result.stdout, device_id=device_id, truncated=result.truncated)

    # ----------------------------------------------------------
    # Battery telemetry
    # ----------------------------------------------------------

    def get_battery_telemetry(self, serial: str) -> BatteryTelemetryResult:
        """Collect battery telemetry from 'adb shell dumpsys battery'.

        IMPORTANT: This diagnostic verifies that battery telemetry can be
        successfully retrieved. PASS status means telemetry was collected
        successfully. It does NOT represent battery health assessment.

        Args:
            serial: Validated ADB serial number.

        Returns:
            BatteryTelemetryResult with telemetry data and evidence metadata.
        """
        validated_serial = validate_device_serial(serial)
        collected_at = datetime.now(UTC)
        evidence_source = "ADB / dumpsys battery"
        collection_method = "adb shell dumpsys battery"

        try:
            adb = self._require_adb()
        except FileNotFoundError as exc:
            return BatteryTelemetryResult(
                telemetry=None,
                status="ERROR",
                confidence=0.0,
                evidence_source=evidence_source,
                collection_method=collection_method,
                error=str(exc),
                collected_at=collected_at,
            )

        try:
            result = run_command(
                [adb, "-s", validated_serial, "shell", "dumpsys", "battery"],
                timeout=15.0,
            )
        except Exception as exc:
            logger.error("dumpsys battery command failed: %s", exc)
            return BatteryTelemetryResult(
                telemetry=None,
                status="ERROR",
                confidence=0.0,
                evidence_source=evidence_source,
                collection_method=collection_method,
                error=f"Battery telemetry command failed: {exc}",
                collected_at=collected_at,
            )

        if result.return_code != 0:
            # Device likely disconnected between discovery and test
            return BatteryTelemetryResult(
                telemetry=None,
                status="ERROR",
                confidence=0.0,
                evidence_source=evidence_source,
                collection_method=collection_method,
                error=(
                    f"dumpsys battery returned exit code {result.return_code}. "
                    "The device may have been disconnected."
                ),
                collected_at=collected_at,
            )

        raw_output = result.stdout
        telemetry = _parse_battery_output(raw_output, collected_at)
        status, confidence = _evaluate_battery_telemetry(telemetry)

        return BatteryTelemetryResult(
            telemetry=telemetry,
            status=status,
            confidence=confidence,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=None,
            collected_at=collected_at,
        )


# ============================================================
# Parsing helpers
# ============================================================


def _parse_devices_output(output: str) -> AndroidDiscoveryResult:
    """Parse 'adb devices -l' output into a typed discovery result.

    Handles: no devices, one device, unauthorized, offline, multiple, malformed.
    """
    devices: list[AdbDeviceEntry] = []
    lines = output.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip informational lines
        if stripped.startswith("List of devices"):
            continue
        if stripped.startswith("*") or stripped.startswith("daemon"):
            continue
        # Each device line: "<serial>   <state>   [qualifiers]"
        parts = stripped.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state_str = parts[1].lower()
        qualifiers: dict[str, str] = {}
        for qualifier in parts[2:]:
            if ":" in qualifier:
                k, _, v = qualifier.partition(":")
                qualifiers[k.strip()] = v.strip()

        if state_str == "device":
            state = AdbDeviceState.DEVICE
        elif state_str == "unauthorized":
            state = AdbDeviceState.UNAUTHORIZED
        elif state_str == "offline":
            state = AdbDeviceState.OFFLINE
        else:
            # Unknown state — treat as offline for safety
            state = AdbDeviceState.OFFLINE

        # Basic serial sanity: skip obviously invalid serials
        if not serial or serial.startswith("*"):
            continue

        devices.append(AdbDeviceEntry(serial=serial, state=state, qualifiers=qualifiers))

    if not devices:
        return AndroidDiscoveryResult(
            state=AdbDeviceState.NO_DEVICE,
            devices=[],
            message="No Android devices detected. Connect a phone with USB Debugging enabled.",
            adb_available=True,
        )

    if len(devices) > 1:
        return AndroidDiscoveryResult(
            state=AdbDeviceState.MULTIPLE_DEVICES,
            devices=devices,
            message=(
                f"{len(devices)} Android devices detected. "
                "Connect only one device for VECTOR diagnostics."
            ),
            adb_available=True,
        )

    # Exactly one device
    entry = devices[0]

    if entry.state == AdbDeviceState.UNAUTHORIZED:
        return AndroidDiscoveryResult(
            state=AdbDeviceState.UNAUTHORIZED,
            devices=devices,
            message=(
                "Android device detected but not authorized. "
                "Unlock the phone and approve the USB debugging prompt on the device screen."
            ),
            adb_available=True,
        )

    if entry.state == AdbDeviceState.OFFLINE:
        return AndroidDiscoveryResult(
            state=AdbDeviceState.OFFLINE,
            devices=devices,
            message=(
                "Android device is listed as offline by ADB. "
                "Disconnect and reconnect the USB cable, ensuring it supports data transfer."
            ),
            adb_available=True,
        )

    return AndroidDiscoveryResult(
        state=AdbDeviceState.DEVICE,
        devices=devices,
        message="Android device connected and authorized.",
        adb_available=True,
    )


def _parse_battery_output(raw: str, collected_at: datetime) -> BatteryTelemetry:
    """Parse 'dumpsys battery' output into BatteryTelemetry.

    Handles missing fields safely. Does not raise on malformed values.
    """
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            fields[key.strip().lower()] = value.strip()

    def _int_field(key: str) -> int | None:
        v = fields.get(key)
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            logger.debug("Battery field %r has non-integer value: %r", key, v)
            return None

    def _bool_field(key: str) -> bool | None:
        v = fields.get(key)
        if v is None:
            return None
        return v.lower() in ("true", "1", "yes")

    level = _int_field("level")
    scale = _int_field("scale")
    voltage_mv = _int_field("voltage")
    temperature_tenths = _int_field("temperature")
    present = _bool_field("present")

    # Status: ADB may report numeric or string
    status_raw = fields.get("status")
    status_str: str | None = None
    if status_raw is not None:
        status_str = _BATTERY_STATUS_MAP.get(status_raw, status_raw)

    # Health: similar
    health_raw = fields.get("health")
    health_str: str | None = None
    if health_raw is not None:
        health_str = _BATTERY_HEALTH_MAP.get(health_raw, health_raw)

    # Plugged: prefer the explicit 'plugged' numeric field, otherwise infer
    plugged_raw = fields.get("plugged")
    plugged_str: str | None = None
    if plugged_raw is not None:
        plugged_str = _BATTERY_PLUGGED_MAP.get(plugged_raw, plugged_raw)
    else:
        # Infer from ac powered / usb powered boolean fields
        ac = _bool_field("ac powered")
        usb = _bool_field("usb powered")
        wireless = _bool_field("wireless powered")
        if ac:
            plugged_str = "AC"
        elif usb:
            plugged_str = "USB"
        elif wireless:
            plugged_str = "Wireless"
        elif ac is not None or usb is not None:
            plugged_str = "Unplugged"

    technology = fields.get("technology")

    return BatteryTelemetry(
        level=level,
        scale=scale,
        status=status_str,
        health=health_str,
        plugged=plugged_str,
        voltage_mv=voltage_mv,
        temperature_tenths_c=temperature_tenths,
        technology=technology if technology else None,
        present=present,
        raw_output=raw,
        collected_at=collected_at,
    )


def _evaluate_battery_telemetry(telemetry: BatteryTelemetry) -> tuple[str, float]:
    """Determine PASS/INCONCLUSIVE/ERROR status and confidence for battery telemetry.

    PASS means: telemetry was successfully retrieved and parsed.
    It does NOT mean the battery is healthy.

    Returns:
        (status, confidence) where status is "PASS" | "INCONCLUSIVE" | "ERROR"
    """
    if telemetry.level is None and telemetry.voltage_mv is None:
        return ("INCONCLUSIVE", 0.4)

    present = telemetry.present
    if present is False:
        # Battery reported as not physically present — unusual
        return ("INCONCLUSIVE", 0.5)

    # Count how many key fields were successfully parsed
    key_fields = [
        telemetry.level,
        telemetry.voltage_mv,
        telemetry.temperature_tenths_c,
        telemetry.status,
    ]
    fields_present = sum(1 for f in key_fields if f is not None)

    if fields_present >= 3:
        return ("PASS", 0.95)
    if fields_present >= 1:
        return ("INCONCLUSIVE", 0.6)

    return ("INCONCLUSIVE", 0.3)


def _clean_prop(value: str | None) -> str | None:
    """Strip whitespace and return None for empty strings."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
