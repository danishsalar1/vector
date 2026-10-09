"""Battery Telemetry Diagnostic — VECTOR's first production diagnostic.

Wraps the existing AndroidDeviceBridge.get_battery_telemetry() and produces
structured DiagnosticResult + EvidenceRecord(s) through the production
Diagnostic contract.

Battery semantics (permanent):
- PASS  = battery telemetry was successfully collected.
- PASS != battery is healthy / battery capacity is good.
- Battery charge percentage != battery health.
- Missing evidence → INCONCLUSIVE, never a false PASS/FAIL.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge, BatteryTelemetry
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

logger = get_logger(__name__)

BATTERY_TELEMETRY_DEFINITION = DiagnosticDefinition(
    diagnostic_id="battery_telemetry",
    name="Battery Telemetry Verification",
    category="battery",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.ANDROID}),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=20.0,
)

# Status note — always included to prevent misinterpretation.
_STATUS_NOTE = (
    "PASS confirms successful battery telemetry collection. "
    "It does not represent full battery-health assessment."
)


class BatteryTelemetryDiagnostic:
    """Production diagnostic for Android battery telemetry.

    Delegates platform communication to AndroidDeviceBridge.
    Owns diagnostic interpretation and evidence production.
    """

    def __init__(self, bridge: AndroidDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return BATTERY_TELEMETRY_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run battery telemetry collection and return a structured result.

        Args:
            device_id: Opaque VECTOR device identifier.
            serial: Validated ADB serial (internal only).
            timeout: Optional execution budget override in seconds.

        Returns:
            DiagnosticResult with evidence records.
        """
        started_at = datetime.now(UTC)
        start_mono = time.monotonic()
        budget = (
            self.definition.timeout_seconds
            if timeout is None
            else min(timeout, self.definition.timeout_seconds)
        )

        remaining = budget - (time.monotonic() - start_mono)
        if remaining <= 0:
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Battery telemetry collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(time.monotonic() - start_mono, 3),
            )

        try:
            bridge_result = self._bridge.get_battery_telemetry(serial, timeout=remaining)
        except Exception as exc:
            completed_at = datetime.now(UTC)
            duration = time.monotonic() - start_mono
            logger.error("Battery telemetry diagnostic failed (%s)", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Battery telemetry collection failed due to an execution error.",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=round(duration, 3),
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        # Map bridge status string to DiagnosticStatus enum.
        status = _map_status(bridge_result.status)

        # Build evidence records from the collected telemetry.
        evidence: list[EvidenceRecord] = []
        if bridge_result.telemetry is not None:
            evidence = _build_evidence_records(
                telemetry=bridge_result.telemetry,
                device_id=device_id,
                diagnostic_id=self.definition.diagnostic_id,
                evidence_source=bridge_result.evidence_source,
                collection_method=bridge_result.collection_method,
                confidence=bridge_result.confidence,
                collected_at=bridge_result.collected_at,
            )

        summary = _build_summary(status, bridge_result.error)

        return DiagnosticResult(
            diagnostic_id=self.definition.diagnostic_id,
            diagnostic_name=self.definition.name,
            category=self.definition.category,
            status=status,
            automation_level=self.definition.automation_level,
            evidence=evidence,
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=round(duration, 3),
        )


# ============================================================
# Private helpers
# ============================================================


def _map_status(bridge_status: str) -> DiagnosticStatus:
    """Map the bridge's string status to DiagnosticStatus enum."""
    mapping = {
        "PASS": DiagnosticStatus.PASS,
        "INCONCLUSIVE": DiagnosticStatus.INCONCLUSIVE,
        "ERROR": DiagnosticStatus.ERROR,
    }
    return mapping.get(bridge_status, DiagnosticStatus.ERROR)


def _build_summary(status: DiagnosticStatus, error: str | None) -> str:
    """Produce a human-readable summary for the diagnostic result."""
    if status == DiagnosticStatus.PASS:
        return _STATUS_NOTE
    if status == DiagnosticStatus.INCONCLUSIVE:
        return (
            "Battery telemetry was partially collected. "
            "Some key fields were missing or unparseable."
        )
    # ERROR or unexpected: fixed safe message to prevent leaking internal error details
    return "Battery telemetry collection encountered an execution error."


def _build_evidence_records(
    *,
    telemetry: BatteryTelemetry,
    device_id: str,
    diagnostic_id: str,
    evidence_source: str,
    collection_method: str,
    confidence: float | None,
    collected_at: datetime,
) -> list[EvidenceRecord]:
    """Convert BatteryTelemetry fields into structured EvidenceRecords.

    Each key telemetry field becomes a separate evidence record so that
    provenance is traceable per measurement.

    Normalized values are NOT fabricated.  Battery percentage is NOT
    mapped to a health score.  Fields retain their literal meaning.

    raw_output from the bridge is NOT included here; it stays in the bridge
    for transient debugging only and must never surface through the evidence
    pipeline or API responses.
    """
    records: list[EvidenceRecord] = []

    def _add(
        field_name: str,
        raw_value: str | None,
        *,
        unit: str | None = None,
        normalized_value: float | None = None,
        reliability: float | None = None,
    ) -> None:
        if raw_value is None:
            return
        records.append(
            EvidenceRecord(
                diagnostic_id=diagnostic_id,
                device_id=device_id,
                source_type=EvidenceSourceType.ADB_DUMPSYS,
                source_name=evidence_source,
                collection_method=collection_method,
                timestamp=collected_at,
                raw_value=raw_value,
                normalized_value=normalized_value,
                unit=unit,
                reliability=reliability,
                confidence=None,
                metadata={"field": field_name},
            )
        )

    # Battery level — raw percentage, NOT a health score.
    if telemetry.level is not None:
        _add(
            "battery_level",
            str(telemetry.level),
            unit="percent",
            # normalized_value intentionally omitted.
            # Battery level is NOT battery health.
        )

    # Voltage
    if telemetry.voltage_mv is not None:
        _add(
            "battery_voltage",
            str(telemetry.voltage_mv),
            unit="mV",
        )

    # Temperature
    if telemetry.temperature_tenths_c is not None:
        _add(
            "battery_temperature",
            str(telemetry.temperature_tenths_c),
            unit="tenths_celsius",
        )

    # OS-reported battery health classification (e.g. "Good", "Overheat").
    if telemetry.health is not None:
        _add("battery_health_classification", telemetry.health)

    # Charging status
    if telemetry.status is not None:
        _add("battery_charging_status", telemetry.status)

    # Plugged state
    if telemetry.plugged is not None:
        _add("battery_plugged", telemetry.plugged)

    # Technology
    if telemetry.technology is not None:
        _add("battery_technology", telemetry.technology)

    # Battery present
    if telemetry.present is not None:
        _add("battery_present", str(telemetry.present))

    return records
