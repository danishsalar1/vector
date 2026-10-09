"""Adversarial regression and integrity tests for PG-13 (Phase 8E Checkpoint 2C).

Enforces core invariant: An unresolved, applicable reference-source conflict must
prevent VECTOR from issuing a definitive consistency or mismatch conclusion for the
affected specification.

Groups covered:
Group 1 — Primary failure (Cases 1-6)
Group 2 — No false positive conflicts (Cases 7-12)
Group 3 — Hierarchy and scope (Cases 13-17)
Group 4 — Reference values and source semantics (Cases 18-23)
Group 5 — Integration protection (Cases 24-30)
Group 6 — Report invariants (Cases 31-38)
"""

from datetime import UTC, datetime

import pytest

from vector_agent.models.reference import (
    CameraReferenceSpec,
    CameraSensorSpec,
    ComparisonOutcome,
    DeviceModelReference,
    DeviceResolutionResult,
    DeviceSpecification,
    DeviceVariantReference,
    ManufacturerReference,
    ReferenceConflict,
    ReferenceSource,
    ResolutionStatus,
    SensorReferenceSpec,
    SocReferenceSpec,
    SourceClassification,
)
from vector_agent.reference.catalog import ReferenceCatalog
from vector_agent.reference.comparator import SpecificationComparator
from vector_agent.reference.evidence_adapter import DiagnosticEvidenceAdapter


@pytest.mark.parametrize(
    "path,blocked",
    [
        (
            "future_domain.deep.field",
            {
                "soc.core_count",
                "sensors.nfc_present",
                "sensors.barometer_present",
                "network.5g_mmwave_supported",
            },
        ),
        ("sensors.future_flag", {"sensors.nfc_present", "sensors.barometer_present"}),
        ("connectivity", {"network.5g_mmwave_supported"}),
        ("connectivity.network_configuration", {"network.5g_mmwave_supported"}),
    ],
)
def test_fail_closed_guards_preserve_report_and_sibling_scope(path: str, blocked: set[str]) -> None:
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="guard-conflict",
            target_entity_type="model",
            target_entity_id=model.model_id,
            field_path=path,
            source_a_id="src-a",
            source_a_value="yes",
            source_b_id="src-b",
            source_b_value="no",
            conflict_notes="Unresolved fixture dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    report = SpecificationComparator(cat).compare(
        DeviceResolutionResult(
            status=ResolutionStatus.EXACT_MATCH,
            resolved_model=model,
            resolved_variant=variant,
            reason="Fixture",
        ),
        {"cpu_cores": 8, "feature_nfc": 1, "feature_barometer": 1, "feature_5g_mmwave": 1},
    )
    by_path = {i.property_path: i for i in report.items}
    for p in blocked:
        item = by_path[p]
        assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
        assert item.reference_value is None
        assert item.source_ids == ("src-a", "src-b")
        assert item.limitations and "guard-conflict" in item.limitations[0]
    for p in {"soc.core_count", "sensors.nfc_present", "sensors.barometer_present"} - blocked:
        assert by_path[p].outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert report.differs_count == 0
    assert report.consistent_count == len(
        {"soc.core_count", "sensors.nfc_present", "sensors.barometer_present"} - blocked
    )


