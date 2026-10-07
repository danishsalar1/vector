"""Domain integration without collectors, transports, routes or hardware claims."""

import ast
import json
from itertools import combinations
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.test_component_models import NOW, component, signal
from tests.test_provenance_policy import assess
from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    ScanSummary,
    TrustEngineStatus,
)
from vector_agent.models.probe import ProbeResponseEnvelope
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
    ComponentAssessment,
    OriginAssessment,
)
from vector_agent.models.provenance import (
    InstallationAssessment as Installation,
)
from vector_agent.models.provenance import (
    ManipulationAssessment as Manipulation,
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
    UsedPartAssessment as Used,
)
from vector_agent.provenance import assess_component_provenance


@pytest.mark.parametrize(
    "status,kind,expected",
    [
        (DiagnosticStatus.PASS, None, OriginAssessment.UNKNOWN),
        (DiagnosticStatus.PASS, Signal.NON_OEM_ORIGIN_ASSERTED, OriginAssessment.NON_OEM_INDICATED),
        (DiagnosticStatus.FAIL, Signal.OEM_ORIGIN_ASSERTED, OriginAssessment.VERIFIED_OEM),
        (DiagnosticStatus.ERROR, None, OriginAssessment.UNKNOWN),
        (DiagnosticStatus.RESTRICTED, None, OriginAssessment.UNKNOWN),
        (DiagnosticStatus.UNSUPPORTED, None, OriginAssessment.UNKNOWN),
        (DiagnosticStatus.INCONCLUSIVE, None, OriginAssessment.UNKNOWN),
    ],
)
def test_functional_results_remain_separate(status, kind, expected):
    evidence = EvidenceRecord(
        diagnostic_id="fixture_function",
        device_id=component().device_id,
        source_type=EvidenceSourceType.SYNTHETIC_TEST_ONLY,
        source_name="fabricated-test",
        collection_method="fixture",
        timestamp=NOW,
    )
    functional = DiagnosticResult(
        diagnostic_id="fixture_function",
        diagnostic_name="Fabricated function",
        category="battery",
        status=status,
        automation_level=AutomationLevel.AUTOMATIC,
        evidence=[evidence],
    )
    signals = () if kind is None else (signal(kind),)
    result = assess(signals, functionality_result_refs=(functional.diagnostic_id,))
    assert result.origin == expected
    assert result.functionality_result_refs == ("fixture_function",)
    assert str(evidence.evidence_id) not in result.supporting_evidence_ids
    assert functional.status == status


@pytest.mark.parametrize("device_id", ["android-012345abcdef", "ios-012345abcdef"])
def test_same_normalized_policy_for_either_device_namespace(device_id):
    target = component(device_id=device_id)
    record = signal(component_id=target.component_id)
    result = assess_component_provenance(target, (record,), assessed_at=NOW)
    assert result.origin == OriginAssessment.VERIFIED_OEM
    assert result.supporting_evidence_ids == record.evidence_ids


def test_existing_evidence_uuid_can_be_referenced_without_payload_copy():
    evidence = EvidenceRecord(
        diagnostic_id="fixture_record",
        device_id=component().device_id,
        source_type=EvidenceSourceType.SYNTHETIC_TEST_ONLY,
        source_name="fabricated-test",
        collection_method="fixture",
        raw_value="FABRICATED-PRIVATE-PAYLOAD",
        timestamp=NOW,
    )
    record = signal(evidence_ids=(str(evidence.evidence_id),))
    result = assess((record,))
    assert result.supporting_evidence_ids == (str(evidence.evidence_id),)
    assert "FABRICATED-PRIVATE-PAYLOAD" not in result.model_dump_json()
    assert "FABRICATED-PRIVATE-PAYLOAD" not in repr(result)


def test_assessment_roundtrip_immutability_and_no_fabricated_confidence():
    result = assess((signal(),))
    assert result == ComponentAssessment.model_validate_json(result.model_dump_json())
    with pytest.raises(ValidationError):
        result.origin = OriginAssessment.UNKNOWN
    with pytest.raises(ValidationError):
        result.component.ordinal = 3
    for forbidden in ("confidence", "trust_score", "metadata", "raw_serial", "raw_value"):
        assert forbidden not in ComponentAssessment.model_fields
        with pytest.raises(ValidationError):
            ComponentAssessment.model_validate(result.model_dump() | {forbidden: "private"})
    assert ScanSummary.model_fields["trust_score"].default is None
    assert ScanSummary.model_fields["trust_engine_status"].default == TrustEngineStatus.NOT_READY


