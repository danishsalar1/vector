"""Product truth table: function, OEM origin, history and anomalies are distinct."""

import pytest

from tests.test_component_models import signal
from tests.test_provenance_policy import ISSUERS, assess
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
    ProvenanceReasonCode as Reason,
)
from vector_agent.models.provenance import (
    ProvenanceSignalType as Signal,
)
from vector_agent.models.provenance import (
    UsedPartAssessment as Used,
)


def behavioral(kind, number=10):
    return signal(
        kind,
        number,
        authority_class=Authority.BEHAVIORAL_MEASUREMENT,
        issuer_type=ISSUERS[Authority.BEHAVIORAL_MEASUREMENT],
    )


def test_case_01_no_evidence_is_not_assessed():
    result = assess()
    assert result.origin == Origin.UNKNOWN
    assert result.installation == Installation.UNKNOWN
    assert result.used_part == Used.NOT_ESTABLISHED
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.anomaly == Anomaly.UNKNOWN
    assert result.sufficiency == Sufficiency.NOT_ASSESSED
    assert result.summary_label == Label.UNKNOWN
    assert result.reason_codes == (Reason.NO_PROVENANCE_EVIDENCE,)
    assert result.supporting_evidence_ids == result.contradicting_evidence_ids == ()
    assert (
        result.contextual_evidence_ids == result.signal_ids == result.source_dependency_keys == ()
    )


def test_case_02_normal_behavior_cannot_prove_origin():
    result = assess((behavioral(Signal.NO_ANOMALY_OBSERVED),))
    assert result.origin == Origin.UNKNOWN
    assert result.summary_label == Label.UNKNOWN


@pytest.mark.parametrize(
    "authority",
    [Authority.DEVICE_REPORTED_METADATA, Authority.USER_DECLARATION, Authority.REFERENCE_CATALOG],
)
def test_cases_03_04_05_familiar_claims_are_not_proof(authority):
    result = assess(
        (
            signal(
                authority_class=authority, issuer_type=ISSUERS[authority], issuer_key="familiar-oem"
            ),
        )
    )
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.summary_label == Label.UNKNOWN


def test_case_06_oem_origin_does_not_establish_history():
    result = assess((signal(),))
    assert result.origin == Origin.VERIFIED_OEM
    assert result.installation == Installation.UNKNOWN
    assert result.summary_label == Label.VERIFIED_OEM_ORIGIN_ONLY


@pytest.mark.parametrize(
    "history,used,label",
    [
        (Signal.ORIGINAL_INSTALLATION_ASSERTED, False, Label.VERIFIED_OEM_ORIGINAL),
        (Signal.REPLACEMENT_INSTALLATION_ASSERTED, False, Label.VERIFIED_OEM_REPLACEMENT),
        (Signal.REPLACEMENT_INSTALLATION_ASSERTED, True, Label.VERIFIED_OEM_USED_REPLACEMENT),
    ],
)
def test_cases_07_08_09_explicit_history_and_used(history, used, label):
    from vector_agent.models.provenance import ProvenanceSubjectBinding as Binding

    inputs = (signal(), signal(history, 11, subject_binding=Binding.DEVICE_SLOT_BOUND))
    if used:
        inputs += (signal(Signal.USED_PART_ASSERTED, 12),)
    result = assess(inputs)
    assert result.summary_label == label
    assert result.used_part == (Used.USED_VERIFIED if used else Used.NOT_ESTABLISHED)


def test_case_10_anomaly_does_not_mean_manipulation_or_non_oem():
    result = assess((behavioral(Signal.ANOMALY_OBSERVED),))
    assert result.anomaly == Anomaly.INDICATED
    assert result.origin == Origin.UNKNOWN
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.installation == Installation.UNKNOWN
    assert result.used_part == Used.NOT_ESTABLISHED
    assert result.summary_label == Label.SUSPICIOUS


def test_case_11_explicit_manipulation_evidence():
    result = assess((signal(Signal.MANIPULATION_ASSERTED),))
    assert result.manipulation == Manipulation.INDICATED
    assert result.origin == Origin.UNKNOWN
    assert result.summary_label == Label.SUSPICIOUS


def test_case_12_no_anomaly_never_proves_absence_of_manipulation():
    result = assess((signal(Signal.NO_ANOMALY_OBSERVED),))
    assert result.anomaly == Anomaly.NO_ANOMALY_OBSERVED
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.origin == Origin.UNKNOWN
    assert result.installation == Installation.UNKNOWN
    assert result.summary_label == Label.UNKNOWN


def test_case_13_strong_non_oem():
    result = assess((signal(Signal.NON_OEM_ORIGIN_ASSERTED),))
    assert result.origin == Origin.NON_OEM_INDICATED
    assert result.summary_label == Label.NON_OEM_INDICATED


