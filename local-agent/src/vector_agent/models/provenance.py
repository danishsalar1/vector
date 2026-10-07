"""Normalized internal assertions, not a wire protocol or proof of authority.

Future qualified adapters must establish authority, binding and evidence ownership
before constructing these models. Schema validation cannot authenticate an issuer.
"""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from .component import (
    ComponentId,
    ComponentReference,
    DomainModel,
    OpaqueId,
    SafeSlug,
)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("A timezone-aware UTC timestamp is required.")
    return value


UTCDateTime = Annotated[datetime, Field(strict=True), AfterValidator(require_utc)]
EvidenceIds = Annotated[tuple[OpaqueId, ...], Field(max_length=8192)]
FunctionalityRef = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"
    ),
]
FunctionalityRefs = Annotated[tuple[FunctionalityRef, ...], Field(max_length=256)]


class OriginAssessment(StrEnum):
    VERIFIED_OEM = "VERIFIED_OEM"
    NON_OEM_INDICATED = "NON_OEM_INDICATED"
    UNKNOWN = "UNKNOWN"


class InstallationAssessment(StrEnum):
    ORIGINAL_VERIFIED = "ORIGINAL_VERIFIED"
    REPLACEMENT_VERIFIED = "REPLACEMENT_VERIFIED"
    UNKNOWN = "UNKNOWN"


class UsedPartAssessment(StrEnum):
    """Prior installation/use before the component's current installation."""

    USED_VERIFIED = "USED_VERIFIED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class ManipulationAssessment(StrEnum):
    INDICATED = "INDICATED"
    NO_INDICATION_IN_OBSERVED_SCOPE = "NO_INDICATION_IN_OBSERVED_SCOPE"
    UNKNOWN = "UNKNOWN"


class AnomalyAssessment(StrEnum):
    INDICATED = "INDICATED"
    NO_ANOMALY_OBSERVED = "NO_ANOMALY_OBSERVED"
    UNKNOWN = "UNKNOWN"


class AssessmentSufficiency(StrEnum):
    SUPPORTED = "SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_ASSESSED = "NOT_ASSESSED"


class AuthenticityLabel(StrEnum):
    VERIFIED_OEM_ORIGINAL = "VERIFIED_OEM_ORIGINAL"
    VERIFIED_OEM_REPLACEMENT = "VERIFIED_OEM_REPLACEMENT"
    VERIFIED_OEM_USED_REPLACEMENT = "VERIFIED_OEM_USED_REPLACEMENT"
    VERIFIED_OEM_ORIGIN_ONLY = "VERIFIED_OEM_ORIGIN_ONLY"
    NON_OEM_INDICATED = "NON_OEM_INDICATED"
    SUSPICIOUS = "SUSPICIOUS"
    UNKNOWN = "UNKNOWN"


class ProvenanceSignalType(StrEnum):
    OEM_ORIGIN_ASSERTED = "OEM_ORIGIN_ASSERTED"
    NON_OEM_ORIGIN_ASSERTED = "NON_OEM_ORIGIN_ASSERTED"
    ORIGINAL_INSTALLATION_ASSERTED = "ORIGINAL_INSTALLATION_ASSERTED"
    REPLACEMENT_INSTALLATION_ASSERTED = "REPLACEMENT_INSTALLATION_ASSERTED"
    USED_PART_ASSERTED = "USED_PART_ASSERTED"
    MANIPULATION_ASSERTED = "MANIPULATION_ASSERTED"
    ANOMALY_OBSERVED = "ANOMALY_OBSERVED"
    NO_ANOMALY_OBSERVED = "NO_ANOMALY_OBSERVED"


class ProvenanceAuthorityClass(StrEnum):
    OEM_AUTHORITATIVE = "OEM_AUTHORITATIVE"
    AUTHORIZED_SERVICE_RECORD = "AUTHORIZED_SERVICE_RECORD"
    CRYPTOGRAPHIC_COMPONENT_ASSERTION = "CRYPTOGRAPHIC_COMPONENT_ASSERTION"
    REFERENCE_CATALOG = "REFERENCE_CATALOG"
    DEVICE_REPORTED_METADATA = "DEVICE_REPORTED_METADATA"
    BEHAVIORAL_MEASUREMENT = "BEHAVIORAL_MEASUREMENT"
    USER_DECLARATION = "USER_DECLARATION"