def create_synthetic_source(
    source_id: str,
    title: str = "Test Source",
    publisher: str = "Test Publisher",
    is_synthetic: bool = False,
    classification: SourceClassification = SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE,
) -> ReferenceSource:
    return ReferenceSource(
        source_id=source_id,
        title=title,
        publisher=publisher,
        url_or_document_id=f"https://example.org/{source_id}",
        source_classification=classification,
        is_synthetic=is_synthetic,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def create_base_synthetic_catalog() -> tuple[
    ReferenceCatalog, DeviceModelReference, DeviceVariantReference
]:
    cat = ReferenceCatalog(test_only=True)
    src_a = create_synthetic_source("src-a", title="Primary OEM Specification")
    src_b = create_synthetic_source("src-b", title="Secondary Technical Resource")
    cat.register_source(src_a)
    cat.register_source(src_b)

    mfg = ManufacturerReference(
        manufacturer_id="mfg-synth",
        canonical_name="Synthetic Corp",
        source_id="src-a",
    )
    cat.register_manufacturer(mfg)

    model = DeviceModelReference(
        model_id="synth-phone-alpha",
        manufacturer_id="mfg-synth",
        marketed_name="Synth Alpha",
        model_family="Alpha Series",
        source_ids=("src-a",),
    )
    cat.register_model(model)

    spec = DeviceSpecification(
        soc=SocReferenceSpec(
            chip_maker="SynthChip",
            marketing_name="SC8000",
            cpu_architecture="arm64",
            core_count=8,
        ),
        camera=CameraReferenceSpec(
            rear_cameras=(
                CameraSensorSpec(role="main", resolution_mp=50.0),
                CameraSensorSpec(role="ultra_wide", resolution_mp=12.0),
                CameraSensorSpec(role="telephoto", resolution_mp=10.0),
            ),
        ),
        sensors=SensorReferenceSpec(nfc=True, barometer=True),
        source_ids=("src-a",),
    )

    variant = DeviceVariantReference(
        variant_id="synth-alpha-global",
        model_id="synth-phone-alpha",
        region_market="Global",
        specifications=spec,
        source_ids=("src-a",),
    )
    cat.register_variant(variant)

    return cat, model, variant


# ============================================================================
# Group 1 — Primary failure (Cases 1-6)
# ============================================================================


def test_two_sources_disagree_same_property_blocks_definitive_verdict() -> None:
    """Case 1: Two sources disagree on soc.core_count. Disputed reference must block CONSISTENT."""
    cat, model, variant = create_base_synthetic_catalog()
    conflict = ReferenceConflict(
        conflict_id="conf-soc-cores",
        target_entity_type="variant",
        target_entity_id="synth-alpha-global",
        field_path="specifications.soc.core_count",
        source_a_id="src-a",
        source_a_value="8",
        source_b_id="src-b",
        source_b_value="6",
        conflict_notes="Secondary teardown observed 6 cores instead of documented 8.",
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    cat.register_conflict(conflict)

    resolution = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Exact match synthetic",
    )
    comparator = SpecificationComparator(cat)
    report = comparator.compare(resolution, {"cpu_cores": 8})

    item = next(i for i in report.items if i.property_path == "soc.core_count")
    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.outcome != ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert item.outcome != ComparisonOutcome.DIFFERS_FROM_REFERENCE
    assert "disputed between conflicting sources" in item.reason
    assert "src-a" in item.source_ids and "src-b" in item.source_ids
    assert report.consistent_count == 0


def test_conflict_observed_value_equals_source_a_remains_non_definitive() -> None:
    """Case 2: Observed value equals Source A (8). Must still return REFERENCE_UNAVAILABLE."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-cores",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed core count",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Exact match",
    )
    comp = SpecificationComparator(cat)
    report = comp.compare(resolution, {"cpu_cores": 8})
    item = next(i for i in report.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.observed_value == 8
    assert report.consistent_count == 0
    assert report.differs_count == 0


def test_conflict_observed_value_equals_source_b_remains_non_definitive() -> None:
    """Case 3: Observed value equals Source B (6). Must not return DIFFERS_FROM_REFERENCE."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-cores",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed core count",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Exact match",
    )
    comp = SpecificationComparator(cat)
    report = comp.compare(resolution, {"cpu_cores": 6})
    item = next(i for i in report.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.outcome != ComparisonOutcome.DIFFERS_FROM_REFERENCE
    assert report.differs_count == 0


def test_conflict_observed_value_matches_neither_source_remains_non_definitive() -> None:
    """Case 4: Observed value (4) matches neither source. Handset is not blamed with DIFFERS."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-cores",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed core count",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Exact match",
    )
    comp = SpecificationComparator(cat)
    report = comp.compare(resolution, {"cpu_cores": 4})
    item = next(i for i in report.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.outcome != ComparisonOutcome.DIFFERS_FROM_REFERENCE
    assert report.differs_count == 0


def test_reverse_source_insertion_order_produces_identical_conflict_outcome() -> None:
    """Case 5: Reversing source registration order does not change verdict or source_ids."""
    cat1 = ReferenceCatalog(test_only=True)
    src_a = create_synthetic_source("src-a")
    src_b = create_synthetic_source("src-b")
    cat1.register_source(src_a)
    cat1.register_source(src_b)

    cat2 = ReferenceCatalog(test_only=True)
    cat2.register_source(src_b)
    cat2.register_source(src_a)

    for cat in (cat1, cat2):
        mfg = ManufacturerReference(manufacturer_id="mfg", canonical_name="M", source_id="src-a")
        cat.register_manufacturer(mfg)
        mod = DeviceModelReference(
            model_id="mod",
            manufacturer_id="mfg",
            marketed_name="M",
            model_family="F",
            source_ids=("src-a",),
        )
        cat.register_model(mod)
        var = DeviceVariantReference(
            variant_id="var",
            model_id="mod",
            region_market="G",
            specifications=DeviceSpecification(
                soc=SocReferenceSpec(
                    chip_maker="C", marketing_name="M", cpu_architecture="arm", core_count=8
                ),
                source_ids=("src-a",),
            ),
            source_ids=("src-a",),
        )
        cat.register_variant(var)

    cat1.register_conflict(
        ReferenceConflict(
            conflict_id="c1",
            target_entity_type="variant",
            target_entity_id="var",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Notes",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    cat2.register_conflict(
        ReferenceConflict(
            conflict_id="c1",
            target_entity_type="variant",
            target_entity_id="var",
            field_path="soc.core_count",
            source_a_id="src-b",
            source_a_value="6",
            source_b_id="src-a",
            source_b_value="8",
            conflict_notes="Notes",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res1 = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=cat1.get_model("mod"),
        resolved_variant=cat1.get_variant("var"),
        reason="Match",
    )
    res2 = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=cat2.get_model("mod"),
        resolved_variant=cat2.get_variant("var"),
        reason="Match",
    )

    rep1 = SpecificationComparator(cat1).compare(res1, {"cpu_cores": 8})
    rep2 = SpecificationComparator(cat2).compare(res2, {"cpu_cores": 8})

    i1 = next(i for i in rep1.items if i.property_path == "soc.core_count")
    i2 = next(i for i in rep2.items if i.property_path == "soc.core_count")

    assert i1.outcome == i2.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert i1.source_ids == i2.source_ids == ("src-a", "src-b")


def test_reverse_observation_construction_order_produces_identical_conflict_outcome() -> None:
    """Case 6: Observed property dictionary key ordering does not change conflict verdict."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-cores",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    comp = SpecificationComparator(cat)

    rep_a = comp.compare(res, {"cpu_cores": 8, "feature_nfc": 1})
    rep_b = comp.compare(res, {"feature_nfc": 1, "cpu_cores": 8})

    item_a = next(i for i in rep_a.items if i.property_path == "soc.core_count")
    item_b = next(i for i in rep_b.items if i.property_path == "soc.core_count")

    assert item_a.outcome == item_b.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert rep_a.consistent_count == rep_b.consistent_count == 1  # NFC is consistent!


# ============================================================================
# Group 2 — No false positive conflicts (Cases 7-12)
# ============================================================================


def test_two_sources_identical_compatible_assertions_no_conflict() -> None:
    """Case 7: Two sources assert identical values. Does not block comparison."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-identical",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="8",  # Identical value!
            conflict_notes="Compatible duplicate claim",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rep.consistent_count >= 1


def test_same_source_asserted_twice_with_identical_value_no_conflict() -> None:
    """Case 8: Same source registered with identical value twice does not create a conflict."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-same-source",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-a",  # Same source ID!
            source_b_value="8",
            conflict_notes="Self duplicate",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")
    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE


def test_different_sources_assert_different_properties_no_conflict() -> None:
    """Case 9: Sources assert different properties. Unrelated properties remain unpoisoned."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-camera-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="camera.rear_cameras_count",
            source_a_id="src-a",
            source_a_value="3",
            source_b_id="src-b",
            source_b_value="2",
            conflict_notes="Disputed rear camera count",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8, "rear_camera_count": 3})
    item_soc = next(i for i in rep.items if i.property_path == "soc.core_count")
    item_cam = next(i for i in rep.items if i.property_path == "camera.rear_cameras_count")

    # SoC is unpoisoned and consistent!
    assert item_soc.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    # Camera is conflicted and unavailable!
    assert item_cam.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE


def test_missing_or_unknown_source_assertion_no_conflict() -> None:
    """Case 10: Missing reference assertion for an unasserted field is not treated as conflict."""
    cat, model, variant = create_base_synthetic_catalog()
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {})
    # No conflict registered; soc reports INSUFFICIENT_EVIDENCE
    item_soc = next(i for i in rep.items if i.property_path == "soc.core_count")
    assert item_soc.outcome == ComparisonOutcome.INSUFFICIENT_EVIDENCE


def test_unrelated_conflict_from_different_model_does_not_poison() -> None:
    """Case 11: Conflict on Model X does not affect comparison of Model Y."""
    cat, model, variant = create_base_synthetic_catalog()

    # Register second model
    model_beta = DeviceModelReference(
        model_id="synth-phone-beta",
        manufacturer_id="mfg-synth",
        marketed_name="Synth Beta",
        model_family="Beta Series",
        source_ids=("src-a",),
    )
    cat.register_model(model_beta)
    # Register conflict strictly targeting synth-phone-beta
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-beta-soc",
            target_entity_type="model",
            target_entity_id="synth-phone-beta",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="4",
            conflict_notes="Beta core count dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    # Synth Alpha is unaffected!
    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE


def test_unrelated_conflict_from_different_variant_does_not_poison() -> None:
    """Case 12: Conflict on Variant A does not contaminate sibling Variant B."""
    cat, model, variant_a = create_base_synthetic_catalog()

    # Create sibling variant B
    variant_b = DeviceVariantReference(
        variant_id="synth-alpha-regional-jp",
        model_id="synth-phone-alpha",
        region_market="Japan",
        specifications=variant_a.specifications,
        source_ids=("src-a",),
    )
    cat.register_variant(variant_b)

    # Conflict on variant A only
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-var-a-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Variant A dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res_b = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant_b,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res_b, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    # Variant B is unaffected!
    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE


# ============================================================================
# Group 3 — Hierarchy and scope (Cases 13-17)
# ============================================================================


def test_model_level_conflict_inherited_by_variant() -> None:
    """Case 13: Model-level conflict inherits down to all variants of that model."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-model-cores",
            target_entity_type="model",
            target_entity_id="synth-phone-alpha",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Model level dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert "disputed between conflicting sources" in item.reason


def test_variant_only_conflict_does_not_poison_sibling_variant() -> None:
    """Case 14: Sibling variant without conflict evaluates independently."""
    cat, model, variant_a = create_base_synthetic_catalog()
    variant_b = DeviceVariantReference(
        variant_id="synth-alpha-sibling",
        model_id="synth-phone-alpha",
        region_market="EU",
        specifications=variant_a.specifications,
        source_ids=("src-a",),
    )
    cat.register_variant(variant_b)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-var-a-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="sensors.nfc_present",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="NFC dispute on Global variant only",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res_a = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant_a,
        reason="Match",
    )
    res_b = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant_b,
        reason="Match",
    )
    comp = SpecificationComparator(cat)

    rep_a = comp.compare(res_a, {"feature_nfc": 1})
    rep_b = comp.compare(res_b, {"feature_nfc": 1})

    item_a = next(i for i in rep_a.items if i.property_path == "sensors.nfc_present")
    item_b = next(i for i in rep_b.items if i.property_path == "sensors.nfc_present")

    assert item_a.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item_b.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE


