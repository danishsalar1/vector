"""Comprehensive unit, regression, negative, and evidence-honesty tests for Phase 8E."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from vector_agent.models.device import DeviceIdentity, Platform
from vector_agent.models.reference import (
    ComparisonMethod,
    ComparisonOutcome,
    DeviceResolutionResult,
    DeviceSpecification,
    PerformanceMetricReference,
    ReferenceConflict,
    ReferenceSource,
    ResolutionStatus,
    SourceClassification,
)
from vector_agent.reference.catalog import ReferenceCatalog
from vector_agent.reference.comparator import SpecificationComparator
from vector_agent.reference.importer import CatalogImportError, import_catalog_payload
from vector_agent.reference.performance import PerformanceReferenceManager
from vector_agent.reference.resolver import DeviceResolver
from vector_agent.reference.seed import (
    build_seed_catalog,
    build_seed_payload,
    get_coverage_inventory,
)

# ============================================================================
# 1. CATALOG AND IMPORTER TESTS
# ============================================================================


class TestCatalogAndImporter:
    """Tests for ReferenceCatalog and import_catalog_payload."""

    def test_seed_catalog_loads_successfully(self) -> None:
        """Seed catalog builds without integrity errors and has verified entries."""
        catalog = build_seed_catalog(test_only=True)
        summary = catalog.summary()

        assert summary["manufacturers_count"] >= 3
        assert summary["models_count"] >= 3
        assert summary["variants_count"] >= 6
        assert summary["sources_count"] >= 6

        # Check Google Pixel 7 Pro US variant exists
        variant = catalog.get_variant("pixel-7-pro-us-ge2ae")
        assert variant is not None
        assert variant.region_market == "US"
        assert "ge2ae" in variant.model_codes
        assert variant.specifications.battery is not None
        assert variant.specifications.battery.rated_capacity_mah == 4926

    def test_duplicate_import_is_idempotent(self) -> None:
        """Re-importing the same seed payload updates catalog cleanly without duplication."""
        catalog = ReferenceCatalog(test_only=True)
        payload = build_seed_payload()

        # First import
        result1 = import_catalog_payload(payload, catalog)
        assert result1["sources_imported"] > 0
        m_count1 = len(catalog.all_manufacturers())
        v_count1 = len(catalog.all_variants())

        # Second import of identical payload
        result2 = import_catalog_payload(payload, catalog)
        assert result2["sources_imported"] > 0
        assert len(catalog.all_manufacturers()) == m_count1
        assert len(catalog.all_variants()) == v_count1

    def test_unsupported_schema_version_rejected(self) -> None:
        """Importing a payload with unsupported schema version raises CatalogImportError."""
        catalog = ReferenceCatalog(test_only=True)
        payload = {"schema_version": "vector-catalog-v999", "sources": []}
        with pytest.raises(CatalogImportError, match="Unsupported catalog schema version"):
            import_catalog_payload(payload, catalog)

    def test_payload_exceeding_max_records_rejected(self) -> None:
        """Ingesting an unbounded payload exceeding max record limits is rejected."""
        catalog = ReferenceCatalog(test_only=True)
        payload: dict[str, Any] = {
            "schema_version": "vector-catalog-v1",
            "sources": [
                {
                    "source_id": f"src-{i}",
                    "title": f"Source {i}",
                    "publisher": "Test",
                    "url_or_document_id": f"https://example.com/src/{i}",
                    "source_classification": SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE.value,
                    "retrieved_at": "2026-10-01T00:00:00Z",
                    "version_or_revision": "1.0",
                }
                for i in range(1005)
            ],
        }
        with pytest.raises(CatalogImportError, match="exceeds safe limit"):
            import_catalog_payload(payload, catalog)

    def test_missing_source_attribution_rejected(self) -> None:
        """Specifications with non-existent source_ids fail referential integrity."""
        catalog = ReferenceCatalog(test_only=True)
        payload = {
            "schema_version": "vector-catalog-v1",
            "sources": [],
            "manufacturers": [
                {
                    "manufacturer_id": "google",
                    "canonical_name": "Google",
                    "aliases": ["Google LLC"],
                    "source_id": "non-existent-source",
                }
            ],
        }
        with pytest.raises(CatalogImportError, match="cites unknown source"):
            import_catalog_payload(payload, catalog)

    def test_transactional_rollback_on_malformed_entry(self) -> None:
        """If a batch payload contains an invalid record midway, previous records are rolled back."""
        catalog = build_seed_catalog(test_only=True)
        initial_manufacturers = len(catalog.all_manufacturers())

        # Malformed payload: valid source, but manufacturer references invalid source
        bad_payload = {
            "schema_version": "vector-catalog-v1",
            "sources": [
                {
                    "source_id": "new-valid-source",
                    "title": "Valid Source",
                    "publisher": "Vendor",
                    "url_or_document_id": "https://example.com/doc",
                    "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                    "retrieved_at": "2026-10-01T00:00:00Z",
                }
            ],
            "manufacturers": [
                {
                    "manufacturer_id": "new-vendor",
                    "canonical_name": "New Vendor",
                    "aliases": [],
                    "source_id": "ghost-source-does-not-exist",
                }
            ],
        }

        with pytest.raises(CatalogImportError):
            import_catalog_payload(bad_payload, catalog)

        # Catalog must not have been mutated
        assert len(catalog.all_manufacturers()) == initial_manufacturers
        assert catalog.get_source("new-valid-source") is None

    def test_catalog_conflict_recording(self) -> None:
        """Registering an explicit conflict preserves both sources and records ReferenceConflict."""
        catalog = build_seed_catalog(test_only=True)
        initial_conflicts = len(catalog.all_conflicts())

        # Create a new source claiming a conflicting battery capacity
        conflict_source = ReferenceSource(
            source_id="teardown-conflict-01",
            title="Independent Teardown Analysis",
            publisher="TeardownLab",
            url_or_document_id="https://teardownlab.example.org/pixel7pro",
            source_classification=SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE,
            publication_date=date(2023, 2, 1),
            retrieved_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
        )
        catalog.register_source(conflict_source)

        conflict = ReferenceConflict(
            conflict_id="conf-pixel7pro-batt",
            target_entity_type="variant",
            target_entity_id="pixel-7-pro-us-ge2ae",
            field_path="specifications.battery.rated_capacity_mah",
            source_a_id="google-pixel7pro-specs",
            source_a_value="4926",
            source_b_id="teardown-conflict-01",
            source_b_value="4850",
            conflict_notes="Teardown reports different nominal battery capacity.",
            recorded_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
        )
        catalog.register_conflict(conflict)

        new_conflicts = catalog.all_conflicts()
        assert len(new_conflicts) > initial_conflicts
        retrieved = catalog.get_conflicts_for_entity("variant", "pixel-7-pro-us-ge2ae")
        assert len(retrieved) == 1
        assert retrieved[0].conflict_id == "conf-pixel7pro-batt"

    def test_malformed_numeric_rejected_by_schema(self) -> None:
        """Negative battery capacity or malformed numeric fields are rejected by validation."""
        with pytest.raises(ValidationError):
            DeviceSpecification(
                battery={"rated_capacity_mah": -500},  # type: ignore[arg-type]
                source_ids=("src-test",),
            )

    def test_unknown_fields_rejected_by_schema(self) -> None:
        """Unrecognized extra fields are rejected to prevent loose ingestion."""
        with pytest.raises(ValidationError):
            ReferenceSource.model_validate(
                {
                    "source_id": "src-extra",
                    "title": "Extra",
                    "publisher": "Test",
                    "url_or_document_id": "https://example.com",
                    "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                    "retrieved_at": "2026-10-01T00:00:00Z",
                    "unexpected_extra_field": "disallowed",
                }
            )


# ============================================================================
# 2. PROVENANCE AND SOURCE QUALITY TESTS
# ============================================================================


class TestProvenanceAndSourceQuality:
    """Tests for reference source hierarchy, synthetic flags, and provenance integrity."""

    def test_source_hierarchy_ranking(self) -> None:
        """OEM_DOCUMENTATION and REGULATORY_FILING rank strictly higher than independent references."""
        from vector_agent.models.reference import SOURCE_AUTHORITY_RANK

        oem_rank = SOURCE_AUTHORITY_RANK[SourceClassification.OEM_DOCUMENTATION]
        reg_rank = SOURCE_AUTHORITY_RANK[SourceClassification.REGULATORY_FILING]
        indep_rank = SOURCE_AUTHORITY_RANK[SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE]
        synth_rank = SOURCE_AUTHORITY_RANK[SourceClassification.SYNTHETIC_FIXTURE]

        # Lower rank integer = higher authority
        assert oem_rank < indep_rank
        assert reg_rank < indep_rank
        assert indep_rank < synth_rank

    def test_synthetic_source_flagging(self) -> None:
        """Synthetic fixtures are explicitly flagged and require is_synthetic=True."""
        synthetic_source = ReferenceSource(
            source_id="synth-src-1",
            title="Synthetic Test Fixture",
            publisher="VECTOR Test Suite",
            url_or_document_id="urn:vector:test:synth-1",
            source_classification=SourceClassification.SYNTHETIC_FIXTURE,
            retrieved_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
            is_synthetic=True,
        )
        assert synthetic_source.is_synthetic is True

        # Validation fails if is_synthetic is false for SYNTHETIC_FIXTURE
        with pytest.raises(ValidationError):
            ReferenceSource(
                source_id="synth-src-invalid",
                title="Synthetic Invalid",
                publisher="VECTOR Test Suite",
                url_or_document_id="urn:vector:test:invalid",
                source_classification=SourceClassification.SYNTHETIC_FIXTURE,
                retrieved_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
                is_synthetic=False,
            )

    def test_licensing_and_attribution_retention(self) -> None:
        """Source records preserve licensing and attribution limitations."""
        source = ReferenceSource(
            source_id="src-license-test",
            title="Public Spec Sheet",
            publisher="Test Pub",
            url_or_document_id="https://example.com/spec",
            source_classification=SourceClassification.OEM_DOCUMENTATION,
            retrieved_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
            license_or_usage_constraints="Permitted for non-commercial diagnostic reference only",
            provenance_notes="Imported via official support portal",
        )
        assert source.license_or_usage_constraints is not None
        assert "non-commercial" in source.license_or_usage_constraints
        assert source.provenance_notes is not None


# ============================================================================
# 3. DEVICE AND VARIANT RESOLUTION TESTS
# ============================================================================


class TestDeviceAndVariantResolution:
    """Tests for conservative DeviceResolver matching."""

    @pytest.fixture
    def catalog(self) -> ReferenceCatalog:
        return build_seed_catalog(test_only=True)

    @pytest.fixture
    def resolver(self, catalog: ReferenceCatalog) -> DeviceResolver:
        return DeviceResolver(catalog)

    def test_exact_model_and_variant_match(self, resolver: DeviceResolver) -> None:
        """Exact match resolves cleanly when hardware_model is provided."""
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
            hardware_model="GE2AE",
        )
        result = resolver.resolve(identity)

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.resolved_variant is not None
        assert result.resolved_variant.variant_id == "pixel-7-pro-us-ge2ae"
        assert "ge2ae" in result.resolved_variant.model_codes
        assert len(result.candidate_matches) >= 1

    def test_ambiguous_model_match_preserves_uncertainty(self, resolver: DeviceResolver) -> None:
        """When hardware_model is missing, resolver MUST NOT guess or default to US."""
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
            # hardware_model is intentionally omitted
        )
        result = resolver.resolve(identity)

        assert result.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
        assert result.resolved_variant is None  # MUST NOT pick one!
        assert len(result.candidate_matches) == 2

        candidate_variant_ids = {c.variant_id for c in result.candidate_matches}
        assert "pixel-7-pro-us-ge2ae" in candidate_variant_ids
        assert "pixel-7-pro-global-gp4bc" in candidate_variant_ids

    def test_samsung_regional_variant_resolution(self, resolver: DeviceResolver) -> None:
        """Samsung regional codes (SM-S918U US vs SM-S918B Global) resolve cleanly."""
        us_identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Samsung",
            model="Galaxy S23 Ultra",
            hardware_model="SM-S918U",
        )
        us_result = resolver.resolve(us_identity)
        assert us_result.status == ResolutionStatus.EXACT_MATCH
        assert us_result.resolved_variant is not None
        assert us_result.resolved_variant.variant_id == "galaxy-s23-ultra-us-s918u"

        global_identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Samsung",
            model="Galaxy S23 Ultra",
            hardware_model="SM-S918B",
        )
        global_result = resolver.resolve(global_identity)
        assert global_result.status == ResolutionStatus.EXACT_MATCH
        assert global_result.resolved_variant is not None
        assert global_result.resolved_variant.variant_id == "galaxy-s23-ultra-global-s918b"

    def test_apple_hardware_model_code_resolution(self, resolver: DeviceResolver) -> None:
        """Apple model codes (A2650 US vs A2890 Global) resolve cleanly."""
        identity = DeviceIdentity(
            platform=Platform.IOS,
            manufacturer="Apple",
            model="iPhone 14 Pro",
            hardware_model="A2650",
        )
        result = resolver.resolve(identity)
        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.resolved_variant is not None
        assert result.resolved_variant.variant_id == "iphone-14-pro-us-a2650"

    def test_conflicting_identifiers_rejected(self, resolver: DeviceResolver) -> None:
        """Manufacturer Google with Samsung hardware code SM-S918U raises CONFLICTING_IDENTIFIERS."""
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
            hardware_model="SM-S918U",  # Belongs to Samsung S23 Ultra!
        )
        result = resolver.resolve(identity)
        assert result.status == ResolutionStatus.CONFLICTING_IDENTIFIERS
        assert result.resolved_variant is None
        assert "Contradictory identifiers" in result.reason

    def test_unsupported_device_detected(self, resolver: DeviceResolver) -> None:
        """Recognized manufacturer with an unsupported model yields UNSUPPORTED_DEVICE."""
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 99 Pro Ultra",  # Not in catalog
        )
        result = resolver.resolve(identity)
        assert result.status == ResolutionStatus.UNSUPPORTED_DEVICE
        assert result.resolved_variant is None

    def test_unknown_device_with_no_fields(self, resolver: DeviceResolver) -> None:
        """Empty identity evidence yields UNKNOWN_DEVICE."""
        identity = DeviceIdentity(
            platform=Platform.UNKNOWN,
            manufacturer=None,
        )
        result = resolver.resolve(identity)
        assert result.status == ResolutionStatus.UNKNOWN_DEVICE
        assert result.resolved_variant is None

    def test_deterministic_candidate_ordering(self, resolver: DeviceResolver) -> None:
        """Resolution candidates are sorted deterministically across multiple runs."""
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
        )
        result1 = resolver.resolve(identity)
        result2 = resolver.resolve(identity)

        v_ids1 = [c.variant_id for c in result1.candidate_matches]
        v_ids2 = [c.variant_id for c in result2.candidate_matches]
        assert v_ids1 == v_ids2


# ============================================================================
# 4. SPECIFICATION COMPARISON TESTS
# ============================================================================


class TestSpecificationComparison:
    """Tests for unit-aware, conservative SpecificationComparator."""

    @pytest.fixture
    def catalog(self) -> ReferenceCatalog:
        return build_seed_catalog(test_only=True)

    @pytest.fixture
    def comparator(self, catalog: ReferenceCatalog) -> SpecificationComparator:
        return SpecificationComparator(catalog)

    @pytest.fixture
    def resolved_pixel7pro_us(self, catalog: ReferenceCatalog) -> DeviceResolutionResult:
        variant = catalog.get_variant("pixel-7-pro-us-ge2ae")
        assert variant is not None
        model = catalog.get_model(variant.model_id)
        return DeviceResolutionResult(
            status=ResolutionStatus.EXACT_MATCH,
            resolved_model=model,
            resolved_variant=variant,
            reason="Resolved",
        )

    def test_active_display_orientation_does_not_establish_native_panel(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """Landscape active mode cannot establish native panel dimensions."""
        observed = {"width": 3120, "height": 1440}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "display.resolution")
        assert item.outcome == ComparisonOutcome.NOT_COMPARABLE
        assert item.comparison_method == ComparisonMethod.EXACT_MATCH
        assert "orientation is not a hardware mismatch" in item.reason

    def test_display_refresh_rate_honesty(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """Active 60Hz cannot prove or disprove the advertised 120Hz maximum."""
        observed = {"refresh_rate": 60}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "display.refresh_rate_hz")
        assert item.outcome == ComparisonOutcome.NOT_COMPARABLE
        assert "does not establish maximum" in item.reason
        assert item.observed_value is None

    def test_remaining_charge_is_not_normalized_into_rated_capacity(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """4,926,000 uAh remaining charge cannot establish 4,926 mAh rated capacity."""
        observed = {"charge_counter": 4926000}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "battery.rated_capacity_mah")
        assert item.outcome == ComparisonOutcome.NOT_COMPARABLE
        assert item.observed_value is None
        assert "remaining charge in uAh" in item.reason

    def test_low_remaining_charge_is_not_a_rated_capacity_mismatch(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """3000 uAh is remaining charge, not 3000 mAh or evidence of battery wear."""
        observed = {"charge_counter": 3000}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "battery.rated_capacity_mah")
        assert item.outcome == ComparisonOutcome.NOT_COMPARABLE
        assert item.observed_value is None
        assert "neither battery health nor OEM origin" in item.reason

    def test_os_visible_ram_does_not_prove_physical_capacity(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """11.2 GiB OS-visible memory cannot establish installed physical capacity."""
        observed = {"ram_total": int(11.2 * 1024**3)}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "memory.ram_total_bytes")
        assert item.outcome == ComparisonOutcome.NOT_COMPARABLE
        assert item.observed_value is None
        assert "no percentage allowance" in item.reason

    def test_camera_sensor_presence_honesty(
        self,
        comparator: SpecificationComparator,
        resolved_pixel7pro_us: DeviceResolutionResult,
    ) -> None:
        """Camera sensor count match does NOT prove module OEM provenance."""
        observed = {"rear_camera_count": 3}
        report = comparator.compare(resolved_pixel7pro_us, observed)

        item = next(i for i in report.items if i.property_path == "camera.rear_cameras_count")
        assert item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
        assert "Camera presence does NOT identify camera module or prove OEM origin." in item.reason
        assert any("Capturing an image" in lim for lim in item.limitations)

    def test_variant_ambiguous_comparison(
        self,
        comparator: SpecificationComparator,
        catalog: ReferenceCatalog,
    ) -> None:
        """Comparing variant-specific properties on an ambiguous resolution returns VARIANT_AMBIGUOUS."""
        resolver = DeviceResolver(catalog)
        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
            # hardware_model omitted -> ambiguous
        )
        ambiguous_res = resolver.resolve(identity)
        assert ambiguous_res.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT

        observed = {"feature_5g_mmwave": True}
        report = comparator.compare(ambiguous_res, observed)

        item = next(i for i in report.items if i.property_path == "network.5g_mmwave_supported")
        assert item.outcome == ComparisonOutcome.VARIANT_AMBIGUOUS
        assert "differ" in item.reason

    def test_unresolved_device_reports_reference_unavailable(
        self,
        comparator: SpecificationComparator,
    ) -> None:
        """Attempting comparison on an unresolved device returns REFERENCE_UNAVAILABLE."""
        unresolved = DeviceResolutionResult(
            status=ResolutionStatus.UNSUPPORTED_DEVICE,
            reason="Device not in catalog",
        )
        report = comparator.compare(unresolved, {"width": 1080, "height": 2400})
        assert len(report.items) == 1
        assert report.items[0].outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE


# ============================================================================
# 5. EVIDENCE HONESTY & ANTI-FALLACY TESTS
# ============================================================================


class TestEvidenceHonesty:
    """Tests ensuring false provenance conclusions are strictly rejected."""

    def test_spec_consistency_does_not_imply_oem_authenticity(self) -> None:
        """All comparisons must retain explicit honesty warnings and never claim authenticity."""
        catalog = build_seed_catalog(test_only=True)
        resolver = DeviceResolver(catalog)
        comparator = SpecificationComparator(catalog)

        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Google",
            model="Pixel 7 Pro",
            hardware_model="GE2AE",
        )
        res = resolver.resolve(identity)
        observed = {
            "width": 1440,
            "height": 3120,
            "refresh_rate": 120,
            "charge_counter": 4926000,
            "cpu_cores": 8,
            "ram_total": 12 * 1024**3,
            "rear_camera_count": 3,
        }
        report = comparator.compare(res, observed)

        # Every consistent item must NOT claim physical authenticity or OEM provenance
        for item in report.items:
            if item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE:
                reason_lower = item.reason.lower()
                assert "counterfeit" not in reason_lower
                # If "oem" or "original" appears, it must be preceded by "not"
                if "original" in reason_lower:
                    assert "not" in reason_lower

    def test_missing_optional_hardware_not_flagged_as_failure(self) -> None:
        """Absent optional capability on a non-supporting variant is not flagged as hardware failure."""
        catalog = build_seed_catalog(test_only=True)
        # Pixel 7 Pro Global (GP4BC) network_configuration is "5G Sub-6"
        global_variant = catalog.get_variant("pixel-7-pro-global-gp4bc")
        assert global_variant is not None
        assert global_variant.network_configuration == "5G Sub-6"


# ============================================================================
# 6. PERFORMANCE REFERENCE TESTS
# ============================================================================


class TestPerformanceReference:
    """Tests for PerformanceReferenceManager baseline contracts."""

    def test_unverified_metric_reports_reference_unavailable(self) -> None:
        """Requesting performance baseline for unverified metric returns REFERENCE_UNAVAILABLE."""
        mgr = PerformanceReferenceManager()
        res = mgr.evaluate_metric(
            metric_id="geekbench-single-core",
            observed_value=1450.0,
            model_id="pixel-7-pro",
            variant_id="pixel-7-pro-us-ge2ae",
        )
        assert res.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE
        assert "No verified performance reference baseline" in res.reason

    def test_registered_metric_evaluation_within_bounds(self) -> None:
        """Explicitly synthetic test-only distributions exercise the numeric infrastructure."""
        catalog = build_seed_catalog(test_only=True)
        mgr = PerformanceReferenceManager(catalog)

        ref = PerformanceMetricReference(
            metric_id="storage-seq-read-mb-s",
            metric_name="Sequential Storage Read",
            test_conditions="Ambient 25C, 100MB block",
            applicable_model_ids=("pixel-7-pro",),
            applicable_variant_ids=("pixel-7-pro-us-ge2ae",),
            measurement_unit="MB/s",
            test_methodology="Sequential block read 1MB test",
            reference_mean=1800.0,
            reference_std_dev=100.0,
            reference_min=1500.0,
            reference_max=2100.0,
            sample_count=50,
            source_id="synthetic-test-source",
            confidence_limitations="SYNTHETIC TEST ONLY; not measured hardware performance.",
        )
        mgr.register_metric_reference(ref)

        res = mgr.evaluate_metric(
            metric_id="storage-seq-read-mb-s",
            observed_value=1750.0,
            model_id="pixel-7-pro",
            variant_id="pixel-7-pro-us-ge2ae",
        )
        assert res.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
        assert "within reference baseline distribution" in res.reason


# ============================================================================
# 7. END-TO-END INTEGRATION AND COVERAGE TESTS
# ============================================================================


class TestEndToEndIntegration:
    """Tests cross-package contracts and real coverage inventory."""

    def test_full_pipeline_identity_to_comparison_report(self) -> None:
        """Full flow: DeviceIdentity -> DeviceResolver -> Catalog -> Comparator -> Report."""
        catalog = build_seed_catalog(test_only=True)
        resolver = DeviceResolver(catalog)
        comparator = SpecificationComparator(catalog)

        identity = DeviceIdentity(
            platform=Platform.ANDROID,
            manufacturer="Samsung",
            model="Galaxy S23 Ultra",
            hardware_model="SM-S918U",
        )

        res = resolver.resolve(identity)
        assert res.status == ResolutionStatus.EXACT_MATCH
        assert res.resolved_variant is not None

        observed = {
            "width": 1440,
            "height": 3088,
            "refresh_rate": 120,
            "charge_counter": 5000,
            "cpu_cores": 8,
            "ram_total": int(11.2 * 1024**3),
            "rear_camera_count": 4,
            "feature_barometer": True,
            "feature_nfc": True,
        }

        report = comparator.compare(res, observed)
        assert report.resolution.status == ResolutionStatus.EXACT_MATCH
        assert len(report.items) >= 5
        items = {item.property_path: item for item in report.items}
        for path in (
            "battery.rated_capacity_mah",
            "display.resolution",
            "display.refresh_rate_hz",
            "memory.ram_total_bytes",
        ):
            assert items[path].outcome == ComparisonOutcome.NOT_COMPARABLE
        for path in ("sensors.nfc_present", "sensors.barometer_present"):
            assert items[path].outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
        assert report.differs_count == 0

    def test_coverage_inventory_honesty(self) -> None:
        """Coverage inventory accurately reports real verified vs synthetic counts."""
        catalog = build_seed_catalog(test_only=True)
        inv = get_coverage_inventory(catalog)

        assert inv["status"] == "UNVERIFIED_STARTER_DATASET"
        assert inv["verified_devices_count"] == 0
        assert len(inv["unverified_device_models"]) == 3
        assert inv["total_variants_count"] >= 6
        assert inv["synthetic_fixtures_count"] == 1
        assert "Synthetic Model X" in inv["synthetic_models"]
        assert inv["coverage_limitation_statement"] is not None