class ProvenanceSubjectBinding(StrEnum):
    COMPONENT_BOUND = "COMPONENT_BOUND"
    DEVICE_SLOT_BOUND = "DEVICE_SLOT_BOUND"
    DEVICE_BOUND = "DEVICE_BOUND"
    UNBOUND = "UNBOUND"


class ProvenanceIssuerType(StrEnum):
    OEM = "OEM"
    AUTHORIZED_SERVICE_PROVIDER = "AUTHORIZED_SERVICE_PROVIDER"
    VECTOR = "VECTOR"
    DEVICE = "DEVICE"
    USER = "USER"
    REFERENCE_CATALOG = "REFERENCE_CATALOG"
    OTHER = "OTHER"


class ProvenanceReasonCode(StrEnum):
    NO_PROVENANCE_EVIDENCE = "NO_PROVENANCE_EVIDENCE"
    INSUFFICIENT_AUTHORITY = "INSUFFICIENT_AUTHORITY"
    INSUFFICIENT_SUBJECT_BINDING = "INSUFFICIENT_SUBJECT_BINDING"
    INELIGIBLE_ISSUER = "INELIGIBLE_ISSUER"
    AUTHORITATIVE_OEM_EVIDENCE = "AUTHORITATIVE_OEM_EVIDENCE"
    AUTHORITATIVE_NON_OEM_EVIDENCE = "AUTHORITATIVE_NON_OEM_EVIDENCE"
    AUTHORITATIVE_ORIGINAL_HISTORY = "AUTHORITATIVE_ORIGINAL_HISTORY"
    AUTHORITATIVE_REPLACEMENT_HISTORY = "AUTHORITATIVE_REPLACEMENT_HISTORY"
    AUTHORITATIVE_USED_PART_HISTORY = "AUTHORITATIVE_USED_PART_HISTORY"
    MANIPULATION_EVIDENCE = "MANIPULATION_EVIDENCE"
    ANOMALY_EVIDENCE = "ANOMALY_EVIDENCE"
    NO_ANOMALY_IN_OBSERVED_SCOPE = "NO_ANOMALY_IN_OBSERVED_SCOPE"
    CONFLICTING_ORIGIN_EVIDENCE = "CONFLICTING_ORIGIN_EVIDENCE"
    CONFLICTING_INSTALLATION_EVIDENCE = "CONFLICTING_INSTALLATION_EVIDENCE"
    CONFLICTING_ANOMALY_EVIDENCE = "CONFLICTING_ANOMALY_EVIDENCE"
    CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE = "CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE"
    CONFLICTING_ORIGINAL_USED_EVIDENCE = "CONFLICTING_ORIGINAL_USED_EVIDENCE"


CONFLICT_REASONS = frozenset(
    {
        ProvenanceReasonCode.CONFLICTING_ORIGIN_EVIDENCE,
        ProvenanceReasonCode.CONFLICTING_INSTALLATION_EVIDENCE,
        ProvenanceReasonCode.CONFLICTING_ANOMALY_EVIDENCE,
        ProvenanceReasonCode.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,
        ProvenanceReasonCode.CONFLICTING_ORIGINAL_USED_EVIDENCE,
    }
)
REJECTION_REASONS = frozenset(
    {
        ProvenanceReasonCode.INSUFFICIENT_AUTHORITY,
        ProvenanceReasonCode.INSUFFICIENT_SUBJECT_BINDING,
        ProvenanceReasonCode.INELIGIBLE_ISSUER,
    }
)


def derive_authenticity_label(
    origin: OriginAssessment,
    installation: InstallationAssessment,
    used: UsedPartAssessment,
    manipulation: ManipulationAssessment,
    anomaly: AnomalyAssessment,
    conflicts: frozenset[ProvenanceReasonCode],
) -> AuthenticityLabel:
    """One v1 label contract shared by policy production and DTO validation."""
    if ProvenanceReasonCode.CONFLICTING_ORIGIN_EVIDENCE in conflicts:
        return AuthenticityLabel.SUSPICIOUS
    if origin == OriginAssessment.NON_OEM_INDICATED:
        return AuthenticityLabel.NON_OEM_INDICATED
    if (
        conflicts
        or manipulation == ManipulationAssessment.INDICATED
        or anomaly == AnomalyAssessment.INDICATED
    ):
        return AuthenticityLabel.SUSPICIOUS
    if origin == OriginAssessment.VERIFIED_OEM:
        if installation == InstallationAssessment.ORIGINAL_VERIFIED:
            return AuthenticityLabel.VERIFIED_OEM_ORIGINAL
        if installation == InstallationAssessment.REPLACEMENT_VERIFIED:
            if used == UsedPartAssessment.USED_VERIFIED:
                return AuthenticityLabel.VERIFIED_OEM_USED_REPLACEMENT
            return AuthenticityLabel.VERIFIED_OEM_REPLACEMENT
        return AuthenticityLabel.VERIFIED_OEM_ORIGIN_ONLY
    return AuthenticityLabel.UNKNOWN