def test_ambiguous_variant_cannot_become_exact_because_of_conflict() -> None:
    """Case 15: Conflict on candidate variant does not upgrade resolution status to EXACT_MATCH."""
    cat, model, variant_a = create_base_synthetic_catalog()
    variant_b = DeviceVariantReference(
        variant_id="synth-alpha-b",
        model_id="synth-phone-alpha",
        region_market="NA",
        specifications=variant_a.specifications,
        source_ids=("src-a",),
    )
    cat.register_variant(variant_b)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-on-a",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Conflict on candidate A",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=model,
        resolved_variant=None,
        reason="Ambiguous candidates",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})

    assert rep.resolution.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert rep.resolution.resolved_variant is None


def test_unknown_model_does_not_result_in_invented_reference() -> None:
    """Case 16: UNKNOWN_DEVICE status cleanly halts comparison without reference invention."""
    cat = ReferenceCatalog(test_only=True)
    res = DeviceResolutionResult(
        status=ResolutionStatus.UNKNOWN_DEVICE,
        resolved_model=None,
        resolved_variant=None,
        reason="Unrecognized hardware signature",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})

    assert len(rep.items) == 1
    assert rep.items[0].property_path == "device.specifications"
    assert rep.items[0].outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert rep.consistent_count == 0


def test_conflicts_affecting_optional_missing_fields_reported_truthfully() -> None:
    """Case 17: Conflict on a field missing in variant spec is reported as REFERENCE_UNAVAILABLE."""
    cat = ReferenceCatalog(test_only=True)
    src_a = create_synthetic_source("src-a")
    src_b = create_synthetic_source("src-b")
    cat.register_source(src_a)
    cat.register_source(src_b)

    mfg = ManufacturerReference(manufacturer_id="mfg", canonical_name="M", source_id="src-a")
    cat.register_manufacturer(mfg)
    mod = DeviceModelReference(
        model_id="mod",
        manufacturer_id="mfg",
        marketed_name="M",
        model_family="F",
        source_ids=("src-a",),
    )
    cat.register_model(mod)
    var = DeviceVariantReference(
        variant_id="var",
        model_id="mod",
        region_market="G",
        specifications=DeviceSpecification(source_ids=("src-a",)),  # No SoC or Camera!
        source_ids=("src-a",),
    )
    cat.register_variant(var)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-missing-field",
            target_entity_type="variant",
            target_entity_id="var",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Conflict on unpopulated field",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=mod,
        resolved_variant=var,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert "disputed between conflicting sources" in item.reason


# ============================================================================
# Group 4 — Reference values and source semantics (Cases 18-23)
# ============================================================================