def test_case_14_conflicting_origin_cannot_choose_winner():
    inputs = (signal(), signal(Signal.NON_OEM_ORIGIN_ASSERTED, 11))
    result = assess(inputs)
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.summary_label == Label.SUSPICIOUS
    assert set(result.contradicting_evidence_ids) == {eid for s in inputs for eid in s.evidence_ids}


def test_case_15_conflicting_installation_keeps_origin():
    inputs = (
        signal(),
        signal(Signal.ORIGINAL_INSTALLATION_ASSERTED, 11),
        signal(Signal.REPLACEMENT_INSTALLATION_ASSERTED, 12),
    )
    result = assess(inputs)
    assert result.origin == Origin.VERIFIED_OEM
    assert result.installation == Installation.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.supporting_evidence_ids == inputs[0].evidence_ids
    assert result.contradicting_evidence_ids == inputs[1].evidence_ids + inputs[2].evidence_ids


def test_case_16_oem_and_anomaly_are_independent():
    result = assess((signal(), behavioral(Signal.ANOMALY_OBSERVED, 11)))
    assert result.origin == Origin.VERIFIED_OEM
    assert result.anomaly == Anomaly.INDICATED
    assert result.summary_label == Label.SUSPICIOUS


def test_case_17_functional_pass_without_provenance():
    result = assess(functionality_result_refs=("diagnostic-pass-1",))
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.NOT_ASSESSED
    assert result.summary_label == Label.UNKNOWN


def test_case_18_many_correlated_weak_claims_never_accumulate_authority():
    inputs = tuple(
        signal(
            number=n,
            authority_class=Authority.DEVICE_REPORTED_METADATA,
            issuer_type=ISSUERS[Authority.DEVICE_REPORTED_METADATA],
        )
        for n in range(5)
    )
    result = assess(inputs)
    assert result.origin == Origin.UNKNOWN
    assert result.sufficiency == Sufficiency.INCONCLUSIVE
    assert result.source_dependency_keys == ("fixture-record",)
    assert len(result.contextual_evidence_ids) == 5
    assert result.summary_label == Label.UNKNOWN


def test_case_19_identical_duplicates_cannot_change_result():
    s = signal()
    assert assess((s,)) == assess((s,) * 256)


def test_case_20_conflicting_duplicate_is_rejected():
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        assess((signal(), signal(Signal.NON_OEM_ORIGIN_ASSERTED)))


@pytest.mark.parametrize(
    "authority",
    [
        Authority.USER_DECLARATION,
        Authority.DEVICE_REPORTED_METADATA,
        Authority.BEHAVIORAL_MEASUREMENT,
        Authority.REFERENCE_CATALOG,
    ],
)
@pytest.mark.parametrize(
    "kind",
    [
        Signal.USED_PART_ASSERTED,
        Signal.MANIPULATION_ASSERTED,
        Signal.REPLACEMENT_INSTALLATION_ASSERTED,
    ],
)
def test_weak_used_manipulation_or_replacement_assertions_cannot_resolve(authority, kind):
    result = assess((signal(kind, authority_class=authority, issuer_type=ISSUERS[authority]),))
    assert result.used_part == Used.NOT_ESTABLISHED
    assert result.manipulation == Manipulation.UNKNOWN
    assert result.installation == Installation.UNKNOWN
    assert result.origin == Origin.UNKNOWN


@pytest.mark.parametrize("kind", [Signal.MANIPULATION_ASSERTED, Signal.ANOMALY_OBSERVED])
def test_explicit_non_oem_precedes_suspicion(kind):
    result = assess((signal(Signal.NON_OEM_ORIGIN_ASSERTED), signal(kind, 11)))
    assert result.summary_label == Label.NON_OEM_INDICATED


def test_used_alone_cannot_establish_replacement_or_oem():
    result = assess((signal(Signal.USED_PART_ASSERTED),))
    assert result.used_part == Used.USED_VERIFIED
    assert result.origin == Origin.UNKNOWN
    assert result.installation == Installation.UNKNOWN
    assert result.summary_label == Label.UNKNOWN


def test_no_anomaly_cannot_cancel_explicit_manipulation():
    result = assess((signal(Signal.MANIPULATION_ASSERTED), signal(Signal.NO_ANOMALY_OBSERVED, 11)))
    assert result.manipulation == Manipulation.INDICATED
    assert result.anomaly == Anomaly.NO_ANOMALY_OBSERVED
    assert result.summary_label == Label.SUSPICIOUS


def test_all_weak_sources_together_cannot_prove_origin():
    inputs = tuple(
        signal(
            number=n,
            authority_class=authority,
            issuer_type=ISSUERS[authority],
            source_dependency_key=f"source-{n}",
        )
        for n, authority in enumerate(
            [
                Authority.USER_DECLARATION,
                Authority.DEVICE_REPORTED_METADATA,
                Authority.REFERENCE_CATALOG,
                Authority.BEHAVIORAL_MEASUREMENT,
            ]
        )
    )
    assert assess(inputs).origin == Origin.UNKNOWN
    assert assess(inputs).summary_label == Label.UNKNOWN


