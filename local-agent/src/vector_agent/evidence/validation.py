"""Ingest Probe bytes into attributed observations, NEVER hardware conclusions.

No EvidenceRecord or DiagnosticResult is constructed here. Later desktop diagnostic
interpretation must establish measurement sufficiency and evidence semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vector_agent.models.device import EvidenceSourceType
from vector_agent.models.probe import (
    ProbeBuildIdentity,
    ProbeCapabilityDescriptor,
    ProbeChallengeBinding,
    ProbeCommandStatus,
    ProbeLimitation,
    ProbeObservationType,
    ProbeOperation,
    ProbeRequestEnvelope,
    ProbeUnit,
)
from vector_agent.probe.protocol import ProbeProtocolSession


@dataclass(frozen=True)
class ValidatedProbeObservation:
    """Internal attribution record. No token, nonce, raw dump or metadata escape hatch.

    Python objects are not a security boundary against malicious in-process code;
    callers must use ingest_probe_response for ALL externally supplied observations.
    """

    device_id: str
    probe_session_id: str
    device_epoch: int
    protocol_version: int
    binding: ProbeChallengeBinding
    probe_build: ProbeBuildIdentity | None
    observation_id: str
    collector_id: str
    observation_type: ProbeObservationType
    value: int | float | bool
    unit: ProbeUnit | None
    collection_started_at: datetime
    collection_completed_at: datetime
    complete: bool
    limitations: tuple[ProbeLimitation, ...]
    source: EvidenceSourceType = field(default=EvidenceSourceType.VECTOR_PROBE, init=False)
    confidence: None = field(default=None, init=False)
    reliability: None = field(default=None, init=False)


@dataclass(frozen=True)
class ValidatedProbeResponse:
    """Safe internal response with no echoed secret or hardware verdict."""

    operation: ProbeOperation
    command_status: ProbeCommandStatus
    capabilities: tuple[ProbeCapabilityDescriptor, ...]
    observations: tuple[ValidatedProbeObservation, ...]
    probe_build: ProbeBuildIdentity | None


def ingest_probe_response(
    raw: bytes,
    *,
    session: ProbeProtocolSession,
    current_device_epoch: int,
    expected_request: ProbeRequestEnvelope,
) -> ValidatedProbeResponse:
    """The only external ingestion entry: decode -> schema -> binding -> attribution.

    The epoch must come from the desktop's current device-session snapshot, never
    from the response. Unknown/free-form observation schemas are rejected upstream.
    """
    response = session.accept_response(
        raw, current_device_epoch=current_device_epoch, expected_request=expected_request
    )
    observations: list[ValidatedProbeObservation] = []
    if response.binding is not None:
        for candidate in response.observations:
            observations.append(
                ValidatedProbeObservation(
                    device_id=session.device_id,
                    probe_session_id=response.probe_session_id,
                    device_epoch=response.device_epoch,
                    protocol_version=response.protocol_version,
                    binding=response.binding,
                    probe_build=response.probe_build,
                    observation_id=candidate.observation_id,
                    collector_id=candidate.collector_id,
                    observation_type=candidate.observation_type,
                    value=candidate.value,
                    unit=candidate.unit,
                    collection_started_at=candidate.collection_started_at,
                    collection_completed_at=candidate.collection_completed_at,
                    complete=candidate.complete,
                    limitations=candidate.limitations,
                )
            )
    return ValidatedProbeResponse(
        operation=response.operation,
        command_status=response.status,
        capabilities=response.capabilities,
        observations=tuple(observations),
        probe_build=response.probe_build,
    )