def test_different_units_without_explicit_conversion_treated_as_conflict() -> None:
    """Case 18: Different unit claims without conversion contract are treated as conflicting."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-diff-units",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="battery.rated_capacity_mah",
            source_a_id="src-a",
            source_a_value="5000 mAh",
            source_b_id="src-b",
            source_b_value="18.5 Wh",
            conflict_notes="Unit disagreement without dimensional equivalence",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"charge_counter": 5000000})
    item = next(i for i in rep.items if i.property_path == "battery.rated_capacity_mah")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert "disputed between conflicting sources" in item.reason


def test_empty_or_malformed_conflict_property_reference_handled_safely() -> None:
    """Case 19: Conflict with unrecognizable path fails closed at entity level.

    Safety rationale (CG-02): The catalog permits free-form conflict paths without schema
    validation. Silently ignoring an unrecognizable path whose scope cannot be safely
    determined is unsafe, as it could allow false CONSISTENT verdicts on disputed hardware.
    Under the conservative fail-closed policy, unrecognized paths block comparisons at the
    entity level as REFERENCE_UNAVAILABLE rather than silently failing open.
    """
    cat, model, variant = create_base_synthetic_catalog()
    cat._conflicts.append(
        ReferenceConflict(
            conflict_id="conf-malformed",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="unknown_nonexistent_field_path",
            source_a_id="src-a",
            source_a_value="foo",
            source_b_id="src-b",
            source_b_value="bar",
            conflict_notes="Malformed path",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    # Unrecognized path fails closed at entity level to avoid false CONSISTENT
    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.reference_value is None
    assert "disputed" in (item.reason or "").lower()


def test_recognized_unrelated_field_conflict_does_not_contaminate_unrelated_property() -> None:
    """Case 19b: A recognized unrelated field conflict does not falsely contaminate other fields.

    Companion positive control for Case 19: While unrecognized paths fail closed, recognized
    fields with distinct scope (e.g. display.refresh_rate_hz) do not block unrelated properties
    like soc.core_count.
    """
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-display",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="display.refresh_rate_hz",
            source_a_id="src-a",
            source_a_value="60",
            source_b_id="src-b",
            source_b_value="120",
            conflict_notes="Display refresh dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    # Recognized unrelated conflict leaves soc.core_count comparable
    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert item.reference_value == 8


def test_dangling_source_identifier_in_conflict_handled_safely() -> None:
    """Case 20: Conflict citing a source ID absent from _sources does not crash comparator."""
    cat, model, variant = create_base_synthetic_catalog()
    # Direct injection bypassing register_conflict check
    cat._conflicts.append(
        ReferenceConflict(
            conflict_id="conf-dangling",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="unregistered-source-xyz",
            source_b_value="6",
            conflict_notes="Dangling source citation",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.source_ids == ("src-a",)
    assert any("unregistered-source-xyz" in note for note in item.limitations)


def test_source_metadata_change_without_spec_value_change_no_conflict() -> None:
    """Case 21: Conflicting records with identical values do not block definitive comparison."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-meta-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value=" 8 ",  # Whitespace-equivalent identical value
            conflict_notes="Only publication date metadata differed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE


def test_multiple_conflicting_sources_for_single_property() -> None:
    """Case 22: Three sources disagreeing on one property aggregate all source citations."""
    cat, model, variant = create_base_synthetic_catalog()
    src_c = create_synthetic_source("src-c", title="Regulatory Lab Spec")
    cat.register_source(src_c)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-ab",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Source B claims 6 cores",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-ac",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-c",
            source_b_value="4",
            conflict_notes="Source C claims 4 cores",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.source_ids == ("src-a", "src-b", "src-c")
    assert "disputed across 2 conflicting source assertions" in item.reason
    conflict_notes = [text for text in item.limitations if text.startswith("Reference conflict")]
    assert len(conflict_notes) == 2
    # Every test-only item also carries exactly one explicit TEST-ONLY label (FR-07).
    assert len(item.limitations) == 3 and "TEST-ONLY CATALOG" in item.limitations[-1]


def test_multiple_independent_conflicts_for_different_properties() -> None:
    """Case 23: Multiple distinct properties have independent conflicts."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="SoC dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-cam",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="camera.rear_cameras_count",
            source_a_id="src-a",
            source_a_value="3",
            source_b_id="src-b",
            source_b_value="2",
            conflict_notes="Camera dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(
        res, {"cpu_cores": 8, "rear_camera_count": 3, "feature_nfc": 1}
    )
    item_soc = next(i for i in rep.items if i.property_path == "soc.core_count")
    item_cam = next(i for i in rep.items if i.property_path == "camera.rear_cameras_count")
    item_nfc = next(i for i in rep.items if i.property_path == "sensors.nfc_present")

    assert item_soc.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item_cam.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item_nfc.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rep.consistent_count == 1
    assert rep.differs_count == 0


# ============================================================================
# Group 5 — Integration protection (Cases 24-30)
# ============================================================================


def test_checkpoint2a_exact_match_behavior_remains_intact_when_no_conflicts() -> None:
    """Case 24: Uncontested exact match compares all supported features accurately."""
    cat, model, variant = create_base_synthetic_catalog()
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Exact match",
    )
    rep = SpecificationComparator(cat).compare(
        res, {"cpu_cores": 8, "rear_camera_count": 3, "feature_nfc": 1, "feature_barometer": 1}
    )
    assert rep.consistent_count == 4
    assert rep.differs_count == 0


def test_variant_ambiguity_remains_non_definitive() -> None:
    """Case 25: Candidate variants differing on specs preserve VARIANT_AMBIGUOUS."""
    cat, model, variant_a = create_base_synthetic_catalog()
    spec_b = DeviceSpecification(
        soc=SocReferenceSpec(
            chip_maker="SynthChip",
            marketing_name="SC8000",
            cpu_architecture="arm64",
            core_count=6,  # Differs from Variant A's 8!
        ),
        source_ids=("src-a",),
    )
    variant_b = DeviceVariantReference(
        variant_id="synth-alpha-regional-b",
        model_id="synth-phone-alpha",
        region_market="Regional",
        specifications=spec_b,
        source_ids=("src-a",),
    )
    cat.register_variant(variant_b)

    res = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=model,
        resolved_variant=None,
        reason="Two regional variants",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")
    assert item.outcome == ComparisonOutcome.VARIANT_AMBIGUOUS


def test_checkpoint2b_evidence_adapter_cannot_bypass_applicable_reference_conflict() -> None:
    """Case 26: DiagnosticEvidenceAdapter path cannot bypass reference conflict."""
    from tests.test_phase8e_checkpoint2b import fabricated_result
    from vector_agent.reference.seed import build_seed_catalog

    catalog = build_seed_catalog(test_only=True)
    # Register conflict on pixel-7-pro model
    catalog.register_conflict(
        ReferenceConflict(
            conflict_id="conf-pixel-nfc",
            target_entity_type="model",
            target_entity_id="pixel-7-pro",
            field_path="sensors.nfc_present",
            source_a_id="google-pixel7pro-specs",
            source_a_value="true",
            source_b_id="fcc-pixel7pro-ge2ae",
            source_b_value="false",
            conflict_notes="NFC presence in dispute on Pixel 7 Pro",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    _, owner, result = fabricated_result()
    adapter = DiagnosticEvidenceAdapter(catalog)
    compared = adapter.compare(result, owner=owner)

    # In adapter's comparison report, nfc must report REFERENCE_UNAVAILABLE due to conflict!
    nfc_item = next(i for i in compared.report.items if i.property_path == "sensors.nfc_present")
    assert nfc_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert "disputed between conflicting sources" in nfc_item.reason
    assert compared.report.consistent_count == 0


def test_caller_supplied_evidence_remains_unverified() -> None:
    """Case 27: Calling compare() maintains unverified disclaimer even with conflict."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    assert "Caller-supplied unverified observations" in rep.honesty_disclaimer


