"""Exhaustive authority/binding eligibility and deterministic policy validation."""

from datetime import timedelta
from itertools import permutations

import pytest
from pydantic import ValidationError

from tests.test_component_models import NOW, component, opaque_id, signal
from vector_agent.models.provenance import (
    AnomalyAssessment as Anomaly,
)
from vector_agent.models.provenance import (
    AssessmentSufficiency as Sufficiency,
)
from vector_agent.models.provenance import (
    AuthenticityLabel as Label,
)
from vector_agent.models.provenance import (
    InstallationAssessment as Installation,
)
from vector_agent.models.provenance import (
    ManipulationAssessment as Manipulation,
)
from vector_agent.models.provenance import (
    OriginAssessment as Origin,
)
from vector_agent.models.provenance import (
    ProvenanceAuthorityClass as Authority,
)
from vector_agent.models.provenance import (
    ProvenanceIssuerType as Issuer,
)
from vector_agent.models.provenance import (
    ProvenanceReasonCode as Reason,
)
from vector_agent.models.provenance import (
    ProvenanceSignalType as Signal,
)
from vector_agent.models.provenance import (
    ProvenanceSubjectBinding as Binding,
)
from vector_agent.models.provenance import (
    UsedPartAssessment as Used,
)
from vector_agent.provenance import assess_component_provenance


def assess(signals=(), **changes):
    return assess_component_provenance(component(), signals, assessed_at=NOW, **changes)


# Independent test specification, deliberately not imported from production maps.
ISSUERS = {
    Authority.OEM_AUTHORITATIVE: Issuer.OEM,
    Authority.AUTHORIZED_SERVICE_RECORD: Issuer.AUTHORIZED_SERVICE_PROVIDER,
    Authority.CRYPTOGRAPHIC_COMPONENT_ASSERTION: Issuer.OEM,
    Authority.REFERENCE_CATALOG: Issuer.REFERENCE_CATALOG,
    Authority.DEVICE_REPORTED_METADATA: Issuer.DEVICE,
    Authority.BEHAVIORAL_MEASUREMENT: Issuer.VECTOR,
    Authority.USER_DECLARATION: Issuer.USER,
}


@pytest.mark.parametrize("kind", Signal)
@pytest.mark.parametrize("authority", Authority)
@pytest.mark.parametrize("binding", Binding)
def test_authority_binding_matrix(kind, authority, binding):
    result = assess(
        (
            signal(
                kind,
                authority_class=authority,
                issuer_type=ISSUERS[authority],
                subject_binding=binding,
            ),
        )
    )
    allowed = {Authority.OEM_AUTHORITATIVE, Authority.AUTHORIZED_SERVICE_RECORD}
    if kind in {
        Signal.OEM_ORIGIN_ASSERTED,
        Signal.NON_OEM_ORIGIN_ASSERTED,
        Signal.MANIPULATION_ASSERTED,
        Signal.ANOMALY_OBSERVED,
        Signal.NO_ANOMALY_OBSERVED,
    }:
        allowed.add(Authority.CRYPTOGRAPHIC_COMPONENT_ASSERTION)
    if kind in {Signal.ANOMALY_OBSERVED, Signal.NO_ANOMALY_OBSERVED}:
        allowed.add(Authority.BEHAVIORAL_MEASUREMENT)
    eligible = authority in allowed and binding in {
        Binding.COMPONENT_BOUND,
        Binding.DEVICE_SLOT_BOUND,
    }
    assert result.sufficiency == (Sufficiency.SUPPORTED if eligible else Sufficiency.INCONCLUSIVE)
    expected = {
        Signal.OEM_ORIGIN_ASSERTED: ("origin", Origin.VERIFIED_OEM, Origin.UNKNOWN),
        Signal.NON_OEM_ORIGIN_ASSERTED: ("origin", Origin.NON_OEM_INDICATED, Origin.UNKNOWN),
        Signal.ORIGINAL_INSTALLATION_ASSERTED: (
            "installation",
            Installation.ORIGINAL_VERIFIED,
            Installation.UNKNOWN,
        ),
        Signal.REPLACEMENT_INSTALLATION_ASSERTED: (
            "installation",
            Installation.REPLACEMENT_VERIFIED,
            Installation.UNKNOWN,
        ),
        Signal.USED_PART_ASSERTED: ("used_part", Used.USED_VERIFIED, Used.NOT_ESTABLISHED),
        Signal.MANIPULATION_ASSERTED: (
            "manipulation",
            Manipulation.INDICATED,
            Manipulation.UNKNOWN,
        ),
        Signal.ANOMALY_OBSERVED: ("anomaly", Anomaly.INDICATED, Anomaly.UNKNOWN),
        Signal.NO_ANOMALY_OBSERVED: ("anomaly", Anomaly.NO_ANOMALY_OBSERVED, Anomaly.UNKNOWN),
    }
    field, supported, unknown = expected[kind]
    assert getattr(result, field) == (supported if eligible else unknown)
    evidence = signal().evidence_ids
    assert result.supporting_evidence_ids == (evidence if eligible else ())
    assert result.contextual_evidence_ids == (() if eligible else evidence)
    assert result.contradicting_evidence_ids == ()


