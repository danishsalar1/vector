"""Checkpoint regressions: synthetic inputs, never physical qualification."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from tests.test_phase8c_cross_language import run_contract
from vector_agent.models.probe_diagnostics import DiagnosticMetric
from vector_agent.models.reference import (
    ComparisonOutcome as O,
)
from vector_agent.models.reference import (
    DeviceResolutionResult,
    ReferenceSource,
    ResolutionStatus,
)
from vector_agent.reference.catalog import ReferenceCatalog
from vector_agent.reference.comparator import SpecificationComparator
from vector_agent.reference.importer import import_catalog_payload
from vector_agent.reference.performance import PerformanceReferenceManager
from vector_agent.reference.seed import (
    build_seed_catalog,
    build_seed_payload,
    get_coverage_inventory,
)


def compare(observed: dict[str, Any], catalog: ReferenceCatalog | None = None) -> dict[str, Any]:
    cat = catalog or build_seed_catalog(test_only=True)
    variant = cat.get_variant("pixel-7-pro-us-ge2ae")
    assert variant is not None
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.EXACT_MATCH,
        resolved_model=cat.get_model(variant.model_id),
        resolved_variant=variant,
        reason="Synthetic test selection; not a connected device identity.",
    )
    return {
        i.property_path: i for i in SpecificationComparator(cat).compare(resolution, observed).items
    }


@pytest.mark.parametrize("charge", [2463000, 4926000, 4926, 0, -1, 3000])
def test_pg01_remaining_charge_never_compares_as_rated_capacity(charge: int) -> None:
    item = compare({"charge_counter": charge})["battery.rated_capacity_mah"]
    assert item.outcome == O.NOT_COMPARABLE
    assert item.observed_value is None  # No rated-capacity measurement exists.
    assert item.reference_value == 4926
    assert "remaining charge" in item.reason


@pytest.mark.parametrize(
    "observed", [{}, {"battery_capacity_design": 4926}, {"rated_capacity": 4926}]
)
def test_pg01_missing_or_nonemitted_capacity_is_not_manufactured(observed: dict[str, Any]) -> None:
    item = compare(observed)["battery.rated_capacity_mah"]
    assert item.outcome in {O.INSUFFICIENT_EVIDENCE, O.NOT_COMPARABLE}
    assert item.observed_value is None


@pytest.mark.parametrize(
    "name,unit", [("charge_counter", "mAh"), ("ram_total", "GiB"), ("width", "fake")]
)
def test_fake_units_are_rejected_by_real_probe_contract(name: str, unit: str) -> None:
    with pytest.raises(ValidationError):
        DiagnosticMetric(name=name, value=4926, unit=unit)


@pytest.mark.parametrize("unit", ["mAh", "fake", "uAh"])
def test_pg01_even_unit_bearing_remaining_charge_cannot_match_rated_capacity(unit: str) -> None:
    item = compare({"charge_counter": {"value": 4926, "unit": unit}})["battery.rated_capacity_mah"]
    assert item.outcome == O.NOT_COMPARABLE
    assert item.observed_value is None


@pytest.mark.parametrize("width,height", [(1080, 2340), (1440, 3120), (3120, 1440)])
def test_pg09_active_resolution_is_not_native_panel_evidence(width: int, height: int) -> None:
    item = compare({"width": width, "height": height})["display.resolution"]
    assert item.outcome == O.NOT_COMPARABLE


@pytest.mark.parametrize("rate", [10, 60, 73, 120, 144])
def test_pg09_active_rate_cannot_prove_advertised_maximum(rate: int) -> None:
    assert compare({"refresh_rate": rate})["display.refresh_rate_hz"].outcome == O.NOT_COMPARABLE


@pytest.mark.parametrize(
    "modes",
    [
        {"mode_count": 1, "mode0_width": 1440, "mode0_height": 3120, "mode0_rate": 120},
        {"mode_count": 2, "mode0_width": 1440, "mode0_height": 3120, "mode0_rate": 120},
        {"mode_count": 1, "mode0_width": -1, "mode0_height": 3120, "mode0_rate": "fake"},
    ],
)
def test_pg09_mode_records_do_not_identify_native_panel_or_invent_missing_modes(
    modes: dict[str, Any],
) -> None:
    items = compare(modes)
    assert items["display.resolution"].outcome == O.NOT_COMPARABLE
    assert items["display.refresh_rate_hz"].outcome == O.NOT_COMPARABLE


def test_pg09_no_display_observations_remain_missing() -> None:
    items = compare({})
    assert items["display.resolution"].outcome == O.INSUFFICIENT_EVIDENCE
    assert items["display.refresh_rate_hz"].outcome == O.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("gib", [9.7, 10, 11.2, 12, 16])
def test_pg10_os_visible_ram_has_no_installed_memory_tolerance(gib: float) -> None:
    item = compare({"ram_total": int(gib * 1024**3)})["memory.ram_total_bytes"]
    assert item.outcome == O.NOT_COMPARABLE
    assert item.observed_value is None


@pytest.mark.parametrize("observed", [{}, {"ram_available": 12 * 1024**3}, {"ram_total": None}])
def test_pg10_free_or_missing_memory_is_not_installed_memory(observed: dict[str, Any]) -> None:
    item = compare(observed)["memory.ram_total_bytes"]
    assert item.outcome == O.INSUFFICIENT_EVIDENCE
    assert item.observed_value is None


@pytest.mark.parametrize("unit", ["bytes", "MiB", "GiB", "fake"])
def test_pg10_unit_labels_cannot_convert_os_ram_into_physical_ram(unit: str) -> None:
    item = compare({"ram_total": {"value": 12, "unit": unit}})["memory.ram_total_bytes"]
    assert item.outcome == O.NOT_COMPARABLE


@pytest.mark.parametrize("toggle", [False, True, 0, 1])
def test_pg11_nfc_toggle_alone_is_not_hardware_evidence(toggle: bool | int) -> None:
    assert (
        compare({"nfc_enabled": toggle})["sensors.nfc_present"].outcome == O.INSUFFICIENT_EVIDENCE
    )


@pytest.mark.parametrize(
    "feature,toggle,outcome",
    [
        (1, 0, O.CONSISTENT_WITH_REFERENCE),
        (0, 1, O.DIFFERS_FROM_REFERENCE),
        (False, False, O.DIFFERS_FROM_REFERENCE),
    ],
)
def test_pg11_nfc_feature_declaration_is_independent_of_toggle(
    feature: bool | int, toggle: int | bool, outcome: O
) -> None:
    item = compare({"feature_nfc": feature, "nfc_enabled": toggle})["sensors.nfc_present"]
    assert item.outcome == outcome
    assert "declaration" in item.reason
    assert "function" in " ".join(item.limitations)


@pytest.mark.parametrize("feature", ["false", "true", 2, -1, {}, None])
def test_pg11_malformed_nfc_feature_never_becomes_truthy_presence(feature: Any) -> None:
    assert (
        compare({"feature_nfc": feature})["sensors.nfc_present"].outcome == O.INSUFFICIENT_EVIDENCE
    )


def test_pg05_production_has_no_invented_performance_distribution() -> None:
    cat = build_seed_catalog(test_only=True)
    assert build_seed_payload()["performance_metrics"] == []
    assert cat.summary()["performance_metrics_count"] == 0
    manager = PerformanceReferenceManager(cat)
    assert manager.get_metrics_for_model("pixel-7-pro") == ()
    for metric in ("geekbench-single-core-tensor-g2", "unknown-metric"):
        result = manager.evaluate_metric(metric, 1420.0, "pixel-7-pro")
        assert result.outcome == O.REFERENCE_UNAVAILABLE
        assert result.source_id is None


def test_pg06_seed_does_not_invent_retrieval_publication_or_revision() -> None:
    for source in build_seed_catalog(test_only=True).all_sources():
        assert source.retrieved_at is None, source.source_id
        assert source.publication_date is None, source.source_id
        assert source.version_or_revision is None, source.source_id


@pytest.mark.parametrize("explicit_null", [False, True])
def test_pg06_unknown_metadata_imports_and_roundtrips(explicit_null: bool) -> None:
    data = dict(build_seed_payload()["sources"][0])
    for key in ("retrieved_at", "publication_date", "version_or_revision"):
        data.pop(key, None)
        if explicit_null:
            data[key] = None
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload({"schema_version": "vector-catalog-v1", "sources": [data]}, cat)
    source = cat.all_sources()[0]
    roundtrip = ReferenceSource.model_validate_json(source.model_dump_json())
    assert roundtrip.retrieved_at is None
    assert roundtrip.publication_date is None
    assert roundtrip.version_or_revision is None


def test_pg06_explicit_metadata_is_preserved_without_claiming_verification() -> None:
    # Fabricated metadata tests serialization only; no real retrieval is asserted.
    data = dict(build_seed_payload()["sources"][0])
    data.update(
        retrieved_at="2024-02-03T04:05:06Z",
        publication_date="2024-01-01",
        version_or_revision="document-revision-2",
    )
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload({"schema_version": "vector-catalog-v1", "sources": [data]}, cat)
    source = ReferenceSource.model_validate_json(cat.all_sources()[0].model_dump_json())
    assert source.retrieved_at == datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert str(source.publication_date) == "2024-01-01"
    assert source.version_or_revision == "document-revision-2"


@pytest.mark.parametrize("stamp", ["2024-01-01T00:00:00", "2024-01-01T01:00:00+01:00", "fake", 0])
def test_pg06_optional_metadata_still_rejects_invalid_timestamps(stamp: Any) -> None:
    data = dict(build_seed_payload()["sources"][0], retrieved_at=stamp)
    with pytest.raises(ValidationError):
        ReferenceSource.model_validate(data)


def test_pg06_synthetic_flag_cannot_be_removed_to_claim_real_source() -> None:
    data = next(s for s in build_seed_payload()["sources"] if s["is_synthetic"])
    with pytest.raises(ValidationError):
        ReferenceSource.model_validate(dict(data, is_synthetic=False))


def test_pg06_unverified_seed_coverage_is_not_verified_coverage() -> None:
    inv = get_coverage_inventory()
    assert inv["verified_devices_count"] == 0
    assert inv["verified_device_models"] == []
    assert build_seed_catalog(test_only=True).summary()["verified_sources_count"] == 0


@pytest.mark.parametrize(
    "section,field,value,path",
    [
        ("battery", "rated_capacity_mah", 4500, "battery.rated_capacity_mah"),
        ("memory_storage", "ram_options_bytes", [8 * 1024**3], "memory.ram_total_bytes"),
        ("display", "resolution_width", 1080, "display.resolution"),
        ("display", "refresh_rate_max_hz", 144, "display.refresh_rate_hz"),
        ("sensors", "nfc", False, "sensors.nfc_present"),
        ("sensors", "barometer", False, "sensors.barometer_present"),
        ("soc", "core_count", 4, "soc.core_count"),
    ],
)
@pytest.mark.parametrize("missing", [False, True])
def test_pg04_differing_or_missing_candidate_property_cannot_use_first_variant(
    section: str, field: str, value: Any, path: str, missing: bool
) -> None:
    payload = build_seed_payload()
    variant = next(v for v in payload["variants"] if v["variant_id"] == "pixel-7-pro-us-ge2ae")
    if missing:
        variant["specifications"][section] = None
    else:
        variant["specifications"][section][field] = value
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Synthetic ambiguous test",
    )
    report = SpecificationComparator(cat).compare(
        resolution,
        {
            "charge_counter": 4926000,
            "ram_total": 12 * 1024**3,
            "width": 1440,
            "height": 3120,
            "refresh_rate": 120,
            "feature_nfc": True,
            "feature_barometer": True,
            "cpu_cores": 8,
        },
    )
    item = next(i for i in report.items if i.property_path == path)
    assert item.outcome == O.VARIANT_AMBIGUOUS
    assert item.reference_value is None
    assert item.applicable_variant_id is None


def test_pg11_optional_variant_nfc_absence_compares_only_declaration() -> None:
    payload = build_seed_payload()
    variant = next(v for v in payload["variants"] if v["variant_id"] == "pixel-7-pro-us-ge2ae")
    variant["specifications"]["sensors"]["nfc"] = False  # Explicit synthetic variant scenario.
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    assert (
        compare({"feature_nfc": 0, "nfc_enabled": 0}, cat)["sensors.nfc_present"].outcome
        == O.CONSISTENT_WITH_REFERENCE
    )


def test_java_produced_evidence_preserved_and_display_not_misclassified() -> None:
    # Real Java-produced fixtures through production transport/lifecycle; no device qualification.
    from tests.cross_language_contract import contract

    names = [
        s["name"]
        for s in contract()["scenarios"]
        if any(e.get("diagnostic_id") == "display" for e in s["exchanges"])
    ]
    assert names
    found = False
    for name in names:
        for report, result in run_contract(name).values():
            if report is None or report.diagnostic_id != "display" or result is None:
                continue
            before = result.model_dump_json()
            # Test-only projection; production evidence adapter is explicitly deferred.
            observed = {e.source_name: e.normalized_value for e in result.evidence}
            if "width" not in observed:
                continue
            found = True
            assert {e.source_name: e.unit for e in result.evidence}["width"] == "pixels"
            assert compare(observed)["display.resolution"].outcome == O.NOT_COMPARABLE
            assert result.model_dump_json() == before
            assert all(e.metadata["authenticity"] == "UNKNOWN" for e in result.evidence)
    assert found


def test_java_battery_evidence_keeps_original_charge_unit_and_unknown_authenticity() -> None:
    found = False
    for report, result in run_contract("sensors_battery").values():
        if report is None or result is None or report.diagnostic_id != "battery":
            continue
        metrics = {metric.name: metric for metric in report.metrics}
        before = result.model_dump_json()
        observations = {e.source_name: e.normalized_value for e in result.evidence}
        items = compare(observations)
        assert items["battery.rated_capacity_mah"].outcome in {
            O.NOT_COMPARABLE,
            O.INSUFFICIENT_EVIDENCE,
        }
        for evidence in result.evidence:
            if evidence.source_name == "charge_counter":
                found = True
                assert evidence.unit == metrics["charge_counter"].unit == "uAh"
                assert evidence.normalized_value == metrics["charge_counter"].value
                assert evidence.metadata["authenticity"] == "UNKNOWN"
        assert result.model_dump_json() == before
    assert found


def test_invariant_nfc_can_compare_when_other_variant_properties_differ() -> None:
    payload = build_seed_payload()
    variant = next(v for v in payload["variants"] if v["variant_id"] == "pixel-7-pro-us-ge2ae")
    variant["specifications"]["sensors"]["barometer"] = False
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    resolution = DeviceResolutionResult(
        status=ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
        resolved_model=cat.get_model("pixel-7-pro"),
        reason="Synthetic ambiguous test",
    )
    report = SpecificationComparator(cat).compare(
        resolution, {"feature_nfc": 1, "feature_barometer": 1}
    )
    items = {i.property_path: i for i in report.items}
    assert items["sensors.barometer_present"].outcome == O.VARIANT_AMBIGUOUS
    assert items["sensors.nfc_present"].outcome == O.CONSISTENT_WITH_REFERENCE
    assert items["sensors.nfc_present"].applicable_variant_id is None


def test_incomparable_inputs_do_not_claim_authenticity_or_modify_diagnostics() -> None:
    items = compare(
        {
            "charge_counter": 4926000,
            "ram_total": 12 * 1024**3,
            "width": 1440,
            "height": 3120,
            "refresh_rate": 120,
        }
    )
    for path in (
        "battery.rated_capacity_mah",
        "memory.ram_total_bytes",
        "display.resolution",
        "display.refresh_rate_hz",
    ):
        item = items[path]
        assert item.outcome == O.NOT_COMPARABLE
        assert "authenticity" not in item.model_dump()
        assert "trust_score" not in item.model_dump()


def test_missing_numeric_observations_have_no_supported_claims() -> None:
    items = compare({})
    assert all(
        i.outcome not in {O.CONSISTENT_WITH_REFERENCE, O.DIFFERS_FROM_REFERENCE}
        for i in items.values()
    )
    assert all(i.observed_value is None for i in items.values())
