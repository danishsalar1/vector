"""PG-02/03 regressions. All identities/transports here are synthetic test inputs."""

from typing import Any
from unittest.mock import patch

import pytest

from vector_agent.core.config import AgentSettings
from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState, AndroidDeviceBridge
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.models.device import DeviceIdentity, Platform
from vector_agent.models.reference import ResolutionStatus as S
from vector_agent.reference.catalog import ReferenceCatalog
from vector_agent.reference.importer import CatalogImportError, import_catalog_payload
from vector_agent.reference.resolver import DeviceResolver
from vector_agent.reference.seed import build_seed_catalog, build_seed_payload


def resolver_with_one_pixel_variant() -> DeviceResolver:
    payload = build_seed_payload()
    payload["variants"] = [
        v for v in payload["variants"] if v["variant_id"] != "pixel-7-pro-global-gp4bc"
    ]
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    return DeviceResolver(cat)


@pytest.mark.parametrize(
    "fields",
    [
        {"manufacturer": "Google", "brand": "Samsung"},
        {"manufacturer": "Samsung", "brand": "Google"},
        {"model": "SM-S918B", "marketing_name": "Pixel 7 Pro"},
        {"model": "Pixel 7 Pro", "hardware_model": "SM-S918B"},
        {"model": "Pixel 7 Pro", "device_codename": "dm3q"},
        {"model": "Galaxy S23 Ultra", "product_type": "iPhone15,2"},
        {
            "manufacturer": "Google",
            "brand": "Samsung",
            "model": "Pixel 7 Pro",
            "hardware_model": "GE2AE",
        },
        {"model": "SM-S918B", "hardware_model": "SM-S918U"},
        {"model": "GE2AE", "hardware_model": "GP4BC"},
    ],
)
def test_pg02_all_recognized_claims_must_agree(fields: dict[str, str]) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(DeviceIdentity(**fields))
    assert result.status == S.CONFLICTING_IDENTIFIERS
    assert result.resolved_variant is None
    assert "Contradictory identifiers" in result.reason
    assert all(result.considered_fields[k] == v for k, v in fields.items())


def test_pg02_unknown_manufacturer_cannot_be_silently_assumed_samsung() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(manufacturer="Xiaomi", model="SM-S918B")
    )
    assert result.status == S.UNSUPPORTED_DEVICE
    assert result.resolved_variant is None
    assert "manufacturer" in result.reason


@pytest.mark.parametrize(
    "field",
    ["model", "marketing_name", "device_codename", "hardware_model", "product_type", "brand"],
)
def test_pg02_unmapped_supplied_claim_blocks_exact_without_inventing_conflict(field: str) -> None:
    fields = {"manufacturer": "Google", "model": "Pixel 7 Pro", "hardware_model": "GE2AE"}
    fields[field] = "unknown-test-value"
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(DeviceIdentity(**fields))
    assert result.status != S.EXACT_MATCH
    assert result.resolved_variant is None
    assert field in result.reason


@pytest.mark.parametrize(
    "code,variant",
    [
        ("SM-S918B", "galaxy-s23-ultra-global-s918b"),
        ("SM-S918U", "galaxy-s23-ultra-us-s918u"),
        (" sm_s918b ", "galaxy-s23-ultra-global-s918b"),
    ],
)
def test_pg02_compatible_samsung_codes_and_aliases_still_resolve(code: str, variant: str) -> None:
    identity = DeviceIdentity(
        manufacturer=" Samsung Electronics ",
        brand="SAMSUNG",
        model=code,
        marketing_name="Galaxy S23 Ultra",
        device_codename="dm3q",
    )
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(identity)
    assert result.status == S.EXACT_MATCH
    assert result.resolved_variant is not None
    assert result.resolved_variant.variant_id == variant


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"manufacturer": "Unknown Test Vendor", "model": "Unknown Test Model"},
        {"platform": Platform.ANDROID},
    ],
)
def test_pg02_empty_and_unknown_identity_never_resolves_exactly(fields: dict[str, Any]) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(DeviceIdentity(**fields))
    assert result.status in {S.UNKNOWN_DEVICE, S.UNSUPPORTED_DEVICE}
    assert result.resolved_variant is None


def test_pg03_missing_optional_fields_do_not_conflict_with_positive_code() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(model="SM-S918B")
    )
    assert result.status == S.EXACT_MATCH


@pytest.mark.parametrize(
    "fields",
    [
        {"model": "Pixel 7 Pro"},
        {"model": "Pixel 7 Pro", "hardware_model": "GP4BC"},
        {"model": "Pixel 7 Pro", "hardware_model": "GVU6C"},
    ],
)
def test_pg03_one_catalog_variant_is_not_evidence_of_that_variant(fields: dict[str, str]) -> None:
    result = resolver_with_one_pixel_variant().resolve(
        DeviceIdentity(manufacturer="Google", **fields)
    )
    assert result.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert result.resolved_variant is None