@pytest.mark.parametrize(
    "history,used",
    [
        (Signal.ORIGINAL_INSTALLATION_ASSERTED, False),
        (Signal.REPLACEMENT_INSTALLATION_ASSERTED, False),
        (Signal.REPLACEMENT_INSTALLATION_ASSERTED, True),
    ],
)
@pytest.mark.parametrize("hazard", [Signal.ANOMALY_OBSERVED, Signal.MANIPULATION_ASSERTED])
@pytest.mark.parametrize("conflict", [None, "origin", "installation"])
def test_oem_history_labels_yield_to_hazards_and_conflicts(history, used, hazard, conflict):
    records = [signal(), signal(history, 11), signal(hazard, 12)]
    if used:
        records.append(signal(Signal.USED_PART_ASSERTED, 13))
    conflicting_ids = set()
    if conflict == "origin":
        records.append(signal(Signal.NON_OEM_ORIGIN_ASSERTED, 14))
        conflicting_ids.update(records[0].evidence_ids + records[-1].evidence_ids)
        if history == Signal.ORIGINAL_INSTALLATION_ASSERTED:
            conflicting_ids.update(records[1].evidence_ids)
    elif conflict == "installation":
        opposite = (
            Signal.REPLACEMENT_INSTALLATION_ASSERTED
            if history == Signal.ORIGINAL_INSTALLATION_ASSERTED
            else Signal.ORIGINAL_INSTALLATION_ASSERTED
        )
        records.append(signal(opposite, 14))
        conflicting_ids.update(records[1].evidence_ids + records[-1].evidence_ids)
        if used:
            conflicting_ids.update(records[3].evidence_ids)
    result = assess(tuple(records))
    assert result.summary_label == Label.SUSPICIOUS
    assert result.origin == (Origin.UNKNOWN if conflict == "origin" else Origin.VERIFIED_OEM)
    installation_conflicted = conflict == "installation" or (
        conflict == "origin" and history == Signal.ORIGINAL_INSTALLATION_ASSERTED
    )
    expected_installation = (
        Installation.ORIGINAL_VERIFIED
        if history == Signal.ORIGINAL_INSTALLATION_ASSERTED
        else Installation.REPLACEMENT_VERIFIED
    )
    assert result.installation == (
        Installation.UNKNOWN if installation_conflicted else expected_installation
    )
    assert result.used_part == (Used.USED_VERIFIED if used else Used.NOT_ESTABLISHED)
    assert result.anomaly == (
        Anomaly.INDICATED if hazard == Signal.ANOMALY_OBSERVED else Anomaly.UNKNOWN
    )
    assert result.manipulation == (
        Manipulation.INDICATED if hazard == Signal.MANIPULATION_ASSERTED else Manipulation.UNKNOWN
    )
    assert result.sufficiency == (Sufficiency.INCONCLUSIVE if conflict else Sufficiency.SUPPORTED)
    expected_support = set(records[2].evidence_ids)
    if conflict != "origin":
        expected_support.update(records[0].evidence_ids)
    if not installation_conflicted:
        expected_support.update(records[1].evidence_ids)
    if used:
        expected_support.update(records[3].evidence_ids)
    assert set(result.supporting_evidence_ids) == expected_support
    assert set(result.contradicting_evidence_ids) == conflicting_ids
    assert result.contextual_evidence_ids == ()
    assert set(result.signal_ids) == {r.signal_id for r in records}

    expected_reasons = set()
    if hazard == Signal.ANOMALY_OBSERVED:
        expected_reasons.add(Reason.ANOMALY_EVIDENCE)
    else:
        expected_reasons.add(Reason.MANIPULATION_EVIDENCE)

    if conflict == "origin":
        expected_reasons.add(Reason.CONFLICTING_ORIGIN_EVIDENCE)
        if history == Signal.ORIGINAL_INSTALLATION_ASSERTED:
            expected_reasons.add(Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE)
    else:
        expected_reasons.add(Reason.AUTHORITATIVE_OEM_EVIDENCE)

    if conflict == "installation":
        expected_reasons.add(Reason.CONFLICTING_INSTALLATION_EVIDENCE)
    elif conflict == "origin" and history == Signal.ORIGINAL_INSTALLATION_ASSERTED:
        pass
    else:
        if history == Signal.ORIGINAL_INSTALLATION_ASSERTED:
            expected_reasons.add(Reason.AUTHORITATIVE_ORIGINAL_HISTORY)
        else:
            expected_reasons.add(Reason.AUTHORITATIVE_REPLACEMENT_HISTORY)

    if used:
        expected_reasons.add(Reason.AUTHORITATIVE_USED_PART_HISTORY)
        if history == Signal.ORIGINAL_INSTALLATION_ASSERTED or conflict == "installation":
            expected_reasons.add(Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE)

    assert set(result.reason_codes) == expected_reasons
