"""Final Phase 8E remediation: negative regressions for FR-01 through FR-09.

All data is fabricated. Production-mode catalogs (``ReferenceCatalog()``) require an
exact curator verification record; test-only catalogs waive it and carry labels.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from vector_agent.devices.android.bridge import _evaluate_battery_telemetry, _parse_battery_output
from vector_agent.models.device import DeviceIdentity, Platform
from vector_agent.models.reference import (
    CameraReferenceSpec,
    CameraSensorSpec,
    ComparisonOutcome,
    DeviceModelReference,
    DeviceSpecification,
    DeviceVariantReference,
    ManufacturerReference,
    PerformanceMetricReference,
    ReferenceClaimVerification,
    ReferenceSource,
    ResolutionStatus,
    SensorReferenceSpec,
    SocReferenceSpec,
    SourceClassification,
)
from vector_agent.reference.catalog import CatalogIntegrityError, ReferenceCatalog
from vector_agent.reference.comparator import SpecificationComparator
from vector_agent.reference.importer import CatalogImportError, import_catalog_payload
from vector_agent.reference.performance import PerformanceReferenceManager
from vector_agent.reference.resolver import DeviceResolver
from vector_agent.reference.seed import build_seed_catalog, build_seed_payload

Out = ComparisonOutcome
DEFINITIVE = {Out.CONSISTENT_WITH_REFERENCE, Out.DIFFERS_FROM_REFERENCE}
FULL = {
    "feature_nfc": 1,
    "feature_barometer": 1,
    "feature_5g_mmwave": 1,
    "cpu_cores": 8,
    "rear_camera_count": 3,
}


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def claim(entity: str, path: str, value: object) -> ReferenceClaimVerification:
    return ReferenceClaimVerification(
        entity_id=entity,
        property_path=path,
        reference_value_json=_json(value),
        verified_at=datetime.now(UTC),
        verification_notes="Fabricated unit-test verification; not an OEM audit.",
    )


def source(
    source_id: str = "src", claims: tuple[ReferenceClaimVerification, ...] = ()
) -> ReferenceSource:
    return ReferenceSource(
        source_id=source_id,
        title="Fixture",
        publisher="Fixture",
        url_or_document_id="https://example.invalid/doc",
        source_classification=SourceClassification.OEM_DOCUMENTATION,
        verified_claims=claims,
    )


def spec(spec_sources: tuple[str, ...] = ("src",), cores: int = 8) -> DeviceSpecification:
    return DeviceSpecification(
        soc=SocReferenceSpec(
            chip_maker="x", marketing_name="y", cpu_architecture="arm", core_count=cores
        ),
        sensors=SensorReferenceSpec(nfc=True, barometer=True),
        camera=CameraReferenceSpec(
            rear_cameras=tuple(CameraSensorSpec(role="main", resolution_mp=50.0) for _ in range(3))
        ),
        source_ids=spec_sources,
    )


def catalog(
    *,
    test_only: bool = False,
    claims: tuple[ReferenceClaimVerification, ...] = (),
    variants: tuple[tuple[str, str], ...] = (("v-a", "am-a"), ("v-b", "am-b")),
    spec_sources: tuple[str, ...] = ("src",),
    variant_sources: tuple[str, ...] = ("src",),
    network: str = "5G Sub-6 + mmWave",
) -> ReferenceCatalog:
    cat = ReferenceCatalog(test_only=test_only)
    cat.register_source(source(claims=claims))
    cat.register_manufacturer(
        ManufacturerReference(manufacturer_id="acme", canonical_name="Acme", source_id="src")
    )
    cat.register_model(
        DeviceModelReference(
            model_id="acme-one",
            manufacturer_id="acme",
            marketed_name="Acme One",
            model_family="Acme",
            known_model_codes=tuple(code for _, code in variants),
            source_ids=("src",),
        )
    )
    for variant_id, code in variants:
        cat.register_variant(
            DeviceVariantReference(
                variant_id=variant_id,
                model_id="acme-one",
                region_market=variant_id,
                model_codes=(code,),
                network_configuration=network,
                specifications=spec(spec_sources),
                source_ids=variant_sources,
            )
        )
    return cat


def identity(model: str | None = None, **kwargs: object) -> DeviceIdentity:
    kwargs.setdefault("platform", Platform.ANDROID)
    kwargs.setdefault("manufacturer", "Acme")
    return DeviceIdentity(model=model, **kwargs)  # type: ignore[arg-type]


def compare(cat: ReferenceCatalog, who: DeviceIdentity, observed: dict[str, object]):
    resolution = DeviceResolver(cat).resolve(who)
    report = SpecificationComparator(cat).compare(resolution, observed)
    return resolution, {i.property_path: i for i in report.items}, report


# --------------------------------------------------------------------------
# FR-01: six pinned guards (each found unpinned by the final audit's mutants)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reverse", [False, True])
def test_fr01_variants_sharing_a_code_never_resolve_exact(reverse: bool) -> None:
    cat = ReferenceCatalog(test_only=True)
    cat.register_source(source())
    cat.register_manufacturer(
        ManufacturerReference(manufacturer_id="acme", canonical_name="Acme", source_id="src")
    )
    cat.register_model(
        DeviceModelReference(
            model_id="acme-one",
            manufacturer_id="acme",
            marketed_name="Acme One",
            model_family="Acme",
            known_model_codes=("am-shared",),
            source_ids=("src",),
        )
    )
    ids = ["v-a", "v-b"]
    for variant_id in reversed(ids) if reverse else ids:
        cat.register_variant(
            DeviceVariantReference(
                variant_id=variant_id,
                model_id="acme-one",
                region_market=variant_id,
                model_codes=("am-shared",),
                network_configuration="5G Sub-6",
                specifications=spec(),
                source_ids=("src",),
            )
        )
    resolution = DeviceResolver(cat).resolve(identity("am-shared"))
    assert resolution.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert resolution.resolved_variant is None
    assert {c.variant_id for c in resolution.candidate_matches} == {"v-a", "v-b"}


def test_fr01_claim_for_another_variant_does_not_authorize() -> None:
    cat = catalog(claims=(claim("v-b", "soc.core_count", 8),))
    _, items, _ = compare(cat, identity("am-a"), {"cpu_cores": 8})
    assert items["soc.core_count"].outcome == Out.REFERENCE_UNAVAILABLE
    # Positive control: the same claim authorizes exactly the variant it names.
    _, control, _ = compare(cat, identity("am-b"), {"cpu_cores": 8})
    assert control["soc.core_count"].outcome == Out.CONSISTENT_WITH_REFERENCE


@pytest.mark.parametrize(
    "path,spec_sources,variant_sources",
    [
        ("soc.core_count", (), ("src",)),
        ("network.5g_mmwave_supported", ("src",), ()),
    ],
)
def test_fr01_variant_without_citations_is_never_authoritative(
    path: str, spec_sources: tuple[str, ...], variant_sources: tuple[str, ...]
) -> None:
    value = 8 if path == "soc.core_count" else True
    cat = catalog(
        claims=(claim("v-a", path, value),),
        spec_sources=spec_sources,
        variant_sources=variant_sources,
    )
    observed = {"cpu_cores": 8, "feature_5g_mmwave": 1}
    _, items, _ = compare(cat, identity("am-a"), observed)
    assert items[path].outcome == Out.REFERENCE_UNAVAILABLE
    assert items[path].reference_value is None


@pytest.mark.parametrize(
    "value",
    [2, -1, 0.5, float("nan"), float("inf"), "false", "true", [], {}, None],
)
def test_fr01_invalid_mmwave_values_are_not_comparable(value: object) -> None:
    cat = catalog(test_only=True)
    _, items, _ = compare(cat, identity("am-a"), {"feature_5g_mmwave": value})
    item = items["network.5g_mmwave_supported"]
    assert item.outcome not in DEFINITIVE
    assert item.observed_value is None


def test_fr01_valid_mmwave_values_still_compare() -> None:
    cat = catalog(test_only=True)
    _, match, _ = compare(cat, identity("am-a"), {"feature_5g_mmwave": True})
    _, differ, _ = compare(cat, identity("am-a"), {"feature_5g_mmwave": 0})
    assert match["network.5g_mmwave_supported"].outcome == Out.CONSISTENT_WITH_REFERENCE
    assert differ["network.5g_mmwave_supported"].outcome == Out.DIFFERS_FROM_REFERENCE


def _perf_manager(
    *, claim_path: str | None, claimed: bool = True, **metric_kwargs: object
) -> PerformanceReferenceManager:
    fields: dict[str, object] = {
        "metric_id": "score-a",
        "metric_name": "Fixture score",
        "measurement_unit": "points",
        "test_methodology": "Fabricated fixture only",
        "applicable_model_ids": ("acme-one",),
        "test_conditions": "Fixture",
        "source_id": "src",
        "reference_min": 1.0,
        "reference_max": 2.0,
    }
    fields.update(metric_kwargs)
    metric = PerformanceMetricReference(**fields)  # type: ignore[arg-type]
    claims = ()
    if claimed and claim_path is not None:
        claims = (claim("score-a", claim_path, metric.model_dump(mode="json")),)
    cat = catalog(claims=claims)
    cat.register_performance_metric(metric)
    return PerformanceReferenceManager(cat)


def test_fr01_performance_claim_must_bind_the_baseline_property_path() -> None:
    wrong = _perf_manager(claim_path="performance.other")
    assert wrong.evaluate_metric("score-a", 1.5, "acme-one").outcome == Out.REFERENCE_UNAVAILABLE
    right = _perf_manager(claim_path="performance.baseline")
    assert (
        right.evaluate_metric("score-a", 1.5, "acme-one").outcome == Out.CONSISTENT_WITH_REFERENCE
    )


@pytest.mark.parametrize("observed", [-1.0, -0.0001, -1e308])
def test_fr01_negative_performance_observation_is_insufficient_not_a_mismatch(
    observed: float,
) -> None:
    manager = _perf_manager(claim_path="performance.baseline")
    result = manager.evaluate_metric("score-a", observed, "acme-one")
    assert result.outcome == Out.INSUFFICIENT_EVIDENCE
    assert result.observed_value is None
    # Control: a non-negative value outside the range is a genuine, verified mismatch.
    assert manager.evaluate_metric("score-a", 3.0, "acme-one").outcome == Out.DIFFERS_FROM_REFERENCE


# --------------------------------------------------------------------------
# FR-02: malformed performance observations never raise and never match
# --------------------------------------------------------------------------

BAD_OBSERVATIONS = [
    float("nan"),
    float("inf"),
    float("-inf"),
    "1.5",
    True,
    False,
    10**400,
    [1.5],
]


@pytest.mark.parametrize("observed", BAD_OBSERVATIONS)
@pytest.mark.parametrize(
    "scenario", ["unknown-metric", "unverified", "wrong-model", "wrong-variant", "verified"]
)
def test_fr02_malformed_performance_observation_is_safe(observed: object, scenario: str) -> None:
    if scenario == "unverified":
        manager = _perf_manager(claim_path=None)
    else:
        manager = _perf_manager(claim_path="performance.baseline", applicable_variant_ids=("v-a",))
    metric_id = "missing" if scenario == "unknown-metric" else "score-a"
    model_id = "other-model" if scenario == "wrong-model" else "acme-one"
    variant_id = "v-b" if scenario == "wrong-variant" else None
    result = manager.evaluate_metric(metric_id, observed, model_id, variant_id)  # type: ignore[arg-type]
    assert result.outcome not in DEFINITIVE
    assert result.observed_value is None


# --------------------------------------------------------------------------
# FR-03: negative standard deviation
# --------------------------------------------------------------------------


def test_fr03_negative_standard_deviation_is_rejected_zero_is_allowed() -> None:
    base = {
        "metric_id": "score-a",
        "metric_name": "n",
        "measurement_unit": "points",
        "test_methodology": "m",
        "applicable_model_ids": ("acme-one",),
        "test_conditions": "c",
        "source_id": "src",
        "reference_mean": 100.0,
    }
    with pytest.raises(ValueError, match="negative"):
        PerformanceMetricReference(**base, reference_std_dev=-0.001)  # type: ignore[arg-type]
    assert PerformanceMetricReference(**base, reference_std_dev=0.0).reference_std_dev == 0.0  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# FR-04: synthetic sources and self-attested verification
# --------------------------------------------------------------------------


def _synthetic_source() -> ReferenceSource:
    return ReferenceSource(
        source_id="synthetic-extra",
        title="Fixture",
        publisher="Fixture",
        url_or_document_id="synthetic://fixture",
        source_classification=SourceClassification.SYNTHETIC_FIXTURE,
        is_synthetic=True,
    )


def test_fr04_production_catalog_rejects_synthetic_source_registration() -> None:
    with pytest.raises(CatalogIntegrityError, match="test-only"):
        ReferenceCatalog().register_source(_synthetic_source())
    test_catalog = ReferenceCatalog(test_only=True)
    test_catalog.register_source(_synthetic_source())
    assert test_catalog.get_source("synthetic-extra") is not None


def test_fr04_synthetic_source_in_import_payload_rejects_atomically() -> None:
    cat = build_seed_catalog()
    before = (cat.export_summary(), [s.source_id for s in cat.all_sources()])
    payload = {
        "schema_version": "vector-catalog-v1",
        "sources": [_synthetic_source().model_dump(mode="json")],
    }
    with pytest.raises(CatalogImportError):
        import_catalog_payload(payload, cat)
    assert (cat.export_summary(), [s.source_id for s in cat.all_sources()]) == before


def _claim_payload() -> dict[str, object]:
    src = source(claims=(claim("v-a", "soc.core_count", 8),)).model_dump(mode="json")
    return {"schema_version": "vector-catalog-v1", "sources": [src]}


def test_fr04_untrusted_import_cannot_manufacture_verified_claims() -> None:
    cat = ReferenceCatalog()
    with pytest.raises(CatalogImportError, match="verified_claims"):
        import_catalog_payload(_claim_payload(), cat)
    assert cat.all_sources() == ()
    # The seed payload (no claims) still imports, and loaded sources stay unverified.
    seeded = build_seed_catalog()
    assert all(not s.verified_claims for s in seeded.all_sources())


def test_fr04_explicit_curator_and_test_only_paths_remain_available() -> None:
    curated = ReferenceCatalog()
    import_catalog_payload(_claim_payload(), curated, curator_authorized=True)
    assert curated.get_source("src").verified_claims  # type: ignore[union-attr]
    fixture = ReferenceCatalog(test_only=True)
    import_catalog_payload(_claim_payload(), fixture)
    assert fixture.get_source("src").verified_claims  # type: ignore[union-attr]


def test_fr04_seed_payload_still_imports_into_production_without_authorization() -> None:
    payload = build_seed_payload()
    payload["sources"] = [s for s in payload["sources"] if not s["is_synthetic"]]
    payload["manufacturers"] = [
        m for m in payload["manufacturers"] if m["manufacturer_id"] != "synthetic-mfg"
    ]
    payload["models"] = [m for m in payload["models"] if not m.get("is_synthetic", False)]
    ids = {m["model_id"] for m in payload["models"]}
    payload["variants"] = [v for v in payload["variants"] if v["model_id"] in ids]
    summary = import_catalog_payload(payload, ReferenceCatalog())
    assert summary["models_imported"] == 3


# --------------------------------------------------------------------------
# FR-05: contradictory platform / manufacturer
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "who",
    [
        DeviceIdentity(platform=Platform.IOS, model="SM-S918B"),
        DeviceIdentity(platform=Platform.IOS, manufacturer="Samsung", model="SM-S918B"),
        DeviceIdentity(
            platform=Platform.ANDROID, manufacturer="Apple Inc.", product_type="iPhone15,2"
        ),
        DeviceIdentity(platform=Platform.ANDROID, product_type="iPhone15,2"),
    ],
)
def test_fr05_contradictory_platform_is_not_resolved(who: DeviceIdentity) -> None:
    resolution = DeviceResolver(build_seed_catalog()).resolve(who)
    assert resolution.status == ResolutionStatus.CONFLICTING_IDENTIFIERS
    assert resolution.resolved_variant is None and resolution.resolved_model is None


@pytest.mark.parametrize(
    "who,expected",
    [
        (DeviceIdentity(platform=Platform.ANDROID, model="SM-S918B"), "EXACT_MATCH"),
        (DeviceIdentity(platform=Platform.UNKNOWN, model="SM-S918B"), "EXACT_MATCH"),
        (
            DeviceIdentity(
                platform=Platform.IOS, manufacturer="Apple Inc.", product_type="iPhone15,2"
            ),
            "MODEL_MATCH_AMBIGUOUS_VARIANT",
        ),
    ],
)
def test_fr05_consistent_platform_resolution_is_unchanged(
    who: DeviceIdentity, expected: str
) -> None:
    assert DeviceResolver(build_seed_catalog()).resolve(who).status.value == expected


# --------------------------------------------------------------------------
# FR-06: no mismatch is asserted while the variant is unresolved
# --------------------------------------------------------------------------

AMBIGUOUS_CASES = [
    ("soc.core_count", {"cpu_cores": 4}, {"cpu_cores": 8}),
    ("sensors.nfc_present", {"feature_nfc": 0}, {"feature_nfc": 1}),
    ("sensors.barometer_present", {"feature_barometer": 0}, {"feature_barometer": 1}),
    ("camera.rear_cameras_count", {"rear_camera_count": 2}, {"rear_camera_count": 3}),
    ("network.5g_mmwave_supported", {"feature_5g_mmwave": 0}, {"feature_5g_mmwave": 1}),
]


@pytest.mark.parametrize("path,differing,matching", AMBIGUOUS_CASES)
def test_fr06_ambiguous_variant_withholds_mismatch_but_keeps_proven_consensus(
    path: str, differing: dict[str, object], matching: dict[str, object]
) -> None:
    cat = catalog(test_only=True)
    resolution, items, _ = compare(cat, identity(marketing_name="Acme One"), differing)
    assert resolution.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
    item = items[path]
    assert item.outcome == Out.VARIANT_AMBIGUOUS
    assert any("Mismatch verdict withheld" in text for text in item.limitations)
    assert item.observed_value is not None  # observation is preserved, not discarded
    _, consensus, _ = compare(cat, identity(marketing_name="Acme One"), matching)
    assert consensus[path].outcome == Out.CONSISTENT_WITH_REFERENCE
    assert any("candidate consensus" in text for text in consensus[path].limitations)
    # Control: once the exact variant is established, a real mismatch is still reported.
    exact_resolution, exact, _ = compare(cat, identity("am-a"), differing)
    assert exact_resolution.status == ResolutionStatus.EXACT_MATCH
    assert exact[path].outcome == Out.DIFFERS_FROM_REFERENCE


# --------------------------------------------------------------------------
# FR-07: item-level TEST-ONLY labels
# --------------------------------------------------------------------------


def test_fr07_every_test_only_item_is_labeled_including_unresolved_reports() -> None:
    cat = catalog(test_only=True)
    for who in (identity("am-a"), identity(marketing_name="Acme One"), identity("unknown-code")):
        resolution = DeviceResolver(cat).resolve(who)
        report = SpecificationComparator(cat).compare(resolution, FULL)
        assert report.items
        assert "TEST-ONLY CATALOG" in report.honesty_disclaimer
        assert all(
            any(text.startswith("TEST-ONLY CATALOG") for text in item.limitations)
            for item in report.items
        )


def test_fr07_production_items_carry_no_test_only_label() -> None:
    cat = build_seed_catalog()
    resolution = DeviceResolver(cat).resolve(
        DeviceIdentity(platform=Platform.ANDROID, model="SM-S918B")
    )
    report = SpecificationComparator(cat).compare(resolution, FULL)
    assert report.items and "TEST-ONLY" not in report.honesty_disclaimer
    assert not any("TEST-ONLY" in text for item in report.items for text in item.limitations)


# --------------------------------------------------------------------------
# FR-08 / FR-09: battery parsing hardening (valid telemetry unchanged)
# --------------------------------------------------------------------------

NOW = datetime.now(UTC)


def _raw(**overrides: str) -> str:
    values = {
        "level": "83",
        "scale": "100",
        "voltage": "4127",
        "temperature": "314",
        "status": "2",
    }
    values.update(overrides)
    return "\n".join(f"{k}: {v}" for k, v in values.items())


@pytest.mark.parametrize("field", ["level", "scale", "voltage", "temperature"])
@pytest.mark.parametrize(
    "text", ["8_3", "+83", "٨٣", "1e2", "0x53", "83.0", "9" * 5000, "- 5", "--5", ""]
)
def test_fr08_non_ascii_decimal_integers_are_invalid_not_coerced(field: str, text: str) -> None:
    telemetry = _parse_battery_output(_raw(**{field: text}), NOW)
    assert field in telemetry.invalid_fields
    assert _evaluate_battery_telemetry(telemetry)[0] == "INCONCLUSIVE"


@pytest.mark.parametrize("level,temp", [("0", "-400"), ("100", "850"), ("83", "314"), ("83", "-0")])
def test_fr08_valid_ascii_integers_still_pass(level: str, temp: str) -> None:
    telemetry = _parse_battery_output(_raw(level=level, temperature=temp), NOW)
    assert telemetry.invalid_fields == ()
    assert _evaluate_battery_telemetry(telemetry)[0] == "PASS"


@pytest.mark.parametrize("plugged", ["99999", "garbage", "3", "", "AC; rm -rf"])
def test_fr09_unrecognized_plug_source_is_not_published_and_does_not_change_pass(
    plugged: str,
) -> None:
    telemetry = _parse_battery_output(_raw() + f"\nplugged: {plugged}", NOW)
    assert telemetry.plugged is None
    assert telemetry.invalid_fields == ()
    assert _evaluate_battery_telemetry(telemetry)[0] == "PASS"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", "Unplugged"),
        ("1", "AC"),
        ("2", "USB"),
        ("4", "Wireless"),
        ("8", "Dock"),
        ("USB", "USB"),
    ],
)
def test_fr09_recognized_plug_sources_are_published(raw: str, expected: str) -> None:
    assert _parse_battery_output(_raw() + f"\nplugged: {raw}", NOW).plugged == expected
