"""Canonical diagnostic evidence -> reference comparison, without new provenance claims.

collect_and_compare consumes the result of the existing authenticated lifecycle
directly. compare accepts supplied canonical results but cannot authenticate them.
Neither a Python model nor matching metadata is an authentication receipt. These
are trusted in-process APIs, not deserialization or HTTP endpoints; as with the
existing transport, malicious in-process replacement of methods is out of scope.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.models.component import OpaqueDeviceId, OpaqueId, SessionEpoch
from vector_agent.models.device import (
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
)
from vector_agent.models.probe import ProbeOperation
from vector_agent.models.probe_diagnostics import DiagnosticMetric, DiagnosticReport
from vector_agent.models.provenance import (
    AuthenticityLabel,
    ProvenanceAuthorityClass,
    ProvenanceSubjectBinding,
    require_utc,
)
from vector_agent.models.reference import ComparisonOutcome, SpecificationComparisonReport
from vector_agent.probe.lifecycle import ProbeConnection

from ..models.component import DomainModel  # noqa: TID252
from .catalog import ReferenceCatalog
from .comparator import SpecificationComparator
from .resolver import DeviceResolver


class _RecordContext(DomainModel):
    """Strict projection of the existing normalizer's metadata, not an attestation."""

    device_session_epoch: SessionEpoch
    probe_session_id: OpaqueId
    challenge_id: OpaqueId
    qualification: Literal["CODE_TESTED"]
    authenticity: Literal["UNKNOWN"]
    collection_elapsed_ms: int
    collection_state: str
    reason: str


@dataclass(frozen=True)
class EvidenceUse:
    """Admission decision referencing an existing canonical record; no copied value."""

    evidence_id: UUID
    property_paths: tuple[str, ...]
    admitted: bool
    reason: str
    authority: ProvenanceAuthorityClass
    binding: ProvenanceSubjectBinding


@dataclass(frozen=True)
class DiagnosticEvidenceComparison:
    """Internal result retaining canonical evidence and per-record decisions.

    diagnostic_result is a defensive copy, not a second evidence hierarchy or a
    public DTO. Do not serialize arbitrary raw evidence/metadata into APIs/logs.
    Report source_ids are OEM assertions; uses.evidence_id are observation IDs.
    """

    report: SpecificationComparisonReport
    diagnostic_result: DiagnosticResult = field(repr=False)
    uses: tuple[EvidenceUse, ...]
    transport_attributed: bool
    rejection: str | None
    qualification: Literal["CODE_TESTED"] = "CODE_TESTED"
    authenticity: AuthenticityLabel = AuthenticityLabel.UNKNOWN


def _properties(name: str) -> tuple[str, ...]:
    if name == "feature_nfc":
        return ("sensors.nfc_present",)
    if name == "feature_barometer":
        return ("sensors.barometer_present",)
    if name in {"charge_counter", "end_charge_counter"}:
        return ("battery.rated_capacity_mah",)
    if name in {"ram_total", "ram_available"}:
        return ("memory.ram_total_bytes",)
    if name in {"width", "height", "display_width", "display_height"}:
        return ("display.resolution",)
    if name == "refresh_rate":
        return ("display.refresh_rate_hz",)
    if name == "mode_count" or name.startswith(tuple(f"mode{i}_" for i in range(8))):
        return ("display.resolution", "display.refresh_rate_hz")
    return ()


def _validated_report(
    result: DiagnosticResult, owner: DeviceSession, epoch: int
) -> tuple[DiagnosticReport | None, _RecordContext | None]:
    """Reuse 8C's metric/report contract after checking its lossy normalization boundary.

    Float -> integer here only reverses EvidenceRecord's numeric representation
    for integral values. No dimension, unit, or measurement meaning changes. It
    cannot recover a caller's original input type and grants no authentication.
    """
    if not isinstance(result.status, DiagnosticStatus) or len(result.evidence) > 64:
        raise ValueError("Invalid diagnostic result.")
    if not result.evidence:
        return None, None
    context: _RecordContext | None = None
    metrics: list[DiagnosticMetric] = []
    seen_ids: dict[UUID, EvidenceRecord] = {}
    seen_names: set[str] = set()
    for record in result.evidence:
        if not isinstance(record, EvidenceRecord) or not isinstance(record.evidence_id, UUID):
            raise ValueError("Canonical evidence required.")
        if record.device_id != owner.device_id or record.diagnostic_id != result.diagnostic_id:
            raise ValueError("Evidence owner mismatch.")
        current = _RecordContext.model_validate(record.metadata)
        if current.device_session_epoch != epoch or (context is not None and current != context):
            raise ValueError("Mixed or stale diagnostic context.")
        context = current
        if not isinstance(record.timestamp, datetime):
            raise ValueError("Valid UTC timestamp required.")
        require_utc(record.timestamp)
        expected_source = (
            EvidenceSourceType.USER_ASSISTED
            if record.source_name == "user_report"
            else EvidenceSourceType.VECTOR_PROBE
        )
        if record.source_type is not expected_source:
            raise ValueError("Unexpected evidence source.")
        if record.evidence_id in seen_ids:
            if record != seen_ids[record.evidence_id]:
                raise ValueError("Conflicting evidence identifier.")
            continue  # Same entire canonical record repeated: no new observation or provenance.
        if record.source_name in seen_names:
            raise ValueError("Multiple observations for one metric; no sample selection policy.")
        seen_ids[record.evidence_id] = record
        seen_names.add(record.source_name)
        value = record.normalized_value
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 2**53:
                raise ValueError("Invalid normalized measurement.")
            if value < 0 and (record.unit in {"bytes", "pixels", "count", "Hz", "uAh"}):
                raise ValueError("Negative collection quantity.")
            # Canonical normalization stored int metrics as floats within the exact integer range.
            numeric: int | float | None = int(value) if value == int(value) else value
        else:
            numeric = None
        metrics.append(
            DiagnosticMetric.model_validate(
                {
                    "name": record.source_name,
                    "value": numeric,
                    "unit": record.unit,
                }
            )
        )
    assert context is not None
    outcome = "INCONCLUSIVE" if result.status == DiagnosticStatus.RUNNING else result.status.value
    report = DiagnosticReport.model_validate(
        {
            "schema_version": 1,
            "diagnostic_id": result.diagnostic_id,
            "state": context.collection_state,
            "outcome": outcome,
            "reason": context.reason,
            "elapsed_ms": context.collection_elapsed_ms,
            "metrics": tuple(metrics),
        }
    )
    if (report.state == "RUNNING") != (result.status == DiagnosticStatus.RUNNING):
        raise ValueError("Normalized status disagrees with collection state.")
    return report, context


