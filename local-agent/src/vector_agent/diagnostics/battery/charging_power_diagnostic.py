"""Production diagnostic for iOS charging power and connection telemetry.

Retrieves external power presence and charging state via IORegistry
(AppleARMPMUCharger / AppleSmartBattery) with fallback to com.apple.mobile.battery.

Enforces:
- Every PASS requires real EvidenceRecord.
- Strict timeout budgeting across fallback strategies.
- Never claims charging port physical health or pin integrity.
- Level 1 RUNTIME_DETECTION.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.core.logging import get_logger
from vector_agent.devices.ios.bridge import IOSCommandStatus
from vector_agent.devices.ios.compatibility import IOSCompatibilityResolver, StrategyStatus
from vector_agent.devices.ios.version import AppleOSVersion
from vector_agent.diagnostics.definition import DiagnosticDefinition
from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)

if TYPE_CHECKING:
    from vector_agent.devices.ios.bridge import IOSDeviceBridge

logger = get_logger(__name__)

CHARGING_POWER_DEFINITION = DiagnosticDefinition(
    diagnostic_id="charging_power_telemetry",
    name="Charging Power Telemetry",
    category="battery",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_CHARGING_DISCLAIMER = (
    "PASS confirms external power connection state and charge telemetry from device power subsystem. "
    "Does not verify charging port physical pin integrity or high-wattage fast-charge hardware."
)


def _unpack_telemetry(
    res: Any,
) -> tuple[IOSCommandStatus | None, dict[str, Any] | None, str | None]:
    if hasattr(res, "status"):
        return res.status, res.data, res.error
    if isinstance(res, tuple):
        return None, res[0], res[1] if len(res) > 1 else None
    return None, None, "Invalid result"


class IOSChargingPowerDiagnostic:
    """Production diagnostic for iOS charging power telemetry."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return CHARGING_POWER_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        started_at = datetime.now(UTC)
        start_mono = time.monotonic()
        budget: float = float(
            self.definition.timeout_seconds
            if timeout is None
            else min(timeout, self.definition.timeout_seconds)
        )

        def remaining() -> float:
            return float(budget - (time.monotonic() - start_mono))

        # Query ProductVersion to evaluate strategy compatibility dynamically
        raw_os_ver = None
        try:
            if remaining() > 0:
                raw_os_ver = self._bridge.get_metadata_field(
                    serial, "ProductVersion", timeout=min(2.0, remaining())
                )
        except (ADBCommandTimeoutError, TimeoutError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="ProductVersion query timed out during charging power diagnostic preflight.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )
        except (FileNotFoundError, PermissionError):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include 'ideviceinfo'.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        os_ver = AppleOSVersion.parse(raw_os_ver) if isinstance(raw_os_ver, str) else None

        resolver = IOSCompatibilityResolver(available_tools=self._bridge.get_available_tools())
        strategies = resolver.resolve_strategies(self.definition.diagnostic_id, os_ver)

        if strategies and all(
            status == StrategyStatus.KNOWN_UNSUPPORTED for _, status in strategies
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Charging power diagnostics not supported on this iOS version.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        if strategies and all(
            status == StrategyStatus.RUNTIME_UNAVAILABLE for _, status in strategies
        ):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.UNSUPPORTED,
                automation_level=self.definition.automation_level,
                summary="Host toolchain does not include required tools for charging power diagnostics.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        if strategies and all(status == StrategyStatus.UNKNOWN for _, status in strategies):
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary="Device OS version is unknown; charging power diagnostics cannot be safely planned.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=time.monotonic() - start_mono,
            )

        facts: dict[str, Any] | None = None
        strategy_used: str | None = None
        strategy_id: str | None = None
        strategy_status: str | None = None
        strategy_maturity: str | None = None
        last_error: str | None = None
        source_type: EvidenceSourceType = EvidenceSourceType.IDEVICEDIAGNOSTICS

        for strategy, status in strategies:
            if remaining() <= 0:
                break
            if status not in (StrategyStatus.SUPPORTED, StrategyStatus.RUNTIME_PROBE_REQUIRED):
                continue

            strat_id = strategy.strategy_id
            if strat_id == "ioreg_charger":
                # Try AppleSmartBattery first, then AppleARMPMUCharger
                try:
                    res = self._bridge.get_ioreg_entry(
                        serial, "AppleSmartBattery", timeout=remaining()
                    )
                    r_status, r_data, r_err = _unpack_telemetry(res)
                    if r_status == IOSCommandStatus.TIMEOUT:
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.ERROR,
                            automation_level=self.definition.automation_level,
                            summary="Charging power telemetry query timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                        last_error = "Host toolchain does not include 'idevicediagnostics'."
                    elif r_data:
                        facts = r_data
                        strategy_used = "ioregentry AppleSmartBattery"
                        strategy_id = strat_id
                        strategy_status = status.value
                        strategy_maturity = strategy.maturity.value
                        source_type = EvidenceSourceType.IDEVICEDIAGNOSTICS
                        break
                    else:
                        last_error = r_err
                except (ADBCommandTimeoutError, TimeoutError):
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.ERROR,
                        automation_level=self.definition.automation_level,
                        summary="Charging power telemetry query timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except (FileNotFoundError, PermissionError):
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.UNSUPPORTED,
                        automation_level=self.definition.automation_level,
                        summary="Host toolchain does not include 'idevicediagnostics'.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except Exception as exc:
                    last_error = f"AppleSmartBattery query error: {type(exc).__name__}"

                if not facts and remaining() > 0:
                    try:
                        res = self._bridge.get_ioreg_entry(
                            serial, "AppleARMPMUCharger", timeout=remaining()
                        )
                        r_status, r_data, r_err = _unpack_telemetry(res)
                        if r_status == IOSCommandStatus.TIMEOUT:
                            return DiagnosticResult(
                                diagnostic_id=self.definition.diagnostic_id,
                                diagnostic_name=self.definition.name,
                                category=self.definition.category,
                                status=DiagnosticStatus.ERROR,
                                automation_level=self.definition.automation_level,
                                summary="Charging power telemetry query timed out.",
                                started_at=started_at,
                                completed_at=datetime.now(UTC),
                                duration_seconds=time.monotonic() - start_mono,
                            )
                        if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                            last_error = "Host toolchain does not include 'idevicediagnostics'."
                        elif r_data:
                            facts = r_data
                            strategy_used = "ioregentry AppleARMPMUCharger"
                            strategy_id = strat_id
                            strategy_status = status.value
                            strategy_maturity = strategy.maturity.value
                            source_type = EvidenceSourceType.IDEVICEDIAGNOSTICS
                            break
                        else:
                            last_error = r_err
                    except (ADBCommandTimeoutError, TimeoutError):
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.ERROR,
                            automation_level=self.definition.automation_level,
                            summary="Charging power telemetry query timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    except (FileNotFoundError, PermissionError):
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.UNSUPPORTED,
                            automation_level=self.definition.automation_level,
                            summary="Host toolchain does not include 'idevicediagnostics'.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    except Exception as exc:
                        last_error = f"AppleARMPMUCharger query error: {type(exc).__name__}"

            elif strat_id == "battery_domain_charger":
                try:
                    res = self._bridge.get_battery_telemetry(serial, timeout=remaining())
                    r_status, r_data, r_err = _unpack_telemetry(res)
                    if r_status == IOSCommandStatus.TIMEOUT:
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.ERROR,
                            automation_level=self.definition.automation_level,
                            summary="Charging power telemetry query timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                        last_error = "Host toolchain does not include 'ideviceinfo'."
                    elif r_data:
                        facts = r_data
                        strategy_used = "com.apple.mobile.battery"
                        strategy_id = strat_id
                        strategy_status = status.value
                        strategy_maturity = strategy.maturity.value
                        source_type = EvidenceSourceType.IDEVICEINFO
                        break
                    else:
                        last_error = r_err
                except (ADBCommandTimeoutError, TimeoutError):
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.ERROR,
                        automation_level=self.definition.automation_level,
                        summary="Charging power telemetry query timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except (FileNotFoundError, PermissionError):
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.UNSUPPORTED,
                        automation_level=self.definition.automation_level,
                        summary="Host toolchain does not include 'ideviceinfo'.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except Exception as exc:
                    last_error = f"Battery domain fallback error: {type(exc).__name__}"

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if remaining() <= 0 and not facts:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Charging power telemetry timed out within execution budget.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if not facts:
            if last_error and "Host toolchain does not include" in last_error:
                return DiagnosticResult(
                    diagnostic_id=self.definition.diagnostic_id,
                    diagnostic_name=self.definition.name,
                    category=self.definition.category,
                    status=DiagnosticStatus.UNSUPPORTED,
                    automation_level=self.definition.automation_level,
                    summary=last_error,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                )
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Charging power telemetry unavailable ({last_error or 'no data'}).",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Extract charging facts
        ext_connected = facts.get("external_connected") if "external_connected" in facts else None
        is_charging = (
            facts.get("is_charging")
            if "is_charging" in facts
            else (facts.get("battery_is_charging") if "battery_is_charging" in facts else None)
        )

        # Check contradiction: is_charging=True and external_connected=False
        if is_charging is True and ext_connected is False:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=(
                    "Charging power telemetry contradiction detected: device reports charging "
                    "without external power connected."
                ),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Enforce PASS gate: requires at least one defining charging/power fact
        if ext_connected is None and is_charging is None:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Charging power telemetry via {strategy_used} contains no valid power or charging facts.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Build normalized EvidenceRecord
        meta: dict[str, Any] = {
            "strategy": strategy_used,
            "strategy_id": strategy_id,
            "compatibility_status": strategy_status,
            "strategy_maturity": strategy_maturity,
            "disclaimer": _CHARGING_DISCLAIMER,
            "platform": "IOS",
        }
        for k, v in facts.items():
            meta[k] = v

        raw_parts: list[str] = []
        if ext_connected is not None:
            raw_parts.append(f"ExternalConnected={ext_connected}")
        if is_charging is not None:
            raw_parts.append(f"Charging={is_charging}")
        raw_val_str = ", ".join(raw_parts) if raw_parts else "Charging power telemetry retrieved"

        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=source_type,
            source_name=strategy_used or "charging_power",
            collection_method="Apple Power Subsystem Query",
            timestamp=completed_at,
            raw_value=raw_val_str,
            normalized_value=None,
            unit=None,
            reliability=None,
            confidence=None,
            metadata=meta,
        )

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=DiagnosticStatus.PASS,
            automation_level=self.definition.automation_level,
            evidence=[evidence],
            summary=f"Charging/power telemetry retrieved via {strategy_used}. {_CHARGING_DISCLAIMER}",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
