"""Production defaults and explicit fixture-scope recovery regressions."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from vector_agent.models.device import DeviceIdentity
from vector_agent.models.reference import (
    ComparisonOutcome as O,
)
from vector_agent.models.reference import (
    DeviceResolutionResult,
    ReferenceClaimVerification,
    ReferenceConflict,
    ReferenceSource,
    ResolutionStatus,
    SourceClassification,
    SpecificationComparisonReport,
)
from vector_agent.reference.catalog import CatalogIntegrityError, ReferenceCatalog
from vector_agent.reference.comparator import SpecificationComparator
from vector_agent.reference.importer import CatalogImportError, import_catalog_payload
from vector_agent.reference.resolver import DeviceResolver
from vector_agent.reference.seed import build_seed_catalog, build_seed_payload


def resolution(cat: ReferenceCatalog) -> DeviceResolutionResult:
    return DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=cat.get_model("pixel-7-pro"),
        resolved_variant=cat.get_variant("pixel-7-pro-us-ge2ae"),
        reason="Fixture resolution",
    )


def items(cat: ReferenceCatalog, observed: dict[str, object]) -> dict[str, object]:
    return {
        i.property_path: i
        for i in SpecificationComparator(cat).compare(resolution(cat), observed).items
    }


@pytest.mark.parametrize(
    "entity,field",
    [
        ("manufacturers", "source_id"),
        ("models", "source_ids"),
        ("variants", "source_ids"),
        ("variants", "nested"),
        ("models", "nested"),
    ],
)
def test_unknown_citations_abort_entire_import(entity: str, field: str) -> None:
    payload = build_seed_payload()
    record = payload[entity][0]
    if field == "nested":
        if entity == "models":
            record["base_specifications"] = {"source_ids": ["no-such-source"]}
        else:
            record["specifications"]["source_ids"] = ["no-such-source"]
    else:
        record[field] = "no-such-source" if field == "source_id" else ["no-such-source"]
    cat = ReferenceCatalog(test_only=True)
    with pytest.raises(CatalogImportError, match="unknown source"):
        import_catalog_payload(payload, cat)
    assert cat.all_sources() == () and cat.all_models() == ()


@pytest.mark.parametrize(
    "change",
    [
        {"target_entity_id": "missing"},
        {"source_a_id": "missing"},
        {"field_path": " "},
        {"target_entity_type": "component"},
    ],
)
def test_invalid_conflict_rejected(change: dict[str, str]) -> None:
    cat = build_seed_catalog()
    data = {
        "conflict_id": "fixture-conflict",
        "target_entity_type": "model",
        "target_entity_id": "pixel-7-pro",
        "field_path": "unknown.future.path",
        "source_a_id": "google-pixel7pro-specs",
        "source_a_value": "yes",
        "source_b_id": "fcc-pixel7pro-ge2ae",
        "source_b_value": "no",
        "conflict_notes": "Fixture",
        "recorded_at": datetime.now(UTC),
    }
    data.update(change)
    with pytest.raises(CatalogIntegrityError):
        cat.register_conflict(ReferenceConflict(**data))
    assert cat.all_conflicts() == ()


def test_synthetic_model_requires_explicit_test_scope() -> None:
    prod, test = build_seed_catalog(), build_seed_catalog(test_only=True)
    assert prod.get_model("synthetic-model-x") is None
    assert test.get_model("synthetic-model-x").is_synthetic
    assert (
        DeviceResolver(prod).resolve(DeviceIdentity(model="Synthetic Model X")).status
        != ResolutionStatus.EXACT_MATCH
    )
    with pytest.raises(CatalogImportError, match="Synthetic"):
        import_catalog_payload(build_seed_payload(), ReferenceCatalog())


@pytest.mark.parametrize("field", ["source_ids", "nested"])
def test_synthetic_source_cannot_support_real_model(field: str) -> None:
    payload = build_seed_payload()
    v = payload["variants"][0]
    (v["specifications"] if field == "nested" else v)["source_ids"] = ["synthetic-test-source"]
    with pytest.raises(CatalogImportError, match="Synthetic citation"):
        import_catalog_payload(payload, ReferenceCatalog(test_only=True))


def test_unverified_production_seed_cannot_produce_definitive_comparisons() -> None:
    report = SpecificationComparator(build_seed_catalog()).compare(
        resolution(build_seed_catalog()), {"cpu_cores": 8, "feature_nfc": 1}
    )
    assert report.consistent_count == report.differs_count == 0
    assert all(i.outcome == O.REFERENCE_UNAVAILABLE for i in report.items)


def test_verified_exact_claim_does_not_authorize_other_properties_or_values() -> None:
    cat = build_seed_catalog()
    src = cat.get_source("google-pixel7pro-specs")
    claim = ReferenceClaimVerification(
        entity_id="pixel-7-pro-us-ge2ae",
        property_path="sensors.nfc_present",
        reference_value_json="true",
        verified_at=datetime.now(UTC),
        verification_notes="Fabricated unit-test verification; not an OEM audit.",
    )
    # Fresh source+catalog import represents a curator-controlled revision.
    payload = {
        "schema_version": "vector-catalog-v1",
        "sources": [s.model_dump(mode="json") for s in cat.all_sources()],
        "manufacturers": [m.model_dump(mode="json") for m in cat.all_manufacturers()],
        "models": [m.model_dump(mode="json") for m in cat.all_models()],
        "variants": [v.model_dump(mode="json") for v in cat.all_variants()],
    }
    for s in payload["sources"]:
        if s["source_id"] == src.source_id:
            s["verified_claims"] = [claim.model_dump(mode="json")]
    for variant in payload["variants"]:
        if variant["variant_id"] == "pixel-7-pro-us-ge2ae":
            variant["specifications"]["source_ids"] = [src.source_id]
    verified = ReferenceCatalog()
    import_catalog_payload(payload, verified, curator_authorized=True)
    result = items(verified, {"feature_nfc": 1, "feature_barometer": 1, "cpu_cores": 8})
    assert result["sensors.nfc_present"].outcome == O.CONSISTENT_WITH_REFERENCE
    assert result["sensors.barometer_present"].outcome == O.REFERENCE_UNAVAILABLE
    assert result["soc.core_count"].outcome == O.REFERENCE_UNAVAILABLE
    assert result["sensors.nfc_present"].source_ids == ("google-pixel7pro-specs",)


@pytest.mark.parametrize("bad", ["missing", "synthetic-test-source"])
def test_corrupt_nested_citations_are_not_trusted(bad: str) -> None:
    cat = build_seed_catalog(test_only=True)
    v = cat.get_variant("pixel-7-pro-us-ge2ae")
    corrupt = v.model_copy(
        update={"specifications": v.specifications.model_copy(update={"source_ids": (bad,)})}
    )
    cat._variants[v.variant_id] = corrupt
    result = items(cat, {"cpu_cores": 8})["soc.core_count"]
    assert result.outcome == O.REFERENCE_UNAVAILABLE
    assert result.reference_value is None
    assert "missing" not in result.source_ids


@pytest.mark.parametrize(
    "key,value",
    [
        ("cpu_cores", 8.7),
        ("cpu_cores", True),
        ("cpu_cores", -1),
        ("cpu_cores", "8"),
        ("cpu_cores", float("nan")),
        ("cpu_cores", float("inf")),
        ("cpu_cores", {"value": 8, "unit": "Hz"}),
        ("cpu_cores", None),
        ("feature_5g_mmwave", "false"),
        ("feature_nfc", "false"),
        ("rear_camera_count", 3.7),
    ],
)
def test_invalid_flat_observations_never_get_definitive_verdict(key: str, value: object) -> None:
    cat = build_seed_catalog(test_only=True)
    report = SpecificationComparator(cat).compare(resolution(cat), {key: value})
    assert report.consistent_count == report.differs_count == 0
    assert "unverified" in report.honesty_disclaimer


@pytest.mark.parametrize("path", ["network_configuration", "sku_numbers", "region_market"])
def test_metadata_conflicts_respect_hardware_and_identity_dependencies(path: str) -> None:
    cat = build_seed_catalog(test_only=True)
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="metadata-conflict",
            target_entity_type="model",
            target_entity_id="pixel-7-pro",
            field_path=path,
            source_a_id="google-pixel7pro-specs",
            source_a_value="a",
            source_b_id="fcc-pixel7pro-ge2ae",
            source_b_value="b",
            conflict_notes="Fixture",
            recorded_at=datetime.now(UTC),
        )
    )
    result = items(cat, {"feature_nfc": 1, "feature_5g_mmwave": 1})
    assert result["sensors.nfc_present"].outcome == (
        O.CONSISTENT_WITH_REFERENCE if path == "network_configuration" else O.REFERENCE_UNAVAILABLE
    )
    if path == "network_configuration":
        assert result["network.5g_mmwave_supported"].outcome == O.REFERENCE_UNAVAILABLE


def test_counts_reconstruct_report_and_empty_report() -> None:
    cat = build_seed_catalog(test_only=True)
    report = SpecificationComparator(cat).compare(
        resolution(cat), {"width": 1440, "height": 3120, "cpu_cores": 4, "feature_nfc": 1}
    )
    for r in (
        report,
        SpecificationComparisonReport(
            report_id=str(uuid4()),
            device_id="fixture",
            resolution=resolution(cat),
            evaluated_at=datetime.now(UTC),
        ),
    ):
        assert (
            r.total_items
            == len(r.items)
            == (
                r.consistent_count
                + r.differs_count
                + r.insufficient_evidence_count
                + r.reference_unavailable_count
                + r.ambiguous_count
                + r.not_comparable_count
            )
        )
        assert (
            SpecificationComparisonReport.model_validate_json(r.model_dump_json()).model_dump_json()
            == r.model_dump_json()
        )


def test_concurrent_imports_and_registration_preserve_all_accepted_updates() -> None:
    cat = ReferenceCatalog()
    barrier = threading.Barrier(8)

    def register(i: int) -> None:
        source = ReferenceSource(
            source_id=f"fixture-{i}",
            title="Fixture",
            publisher="Fixture",
            url_or_document_id="urn:test",
            source_classification=SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE,
        )
        barrier.wait(timeout=5)
        if i % 2:
            cat.register_source(source)
        else:
            import_catalog_payload(
                {
                    "schema_version": "vector-catalog-v1",
                    "sources": [source.model_dump(mode="json")],
                },
                cat,
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(register, range(8)))
    assert {s.source_id for s in cat.all_sources()} == {f"fixture-{i}" for i in range(8)}
    before = cat.snapshot()
    src = cat.all_sources()[0]
    with pytest.raises(CatalogIntegrityError):
        cat.register_source(src.model_copy(update={"title": "Conflicting duplicate"}))
    assert cat.all_sources() == before.all_sources()


def test_snapshot_detaches_mutable_component_properties() -> None:
    cat = build_seed_catalog()
    snap = cat.snapshot()
    original = cat._models["pixel-7-pro"].supported_component_alternatives[0]
    original.supported_properties["fixture"] = 1
    assert (
        "fixture"
        not in snap.get_model("pixel-7-pro")
        .supported_component_alternatives[0]
        .supported_properties
    )


def test_import_transaction_excludes_competitor_during_staging() -> None:
    from unittest.mock import patch

    cat = ReferenceCatalog()
    source = ReferenceSource(
        source_id="first",
        title="Fixture",
        publisher="Fixture",
        url_or_document_id="urn:test",
        source_classification=SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE,
    )
    second = source.model_copy(update={"source_id": "second"})
    original = ReferenceCatalog.register_source
    attempted = threading.Event()
    futures = []

    def contender() -> None:
        acquired = cat._lock.acquire(blocking=False)
        if acquired:
            cat._lock.release()
        attempted.set()
        assert not acquired, (
            "Import released its transaction lock while staged changes were uncommitted"
        )
        import_catalog_payload(
            {"schema_version": "vector-catalog-v1", "sources": [second.model_dump(mode="json")]},
            cat,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:

        def intercept(staging: ReferenceCatalog, incoming: ReferenceSource) -> None:
            if incoming.source_id == "first" and not futures:
                futures.append(pool.submit(contender))
                assert attempted.wait(5)
            original(staging, incoming)

        with patch.object(ReferenceCatalog, "register_source", intercept):
            import_catalog_payload(
                {
                    "schema_version": "vector-catalog-v1",
                    "sources": [source.model_dump(mode="json")],
                },
                cat,
            )
            futures[0].result(timeout=5)
    assert {s.source_id for s in cat.all_sources()} == {"first", "second"}


def test_candidate_consensus_preserves_all_sources_and_ambiguity() -> None:
    cat = build_seed_catalog(test_only=True)
    resolved = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Fixture ambiguity",
    )
    report = SpecificationComparator(cat).compare(
        resolved, {"cpu_cores": 8, "rear_camera_count": 3}
    )
    for path in ("soc.core_count", "camera.rear_cameras_count"):
        item = next(i for i in report.items if i.property_path == path)
        assert item.outcome == O.CONSISTENT_WITH_REFERENCE
        assert item.source_ids == ("fcc-pixel7pro-ge2ae", "google-pixel7pro-specs")
        assert item.applicable_variant_id is None
        assert any("consensus" in note for note in item.limitations)
    assert report.resolution.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT


@pytest.mark.parametrize("value", [10**1000, 0])
def test_invalid_cpu_counts_are_not_hardware_comparisons(value: int) -> None:
    report = SpecificationComparator(build_seed_catalog(test_only=True)).compare(
        resolution(build_seed_catalog(test_only=True)), {"cpu_cores": value}
    )
    assert report.consistent_count == report.differs_count == 0


def test_mixed_model_variant_resolution_cannot_compare() -> None:
    cat = build_seed_catalog(test_only=True)
    mismatch = resolution(cat).model_copy(
        update={"resolved_model": cat.get_model("galaxy-s23-ultra")}
    )
    # Use an actually different registered model, not a missing model placeholder.
    assert mismatch.resolved_model is not None
    report = SpecificationComparator(cat).compare(mismatch, {"cpu_cores": 8})
    assert report.consistent_count == report.differs_count == 0
    assert report.reference_unavailable_count == 1


def test_candidate_order_does_not_change_reference_sources() -> None:
    from unittest.mock import patch

    cat = build_seed_catalog(test_only=True)
    resolved = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Fixture ambiguity",
    )
    comp = SpecificationComparator(cat)
    before = comp.compare(resolved, {"cpu_cores": 8, "rear_camera_count": 3})
    original = ReferenceCatalog.find_variants_for_model
    with patch.object(
        ReferenceCatalog,
        "find_variants_for_model",
        lambda self, mid: tuple(reversed(original(self, mid))),
    ):
        after = comp.compare(resolved, {"cpu_cores": 8, "rear_camera_count": 3})
    assert before.items == after.items


def test_invalid_import_section_is_rejected_without_changes() -> None:
    cat = ReferenceCatalog()
    with pytest.raises(CatalogImportError, match="arrays"):
        import_catalog_payload({"schema_version": "vector-catalog-v1", "models": None}, cat)
    assert cat.all_models() == () and cat.all_sources() == ()


def test_performance_baseline_cannot_bypass_source_authority() -> None:
    from vector_agent.models.reference import PerformanceMetricReference
    from vector_agent.reference.performance import PerformanceReferenceManager

    cat = build_seed_catalog()
    metric = PerformanceMetricReference(
        metric_id="fixture-score",
        metric_name="Fixture score",
        test_conditions="Fixture",
        applicable_model_ids=("pixel-7-pro",),
        measurement_unit="points",
        test_methodology="Fabricated test only",
        reference_min=1.0,
        reference_max=2.0,
        source_id="google-pixel7pro-specs",
    )
    cat.register_performance_metric(metric)
    report = PerformanceReferenceManager(cat).evaluate_metric("fixture-score", 1.5, "pixel-7-pro")
    assert report.outcome == O.REFERENCE_UNAVAILABLE
    synthetic = build_seed_catalog(test_only=True).get_source("synthetic-test-source")
    with pytest.raises(CatalogIntegrityError, match="test-only"):
        cat.register_source(synthetic)
    # Simulate corrupted state that bypassed registration: the metric guard must still hold.
    cat._sources[synthetic.source_id] = synthetic
    with pytest.raises(CatalogIntegrityError, match="Synthetic"):
        cat.register_performance_metric(
            metric.model_copy(
                update={"metric_id": "synthetic-score", "source_id": synthetic.source_id}
            )
        )


def test_corrupt_parent_citation_cannot_authorize_comparison() -> None:
    cat = build_seed_catalog(test_only=True)
    model = cat.get_model("pixel-7-pro")
    cat._models[model.model_id] = model.model_copy(update={"source_ids": ("missing",)})
    report = SpecificationComparator(cat).compare(resolution(cat), {"cpu_cores": 8})
    assert report.consistent_count == report.differs_count == 0
    assert all(i.reference_value is None for i in report.items)


def test_equal_network_candidates_produce_consensus_item_without_exact_variant() -> None:
    payload = build_seed_payload()
    for variant in payload["variants"]:
        if variant["model_id"] == "pixel-7-pro":
            variant["network_configuration"] = "5G Sub-6 + mmWave"
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    resolved = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Fixture ambiguity",
    )
    report = SpecificationComparator(cat).compare(resolved, {"feature_5g_mmwave": True})
    item = next((i for i in report.items if i.property_path == "network.5g_mmwave_supported"), None)
    assert item is not None
    assert item.outcome == O.CONSISTENT_WITH_REFERENCE
    assert item.applicable_variant_id is None


def test_unknown_network_description_does_not_assert_mmwave_absence() -> None:
    payload = build_seed_payload()
    payload["variants"][0]["network_configuration"] = "Unknown carrier configuration"
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    item = items(cat, {"feature_5g_mmwave": False})["network.5g_mmwave_supported"]
    assert item.outcome == O.REFERENCE_UNAVAILABLE
    assert item.reference_value is None


def test_disputed_sku_cannot_select_an_uncontested_hardware_reference() -> None:
    payload = build_seed_payload()
    payload["variants"][0]["sku_numbers"] = ["CLAIMED-SKU"]
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    cat.register_conflict(
        ReferenceConflict(
            conflict_id="sku-dispute",
            target_entity_type="variant",
            target_entity_id="pixel-7-pro-us-ge2ae",
            field_path="sku_numbers",
            source_a_id="google-pixel7pro-specs",
            source_a_value="CLAIMED-SKU",
            source_b_id="fcc-pixel7pro-ge2ae",
            source_b_value="OTHER-SKU",
            conflict_notes="Fixture identity ambiguity",
            recorded_at=datetime.now(UTC),
        )
    )
    resolved = DeviceResolver(cat).resolve(DeviceIdentity(model="CLAIMED-SKU"))
    report = SpecificationComparator(cat).compare(resolved, {"cpu_cores": 8})
    assert report.consistent_count == report.differs_count == 0


def test_ambiguous_variant_with_unspecified_network_preserves_network_item() -> None:
    cat = build_seed_catalog(test_only=True)
    resolved = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("synthetic-model-x"),
        reason="Ambiguous synthetic model variant.",
    )
    report = SpecificationComparator(cat).compare(resolved, {"feature_5g_mmwave": 1})
    item = next((i for i in report.items if i.property_path == "network.5g_mmwave_supported"), None)
    assert item is not None
    assert item.observed_value is True
    assert item.outcome == O.REFERENCE_UNAVAILABLE


def test_multiple_candidates_resolution_returns_reference_unavailable_report() -> None:
    cat = build_seed_catalog(test_only=True)
    resolved = DeviceResolutionResult(
        status=ResolutionStatus.MULTIPLE_CANDIDATES,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Multiple candidates matched.",
    )
    report = SpecificationComparator(cat).compare(resolved, {"cpu_cores": 8})
    assert report.consistent_count == report.differs_count == 0
    assert report.reference_unavailable_count == 1
    assert "MULTIPLE_CANDIDATES" in report.items[0].reason