def test_hardware_authenticity_remains_unknown() -> None:
    """Case 28: Specification comparison outcome never evaluates component authenticity."""
    cat, model, variant = create_base_synthetic_catalog()
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    assert "does NOT evaluate component authenticity" in rep.honesty_disclaimer


def test_reference_conflict_cannot_be_presented_as_evidence_of_replacement_or_tampering() -> None:
    """Case 29: Conflict reason cites reference dispute, never tampering or hardware defects."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Third party teardown differs",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 6})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert "tamper" not in item.reason.lower()
    assert "counterfeit" not in item.reason.lower()
    assert "replacement" not in item.reason.lower()
    assert "defect" not in item.reason.lower()
    assert "disputed between conflicting sources" in item.reason


def test_no_source_disagreement_can_become_trust_engine_score_or_verdict() -> None:
    """Case 30: Comparison report contains no trust score or Trust Engine invocation."""
    cat, model, variant = create_base_synthetic_catalog()
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    assert "trust score" not in rep.__dict__
    assert not hasattr(rep, "trust_score")


# ============================================================================
# Group 6 — Report invariants (Cases 31-38)
# ============================================================================


def test_conflict_property_counted_exactly_once_in_items() -> None:
    """Case 31: Exactly one item per property appears in report items."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    soc_items = [i for i in rep.items if i.property_path == "soc.core_count"]
    assert len(soc_items) == 1


def test_conflict_property_not_counted_as_consistent() -> None:
    """Case 32: Conflicted property never increments consistent_count."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    assert rep.consistent_count == 0


def test_conflict_property_not_counted_as_differs() -> None:
    """Case 33: Conflicted property never increments differs_count."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 6})
    assert rep.differs_count == 0


def test_unaffected_properties_retain_valid_outcomes_and_counts() -> None:
    """Case 34: Unaffected properties retain valid outcomes and accurately compute counts."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(
        res,
        {
            "cpu_cores": 8,  # Conflicted: REFERENCE_UNAVAILABLE
            "rear_camera_count": 3,  # Uncontested: CONSISTENT_WITH_REFERENCE
            "feature_nfc": 1,  # Uncontested: CONSISTENT_WITH_REFERENCE
            "feature_barometer": 0,  # Uncontested mismatch: DIFFERS_FROM_REFERENCE
        },
    )
    assert rep.consistent_count == 2
    assert rep.differs_count == 1
    assert rep.reference_unavailable_count >= 1


def test_stable_deterministic_output_across_equivalent_source_orders() -> None:
    """Case 35: Reversing source citation order in conflict produces identical source_ids."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-b",  # b first
            source_a_value="6",
            source_b_id="src-a",  # a second
            source_b_value="8",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")
    # Must be sorted alphabetically
    assert item.source_ids == ("src-a", "src-b")


def test_conflict_reason_references_only_legitimately_available_source_data() -> None:
    """Case 36: Conflict reason contains only genuine source identifiers, no private tokens."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    item = next(i for i in rep.items if i.property_path == "soc.core_count")

    assert "src-a" in item.reason
    assert "src-b" in item.reason
    assert "8" in item.reason
    assert "6" in item.reason
    assert "device-unknown" not in item.reason


def test_repeated_comparisons_do_not_mutate_catalog_state() -> None:
    """Case 37: Running comparison repeatedly leaves catalog structures untouched."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    comp = SpecificationComparator(cat)

    conflicts_before = list(cat.all_conflicts())
    models_before = list(cat.all_models())

    for _ in range(5):
        comp.compare(res, {"cpu_cores": 8})

    assert list(cat.all_conflicts()) == conflicts_before
    assert list(cat.all_models()) == models_before


def test_repeated_comparisons_produce_identical_results_for_unchanged_catalog_state() -> None:
    """Case 38: Idempotency of comparison report outputs on identical inputs."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    comp = SpecificationComparator(cat)

    rep1 = comp.compare(res, {"cpu_cores": 8})
    rep2 = comp.compare(res, {"cpu_cores": 8})

    assert rep1.consistent_count == rep2.consistent_count
    assert rep1.differs_count == rep2.differs_count
    assert rep1.reference_unavailable_count == rep2.reference_unavailable_count
    assert [i.outcome for i in rep1.items] == [i.outcome for i in rep2.items]


# ============================================================================
# CG-03 Adversarial Regression Suite — Groups A through G
# ============================================================================


# Group A: Barometer Conflict Handling
def test_barometer_conflict_blocks_otherwise_consistent_outcome() -> None:
    """Group A1: Applicable conflict on barometer blocks otherwise-CONSISTENT verdict."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-barometer",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="sensors.barometer_present",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="Barometer presence disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    # Observed feature_barometer is 1 (True), matching reference true.
    # Without conflict, this would be CONSISTENT_WITH_REFERENCE.
    rep = SpecificationComparator(cat).compare(res, {"feature_barometer": 1})
    item = next(i for i in rep.items if i.property_path == "sensors.barometer_present")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.outcome != ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert item.reference_value is None
    assert item.observed_value is True
    assert "disputed" in (item.reason or "").lower()
    assert rep.consistent_count == 0