@pytest.mark.parametrize("issuer", Issuer)
@pytest.mark.parametrize("authority", Authority)
def test_issuer_cannot_upgrade_authority(issuer, authority):
    result = assess((signal(issuer_type=issuer, authority_class=authority),))
    eligible = (
        authority in {Authority.OEM_AUTHORITATIVE, Authority.CRYPTOGRAPHIC_COMPONENT_ASSERTION}
        and issuer == Issuer.OEM
    ) or (
        authority == Authority.AUTHORIZED_SERVICE_RECORD
        and issuer in {Issuer.OEM, Issuer.AUTHORIZED_SERVICE_PROVIDER}
    )
    assert (result.origin == Origin.VERIFIED_OEM) == eligible


@pytest.mark.parametrize(
    "first,second,field,reason",
    [
        (
            Signal.OEM_ORIGIN_ASSERTED,
            Signal.NON_OEM_ORIGIN_ASSERTED,
            "origin",
            Reason.CONFLICTING_ORIGIN_EVIDENCE,
        ),
        (
            Signal.ORIGINAL_INSTALLATION_ASSERTED,
            Signal.REPLACEMENT_INSTALLATION_ASSERTED,
            "installation",
            Reason.CONFLICTING_INSTALLATION_EVIDENCE,
        ),
        (
            Signal.ANOMALY_OBSERVED,
            Signal.NO_ANOMALY_OBSERVED,
            "anomaly",
            Reason.CONFLICTING_ANOMALY_EVIDENCE,
        ),
    ],
)
@pytest.mark.parametrize(
    "authority", [Authority.OEM_AUTHORITATIVE, Authority.AUTHORIZED_SERVICE_RECORD]
)
def test_conflicts_have_no_ranking_or_time_winner(first, second, field, reason, authority):
    a = signal(first)
    b = signal(
        second,
        11,
        authority_class=authority,
        issuer_type=ISSUERS[authority],
        observed_at=NOW - timedelta(seconds=1),
    )
    result = assess((a, b))
    assert getattr(result, field).value == "UNKNOWN"
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.summary_label == Label.SUSPICIOUS
    assert result.supporting_evidence_ids == ()
    assert result.contradicting_evidence_ids == tuple(sorted(a.evidence_ids + b.evidence_ids))
    assert reason in result.reason_codes
    assert result == assess((b, a))


def test_permutation_deduplication_and_traceability():
    signals = (
        signal(),
        signal(Signal.REPLACEMENT_INSTALLATION_ASSERTED, 11),
        signal(Signal.USED_PART_ASSERTED, 12, source_dependency_key="second-record"),
    )
    expected = assess(signals)
    for ordering in permutations(signals):
        assert assess(ordering) == expected
        assert assess(ordering + (signals[0],)) == expected
    assert expected.signal_ids == tuple(s.signal_id for s in signals)
    assert expected.supporting_evidence_ids == tuple(s.evidence_ids[0] for s in signals)
    assert expected.source_dependency_keys == ("fixture-record", "second-record")
    assert expected.policy_version == "vector-provenance-v1"
    assert expected.assessed_at == NOW