def test_domain_imports_are_platform_neutral_and_have_no_io():
    root = Path(__file__).parents[1] / "src" / "vector_agent"
    files = [
        root / "models/component.py",
        root / "models/provenance.py",
        *(root / "provenance").glob("*.py"),
    ]
    allowed_absolute = {"__future__", "datetime", "enum", "hashlib", "typing", "types", "pydantic"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in allowed_absolute for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split(".")[0] in allowed_absolute
            elif isinstance(node, ast.ImportFrom):
                assert node.module in {
                    "component",
                    "models.component",
                    "models.provenance",
                    "policy",
                    "references",
                }
    assert "provenance" not in ProbeResponseEnvelope.model_fields
    assert "origin" not in ProbeResponseEnvelope.model_fields


def test_assessment_rejects_duplicate_reasons_and_references():
    result = assess((signal(),))
    for field in ("reason_codes", "signal_ids", "supporting_evidence_ids"):
        values = result.model_dump()
        values[field] = values[field] * 2
        with pytest.raises(ValidationError):
            ComponentAssessment.model_validate(values)


def _assessment_for(kinds):
    return assess(tuple(signal(kind, n) for n, kind in enumerate(kinds)))


@pytest.mark.parametrize("entry", ["constructor", "validate", "json"])
@pytest.mark.parametrize(
    "kinds,changes",
    [
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.ORIGINAL_INSTALLATION_ASSERTED),
            {"supporting_evidence_ids": ()},
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.REPLACEMENT_INSTALLATION_ASSERTED),
            {"supporting_evidence_ids": ()},
        ),
        (
            (
                Signal.OEM_ORIGIN_ASSERTED,
                Signal.REPLACEMENT_INSTALLATION_ASSERTED,
                Signal.USED_PART_ASSERTED,
            ),
            {
                "used_part": Used.NOT_ESTABLISHED,
                "reason_codes": (
                    Reason.AUTHORITATIVE_OEM_EVIDENCE,
                    Reason.AUTHORITATIVE_REPLACEMENT_HISTORY,
                ),
            },
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.ORIGINAL_INSTALLATION_ASSERTED),
            {"summary_label": Label.VERIFIED_OEM_ORIGIN_ONLY},
        ),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"summary_label": Label.NON_OEM_INDICATED}),
        ((Signal.NON_OEM_ORIGIN_ASSERTED,), {"summary_label": Label.UNKNOWN}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"summary_label": Label.UNKNOWN}),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.NON_OEM_ORIGIN_ASSERTED),
            {"summary_label": Label.UNKNOWN},
        ),
        (
            (Signal.NON_OEM_ORIGIN_ASSERTED, Signal.ORIGINAL_INSTALLATION_ASSERTED),
            {"sufficiency": Sufficiency.SUPPORTED},
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED, Signal.USED_PART_ASSERTED),
            {"sufficiency": Sufficiency.SUPPORTED},
        ),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"policy_version": "other-policy"}),
        ((), {"summary_label": Label.SUSPICIOUS}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"summary_label": Label.SUSPICIOUS}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"summary_label": Label.VERIFIED_OEM_ORIGINAL}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"summary_label": Label.VERIFIED_OEM_REPLACEMENT}),
        (
            (
                Signal.OEM_ORIGIN_ASSERTED,
                Signal.REPLACEMENT_INSTALLATION_ASSERTED,
                Signal.USED_PART_ASSERTED,
            ),
            {"summary_label": Label.VERIFIED_OEM_REPLACEMENT},
        ),
        (
            (
                Signal.OEM_ORIGIN_ASSERTED,
                Signal.ORIGINAL_INSTALLATION_ASSERTED,
                Signal.ANOMALY_OBSERVED,
            ),
            {"summary_label": Label.VERIFIED_OEM_ORIGINAL},
        ),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"sufficiency": Sufficiency.NOT_ASSESSED}),
        ((Signal.NON_OEM_ORIGIN_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((Signal.ORIGINAL_INSTALLATION_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((Signal.REPLACEMENT_INSTALLATION_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((Signal.USED_PART_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((Signal.MANIPULATION_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((Signal.ANOMALY_OBSERVED,), {"supporting_evidence_ids": ()}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"signal_ids": ()}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"source_dependency_keys": ()}),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED,),
            {
                "origin": OriginAssessment.NON_OEM_INDICATED,
                "summary_label": Label.NON_OEM_INDICATED,
                "reason_codes": (
                    Reason.AUTHORITATIVE_NON_OEM_EVIDENCE,
                    Reason.AUTHORITATIVE_ORIGINAL_HISTORY,
                ),
            },
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED,),
            {
                "used_part": Used.USED_VERIFIED,
                "reason_codes": (
                    Reason.AUTHORITATIVE_ORIGINAL_HISTORY,
                    Reason.AUTHORITATIVE_USED_PART_HISTORY,
                ),
            },
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.NON_OEM_ORIGIN_ASSERTED),
            {"contradicting_evidence_ids": ()},
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.NON_OEM_ORIGIN_ASSERTED),
            {
                "origin": OriginAssessment.VERIFIED_OEM,
                "supporting_evidence_ids": signal().evidence_ids,
                "reason_codes": (
                    Reason.AUTHORITATIVE_OEM_EVIDENCE,
                    Reason.CONFLICTING_ORIGIN_EVIDENCE,
                ),
            },
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED, Signal.REPLACEMENT_INSTALLATION_ASSERTED),
            {
                "installation": Installation.ORIGINAL_VERIFIED,
                "supporting_evidence_ids": signal().evidence_ids,
                "reason_codes": (
                    Reason.AUTHORITATIVE_ORIGINAL_HISTORY,
                    Reason.CONFLICTING_INSTALLATION_EVIDENCE,
                ),
            },
        ),
        (
            (Signal.ANOMALY_OBSERVED, Signal.NO_ANOMALY_OBSERVED),
            {
                "anomaly": Anomaly.INDICATED,
                "supporting_evidence_ids": signal().evidence_ids,
                "reason_codes": (Reason.ANOMALY_EVIDENCE, Reason.CONFLICTING_ANOMALY_EVIDENCE),
            },
        ),
        (
            (Signal.NON_OEM_ORIGIN_ASSERTED, Signal.ORIGINAL_INSTALLATION_ASSERTED),
            {
                "origin": OriginAssessment.UNKNOWN,
                "supporting_evidence_ids": (),
                "summary_label": Label.SUSPICIOUS,
                "reason_codes": (Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,),
            },
        ),
        (
            (Signal.ORIGINAL_INSTALLATION_ASSERTED, Signal.USED_PART_ASSERTED),
            {
                "used_part": Used.NOT_ESTABLISHED,
                "supporting_evidence_ids": (),
                "reason_codes": (Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE,),
            },
        ),
        ((), {"manipulation": Manipulation.NO_INDICATION_IN_OBSERVED_SCOPE}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"reason_codes": (Reason.AUTHORITATIVE_NON_OEM_EVIDENCE,)}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"sufficiency": Sufficiency.INCONCLUSIVE}),
        (
            (Signal.OEM_ORIGIN_ASSERTED,),
            {"reason_codes": (Reason.AUTHORITATIVE_OEM_EVIDENCE, Reason.INSUFFICIENT_AUTHORITY)},
        ),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"contextual_evidence_ids": signal().evidence_ids}),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"contradicting_evidence_ids": signal().evidence_ids}),
        (
            (
                Signal.OEM_ORIGIN_ASSERTED,
                Signal.REPLACEMENT_INSTALLATION_ASSERTED,
                Signal.USED_PART_ASSERTED,
            ),
            {"supporting_evidence_ids": ()},
        ),
        (
            (Signal.OEM_ORIGIN_ASSERTED, Signal.REPLACEMENT_INSTALLATION_ASSERTED),
            {"summary_label": Label.VERIFIED_OEM_ORIGIN_ONLY},
        ),
        ((Signal.OEM_ORIGIN_ASSERTED,), {"supporting_evidence_ids": ()}),
        ((), {"sufficiency": Sufficiency.INCONCLUSIVE}),
        ((), {"contradicting_evidence_ids": signal().evidence_ids}),
    ],
)
def test_forged_assessments_fail_all_validating_entry_points(entry, kinds, changes):
    values = _assessment_for(kinds).model_dump()
    values.update(changes)
    with pytest.raises(ValidationError):
        if entry == "constructor":
            ComponentAssessment(**values)
        elif entry == "validate":
            ComponentAssessment.model_validate(values)
        else:
            values["assessed_at"] = values["assessed_at"].isoformat()
            ComponentAssessment.model_validate_json(json.dumps(values))