def test_barometer_conflict_blocks_otherwise_differs_outcome() -> None:
    """Group A2: Applicable conflict on barometer blocks otherwise-DIFFERS verdict."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-barometer-diff",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="specifications.sensors.barometer",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="Barometer disputed via specifications. prefix",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    # Observed feature_barometer is 0 (False), mismatching reference true.
    # Without conflict, this would be DIFFERS_FROM_REFERENCE.
    rep = SpecificationComparator(cat).compare(res, {"feature_barometer": 0})
    item = next(i for i in rep.items if i.property_path == "sensors.barometer_present")

    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.outcome != ComparisonOutcome.DIFFERS_FROM_REFERENCE
    assert item.reference_value is None
    assert item.observed_value is False
    assert rep.differs_count == 0


def test_unrelated_nfc_conflict_does_not_incorrectly_block_barometer() -> None:
    """Group A3: Conflict on sensors.nfc does not block sensors.barometer (sibling isolation)."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-nfc-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="sensors.nfc",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="Only NFC in dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"feature_barometer": 1, "feature_nfc": 1})
    baro_item = next(i for i in rep.items if i.property_path == "sensors.barometer_present")
    nfc_item = next(i for i in rep.items if i.property_path == "sensors.nfc_present")

    # Barometer is uncontested and must remain CONSISTENT
    assert baro_item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert baro_item.reference_value is True
    assert baro_item.observed_value is True

    # NFC is contested and must be REFERENCE_UNAVAILABLE
    assert nfc_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert nfc_item.reference_value is None
    assert rep.consistent_count == 1


# Group B: mmWave Conflict Handling
def test_variant_specific_network_conflict_blocks_definitive_mmwave_verdict() -> None:
    """Group B1: Variant-specific network conflict blocks definitive mmWave verdict."""
    cat, model, _ = create_base_synthetic_catalog()
    # Create variant with mmWave network config
    variant_mmwave = DeviceVariantReference(
        variant_id="synth-alpha-us-mmwave",
        model_id=model.model_id,
        region_market="North America",
        network_configuration="5G mmWave + Sub-6",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    cat.register_variant(variant_mmwave)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-mmwave-var",
            target_entity_type="variant",
            target_entity_id="synth-alpha-us-mmwave",
            field_path="network.5g_mmwave_supported",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="5G mmWave support in dispute for US variant",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant_mmwave,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"feature_5g_mmwave": True})
    mmwave_item = next(i for i in rep.items if i.property_path == "network.5g_mmwave_supported")

    assert mmwave_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert mmwave_item.outcome != ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert mmwave_item.reference_value is None
    assert mmwave_item.observed_value is True
    assert rep.consistent_count == 0


def test_model_level_network_conflict_affects_applicable_variants() -> None:
    """Group B2: Model-level network conflict affects all applicable variants."""
    cat, model, _ = create_base_synthetic_catalog()
    variant = DeviceVariantReference(
        variant_id="synth-alpha-us",
        model_id=model.model_id,
        region_market="US",
        network_configuration="5G mmWave + Sub-6",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    cat.register_variant(variant)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-model-net",
            target_entity_type="model",
            target_entity_id=model.model_id,
            field_path="network",
            source_a_id="src-a",
            source_a_value="Sub-6 only",
            source_b_id="src-b",
            source_b_value="mmWave enabled",
            conflict_notes="Model-wide network capabilities in dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"feature_5g_mmwave": True})
    mmwave_item = next(i for i in rep.items if i.property_path == "network.5g_mmwave_supported")

    assert mmwave_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert mmwave_item.reference_value is None


def test_unrelated_regional_variant_remains_unaffected_by_sibling_network_conflict() -> None:
    """Group B3: Network conflict on variant A does not affect sibling variant B."""
    cat, model, _ = create_base_synthetic_catalog()
    var_us = DeviceVariantReference(
        variant_id="synth-alpha-us",
        model_id=model.model_id,
        region_market="US",
        network_configuration="5G mmWave + Sub-6",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    var_eu = DeviceVariantReference(
        variant_id="synth-alpha-eu",
        model_id=model.model_id,
        region_market="Europe",
        network_configuration="5G Sub-6",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    cat.register_variant(var_us)
    cat.register_variant(var_eu)

    # Conflict registered ONLY on var_us
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-us-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-us",
            field_path="network.5g_mmwave_supported",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="US variant dispute only",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    # Evaluate EU variant (observed Sub-6 only: feature_5g_mmwave=False)
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=var_eu,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"feature_5g_mmwave": False})
    mmwave_item = next(i for i in rep.items if i.property_path == "network.5g_mmwave_supported")

    # EU variant is unaffected: reference is False ("mmWave" not in "5G Sub-6"), observed is False -> CONSISTENT
    assert mmwave_item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert mmwave_item.reference_value is False
    assert mmwave_item.observed_value is False


def test_unknown_region_does_not_become_exact_because_of_network_conflict() -> None:
    """Group B4: Network conflict does not artificially collapse ambiguous variant resolution."""
    cat, model, _ = create_base_synthetic_catalog()
    var_a = DeviceVariantReference(
        variant_id="synth-alpha-v1",
        model_id=model.model_id,
        region_market="Region 1",
        network_configuration="5G mmWave",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    var_b = DeviceVariantReference(
        variant_id="synth-alpha-v2",
        model_id=model.model_id,
        region_market="Region 2",
        network_configuration="5G Sub-6",
        specifications=DeviceSpecification(source_ids=("src-a",)),
        source_ids=("src-a",),
    )
    cat.register_variant(var_a)
    cat.register_variant(var_b)

    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-var-a-net",
            target_entity_type="variant",
            target_entity_id="synth-alpha-v1",
            field_path="network.5g_mmwave_supported",
            source_a_id="src-a",
            source_a_value="true",
            source_b_id="src-b",
            source_b_value="false",
            conflict_notes="Disputed",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    # Ambiguous resolution with model (comparator looks up candidate variants from catalog)
    res = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=model,
        reason="Ambiguous regional variant",
    )
    rep = SpecificationComparator(cat).compare(res, {"feature_5g_mmwave": True})
    mmwave_item = next(i for i in rep.items if i.property_path == "network.5g_mmwave_supported")

    # Since var_a has an applicable conflict, mmWave must report REFERENCE_UNAVAILABLE (not VARIANT_AMBIGUOUS and not CONSISTENT)
    assert mmwave_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert mmwave_item.reference_value is None


# Group C: Ambiguous Candidate Variants
def test_ambiguous_variant_with_one_candidate_conflicted_does_not_bypass_conflict() -> None:
    """Group C1: Ambiguous resolution does not bypass conflict by choosing uncontested candidate."""
    cat, model, _ = create_base_synthetic_catalog()
    spec_a = DeviceSpecification(
        soc=SocReferenceSpec(
            chip_maker="SynthChip",
            marketing_name="SC8000",
            cpu_architecture="arm64",
            core_count=8,
        ),
        source_ids=("src-a",),
    )
    spec_b = DeviceSpecification(
        soc=SocReferenceSpec(
            chip_maker="SynthChip",
            marketing_name="SC8000",
            cpu_architecture="arm64",
            core_count=8,
        ),
        source_ids=("src-a",),
    )
    var_a = DeviceVariantReference(
        variant_id="synth-cand-a",
        model_id=model.model_id,
        region_market="Region A",
        specifications=spec_a,
        source_ids=("src-a",),
    )
    var_b = DeviceVariantReference(
        variant_id="synth-cand-b",
        model_id=model.model_id,
        region_market="Region B",
        specifications=spec_b,
        source_ids=("src-a",),
    )
    cat.register_variant(var_a)
    cat.register_variant(var_b)

    # Register conflict on candidate A only
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-cand-a-soc",
            target_entity_type="variant",
            target_entity_id="synth-cand-a",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Candidate A SoC cores in dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    res = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=model,
        reason="Model match with two candidate variants",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})
    soc_item = next(i for i in rep.items if i.property_path == "soc.core_count")

    # Invariant: Comparator must NOT bypass candidate A's conflict to issue CONSISTENT via candidate B
    assert soc_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert soc_item.outcome != ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert soc_item.reference_value is None
    assert soc_item.observed_value == 8
    assert rep.consistent_count == 0