def unique_sorted(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        raise ValueError("Duplicate references are forbidden.")
    return tuple(sorted(value))


class ProvenanceSignal(DomainModel):
    signal_id: OpaqueId
    component_id: ComponentId
    signal_type: ProvenanceSignalType
    authority_class: ProvenanceAuthorityClass
    subject_binding: ProvenanceSubjectBinding
    issuer_type: ProvenanceIssuerType
    issuer_key: SafeSlug | None = None
    evidence_ids: Annotated[tuple[OpaqueId, ...], Field(min_length=1, max_length=32)]
    source_dependency_key: SafeSlug
    observed_at: UTCDateTime
    reference_version: SafeSlug | None = None

    _references = field_validator("evidence_ids")(unique_sorted)


class ComponentAssessment(DomainModel):
    """Internally consistent v1 output; validation does not authenticate evidence."""

    component: ComponentReference
    origin: OriginAssessment
    installation: InstallationAssessment
    used_part: UsedPartAssessment
    manipulation: ManipulationAssessment
    anomaly: AnomalyAssessment
    sufficiency: AssessmentSufficiency
    summary_label: AuthenticityLabel
    supporting_evidence_ids: EvidenceIds
    contradicting_evidence_ids: EvidenceIds
    contextual_evidence_ids: EvidenceIds
    """Ineligible/unresolved context, never counted as proof of a resolved fact."""
    signal_ids: Annotated[tuple[OpaqueId, ...], Field(max_length=256)]
    functionality_result_refs: FunctionalityRefs
    source_dependency_keys: Annotated[tuple[SafeSlug, ...], Field(max_length=256)]
    policy_version: Literal["vector-provenance-v1"]
    assessed_at: UTCDateTime
    reason_codes: Annotated[tuple[ProvenanceReasonCode, ...], Field(min_length=1, max_length=32)]

    _references = field_validator(
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "contextual_evidence_ids",
        "signal_ids",
        "functionality_result_refs",
        "source_dependency_keys",
    )(unique_sorted)

    @field_validator("reason_codes")
    @classmethod
    def sort_reasons(
        cls, value: tuple[ProvenanceReasonCode, ...]
    ) -> tuple[ProvenanceReasonCode, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate reasons are forbidden.")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_assessment(self) -> Self:
        reasons = frozenset(self.reason_codes)
        conflicts = reasons & CONFLICT_REASONS
        rejections = reasons & REJECTION_REASONS
        # Match resolved facts and their explanations in both directions. This
        # checks structural support, not evidence contents or source authority.
        facts = (
            (
                self.origin == OriginAssessment.VERIFIED_OEM,
                ProvenanceReasonCode.AUTHORITATIVE_OEM_EVIDENCE,
            ),
            (
                self.origin == OriginAssessment.NON_OEM_INDICATED,
                ProvenanceReasonCode.AUTHORITATIVE_NON_OEM_EVIDENCE,
            ),
            (
                self.installation == InstallationAssessment.ORIGINAL_VERIFIED,
                ProvenanceReasonCode.AUTHORITATIVE_ORIGINAL_HISTORY,
            ),
            (
                self.installation == InstallationAssessment.REPLACEMENT_VERIFIED,
                ProvenanceReasonCode.AUTHORITATIVE_REPLACEMENT_HISTORY,
            ),
            (
                self.used_part == UsedPartAssessment.USED_VERIFIED,
                ProvenanceReasonCode.AUTHORITATIVE_USED_PART_HISTORY,
            ),
            (
                self.manipulation == ManipulationAssessment.INDICATED,
                ProvenanceReasonCode.MANIPULATION_EVIDENCE,
            ),
            (self.anomaly == AnomalyAssessment.INDICATED, ProvenanceReasonCode.ANOMALY_EVIDENCE),
            (
                self.anomaly == AnomalyAssessment.NO_ANOMALY_OBSERVED,
                ProvenanceReasonCode.NO_ANOMALY_IN_OBSERVED_SCOPE,
            ),
        )
        if any(resolved != (reason in reasons) for resolved, reason in facts):
            raise ValueError("Resolved dimensions and support reasons must agree.")
        has_facts = any(resolved for resolved, _ in facts)
        if has_facts != bool(self.supporting_evidence_ids):
            raise ValueError("Resolved facts require supporting evidence and vice versa.")
        if self.manipulation == ManipulationAssessment.NO_INDICATION_IN_OBSERVED_SCOPE:
            raise ValueError("Policy v1 cannot establish negative manipulation findings.")
        if self.installation == InstallationAssessment.ORIGINAL_VERIFIED and (
            self.origin == OriginAssessment.NON_OEM_INDICATED
            or self.used_part == UsedPartAssessment.USED_VERIFIED
        ):
            raise ValueError("Contradictory original-installation facts must remain unresolved.")
        if conflicts:
            if (
                self.sufficiency != AssessmentSufficiency.INCONCLUSIVE
                or not self.contradicting_evidence_ids
            ):
                raise ValueError(
                    "Authoritative conflicts require inconclusive contradictory evidence."
                )
            if (
                ProvenanceReasonCode.CONFLICTING_ORIGIN_EVIDENCE in conflicts
                and self.origin != OriginAssessment.UNKNOWN
            ):
                raise ValueError("Conflicting origin must remain unknown.")
            installation_conflicts = {
                ProvenanceReasonCode.CONFLICTING_INSTALLATION_EVIDENCE,
                ProvenanceReasonCode.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,
                ProvenanceReasonCode.CONFLICTING_ORIGINAL_USED_EVIDENCE,
            }
            if (
                conflicts & installation_conflicts
                and self.installation != InstallationAssessment.UNKNOWN
            ):
                raise ValueError("Conflicting installation must remain unknown.")
            if (
                ProvenanceReasonCode.CONFLICTING_ANOMALY_EVIDENCE in conflicts
                and self.anomaly != AnomalyAssessment.UNKNOWN
            ):
                raise ValueError("Conflicting anomaly must remain unknown.")
            if (
                ProvenanceReasonCode.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE in conflicts
                and self.origin != OriginAssessment.NON_OEM_INDICATED
                and ProvenanceReasonCode.CONFLICTING_ORIGIN_EVIDENCE not in conflicts
            ):
                raise ValueError("Origin/installation conflict requires non-OEM evidence.")
            if (
                ProvenanceReasonCode.CONFLICTING_ORIGINAL_USED_EVIDENCE in conflicts
                and self.used_part != UsedPartAssessment.USED_VERIFIED
            ):
                raise ValueError("Original/used conflict must retain the prior-use fact.")
        if bool(rejections) != bool(self.contextual_evidence_ids):
            raise ValueError("Rejected claims require contextual evidence and vice versa.")
        if not conflicts and not set(self.contradicting_evidence_ids).issubset(
            self.contextual_evidence_ids
        ):
            raise ValueError(
                "Counterevidence requires an authoritative conflict or rejected context."
            )
        if self.sufficiency == AssessmentSufficiency.NOT_ASSESSED:
            if (
                reasons != {ProvenanceReasonCode.NO_PROVENANCE_EVIDENCE}
                or self.signal_ids
                or self.source_dependency_keys
                or self.supporting_evidence_ids
                or self.contradicting_evidence_ids
                or self.contextual_evidence_ids
            ):
                raise ValueError("Not-assessed output cannot contain provenance findings.")
        else:
            if (
                not self.signal_ids
                or not self.source_dependency_keys
                or ProvenanceReasonCode.NO_PROVENANCE_EVIDENCE in reasons
            ):
                raise ValueError("Assessed output requires signal and dependency references.")
            expected = (
                AssessmentSufficiency.INCONCLUSIVE
                if conflicts or rejections
                else AssessmentSufficiency.SUPPORTED
            )
            if self.sufficiency != expected or not (has_facts or conflicts or rejections):
                raise ValueError("Sufficiency must agree with findings and unresolved claims.")
        if self.summary_label != derive_authenticity_label(
            self.origin,
            self.installation,
            self.used_part,
            self.manipulation,
            self.anomaly,
            conflicts,
        ):
            raise ValueError("Summary label does not match the provenance dimensions.")
        return self