def test_pg03_one_variant_with_its_own_compatible_code_can_resolve() -> None:
    result = resolver_with_one_pixel_variant().resolve(
        DeviceIdentity(manufacturer="Google LLC", model="Pixel 7 Pro", hardware_model="GE2AE")
    )
    assert result.status == S.EXACT_MATCH
    assert result.resolved_variant is not None
    assert result.resolved_variant.variant_id == "pixel-7-pro-us-ge2ae"


def test_pg03_missing_catalog_variant_code_cannot_be_overridden_by_another_code() -> None:
    result = resolver_with_one_pixel_variant().resolve(
        DeviceIdentity(model="GE2AE", hardware_model="GP4BC")
    )
    assert result.status != S.EXACT_MATCH
    assert result.resolved_variant is None


@pytest.mark.parametrize("code", [None, "synth-x1"])
def test_pg03_synthetic_identity_never_becomes_real_exact_identity(code: str | None) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(
            manufacturer="Synthetic Mobile Inc", model="Synthetic Model X", hardware_model=code
        )
    )
    assert result.status == S.UNSUPPORTED_DEVICE
    assert result.resolved_variant is None
    assert "synthetic" in result.reason.lower()


def test_pg02_raw_producer_claim_cannot_be_ignored_or_override_identity() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(manufacturer="Samsung", model="SM-S918B"),
        raw_properties={"ro.product.model": "Pixel 7 Pro"},
    )
    assert result.status == S.CONFLICTING_IDENTIFIERS
    assert result.considered_fields["model"] == "SM-S918B"
    assert result.considered_fields["raw.ro.product.model"] == "Pixel 7 Pro"


def test_pg02_raw_producer_claims_resolve_without_fabricated_identity_fields() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        raw_properties={
            "ro.product.manufacturer": "Samsung",
            "ro.product.model": "SM-S918U",
            "ro.product.brand": "samsung",
        }
    )
    assert result.status == S.EXACT_MATCH
    assert result.resolved_variant is not None
    assert result.resolved_variant.variant_id == "galaxy-s23-ultra-us-s918u"


def test_unrelated_raw_identifiers_are_not_exported() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(model="SM-S918U"),
        raw_properties={"serial": "SYNTHETIC-PRIVATE-MARKER", "UDID": "SYNTHETIC-PRIVATE-MARKER"},
    )
    assert "SYNTHETIC-PRIVATE-MARKER" not in result.model_dump_json()


@pytest.mark.parametrize("product", ["iPhone15,2", "iphone15-2", " IPHONE15,2 "])
def test_ios_product_identifier_matches_model_without_inventing_region(product: str) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(
            platform=Platform.IOS,
            manufacturer="Apple Inc.",
            brand="Apple",
            model=product,
            product_type=product,
            hardware_model="D73AP",
        )
    )
    assert result.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert result.resolved_model is not None
    assert result.resolved_model.model_id == "iphone-14-pro"
    assert result.resolved_variant is None
    assert "hardware_model" in result.reason


@pytest.mark.parametrize("product", ["iPhone1,52", "iPhone152", "iPhone15,,2", "iPhone15/2"])
def test_ios_product_normalization_does_not_collapse_distinct_identifiers(product: str) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(manufacturer="Apple", model=product, product_type=product)
    )
    assert result.resolved_model is None
    assert result.status == S.UNSUPPORTED_DEVICE


def test_candidate_order_is_stable_and_not_variant_proof() -> None:
    payload = build_seed_payload()
    cat = ReferenceCatalog(test_only=True)
    payload["variants"].reverse()
    import_catalog_payload(payload, cat)
    identity = DeviceIdentity(manufacturer="Google", model="Pixel 7 Pro")
    first = DeviceResolver(cat).resolve(identity)
    second = DeviceResolver(build_seed_catalog(test_only=True)).resolve(identity)
    assert first.status == second.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert first.candidate_matches == second.candidate_matches