class DiagnosticEvidenceAdapter:
    """One diagnostic response at a time; never merge scans, sessions or challenges."""

    def __init__(self, catalog: ReferenceCatalog) -> None:
        self._comparator = SpecificationComparator(catalog)
        self._resolver = DeviceResolver(catalog)
        # One terminal challenge per live connection, not an accumulating evidence store.
        self._terminal: WeakKeyDictionary[ProbeConnection, tuple[int, str, str]] = (
            WeakKeyDictionary()
        )
        self._terminal_lock = threading.Lock()

    def compare(
        self, result: DiagnosticResult, *, owner: DeviceSession
    ) -> DiagnosticEvidenceComparison:
        """Consume supplied canonical evidence, explicitly UNVERIFIED.

        A manually constructed, deserialized, copied, or previously returned result
        cannot gain authenticated attribution by matching current owner metadata.
        Use collect_and_compare at the lifecycle call site for that relationship.
        """
        if not isinstance(result, DiagnosticResult) or not isinstance(owner, DeviceSession):
            raise TypeError("Canonical diagnostic result and desktop owner required.")
        return self._compare(result, owner=owner, epoch=owner.session_epoch, attributed=False)

    def collect_and_compare(
        self,
        connection: ProbeConnection,
        operation: ProbeOperation,
        diagnostic_id: str | None = None,
        *,
        owner: DeviceSession,
        manager: DeviceSessionManager,
    ) -> DiagnosticEvidenceComparison:
        """Execute one explicitly requested existing lifecycle exchange and consume its evidence.

        Does not connect, install, grant permissions, poll, retry or aggregate.
        Requires an already connected ProbeConnection and its current desktop owner.
        Lifecycle exceptions propagate; no failed exchange becomes a hardware verdict.
        Fixture transports exercise authentication but remain CODE_TESTED, never
        physically qualified. The caller must not represent a fixture as LIVE.
        """
        if not isinstance(connection, ProbeConnection) or not isinstance(
            manager, DeviceSessionManager
        ):
            raise TypeError("Existing Probe lifecycle and session manager required.")
        # These constructor-owned references never change during a connection's life.
        # Read them to reject a mismatched call BEFORE sending any diagnostic command.
        # No private transport/session state is altered or authentication reimplemented.
        if connection._owner is not owner or connection._manager is not manager:
            raise ValueError("Probe connection belongs to a different desktop owner.")
        epoch = manager.probe_owner_epoch(owner)
        if epoch < 0:
            raise ValueError("Current authorized desktop owner required.")
        result = connection.diagnostic(operation, diagnostic_id)
        if manager.probe_owner_epoch(owner) != epoch:
            raise ValueError("Desktop ownership changed during diagnostic exchange.")
        compared = self._compare(result, owner=owner, epoch=epoch, attributed=True)
        if manager.probe_owner_epoch(owner) != epoch:
            raise ValueError("Desktop ownership changed during comparison.")
        if compared.transport_attributed and result.evidence:
            context = _RecordContext.model_validate(result.evidence[0].metadata)
            if context.collection_state != "RUNNING":
                key = (epoch, context.probe_session_id, context.challenge_id)
                with self._terminal_lock:
                    previous = self._terminal.get(connection)
                    if previous is not None and previous == key:
                        # A fresh response sequence is not a fresh physical observation.
                        # Return the new canonical normalization unchanged, but unadmitted.
                        return self._compare(result, owner=owner, epoch=epoch, attributed=False)
                    self._terminal[connection] = key
        return compared

    def _compare(
        self,
        result: DiagnosticResult,
        *,
        owner: DeviceSession,
        epoch: int,
        attributed: bool,
    ) -> DiagnosticEvidenceComparison:
        if not isinstance(result, DiagnosticResult) or not isinstance(owner, DeviceSession):
            raise TypeError("Canonical diagnostic result and desktop owner required.")
        TypeAdapter(OpaqueDeviceId).validate_python(owner.device_id)
        TypeAdapter(SessionEpoch).validate_python(epoch)
        # Snapshot before evaluation; never mutate canonical input records or regenerate IDs/time.
        result = result.model_copy(deep=True)
        rejection = None
        report = None
        lifecycle_exchange = attributed
        try:
            report, _ = _validated_report(result, owner, epoch)
        except (ValueError, TypeError, OverflowError):
            # Never echo validation details containing caller metadata/raw identifiers.
            rejection = "Invalid, conflicting, incomplete or foreign canonical evidence context."
        attributed = attributed and rejection is None and report is not None
        values: dict[str, float] = {}
        uses: list[EvidenceUse] = []
        seen_use_ids: set[UUID] = set()
        for record in result.evidence:
            if not isinstance(record, EvidenceRecord) or not isinstance(record.evidence_id, UUID):
                raise ValueError("Canonical evidence identifiers required.")
            if record.evidence_id in seen_use_ids:
                continue
            seen_use_ids.add(record.evidence_id)
            paths = _properties(record.source_name) if isinstance(record.source_name, str) else ()
            declared_feature = record.source_name in {"feature_nfc", "feature_barometer"}
            admitted = bool(
                attributed
                and report is not None
                and report.state == "COMPLETED"
                and report.diagnostic_id == "connectivity"
                and report.outcome == "INCONCLUSIVE"
                and report.reason == "CAPABILITY_ONLY"
                and declared_feature
                and record.error is None
                and record.normalized_value is not None
                and record.source_type == EvidenceSourceType.VECTOR_PROBE
            )
            if admitted:
                assert record.normalized_value is not None
                values[record.source_name] = record.normalized_value
                reason = "Completed runtime feature declaration only; no physical function or origin claim."
            elif rejection:
                reason = rejection
            elif not attributed:
                reason = "Supplied record has no authenticated lifecycle association."
            elif record.normalized_value is None or record.error is not None:
                reason = "Measurement unavailable; missing data is not zero or hardware absence."
            else:
                reason = "No admissible equivalent OEM measurement for this observation/state."
            uses.append(
                EvidenceUse(
                    record.evidence_id,
                    paths,
                    admitted,
                    reason,
                    ProvenanceAuthorityClass.USER_DECLARATION
                    if record.source_type == EvidenceSourceType.USER_ASSISTED
                    else ProvenanceAuthorityClass.DEVICE_REPORTED_METADATA,
                    ProvenanceSubjectBinding.DEVICE_BOUND
                    if attributed
                    else ProvenanceSubjectBinding.UNBOUND,
                )
            )
        resolution = self._resolver.resolve(owner.identity)
        comparison = self._comparator._compare_properties(
            resolution, values, device_id=owner.device_id
        )
        uses_by_id = {u.evidence_id: u for u in uses}
        items = []
        for item in comparison.items:
            related = [
                (e, uses_by_id[e.evidence_id])
                for e in result.evidence
                if e.evidence_id in uses_by_id
                and item.property_path in uses_by_id[e.evidence_id].property_paths
            ]
            limitations = tuple(sorted({u.reason for _, u in related}))
            # Preserve valid telemetry's incompatible physical meaning without inventing values.
            incomparable = bool(
                attributed
                and report is not None
                and report.state == "COMPLETED"
                and report.reason == "TELEMETRY_ONLY"
                and related
                and any(e.normalized_value is not None and e.error is None for e, _ in related)
                and item.property_path
                in {
                    "battery.rated_capacity_mah",
                    "memory.ram_total_bytes",
                    "display.resolution",
                    "display.refresh_rate_hz",
                }
            )
            if incomparable and item.outcome == ComparisonOutcome.INSUFFICIENT_EVIDENCE:
                item = item.model_copy(update={"outcome": ComparisonOutcome.NOT_COMPARABLE})
            items.append(item.model_copy(update={"limitations": item.limitations + limitations}))
        if attributed:
            disclaimer_prefix = "Direct lifecycle attribution; CODE_TESTED only. "
        elif lifecycle_exchange and rejection is None and not result.evidence:
            disclaimer_prefix = "Authenticated lifecycle exchange produced no diagnostic evidence; CODE_TESTED only. "
        else:
            disclaimer_prefix = "Unverified supplied evidence; no authenticated Probe attribution. "
        comparison = SpecificationComparisonReport(
            report_id=comparison.report_id,
            device_id=comparison.device_id,
            resolution=comparison.resolution,
            evaluated_at=comparison.evaluated_at,
            items=tuple(items),
            honesty_disclaimer=disclaimer_prefix + comparison.honesty_disclaimer,
        )
        return DiagnosticEvidenceComparison(comparison, result, tuple(uses), attributed, rejection)
