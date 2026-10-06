"""Production diagnostic for extended iOS battery telemetry.

Retrieves low-level battery telemetry (cycle count, design capacity, full charge capacity)
via Diagnostics Relay (GasGauge) or IORegistry (AppleSmartBattery / AppleARMPMUCharger).

Enforces:
- Every PASS requires real EvidenceRecord.
- Strict timeout budgeting across fallback strategies.
- Does NOT claim battery health percentage or authenticity.
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

BATTERY_EXTENDED_DEFINITION = DiagnosticDefinition(
    diagnostic_id="battery_extended_telemetry",
    name="Extended Battery Telemetry",
    category="battery",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.IOS}),
    required_capabilities=frozenset(),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=20.0,
    requires_probe=False,
    prerequisites=frozenset(),
)

_DISCLAIMER_NOTE = (
    "PASS confirms retrieval of extended battery metrics from device power management subsystem. "
    "Does not claim battery health percentage, part authenticity, or remaining lifespan."
)


def _unpack_telemetry(
    res: Any,
) -> tuple[IOSCommandStatus | None, dict[str, Any] | None, str | None]:
    if hasattr(res, "status"):
        return res.status, res.data, res.error
    if isinstance(res, tuple):
        return None, res[0], res[1] if len(res) > 1 else None
    return None, None, "Invalid result"


class IOSBatteryExtendedDiagnostic:
    """Production diagnostic for extended iOS battery telemetry."""

    def __init__(self, bridge: IOSDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return BATTERY_EXTENDED_DEFINITION

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
        try:
            raw_os_ver = None
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
                summary="ProductVersion query timed out during battery diagnostic preflight.",
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
                summary="Extended battery diagnostics not supported on this iOS version.",
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
                summary="Host toolchain does not include required tools for extended battery diagnostics.",
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
                summary="Device OS version is unknown; extended battery diagnostics cannot be safely planned.",
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

        for strategy, status in strategies:
            if remaining() <= 0:
                break
            if status not in (StrategyStatus.SUPPORTED, StrategyStatus.RUNTIME_PROBE_REQUIRED):
                continue

            strat_id = strategy.strategy_id
            if strat_id == "gasgauge":
                try:
                    res = self._bridge.get_gasgauge_telemetry(serial, timeout=remaining())
                    r_status, r_data, r_err = _unpack_telemetry(res)
                    if r_status == IOSCommandStatus.TIMEOUT:
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.ERROR,
                            automation_level=self.definition.automation_level,
                            summary="GasGauge diagnostics collection timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                        last_error = r_err
                    elif r_data:
                        facts = r_data
                        strategy_used = "idevicediagnostics GasGauge"
                        strategy_id = strat_id
                        strategy_status = status.value
                        strategy_maturity = strategy.maturity.value
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
                        summary="GasGauge diagnostics collection timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except Exception as exc:
                    last_error = f"GasGauge strategy exception: {type(exc).__name__}"
            elif strat_id == "ioreg_smart_battery":
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
                            summary="AppleSmartBattery diagnostics collection timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    if r_status == IOSCommandStatus.TOOL_UNAVAILABLE:
                        last_error = r_err
                    elif r_data:
                        facts = r_data
                        strategy_used = "ioregentry AppleSmartBattery"
                        strategy_id = strat_id
                        strategy_status = status.value
                        strategy_maturity = strategy.maturity.value
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
                        summary="AppleSmartBattery diagnostics collection timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except Exception as exc:
                    last_error = f"AppleSmartBattery fallback exception: {type(exc).__name__}"
            elif strat_id == "ioreg_armpmu_charger":
                try:
                    res = self._bridge.get_ioreg_entry(
                        serial, "AppleARMPMUCharger", timeout=remaining()
                    )
                    if res.status == IOSCommandStatus.TIMEOUT:
                        return DiagnosticResult(
                            diagnostic_id=self.definition.diagnostic_id,
                            diagnostic_name=self.definition.name,
                            category=self.definition.category,
                            status=DiagnosticStatus.ERROR,
                            automation_level=self.definition.automation_level,
                            summary="AppleARMPMUCharger diagnostics collection timed out.",
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            duration_seconds=time.monotonic() - start_mono,
                        )
                    if res.status == IOSCommandStatus.TOOL_UNAVAILABLE:
                        last_error = res.error
                    elif res.data:
                        facts = res.data
                        strategy_used = "ioregentry AppleARMPMUCharger"
                        strategy_id = strat_id
                        strategy_status = status.value
                        strategy_maturity = strategy.maturity.value
                        break
                    else:
                        last_error = res.error
                except (ADBCommandTimeoutError, TimeoutError):
                    return DiagnosticResult(
                        diagnostic_id=self.definition.diagnostic_id,
                        diagnostic_name=self.definition.name,
                        category=self.definition.category,
                        status=DiagnosticStatus.ERROR,
                        automation_level=self.definition.automation_level,
                        summary="AppleARMPMUCharger diagnostics collection timed out.",
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        duration_seconds=time.monotonic() - start_mono,
                    )
                except Exception as exc:
                    last_error = f"AppleARMPMUCharger fallback exception: {type(exc).__name__}"

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        if remaining() <= 0 and not facts:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Extended battery telemetry timed out within execution budget.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        if not facts:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=f"Extended battery telemetry unavailable or restricted ({last_error or 'no data'}).",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Enforce defining-fact PASS gate (R1, Section 2):
        # PASS requires:
        # - valid cycle_count
        # OR
        # - a source-specific capacity whose semantics/unit are established (keys ending in _mah)
        # Ambiguous raw capacity alone must NOT create a PASS.
        has_defining_fact = False
        cycle_cnt = facts.get("cycle_count")
        if isinstance(cycle_cnt, int) and cycle_cnt >= 0:
            has_defining_fact = True
        for k, v in facts.items():
            if k.endswith("_mah") and isinstance(v, int) and v > 0:
                has_defining_fact = True
                break

        if not has_defining_fact:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.INCONCLUSIVE,
                automation_level=self.definition.automation_level,
                summary=(
                    f"Extended battery telemetry contains only non-defining raw metrics via {strategy_used} "
                    "(cycle count or established capacity unit missing)."
                ),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
            )

        # Build normalized EvidenceRecord with safe formatting (no None / NonemAh)
        meta: dict[str, Any] = {
            "strategy_id": strategy_id or "unknown",
            "compatibility_status": strategy_status or "SUPPORTED",
            "strategy_maturity": strategy_maturity or "CODE_TESTED",
            "strategy": strategy_used,
            "disclaimer": _DISCLAIMER_NOTE,
            "platform": "IOS",
        }
        for k, v in facts.items():
            meta[k] = v

        raw_parts: list[str] = []
        if isinstance(facts.get("cycle_count"), int):
            raw_parts.append(f"Cycles={facts['cycle_count']}")
        if isinstance(facts.get("design_capacity_mah"), int):
            raw_parts.append(f"Design={facts['design_capacity_mah']}mAh")
        if isinstance(facts.get("raw_max_capacity_mah"), int):
            raw_parts.append(f"RawMax={facts['raw_max_capacity_mah']}mAh")
        if isinstance(facts.get("full_charge_capacity_raw"), int):
            raw_parts.append(f"FullRaw={facts['full_charge_capacity_raw']}")
        if isinstance(facts.get("design_capacity_raw"), int):
            raw_parts.append(f"DesignRaw={facts['design_capacity_raw']}")
        raw_value_str = ", ".join(raw_parts) if raw_parts else "Extended battery metrics retrieved"

        evidence = EvidenceRecord(
            evidence_id=uuid4(),
            diagnostic_id=self.definition.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.IDEVICEDIAGNOSTICS,
            source_name=strategy_used or "idevicediagnostics",
            collection_method="Apple Diagnostics Relay / IORegistry",
            timestamp=completed_at,
            raw_value=raw_value_str,
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
            summary=f"Extended battery telemetry retrieved via {strategy_used}. {_DISCLAIMER_NOTE}",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