def test_weak_counterclaims_and_shared_evidence_are_preserved():
    strong = signal()
    weak = signal(
        Signal.NON_OEM_ORIGIN_ASSERTED,
        11,
        authority_class=Authority.REFERENCE_CATALOG,
        issuer_type=Issuer.REFERENCE_CATALOG,
    )
    result = assess((strong, weak))
    assert result.origin == Origin.VERIFIED_OEM
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.supporting_evidence_ids == strong.evidence_ids
    assert result.contradicting_evidence_ids == result.contextual_evidence_ids == weak.evidence_ids
    shared = signal(Signal.ANOMALY_OBSERVED, 12, evidence_ids=strong.evidence_ids)
    assert assess((strong, shared)).supporting_evidence_ids == strong.evidence_ids


@pytest.mark.parametrize(
    "changes",
    [
        {"signal_type": Signal.NON_OEM_ORIGIN_ASSERTED},
        {"evidence_ids": (opaque_id(99),)},
        {"issuer_key": "other-issuer"},
        {"source_dependency_key": "other-source"},
        {"observed_at": NOW - timedelta(seconds=1)},
    ],
)
def test_conflicting_duplicate_ids_fail(changes):
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        assess((signal(), signal(**changes)))


@pytest.mark.parametrize(
    "target",
    [
        component(ordinal=1),
        component(device_session_epoch=4),
        component(session_scope_id=opaque_id(2)),
        component(device_id="ios-012345abcdef"),
    ],
)
def test_wrong_component_or_session_fails(target):
    with pytest.raises(ValueError, match="another component or session"):
        assess_component_provenance(target, (signal(),), assessed_at=NOW)


@pytest.mark.parametrize(
    "refs",
    [
        ("diagnostic-pass-1", "diagnostic-pass-1"),
        ("../result",),
        ["result"],
        tuple(f"result-{n}" for n in range(257)),
    ],
)
def test_invalid_functionality_refs(refs):
    with pytest.raises(ValueError):
        assess(functionality_result_refs=refs)