@pytest.mark.parametrize(
    "manufacturer,expected", [("Samsung", S.EXACT_MATCH), ("Xiaomi", S.UNSUPPORTED_DEVICE)]
)
def test_actual_android_bridge_and_session_identity_to_resolver(
    manufacturer: str, expected: S
) -> None:
    bridge = AndroidDeviceBridge()
    props = {
        "ro.product.manufacturer": manufacturer,
        "ro.product.model": "SM-S918B",
        "ro.product.device": "dm3q",
        "ro.product.brand": "Samsung",
        "ro.build.version.release": "14",
        "ro.build.version.sdk": "34",
    }
    manager = DeviceSessionManager()
    with (
        patch.object(bridge, "_require_adb", return_value="adb"),
        patch.object(bridge, "_getprop", side_effect=lambda adb, serial, prop: props[prop]),
    ):
        manager.reconcile_android_discovery(
            [AdbDeviceEntry("SYNTHETIC2A", AdbDeviceState.DEVICE, {})],
            adb_identity_fetcher=bridge.get_identity,
        )
    identity = manager.list_sessions()[0].identity
    assert identity is not None
    assert identity.hardware_model is None and identity.product_type is None
    assert identity.marketing_name is None and identity.serial is None
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(identity)
    assert result.status == expected


def test_actual_ios_identity_producer_preserves_unknown_board_and_ambiguous_region() -> None:
    bridge = IOSDeviceBridge(settings=AgentSettings())
    metadata = {
        "ProductType": "iPhone15,2",
        "ProductVersion": "17.4.1",
        "BuildVersion": "21E236",
        "DeviceClass": "iPhone",
        "HardwareModel": "D73AP",
        "CPUArchitecture": "arm64e",
    }
    with patch.object(
        bridge, "get_metadata_field", side_effect=lambda udid, key, **kw: metadata[key]
    ):
        identity = bridge.get_identity("00000000-0000000000000000")
    assert identity is not None
    assert identity.model == identity.product_type == "iPhone15,2"
    assert identity.hardware_model == "D73AP"
    before = identity.model_dump_json()
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(identity)
    assert result.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert result.resolved_variant is None
    assert identity.model_dump_json() == before


def test_pg02_conflicting_models_with_same_manufacturer_do_not_use_score_priority() -> None:
    payload = build_seed_payload()
    # Explicitly synthetic catalog relationship, not an asserted OEM phone mapping.
    sibling = dict(payload["models"][0])
    sibling.update(
        model_id="synthetic-google-sibling",
        marketed_name="Synthetic Google Sibling",
        known_model_codes=["TEST-SIBLING"],
        device_codenames=[],
        source_ids=["synthetic-test-source"],
        is_synthetic=True,
        supported_component_alternatives=[],
    )
    payload["models"].append(sibling)
    cat = ReferenceCatalog(test_only=True)
    import_catalog_payload(payload, cat)
    result = DeviceResolver(cat).resolve(
        DeviceIdentity(manufacturer="Google", model="Pixel 7 Pro", hardware_model="TEST-SIBLING")
    )
    assert result.status == S.CONFLICTING_IDENTIFIERS
    assert "model" in result.reason and "hardware_model" in result.reason


def test_pg03_synthetic_variant_under_real_model_cannot_resolve_exactly() -> None:
    payload = build_seed_payload()
    variant = next(v for v in payload["variants"] if v["variant_id"] == "pixel-7-pro-us-ge2ae")
    variant["source_ids"] = ["synthetic-test-source"]
    cat = ReferenceCatalog(test_only=True)
    with pytest.raises(CatalogImportError, match="Synthetic citation"):
        import_catalog_payload(payload, cat)
    assert cat.all_models() == ()
    # Preserve the original resolver defense-in-depth test against corrupted state.
    cat = build_seed_catalog(test_only=True)
    original = cat.get_variant("pixel-7-pro-us-ge2ae")
    assert original is not None
    cat._variants[original.variant_id] = original.model_copy(
        update={"source_ids": ("synthetic-test-source",)}
    )
    result = DeviceResolver(cat).resolve(
        DeviceIdentity(model="Pixel 7 Pro", hardware_model="GE2AE")
    )
    assert result.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert result.resolved_variant is None
    assert "synthetic" in result.reason


@pytest.mark.parametrize("value", [123, True, {}, []])
def test_malformed_supplemental_claim_cannot_be_ignored_for_exact_matching(value: Any) -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(model="SM-S918B"), raw_properties={"ro.product.model": value}
    )
    assert result.status != S.EXACT_MATCH
    assert "raw.ro.product.model" in result.reason


def test_ios_product_model_without_board_still_does_not_identify_region() -> None:
    result = DeviceResolver(build_seed_catalog(test_only=True)).resolve(
        DeviceIdentity(platform=Platform.IOS, manufacturer="Apple Inc.", product_type="iPhone15,2")
    )
    assert result.status == S.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert result.resolved_model is not None
    assert result.resolved_model.model_id == "iphone-14-pro"
    assert {c.variant_id for c in result.candidate_matches} == {
        "iphone-14-pro-us-a2650",
        "iphone-14-pro-global-a2890",
    }