# Group D: Alias and Prefix Handling
def test_prefix_and_alias_normalization_matches_ancestors_and_collection_elements() -> None:
    """Group D1: Structural segment-aware matching handles prefixes, ancestors, and element indices."""
    cases = [
        ("specifications.sensors", "sensors.nfc_present", True),
        ("specifications.sensors", "sensors.barometer_present", True),
        ("base_specifications.sensors", "sensors.nfc_present", True),
        ("sensors", "sensors.nfc_present", True),
        ("sensors", "sensors.barometer_present", True),
        ("specifications.soc", "soc.core_count", True),
        ("soc", "soc.core_count", True),
        ("camera", "camera.rear_cameras_count", True),
        ("camera.rear_cameras[0]", "camera.rear_cameras_count", True),
        ("  SPECIFICATIONS.SENSORS  ", "sensors.nfc_present", True),
        ("specifications", "soc.core_count", True),
        ("specifications", "sensors.nfc_present", True),
    ]

    for conflict_path, target_prop, should_affect in cases:
        cat, model, variant = create_base_synthetic_catalog()
        cat.register_conflict(
            ReferenceConflict(
                conflict_id=f"conf-test-{abs(hash(conflict_path))}",
                target_entity_type="variant",
                target_entity_id="synth-alpha-global",
                field_path=conflict_path,
                source_a_id="src-a",
                source_a_value="val1",
                source_b_id="src-b",
                source_b_value="val2",
                conflict_notes="Alias/prefix test",
                recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        res = DeviceResolutionResult(
            status=ResolutionStatus.EXACT_MATCH,
            resolved_model=model,
            resolved_variant=variant,
            reason="Match",
        )
        rep = SpecificationComparator(cat).compare(
            res,
            {
                "cpu_cores": 8,
                "feature_nfc": 1,
                "feature_barometer": 1,
                "rear_camera_count": 3,
            },
        )
        item = next(i for i in rep.items if i.property_path == target_prop)
        if should_affect:
            assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE, (
                f"Path '{conflict_path}' failed to affect '{target_prop}'"
            )
            assert item.reference_value is None


def test_similar_looking_unrelated_paths_do_not_falsely_match() -> None:
    """Group D2: Segment matching does NOT substring-match similar words (society != soc, sensor != sensors)."""
    from vector_agent.reference.comparator import _property_matches_conflict

    assert not _property_matches_conflict("soc.core_count", "camera.front_cameras")
    assert not _property_matches_conflict("soc.core_count", "display.resolution")
    assert not _property_matches_conflict("sensors.barometer_present", "sensors.nfc")
    assert not _property_matches_conflict("sensors.nfc_present", "sensors.barometer")
    assert not _property_matches_conflict("soc.core_count", "sensors")
    assert not _property_matches_conflict("sensors.nfc_present", "soc")


# Group E: Source Integrity and Item Contents
def test_conflict_item_source_integrity_and_disputed_metadata() -> None:
    """Group E1: Disputed item retains both source IDs, limitations, observed value, and no duplicates."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-integrity",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="Core count dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8})

    items = [i for i in rep.items if i.property_path == "soc.core_count"]
    assert len(items) == 1, "Duplicate items produced for disputed property"

    item = items[0]
    assert item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert item.reference_value is None
    assert item.observed_value == 8
    assert item.source_ids == ("src-a", "src-b"), (
        "Source IDs must be strictly sorted in deterministic ascending order"
    )
    assert any("conf-soc-integrity" in lim for lim in item.limitations)
    assert "disputed" in (item.reason or "").lower()


# Group F: Uncontested Positive Controls
def test_uncontested_properties_remain_fully_comparable() -> None:
    """Group F1: Uncontested properties remain comparable; fail-all implementation fails here."""
    cat, model, variant = create_base_synthetic_catalog()
    # Catalog has NO conflicts
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(
        res,
        {
            "cpu_cores": 8,
            "feature_nfc": 1,
            "feature_barometer": 1,
            "rear_camera_count": 3,
        },
    )
    assert rep.consistent_count >= 3
    assert rep.differs_count == 0

    soc = next(i for i in rep.items if i.property_path == "soc.core_count")
    nfc = next(i for i in rep.items if i.property_path == "sensors.nfc_present")
    baro = next(i for i in rep.items if i.property_path == "sensors.barometer_present")
    cam = next(i for i in rep.items if i.property_path == "camera.rear_cameras_count")

    assert soc.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert nfc.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert baro.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert cam.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE

    # Now register a conflict strictly on soc.core_count
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-soc-only",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="SoC dispute only",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    rep2 = SpecificationComparator(cat).compare(
        res,
        {
            "cpu_cores": 8,
            "feature_nfc": 1,
            "feature_barometer": 1,
            "rear_camera_count": 3,
        },
    )
    # SoC is blocked, but NFC, barometer, camera MUST remain CONSISTENT!
    soc2 = next(i for i in rep2.items if i.property_path == "soc.core_count")
    nfc2 = next(i for i in rep2.items if i.property_path == "sensors.nfc_present")
    baro2 = next(i for i in rep2.items if i.property_path == "sensors.barometer_present")
    cam2 = next(i for i in rep2.items if i.property_path == "camera.rear_cameras_count")

    assert soc2.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert nfc2.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert baro2.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert cam2.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rep2.consistent_count == 3


# Group G: Existing Diagnostic Evidence Path
def test_diagnostic_evidence_adapter_cannot_bypass_barometer_and_nfc_conflicts() -> None:
    """Group G1: Applicable sensor conflicts cannot be bypassed through DiagnosticEvidenceAdapter."""
    from tests.test_phase8e_checkpoint2b import fabricated_result
    from vector_agent.reference.seed import build_seed_catalog

    catalog = build_seed_catalog(test_only=True)
    # Register conflict on pixel-7-pro model for sensors.barometer
    catalog.register_conflict(
        ReferenceConflict(
            conflict_id="conf-pixel-barometer",
            target_entity_type="model",
            target_entity_id="pixel-7-pro",
            field_path="specifications.sensors.barometer",
            source_a_id="google-pixel7pro-specs",
            source_a_value="true",
            source_b_id="fcc-pixel7pro-ge2ae",
            source_b_value="false",
            conflict_notes="Barometer dispute on Pixel 7 Pro",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    _, owner, result = fabricated_result(
        metrics=[
            {"name": "feature_nfc", "value": 1, "unit": "boolean"},
            {"name": "feature_barometer", "value": 1, "unit": "boolean"},
        ]
    )
    adapter = DiagnosticEvidenceAdapter(catalog)
    compared = adapter.compare(result, owner=owner)

    baro_item = next(
        i for i in compared.report.items if i.property_path == "sensors.barometer_present"
    )
    assert baro_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    assert baro_item.reference_value is None
    assert "disputed" in (baro_item.reason or "").lower()

    # Invariants: unverified caller observations, unknown authenticity, identity ambiguity intact
    assert "level 3" in compared.report.honesty_disclaimer.lower()
    assert compared.authenticity.value == "UNKNOWN"


def test_sibling_collection_element_conflict_does_not_block_unrelated_collection() -> None:
    """Targeted kill for M03: camera.front_cameras[0] must not block camera.rear_cameras_count."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-front-cam-elem",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="camera.front_cameras[0]",
            source_a_id="src-a",
            source_a_value="12mp",
            source_b_id="src-b",
            source_b_value="16mp",
            conflict_notes="Front camera element dispute",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"rear_camera_count": 3})
    rear_item = next(i for i in rep.items if i.property_path == "camera.rear_cameras_count")

    # Front camera element dispute must be recognized as belonging to front_cameras sibling,
    # and therefore must NOT contaminate rear_cameras_count
    assert rear_item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rear_item.reference_value == 3