def test_future_naive_and_raw_inputs_rejected():
    with pytest.raises(ValueError, match="follows assessment"):
        assess((signal(observed_at=NOW + timedelta(microseconds=1)),))
    with pytest.raises(ValueError):
        assess_component_provenance(component(), (), assessed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        assess((signal().model_dump(),))
    with pytest.raises(ValueError):
        assess_component_provenance(component().model_dump(), (), assessed_at=NOW)
    with pytest.raises(ValueError):
        assess([signal()])
    with pytest.raises(ValueError):
        assess((signal(),) * 257)


def test_model_copy_bypass_is_revalidated_at_policy_boundary():
    for forged in (
        signal().model_copy(update={"evidence_ids": ()}),
        signal().model_copy(update={"observed_at": NOW.replace(tzinfo=None)}),
    ):
        with pytest.raises(ValidationError):
            assess((forged,))
    forged_component = component().model_copy(update={"device_session_epoch": -1})
    with pytest.raises(ValidationError):
        assess_component_provenance(forged_component, (), assessed_at=NOW)


def test_opposing_weak_claims_preserve_both_without_resolving_origin():
    inputs = tuple(
        signal(kind, n, authority_class=Authority.USER_DECLARATION, issuer_type=Issuer.USER)
        for n, kind in enumerate((Signal.OEM_ORIGIN_ASSERTED, Signal.NON_OEM_ORIGIN_ASSERTED))
    )
    result = assess(inputs)
    evidence = tuple(s.evidence_ids[0] for s in inputs)
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.supporting_evidence_ids == ()
    assert result.contextual_evidence_ids == result.contradicting_evidence_ids == evidence


def test_signal_count_cannot_outvote_strong_conflict():
    inputs = tuple(signal(number=n) for n in range(200))
    opposing = signal(Signal.NON_OEM_ORIGIN_ASSERTED, 201)
    result = assess(inputs + (opposing,))
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.summary_label == Label.SUSPICIOUS
    assert len(result.contradicting_evidence_ids) == 201


@pytest.mark.parametrize("ref", ["123456789012345", "ABCDEF123456", "raw/value", "x" * 65])
def test_functionality_references_reject_raw_identifier_shapes(ref):
    with pytest.raises(ValueError):
        assess(functionality_result_refs=(ref,))


def test_evaluation_does_not_mutate_inputs_and_preserves_reference_order():
    target = component()
    record = signal()
    before = (target.model_dump_json(), record.model_dump_json())
    result = assess_component_provenance(
        target, (record,), functionality_result_refs=("z-result", "a-result"), assessed_at=NOW
    )
    assert before == (target.model_dump_json(), record.model_dump_json())
    assert result.functionality_result_refs == ("a-result", "z-result")


def test_maximum_evidence_union_is_bounded_and_preserved():
    inputs = tuple(
        signal(number=n, evidence_ids=tuple(opaque_id(10000 + n * 32 + i) for i in range(32)))
        for n in range(256)
    )
    result = assess(inputs)
    assert len(result.supporting_evidence_ids) == 8192
    assert len(result.signal_ids) == 256
    assert result.origin == Origin.VERIFIED_OEM


@pytest.mark.parametrize(
    "kind,reason",
    [
        (Signal.OEM_ORIGIN_ASSERTED, Reason.AUTHORITATIVE_OEM_EVIDENCE),
        (Signal.NON_OEM_ORIGIN_ASSERTED, Reason.AUTHORITATIVE_NON_OEM_EVIDENCE),
        (Signal.ORIGINAL_INSTALLATION_ASSERTED, Reason.AUTHORITATIVE_ORIGINAL_HISTORY),
        (Signal.REPLACEMENT_INSTALLATION_ASSERTED, Reason.AUTHORITATIVE_REPLACEMENT_HISTORY),
        (Signal.USED_PART_ASSERTED, Reason.AUTHORITATIVE_USED_PART_HISTORY),
        (Signal.MANIPULATION_ASSERTED, Reason.MANIPULATION_EVIDENCE),
        (Signal.ANOMALY_OBSERVED, Reason.ANOMALY_EVIDENCE),
        (Signal.NO_ANOMALY_OBSERVED, Reason.NO_ANOMALY_IN_OBSERVED_SCOPE),
    ],
)
def test_resolved_reason_contract(kind, reason):
    result = assess((signal(kind),))
    assert result.reason_codes == (reason,)


@pytest.mark.parametrize(
    "changes,reasons",
    [
        (
            {"authority_class": Authority.USER_DECLARATION, "issuer_type": Issuer.USER},
            (Reason.INSUFFICIENT_AUTHORITY,),
        ),
        ({"subject_binding": Binding.DEVICE_BOUND}, (Reason.INSUFFICIENT_SUBJECT_BINDING,)),
        ({"issuer_type": Issuer.USER}, (Reason.INELIGIBLE_ISSUER,)),
        (
            {
                "authority_class": Authority.USER_DECLARATION,
                "issuer_type": Issuer.USER,
                "subject_binding": Binding.UNBOUND,
            },
            (Reason.INSUFFICIENT_AUTHORITY, Reason.INSUFFICIENT_SUBJECT_BINDING),
        ),
    ],
)
def test_rejected_reason_contract(changes, reasons):
    result = assess((signal(**changes),))
    assert result.reason_codes == reasons
    assert result.sufficiency == Sufficiency.INCONCLUSIVE


@pytest.mark.parametrize("issuer", Issuer)
@pytest.mark.parametrize(
    "kind,reason",
    [
        (Signal.ANOMALY_OBSERVED, Reason.ANOMALY_EVIDENCE),
        (Signal.NO_ANOMALY_OBSERVED, Reason.NO_ANOMALY_IN_OBSERVED_SCOPE),
    ],
)
def test_behavioral_issuer_contract(issuer, kind, reason):
    record = signal(kind, authority_class=Authority.BEHAVIORAL_MEASUREMENT, issuer_type=issuer)
    result = assess((record,))
    allowed = issuer == Issuer.VECTOR
    assert result.reason_codes == ((reason,) if allowed else (Reason.INELIGIBLE_ISSUER,))
    expected_anomaly = (
        Anomaly.INDICATED if kind == Signal.ANOMALY_OBSERVED else Anomaly.NO_ANOMALY_OBSERVED
    )
    assert result.anomaly == (expected_anomaly if allowed else Anomaly.UNKNOWN)
    assert result.origin == Origin.UNKNOWN
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.sufficiency == (Sufficiency.SUPPORTED if allowed else Sufficiency.INCONCLUSIVE)
    assert result.supporting_evidence_ids == (record.evidence_ids if allowed else ())
    assert result.contextual_evidence_ids == (() if allowed else record.evidence_ids)


@pytest.mark.parametrize(
    "kinds,reasons,origin,used,label",
    [
        (
            (Signal.NON_OEM_ORIGIN_ASSERTED, Signal.ORIGINAL_INSTALLATION_ASSERTED),
            (
                Reason.AUTHORITATIVE_NON_OEM_EVIDENCE,
                Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,
            ),
            Origin.NON_OEM_INDICATED,
            Used.NOT_ESTABLISHED,
            Label.NON_OEM_INDICATED,
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED, Signal.USED_PART_ASSERTED),
            (Reason.AUTHORITATIVE_USED_PART_HISTORY, Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE),
            Origin.UNKNOWN,
            Used.USED_VERIFIED,
            Label.SUSPICIOUS,
        ),
        (
            (
                Signal.NON_OEM_ORIGIN_ASSERTED,
                Signal.ORIGINAL_INSTALLATION_ASSERTED,
                Signal.USED_PART_ASSERTED,
            ),
            (
                Reason.AUTHORITATIVE_NON_OEM_EVIDENCE,
                Reason.AUTHORITATIVE_USED_PART_HISTORY,
                Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,
                Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE,
            ),
            Origin.NON_OEM_INDICATED,
            Used.USED_VERIFIED,
            Label.NON_OEM_INDICATED,
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.NON_OEM_ORIGIN_ASSERTED),
            (Reason.CONFLICTING_ORIGIN_EVIDENCE,),
            Origin.UNKNOWN,
            Used.NOT_ESTABLISHED,
            Label.SUSPICIOUS,
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED, Signal.REPLACEMENT_INSTALLATION_ASSERTED),
            (Reason.CONFLICTING_INSTALLATION_EVIDENCE,),
            Origin.UNKNOWN,
            Used.NOT_ESTABLISHED,
            Label.SUSPICIOUS,
        ),
    ],
)
def test_conflict_reason_and_traceability_contract(kinds, reasons, origin, used, label):
    records = tuple(signal(kind, n) for n, kind in enumerate(kinds))
    result = assess(records)
    assert result.origin == origin
    assert result.installation == Installation.UNKNOWN
    assert result.used_part == used
    assert result.anomaly == Anomaly.UNKNOWN
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.summary_label == label
    assert result.reason_codes == tuple(sorted(reasons))
    assert result.contradicting_evidence_ids == tuple(r.evidence_ids[0] for r in records)
    retained = {Signal.NON_OEM_ORIGIN_ASSERTED, Signal.USED_PART_ASSERTED}
    # Origin conflict resolves neither origin assertion.
    if Reason.CONFLICTING_ORIGIN_EVIDENCE in reasons:
        retained.remove(Signal.NON_OEM_ORIGIN_ASSERTED)
    assert result.supporting_evidence_ids == tuple(
        r.evidence_ids[0] for r in records if r.signal_type in retained
    )
    assert result.signal_ids == tuple(r.signal_id for r in records)
    for ordering in permutations(records):
        assert assess(ordering) == result
        assert assess(ordering + (records[0],)) == result


@pytest.mark.parametrize(
    "counterclaim", [Signal.NON_OEM_ORIGIN_ASSERTED, Signal.USED_PART_ASSERTED]
)
def test_weak_cross_dimension_counterclaim_does_not_erase_original(counterclaim):
    original = signal(Signal.ORIGINAL_INSTALLATION_ASSERTED)
    weak = signal(
        counterclaim, 11, authority_class=Authority.USER_DECLARATION, issuer_type=Issuer.USER
    )
    result = assess((original, weak))
    assert result.installation == Installation.ORIGINAL_VERIFIED
    assert result.used_part == Used.NOT_ESTABLISHED
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.reason_codes == (
        Reason.AUTHORITATIVE_ORIGINAL_HISTORY,
        Reason.INSUFFICIENT_AUTHORITY,
    )
    assert result.supporting_evidence_ids == original.evidence_ids
    assert result.contextual_evidence_ids == weak.evidence_ids
