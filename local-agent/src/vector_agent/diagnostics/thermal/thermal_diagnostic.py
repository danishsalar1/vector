"""Thermal Telemetry Diagnostic — VECTOR production Android standard diagnostic.

Wraps AndroidDeviceBridge.get_thermal_telemetry() and produces
structured DiagnosticResult + EvidenceRecord(s) through the production
Diagnostic contract.

Thermal semantics (permanent):
- PASS  = valid live thermal telemetry/status was retrieved from the thermal service.
- PASS != device has no thermal or cooling defects.
- Current temperature / throttling is NOT interpreted as hardware failure.
- Missing or malformed evidence -> INCONCLUSIVE, never false PASS or hardware FAIL.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.android.thermal import ThermalTelemetry
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

THERMAL_TELEMETRY_DEFINITION = DiagnosticDefinition(
    diagnostic_id="thermal_telemetry",
    name="Thermal Telemetry Verification",
    category="thermal",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.ANDROID}),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    required_capabilities=frozenset(),
    prerequisites=frozenset(),
)

_STATUS_NOTE = (
    "PASS confirms successful thermal telemetry collection. "
    "It does not represent thermal hardware health or cooling defect absence."
)


class ThermalTelemetryDiagnostic:
    """Production diagnostic for Android thermal telemetry."""

    def __init__(self, bridge: AndroidDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return THERMAL_TELEMETRY_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run thermal telemetry collection and return a structured result.

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
                summary="Thermal telemetry collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(time.monotonic() - start_mono, 3),
            )

        try:
            bridge_result = self._bridge.get_thermal_telemetry(serial, timeout=remaining)
        except Exception as exc:
            duration = time.monotonic() - start_mono
            logger.error("Thermal telemetry diagnostic failed (%s)", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Thermal telemetry collection failed due to an execution error.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(duration, 3),
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        status = _map_status(bridge_result.status)

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

        summary = _build_summary(status)

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


def _map_status(bridge_status: str) -> DiagnosticStatus:
    mapping = {
        "PASS": DiagnosticStatus.PASS,
        "INCONCLUSIVE": DiagnosticStatus.INCONCLUSIVE,
        "RESTRICTED": DiagnosticStatus.RESTRICTED,
        "UNSUPPORTED": DiagnosticStatus.UNSUPPORTED,
        "ERROR": DiagnosticStatus.ERROR,
    }
    return mapping.get(bridge_status, DiagnosticStatus.ERROR)


def _build_summary(status: DiagnosticStatus) -> str:
    if status == DiagnosticStatus.PASS:
        return _STATUS_NOTE
    if status == DiagnosticStatus.INCONCLUSIVE:
        return "Thermal telemetry was partially collected or ambiguous."
    if status == DiagnosticStatus.RESTRICTED:
        return "Thermal telemetry access restricted by platform permissions."
    if status == DiagnosticStatus.UNSUPPORTED:
        return "Thermal telemetry interface is not available on this device."
    return "Thermal telemetry collection encountered an execution error."


def _build_evidence_records(
    *,
    telemetry: ThermalTelemetry,
    device_id: str,
    diagnostic_id: str,
    evidence_source: str,
    collection_method: str,
    confidence: float,
    collected_at: datetime,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []

    def _add(
        field_name: str,
        raw_val: str,
        *,
        normalized_val: float | None = None,
        unit: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        meta = {"field": field_name}
        if metadata:
            meta.update(metadata)
        records.append(
            EvidenceRecord(
                diagnostic_id=diagnostic_id,
                device_id=device_id,
                source_type=EvidenceSourceType.ADB_DUMPSYS,
                source_name=evidence_source,
                collection_method=collection_method,
                timestamp=collected_at,
                raw_value=raw_val,
                normalized_value=normalized_val,
                unit=unit,
                reliability=1.0,
                confidence=confidence,
                metadata=meta,
            )
        )

    if telemetry.thermal_status_code is not None:
        _add(
            "thermal_status_code",
            str(telemetry.thermal_status_code),
            normalized_val=float(telemetry.thermal_status_code),
            metadata={"status_label": telemetry.thermal_status_label or "UNKNOWN"},
        )

    _add(
        "thermal_sensor_count",
        str(telemetry.sensor_count),
        normalized_val=float(telemetry.sensor_count),
        unit="count",
    )

    for sensor in telemetry.sensors:
        s_meta: dict[str, str] = {"sensor_name": sensor.name}
        if sensor.sensor_type:
            s_meta["sensor_type"] = sensor.sensor_type
        if sensor.status_code is not None:
            s_meta["sensor_status"] = str(sensor.status_code)

        _add(
            f"sensor_{sensor.name}",
            str(sensor.temperature_celsius),
            normalized_val=sensor.temperature_celsius,
            unit="celsius",
            metadata=s_meta,
        )

    return records