@pytest.mark.parametrize(
    "kinds",
    [subset for size in range(len(Signal) + 1) for subset in combinations(tuple(Signal), size)],
)
def test_all_strong_signal_subsets_validate_and_roundtrip(kinds):
    records = tuple(signal(kind, n) for n, kind in enumerate(kinds))
    result = assess(records)
    assert ComponentAssessment(**result.model_dump()) == result
    assert ComponentAssessment.model_validate(result.model_dump()) == result
    assert ComponentAssessment.model_validate_json(result.model_dump_json()) == result
    assert assess(tuple(reversed(records))) == result

    # Verify semantic invariants across all 256 subsets
    if Signal.OEM_ORIGIN_ASSERTED in kinds and Signal.NON_OEM_ORIGIN_ASSERTED in kinds:
        assert result.origin == OriginAssessment.UNKNOWN
        assert Reason.CONFLICTING_ORIGIN_EVIDENCE in result.reason_codes
    elif Signal.OEM_ORIGIN_ASSERTED in kinds:
        assert result.origin == OriginAssessment.VERIFIED_OEM
        assert Reason.AUTHORITATIVE_OEM_EVIDENCE in result.reason_codes
    elif Signal.NON_OEM_ORIGIN_ASSERTED in kinds:
        assert result.origin == OriginAssessment.NON_OEM_INDICATED
        assert Reason.AUTHORITATIVE_NON_OEM_EVIDENCE in result.reason_codes
    else:
        assert result.origin == OriginAssessment.UNKNOWN

    if (
        (
            Signal.ORIGINAL_INSTALLATION_ASSERTED in kinds
            and Signal.REPLACEMENT_INSTALLATION_ASSERTED in kinds
        )
        or (
            Signal.ORIGINAL_INSTALLATION_ASSERTED in kinds
            and Signal.NON_OEM_ORIGIN_ASSERTED in kinds
        )
        or (Signal.ORIGINAL_INSTALLATION_ASSERTED in kinds and Signal.USED_PART_ASSERTED in kinds)
    ):
        assert result.installation == Installation.UNKNOWN
    elif Signal.ORIGINAL_INSTALLATION_ASSERTED in kinds:
        assert result.installation == Installation.ORIGINAL_VERIFIED
        assert Reason.AUTHORITATIVE_ORIGINAL_HISTORY in result.reason_codes
    elif Signal.REPLACEMENT_INSTALLATION_ASSERTED in kinds:
        assert result.installation == Installation.REPLACEMENT_VERIFIED
        assert Reason.AUTHORITATIVE_REPLACEMENT_HISTORY in result.reason_codes
    else:
        assert result.installation == Installation.UNKNOWN

    if Signal.USED_PART_ASSERTED in kinds:
        assert result.used_part == Used.USED_VERIFIED
        assert Reason.AUTHORITATIVE_USED_PART_HISTORY in result.reason_codes
    else:
        assert result.used_part == Used.NOT_ESTABLISHED

    if Signal.MANIPULATION_ASSERTED in kinds:
        assert result.manipulation == Manipulation.INDICATED
        assert Reason.MANIPULATION_EVIDENCE in result.reason_codes
    else:
        assert result.manipulation == Manipulation.UNKNOWN

    if Signal.ANOMALY_OBSERVED in kinds and Signal.NO_ANOMALY_OBSERVED in kinds:
        assert result.anomaly == Anomaly.UNKNOWN
        assert Reason.CONFLICTING_ANOMALY_EVIDENCE in result.reason_codes
    elif Signal.ANOMALY_OBSERVED in kinds:
        assert result.anomaly == Anomaly.INDICATED
        assert Reason.ANOMALY_EVIDENCE in result.reason_codes
    elif Signal.NO_ANOMALY_OBSERVED in kinds:
        assert result.anomaly == Anomaly.NO_ANOMALY_OBSERVED
        assert Reason.NO_ANOMALY_IN_OBSERVED_SCOPE in result.reason_codes
    else:
        assert result.anomaly == Anomaly.UNKNOWN

    if Reason.CONFLICTING_ORIGIN_EVIDENCE in result.reason_codes:
        assert result.summary_label == Label.SUSPICIOUS
    elif result.origin == OriginAssessment.NON_OEM_INDICATED:
        assert result.summary_label == Label.NON_OEM_INDICATED
    elif (
        (
            set(result.reason_codes)
            & {
                Reason.CONFLICTING_INSTALLATION_EVIDENCE,
                Reason.CONFLICTING_ANOMALY_EVIDENCE,
                Reason.CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE,
                Reason.CONFLICTING_ORIGINAL_USED_EVIDENCE,
            }
        )
        or result.manipulation == Manipulation.INDICATED
        or result.anomaly == Anomaly.INDICATED
    ):
        assert result.summary_label == Label.SUSPICIOUS


@pytest.mark.parametrize(
    "authority,issuer",
    [
        (Authority.DEVICE_REPORTED_METADATA, Issuer.DEVICE),
        (Authority.USER_DECLARATION, Issuer.USER),
        (Authority.REFERENCE_CATALOG, Issuer.REFERENCE_CATALOG),
    ],
)
def test_weak_evidence_assessment_roundtrip(authority, issuer):
    weak = signal(
        Signal.OEM_ORIGIN_ASSERTED,
        authority_class=authority,
        issuer_type=issuer,
    )
    result = assess((weak,))
    assert ComponentAssessment(**result.model_dump()) == result
    assert ComponentAssessment.model_validate(result.model_dump()) == result
    assert ComponentAssessment.model_validate_json(result.model_dump_json()) == result
