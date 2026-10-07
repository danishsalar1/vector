# Relative imports retain type resolution under the repository's src package.
# ruff: noqa: TID252
"""Pure v1 assessment over trusted, normalized internal assertions.

This does not authenticate records, validate signatures, resolve evidence IDs or
establish freshness against a live session. Those are future adapter obligations.
"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from ..models.component import ComponentReference, DomainModel
from ..models.provenance import (
    AnomalyAssessment as Anomaly,
)
from ..models.provenance import (
    AssessmentSufficiency as Sufficiency,
)
from ..models.provenance import (
    ComponentAssessment,
    FunctionalityRefs,
    ProvenanceSignal,
    UTCDateTime,
    derive_authenticity_label,
    unique_sorted,
)
from ..models.provenance import (
    InstallationAssessment as Installation,
)
from ..models.provenance import (
    ManipulationAssessment as Manipulation,
)
from ..models.provenance import (
    OriginAssessment as Origin,
)
from ..models.provenance import (
    ProvenanceReasonCode as Reason,
)
from ..models.provenance import (
    ProvenanceSignalType as Signal,
)
from ..models.provenance import (
    UsedPartAssessment as Used,
)
from .references import (
    CONFLICT_PAIRS,
    ELIGIBLE_AUTHORITIES,
    ELIGIBLE_BINDINGS,
    ELIGIBLE_ISSUERS,
    MAX_SIGNALS,
    POLICY_VERSION,
    SUPPORT_REASONS,
)


class _AssessmentInput(DomainModel):
    component: ComponentReference
    signals: Annotated[tuple[ProvenanceSignal, ...], Field(max_length=MAX_SIGNALS)]
    functionality_result_refs: FunctionalityRefs
    assessed_at: UTCDateTime

    _refs = field_validator("functionality_result_refs")(unique_sorted)

    @model_validator(mode="after")
    def check_signals(self) -> Self:
        seen: dict[str, ProvenanceSignal] = {}
        for signal in self.signals:
            if signal.component_id != self.component.component_id:
                raise ValueError("Signal belongs to another component or session.")
            if signal.observed_at > self.assessed_at:
                raise ValueError("Signal observation follows assessment time.")
            if signal.signal_id in seen and seen[signal.signal_id] != signal:
                raise ValueError("Conflicting duplicate signal identifier.")
            seen[signal.signal_id] = signal
        return self


def assess_component_provenance(
    component: ComponentReference,
    signals: tuple[ProvenanceSignal, ...],
    *,
    functionality_result_refs: tuple[str, ...] = (),
    assessed_at: datetime,
) -> ComponentAssessment:
    """Assess only explicit claims; no counting, inference from function, or I/O.

    Required assessed_at keeps evaluation reproducible. Exact duplicates are
    removed; conflicting duplicates, wrong targets and future observations fail.
    Raw dictionaries (including Probe payloads) are not an accepted entry point.
    """
    if not isinstance(component, ComponentReference):
        raise ValueError("A normalized component reference is required.")
    if type(signals) is not tuple or len(signals) > MAX_SIGNALS:
        raise ValueError("A bounded tuple of normalized signals is required.")
    if any(not isinstance(signal, ProvenanceSignal) for signal in signals):
        raise ValueError("Only normalized provenance signals are accepted.")
    data = _AssessmentInput(
        component=component,
        signals=signals,
        functionality_result_refs=functionality_result_refs,
        assessed_at=assessed_at,
    )
    unique = {signal.signal_id: signal for signal in data.signals}
    eligible: dict[Signal, set[str]] = {}
    ineligible: dict[Signal, set[str]] = {}
    reasons: set[Reason] = set()
    for signal in unique.values():
        rejection: set[Reason] = set()
        if signal.authority_class not in ELIGIBLE_AUTHORITIES[signal.signal_type]:
            rejection.add(Reason.INSUFFICIENT_AUTHORITY)
        if signal.issuer_type not in ELIGIBLE_ISSUERS[signal.authority_class]:
            rejection.add(Reason.INELIGIBLE_ISSUER)
        if signal.subject_binding not in ELIGIBLE_BINDINGS:
            rejection.add(Reason.INSUFFICIENT_SUBJECT_BINDING)
        reasons.update(rejection)
        bucket = ineligible if rejection else eligible
        bucket.setdefault(signal.signal_type, set()).update(signal.evidence_ids)

    conflicts: set[Reason] = set()
    contradicted: set[Signal] = set()
    contradicting: set[str] = set()
    for positive, negative, reason in CONFLICT_PAIRS:
        if positive in eligible and negative in eligible:
            conflicts.add(reason)
            contradicted.update((positive, negative))
            contradicting.update(eligible[positive] | eligible[negative])
        # Weak counterclaims remain traceable without defeating strong facts.
        if positive in eligible:
            contradicting.update(ineligible.get(negative, ()))
        if negative in eligible:
            contradicting.update(ineligible.get(positive, ()))
        if positive in ineligible and negative in ineligible:
            contradicting.update(ineligible[positive] | ineligible[negative])

    # Inspect the full eligible set before resolving dimensions so overlapping
    # conflicts cannot hide each other. Retain non-OEM/prior-use facts, while
    # the incompatible factory-original installation assertion is unresolved.
    for counterclaim, reason in (
        (Signal.NON_OEM_ORIGIN_ASSERTED, Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE),
        (Signal.USED_PART_ASSERTED, Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE),
    ):
        if Signal.ORIGINAL_INSTALLATION_ASSERTED in eligible and counterclaim in eligible:
            conflicts.add(reason)
            contradicted.add(Signal.ORIGINAL_INSTALLATION_ASSERTED)
            contradicting.update(
                eligible[Signal.ORIGINAL_INSTALLATION_ASSERTED] | eligible[counterclaim]
            )

    resolved = set(eligible) - contradicted
    reasons.update(conflicts)
    reasons.update(SUPPORT_REASONS[kind] for kind in resolved)
    supporting = {eid for kind in resolved for eid in eligible[kind]}
    contextual = {eid for ids in ineligible.values() for eid in ids}

    origin = Origin.UNKNOWN
    if Signal.OEM_ORIGIN_ASSERTED in resolved:
        origin = Origin.VERIFIED_OEM
    elif Signal.NON_OEM_ORIGIN_ASSERTED in resolved:
        origin = Origin.NON_OEM_INDICATED
    installation = Installation.UNKNOWN
    if Signal.ORIGINAL_INSTALLATION_ASSERTED in resolved:
        installation = Installation.ORIGINAL_VERIFIED
    elif Signal.REPLACEMENT_INSTALLATION_ASSERTED in resolved:
        installation = Installation.REPLACEMENT_VERIFIED
    used = Used.USED_VERIFIED if Signal.USED_PART_ASSERTED in resolved else Used.NOT_ESTABLISHED
    manipulation = (
        Manipulation.INDICATED if Signal.MANIPULATION_ASSERTED in resolved else Manipulation.UNKNOWN
    )
    anomaly = Anomaly.UNKNOWN
    if Signal.ANOMALY_OBSERVED in resolved:
        anomaly = Anomaly.INDICATED
    elif Signal.NO_ANOMALY_OBSERVED in resolved:
        anomaly = Anomaly.NO_ANOMALY_OBSERVED

    if not unique:
        sufficiency = Sufficiency.NOT_ASSESSED
        reasons.add(Reason.NO_PROVENANCE_EVIDENCE)
    elif ineligible or conflicts:
        sufficiency = Sufficiency.INCONCLUSIVE
    else:
        sufficiency = Sufficiency.SUPPORTED
    return ComponentAssessment(
        component=data.component,
        origin=origin,
        installation=installation,
        used_part=used,
        manipulation=manipulation,
        anomaly=anomaly,
        sufficiency=sufficiency,
        summary_label=derive_authenticity_label(
            origin, installation, used, manipulation, anomaly, frozenset(conflicts)
        ),
        supporting_evidence_ids=tuple(sorted(supporting)),
        contradicting_evidence_ids=tuple(sorted(contradicting)),
        contextual_evidence_ids=tuple(sorted(contextual)),
        signal_ids=tuple(sorted(unique)),
        functionality_result_refs=data.functionality_result_refs,
        source_dependency_keys=tuple(sorted({s.source_dependency_key for s in unique.values()})),
        policy_version=POLICY_VERSION,
        assessed_at=data.assessed_at,
        reason_codes=tuple(sorted(reasons)),
    )