def test_prefix_normalization_prevents_cross_domain_contamination() -> None:
    """Targeted kill for M04: specifications.soc.core_count must not contaminate sensors.nfc_present."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-prefix-spec",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="specifications.soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="SoC core count dispute with specifications. prefix",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8, "feature_nfc": 1})
    soc_item = next(i for i in rep.items if i.property_path == "soc.core_count")
    nfc_item = next(i for i in rep.items if i.property_path == "sensors.nfc_present")

    # SoC is blocked
    assert soc_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    # NFC is in a different domain (sensors) and must NOT be contaminated by specifications.soc prefix
    assert nfc_item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rep.consistent_count == 1


def test_base_specifications_prefix_normalization_prevents_cross_domain_contamination() -> None:
    """Targeted kill for M05: base_specifications.soc.core_count must not contaminate sensors.nfc_present."""
    cat, model, variant = create_base_synthetic_catalog()
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="conf-prefix-base",
            target_entity_type="variant",
            target_entity_id="synth-alpha-global",
            field_path="base_specifications.soc.core_count",
            source_a_id="src-a",
            source_a_value="8",
            source_b_id="src-b",
            source_b_value="6",
            conflict_notes="SoC core count dispute with base_specifications. prefix",
            recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    res = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=model,
        resolved_variant=variant,
        reason="Match",
    )
    rep = SpecificationComparator(cat).compare(res, {"cpu_cores": 8, "feature_nfc": 1})
    soc_item = next(i for i in rep.items if i.property_path == "soc.core_count")
    nfc_item = next(i for i in rep.items if i.property_path == "sensors.nfc_present")

    # SoC is blocked
    assert soc_item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
    # NFC is in a different domain (sensors) and must NOT be contaminated by base_specifications.soc prefix
    assert nfc_item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
    assert rep.consistent_count == 1
