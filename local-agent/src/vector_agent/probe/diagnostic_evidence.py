"""Interpret already accepted Probe measurements without provenance inference."""

from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
)
from vector_agent.models.probe import ProbeChallengeBinding
from vector_agent.models.probe_diagnostics import DiagnosticMetric, DiagnosticReport

# Sample statistics and the count that says whether any valid sample existed.
_SAMPLE_COUNTS = {"audio_rms": "audio_samples", "audio_peak": "audio_samples"} | {
    f"axis{i}_{s}": "sample_count" for i in range(3) for s in ("min", "max", "mean")
}


def _missing_value(report: DiagnosticReport, metric: DiagnosticMetric) -> str | None:
    """Why a value is absent. Absence is never a measurement of zero or of failure."""
    if metric.value is not None:
        return None
    if report.state == "RUNNING":
        return "NOT_YET_MEASURED"
    if report.state in {"CANCELLED", "EXPIRED"}:
        return "INTERRUPTED_BEFORE_MEASUREMENT"
    counts = {m.name: m.value for m in report.metrics}
    if report.reason == "NO_SAMPLES" or (
        metric.name in _SAMPLE_COUNTS and counts.get(_SAMPLE_COUNTS[metric.name]) == 0
    ):
        return "NO_SAMPLES_OBSERVED"
    return "UNSUPPORTED_MEASUREMENT"


def diagnostic_result(
    report: DiagnosticReport,
    *,
    device_id: str,
    epoch: int,
    session_id: str,
    binding: ProbeChallengeBinding,
) -> DiagnosticResult:
    """Internal only: caller must first authenticate and bind the report."""
    report = DiagnosticReport.model_validate(report)
    if report.diagnostic_id != binding.diagnostic_id:
        raise ValueError("Evidence binding mismatch.")
    interactive = report.diagnostic_id in {"touch", "pixels", "speaker", "microphone", "vibration"}
    context = {
        "device_session_epoch": epoch,
        "probe_session_id": session_id,
        "challenge_id": binding.challenge_id,
        "qualification": "CODE_TESTED",
        "authenticity": "UNKNOWN",
        "collection_elapsed_ms": report.elapsed_ms,
        "collection_state": report.state,
        "reason": report.reason,
    }
    records = [
        EvidenceRecord(
            diagnostic_id=report.diagnostic_id,
            device_id=device_id,
            source_type=EvidenceSourceType.USER_ASSISTED
            if m.name == "user_report"
            else EvidenceSourceType.VECTOR_PROBE,
            source_name=m.name,
            collection_method="Authenticated foreground Probe v2",
            normalized_value=m.value,
            unit=m.unit,
            metadata=context,
            error=_missing_value(report, m),
        )
        for m in report.metrics
    ]
    return DiagnosticResult(
        diagnostic_id=report.diagnostic_id,
        diagnostic_name=report.diagnostic_id,
        category=report.diagnostic_id.split("_")[0],
        status=DiagnosticStatus.RUNNING
        if report.state == "RUNNING"
        else DiagnosticStatus(report.outcome),
        automation_level=AutomationLevel.ASSISTED if interactive else AutomationLevel.AUTOMATIC,
        evidence=records,
        duration_seconds=report.elapsed_ms / 1000,
        summary=f"{report.reason}. Limited to recorded observations; no component health or authenticity conclusion.",
    )
