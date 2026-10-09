"""Display Metrics Diagnostic — VECTOR production Android standard diagnostic.

Wraps AndroidDeviceBridge.get_display_metrics() and produces
structured DiagnosticResult + EvidenceRecord(s) through the production
Diagnostic contract.

Display semantics (permanent):
- PASS  = valid display dimensions and density metrics were retrieved from the window manager.
- PASS != screen has no dead pixels, burn-in, cracks, or touch defects.
- Does not confuse override/logical metrics with physical metrics.
- Missing or malformed evidence -> INCONCLUSIVE, never false PASS or hardware FAIL.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.android.display import DisplayMetrics
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

DISPLAY_METRICS_DEFINITION = DiagnosticDefinition(
    diagnostic_id="display_metrics",
    name="Display Metrics Verification",
    category="display",
    verification_level=VerificationLevel.RUNTIME_DETECTION,
    supported_platforms=frozenset({Platform.ANDROID}),
    automation_level=AutomationLevel.AUTOMATIC,
    timeout_seconds=15.0,
    requires_probe=False,
    required_capabilities=frozenset(),
    prerequisites=frozenset(),
)

_STATUS_NOTE = (
    "PASS confirms successful display metrics retrieval. "
    "It does not verify pixel integrity, touch, burn-in, or screen defects."
)


class DisplayMetricsDiagnostic:
    """Production diagnostic for Android display metrics."""

    def __init__(self, bridge: AndroidDeviceBridge) -> None:
        self._bridge = bridge

    @property
    def definition(self) -> DiagnosticDefinition:
        return DISPLAY_METRICS_DEFINITION

    def is_supported(self, platform: Platform) -> bool:
        return platform in self.definition.supported_platforms

    def execute(
        self,
        *,
        device_id: str,
        serial: str,
        timeout: float | None = None,
    ) -> DiagnosticResult:
        """Run display metrics collection and return a structured result.

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
                summary="Display metrics collection timed out within allocated budget.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(time.monotonic() - start_mono, 3),
            )

        try:
            bridge_result = self._bridge.get_display_metrics(serial, timeout=remaining)
        except Exception as exc:
            duration = time.monotonic() - start_mono
            logger.error("Display metrics diagnostic failed (%s)", type(exc).__name__)
            return DiagnosticResult(
                diagnostic_id=self.definition.diagnostic_id,
                diagnostic_name=self.definition.name,
                category=self.definition.category,
                status=DiagnosticStatus.ERROR,
                automation_level=self.definition.automation_level,
                summary="Display metrics collection failed due to an execution error.",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_seconds=round(duration, 3),
            )

        completed_at = datetime.now(UTC)
        duration = time.monotonic() - start_mono

        status = _map_status(bridge_result.status)

        evidence: list[EvidenceRecord] = []
        if bridge_result.metrics is not None:
            evidence = _build_evidence_records(
                metrics=bridge_result.metrics,
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
        return "Display metrics were partially collected or unparseable."
    if status == DiagnosticStatus.RESTRICTED:
        return "Window manager access restricted by platform permissions."
    if status == DiagnosticStatus.UNSUPPORTED:
        return "Display metrics interface is not available on this device."
    return "Display metrics collection encountered an execution error."


def _build_evidence_records(
    *,
    metrics: DisplayMetrics,
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
        metadata: dict[str, str | int] | None = None,
    ) -> None:
        meta: dict[str, str | int] = {"field": field_name}
        if metadata:
            meta.update(metadata)
        records.append(
            EvidenceRecord(
                diagnostic_id=diagnostic_id,
                device_id=device_id,
                source_type=EvidenceSourceType.ADB_SHELL,
                source_name=evidence_source,
                collection_method=collection_method,
                timestamp=collected_at,
                raw_value=raw_val,
                normalized_value=normalized_val,
                unit=unit,
                reliability=None,
                confidence=None,
                metadata=meta,
            )
        )

    # Physical resolution
    _add(
        "display_physical_resolution",
        f"{metrics.physical_width}x{metrics.physical_height}",
        metadata={"width": metrics.physical_width, "height": metrics.physical_height},
    )

    # Physical density
    _add(
        "display_physical_density_dpi",
        str(metrics.physical_density),
        normalized_val=float(metrics.physical_density),
        unit="dpi",
    )

    # Override resolution if reported
    if metrics.override_width is not None and metrics.override_height is not None:
        _add(
            "display_override_resolution",
            f"{metrics.override_width}x{metrics.override_height}",
            metadata={"width": metrics.override_width, "height": metrics.override_height},
        )

    # Override density if reported
    if metrics.override_density is not None:
        _add(
            "display_override_density_dpi",
            str(metrics.override_density),
            normalized_val=float(metrics.override_density),
            unit="dpi",
        )

    return records
