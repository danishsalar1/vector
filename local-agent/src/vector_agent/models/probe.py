"""Strict v1 control-plane contracts, not diagnostic verdicts.

Wire models are schemas only. Untrusted bytes MUST enter through ProbeProtocolSession;
constructing a model is not proof of attribution, freshness, or authentication.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MAX_PROTOCOL_MESSAGE_BYTES = 65_536
MAX_STRING_LENGTH = 4_096
MAX_COLLECTION_ITEMS = 256
MAX_OBJECT_KEYS = 64
MAX_NESTING_DEPTH = 6
MAX_SEQUENCE_NUMBER = (1 << 63) - 1

ProbeSessionId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]
ProbeIdentifier = ProbeSessionId
DiagnosticId = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
]
SequenceNumber = Annotated[int, Field(strict=True, ge=0, le=MAX_SEQUENCE_NUMBER)]
Nonce = Annotated[
    str,
    StringConstraints(strict=True, min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$"),
]
UTCDateTime = Annotated[datetime, Field(strict=True)]


class ProbeProtocolVersion(IntEnum):
    V1 = 1


class ProbeOperation(StrEnum):
    HELLO = "HELLO"
    GET_CAPABILITIES = "GET_CAPABILITIES"
    START_CHALLENGE = "START_CHALLENGE"
    CANCEL_CHALLENGE = "CANCEL_CHALLENGE"
    FETCH_OBSERVATIONS = "FETCH_OBSERVATIONS"
    HEARTBEAT = "HEARTBEAT"


class ProbeCommandStatus(StrEnum):
    """Collection/control outcomes. OK does not mean hardware PASS."""

    OK = "OK"
    RESTRICTED = "RESTRICTED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class ProbeObservationType(StrEnum):
    """Only control/collection observations in v1's initial 8A schema.

    Later collectors must add explicit typed schemas; there is no arbitrary payload.
    """

    CONTROL_ACKNOWLEDGEMENT = "CONTROL_ACKNOWLEDGEMENT"
    SAMPLE_COUNT = "SAMPLE_COUNT"
    COLLECTION_DURATION = "COLLECTION_DURATION"


class ProbeUnit(StrEnum):
    COUNT = "count"
    MILLISECOND = "ms"


class ProbeLimitation(StrEnum):
    PARTIAL_COLLECTION = "PARTIAL_COLLECTION"
    PERMISSION_RESTRICTED = "PERMISSION_RESTRICTED"
    INTERRUPTED = "INTERRUPTED"
    CLOCK_UNCERTAIN = "CLOCK_UNCERTAIN"


class ProbeCapabilityId(StrEnum):
    CONTROL_CHANNEL = "CONTROL_CHANNEL"


class ProbeModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
        revalidate_instances="always",
        str_max_length=MAX_STRING_LENGTH,
    )


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("A timezone-aware UTC timestamp is required.")
    return value


class ProbeChallengeBinding(ProbeModel):
    scan_id: ProbeIdentifier
    diagnostic_id: DiagnosticId
    attempt_id: ProbeIdentifier
    challenge_id: ProbeIdentifier
    collection_not_before: UTCDateTime

    _utc = field_validator("collection_not_before")(require_utc)


class ProbeBuildIdentity(ProbeModel):
    """Self-reported artifact digest, NOT signing verification or attestation."""

    artifact_sha256: Annotated[
        str, StringConstraints(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    ]


class ProbeCapabilityDescriptor(ProbeModel):
    capability_id: ProbeCapabilityId
    available: Annotated[bool, Field(strict=True)]
    operations: Annotated[tuple[ProbeOperation, ...], Field(min_length=1, max_length=6)]

    @field_validator("operations")
    @classmethod
    def unique_operations(cls, value: tuple[ProbeOperation, ...]) -> tuple[ProbeOperation, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate operations are forbidden.")
        return value


class ProbeHello(ProbeModel):
    """8B optional v1 HELLO metadata. Identity still requires adapter verification."""

    application_version: Annotated[
        str,
        StringConstraints(
            strict=True, pattern=r"^[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}$", max_length=17
        ),
    ]
    version_code: Annotated[int, Field(strict=True, ge=1, le=MAX_SEQUENCE_NUMBER)]
    protocol_versions: Annotated[
        tuple[Annotated[int, Field(strict=True, ge=1)], ...], Field(min_length=1, max_length=16)
    ]
    supported_operations: Annotated[tuple[ProbeOperation, ...], Field(min_length=1, max_length=6)]
    api_level: Annotated[int, Field(strict=True, ge=26, le=1000)]

    @model_validator(mode="after")
    def unique_metadata(self) -> Self:
        if len(set(self.protocol_versions)) != len(self.protocol_versions) or len(
            set(self.supported_operations)
        ) != len(self.supported_operations):
            raise ValueError("Duplicate HELLO metadata is forbidden.")
        return self


class ProbeObservationCandidate(ProbeModel):
    observation_id: ProbeIdentifier
    observation_type: ProbeObservationType
    collector_id: DiagnosticId
    value: (
        Annotated[int, Field(strict=True, ge=0, le=MAX_SEQUENCE_NUMBER)]
        | Annotated[float, Field(strict=True, ge=0, le=MAX_SEQUENCE_NUMBER)]
        | Annotated[bool, Field(strict=True)]
    )
    unit: ProbeUnit | None
    collection_started_at: UTCDateTime
    collection_completed_at: UTCDateTime
    complete: Annotated[bool, Field(strict=True)]
    limitations: Annotated[tuple[ProbeLimitation, ...], Field(max_length=4)]

    _utc = field_validator("collection_started_at", "collection_completed_at")(require_utc)

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        if self.collection_completed_at < self.collection_started_at:
            raise ValueError("Collection window is reversed.")
        if len(self.limitations) != len(set(self.limitations)):
            raise ValueError("Duplicate limitations are forbidden.")
        if not self.complete and not self.limitations:
            raise ValueError("Incomplete observations require a limitation.")
        if self.complete and self.limitations:
            raise ValueError("Limited observations cannot claim completeness.")
        if self.observation_type == ProbeObservationType.CONTROL_ACKNOWLEDGEMENT:
            valid = type(self.value) is bool and self.unit is None
        elif self.observation_type == ProbeObservationType.SAMPLE_COUNT:
            valid = type(self.value) is int and self.unit == ProbeUnit.COUNT
        else:
            valid = type(self.value) in (int, float) and self.unit == ProbeUnit.MILLISECOND
        if not valid:
            raise ValueError("Observation type, numeric type, and unit must agree.")
        return self


class ProbeEnvelope(ProbeModel):
    protocol_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    probe_session_id: ProbeSessionId
    device_epoch: SequenceNumber
    binding: ProbeChallengeBinding | None
    nonce: Nonce = Field(repr=False)
    sequence_number: SequenceNumber
    issued_at: UTCDateTime
    expires_at: UTCDateTime
    operation: ProbeOperation

    _utc = field_validator("issued_at", "expires_at")(require_utc)

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        needs_binding = self.operation in (
            ProbeOperation.START_CHALLENGE,
            ProbeOperation.CANCEL_CHALLENGE,
            ProbeOperation.FETCH_OBSERVATIONS,
        )
        if needs_binding != (self.binding is not None):
            raise ValueError("Operation and challenge binding do not agree.")
        if self.expires_at <= self.issued_at:
            raise ValueError("Message expiry must follow issuance.")
        return self


class ProbeRequestEnvelope(ProbeEnvelope):
    """Desktop-generated request with no executable or free-form payload."""


class ProbeResponseEnvelope(ProbeEnvelope):
    """Echoes request identity/nonce/sequence; timestamps describe this response."""

    status: ProbeCommandStatus
    hello: ProbeHello | None = None
    probe_build: ProbeBuildIdentity | None
    capabilities: Annotated[
        tuple[ProbeCapabilityDescriptor, ...], Field(max_length=MAX_COLLECTION_ITEMS)
    ]
    observations: Annotated[
        tuple[ProbeObservationCandidate, ...], Field(max_length=MAX_COLLECTION_ITEMS)
    ]

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.hello is not None and (
            self.operation != ProbeOperation.HELLO or self.status != ProbeCommandStatus.OK
        ):
            raise ValueError("HELLO metadata requires a successful HELLO response.")
        if self.status != ProbeCommandStatus.OK and (self.capabilities or self.observations):
            raise ValueError("Unsuccessful responses cannot supply accepted payloads.")
        if self.capabilities and self.operation != ProbeOperation.GET_CAPABILITIES:
            raise ValueError("Capabilities require the capability operation.")
        if self.observations and self.operation != ProbeOperation.FETCH_OBSERVATIONS:
            raise ValueError("Observations require the observation operation.")
        if len({c.capability_id for c in self.capabilities}) != len(self.capabilities):
            raise ValueError("Duplicate capability descriptors are forbidden.")
        if len({o.observation_id for o in self.observations}) != len(self.observations):
            raise ValueError("Duplicate observation identifiers are forbidden.")
        return self
