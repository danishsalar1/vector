"""OEM Specification Comparison Engine.

Consumes:
1. DeviceResolutionResult (exact variant or ambiguous model)
2. DeviceSpecification (reference facts and source citations)
3. Explicitly unverified caller properties, or inputs admitted by DiagnosticEvidenceAdapter

Produces:
SpecificationComparisonReport with discrete, unit-aware, evidence-honest outcomes.

Core Principles:
- Specification match does NOT prove component originality or OEM authenticity.
- Specification mismatch does NOT prove counterfeit, tampering, or component failure.
- Current display modes, remaining charge and OS-visible RAM are not physical specifications.
- Variant ambiguity is preserved: properties that vary across candidates report VARIANT_AMBIGUOUS.
- Missing reference data reports REFERENCE_UNAVAILABLE.
- Missing observation reports INSUFFICIENT_EVIDENCE.
- Unresolved reference conflicts report REFERENCE_UNAVAILABLE; consistency or mismatch verdicts prohibited when reference assertions disagree.
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from vector_agent.models.device import DiagnosticResult, EvidenceRecord
from vector_agent.models.reference import (
    ComparisonMethod,
    ComparisonOutcome,
    DeviceResolutionResult,
    DeviceVariantReference,
    ReferenceConflict,
    ResolutionStatus,
    SpecificationComparisonItem,
    SpecificationComparisonReport,
)

from .catalog import CatalogIntegrityError, ReferenceCatalog


def _extract_observed_number(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val) if math.isfinite(val) else None
    if isinstance(val, str):
        try:
            f = float(val.strip())
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def _reference_value(variant: DeviceVariantReference, path: str) -> Any:
    specs = variant.specifications
    if path == "display.resolution":
        return (
            (specs.display.resolution_width, specs.display.resolution_height)
            if specs.display
            else None
        )
    if path == "display.refresh_rate_hz":
        return specs.display.refresh_rate_max_hz if specs.display else None
    if path == "battery.rated_capacity_mah":
        return specs.battery.rated_capacity_mah if specs.battery else None
    if path == "memory.ram_total_bytes":
        return specs.memory_storage.ram_options_bytes if specs.memory_storage else None
    if path == "soc.core_count":
        return specs.soc.core_count if specs.soc else None
    if path == "camera.rear_cameras_count":
        return len(specs.camera.rear_cameras) if specs.camera else None
    if path == "sensors.nfc_present":
        return specs.sensors.nfc if specs.sensors else None
    if path == "sensors.barometer_present":
        return specs.sensors.barometer if specs.sensors else None
    if path == "network.5g_mmwave_supported":
        # Only explicit supported descriptions establish this boolean property.
        # Absence of the substring in arbitrary prose is not evidence of absence.
        return {
            "5g sub-6": False,
            "5g sub-6 + mmwave": True,
            "5g mmwave + sub-6": True,
            "5g mmwave": True,
        }.get((variant.network_configuration or "").strip().lower())
    raise ValueError(f"Unknown comparison property: {path}")


_KNOWN_DOMAINS: set[str] = {
    "display",
    "battery",
    "soc",
    "memory",
    "memory_storage",
    "sensors",
    "camera",
    "network",
    "connectivity",
    "audio_haptics",
}

_KNOWN_FIELDS_BY_DOMAIN: dict[str, set[str]] = {
    "display": {
        "resolution",
        "resolution_width",
        "resolution_height",
        "refresh_rate_hz",
        "refresh_rate_max_hz",
        "refresh_rate_min_hz",
        "refresh_rates",
        "supported_refresh_rates",
        "size_diagonal_inches",
        "pixel_density_ppi",
        "technology",
        "hdr_standards",
    },
    "battery": {
        "rated_capacity_mah",
        "typical_capacity_mah",
        "chemistry",
        "nominal_voltage_mv",
        "max_charging_wattage_wired",
        "wireless_charging_supported",
        "max_charging_wattage_wireless",
        "removable",
    },
    "soc": {
        "core_count",
        "chip_maker",
        "marketing_name",
        "part_number",
        "cpu_architecture",
        "gpu_model",
        "process_node_nm",
    },
    "memory": {
        "ram_total_bytes",
        "ram_options_bytes",
        "ram_type",
        "storage_options_bytes",
        "storage_type",
        "expandable_storage",
    },
    "memory_storage": {
        "ram_total_bytes",
        "ram_options_bytes",
        "ram_type",
        "storage_options_bytes",
        "storage_type",
        "expandable_storage",
    },
    "sensors": {
        "nfc",
        "nfc_present",
        "barometer",
        "barometer_present",
        "accelerometer",
        "gyroscope",
        "magnetometer",
        "proximity",
        "ambient_light",
        "fingerprint_type",
        "ultra_wideband",
    },
    "camera": {
        "rear_cameras",
        "rear_cameras_count",
        "front_cameras",
        "has_flash",
        "lidar_or_tof_present",
    },
    "network": {
        "5g_mmwave_supported",
        "network_configuration",
        "wifi_generations",
        "bluetooth_version",
        "cellular_generations",
        "usb_type",
        "usb_version",
    },
    "connectivity": {
        "5g_mmwave_supported",
        "network_configuration",
        "wifi_generations",
        "bluetooth_version",
        "cellular_generations",
        "usb_type",
        "usb_version",
    },
    "audio_haptics": {
        "speaker_type",
        "headphone_jack_3_5mm",
        "haptic_motor_type",
    },
}

_PROPERTY_SPEC_MAP: dict[str, dict[str, Any]] = {
    "display.resolution": {
        "domain": "display",
        "targets": {"resolution", "resolution_width", "resolution_height"},
    },
    "display.refresh_rate_hz": {
        "domain": "display",
        "targets": {
            "refresh_rate_hz",
            "refresh_rate_max_hz",
            "refresh_rates",
            "supported_refresh_rates",
        },
    },
    "battery.rated_capacity_mah": {
        "domain": "battery",
        "targets": {"rated_capacity_mah"},
    },
    "soc.core_count": {
        "domain": "soc",
        "targets": {"core_count"},
    },
    "memory.ram_total_bytes": {
        "domain": "memory",
        "targets": {"ram_total_bytes", "ram_options_bytes"},
    },
    "sensors.nfc_present": {
        "domain": "sensors",
        "targets": {"nfc", "nfc_present"},
    },
    "sensors.barometer_present": {
        "domain": "sensors",
        "targets": {"barometer", "barometer_present"},
    },
    "camera.rear_cameras_count": {
        "domain": "camera",
        "targets": {"rear_cameras_count", "rear_cameras"},
    },
    "network.5g_mmwave_supported": {
        "domain": "network",
        "targets": {"5g_mmwave_supported", "network_configuration"},
    },
}


def _property_matches_conflict(property_path: str, conflict_field_path: str) -> bool:
    """Segment-aware structural matching for reference conflict paths.

    Correctly resolves container paths, collection-element indexing, domain ancestors,
    and property aliases while preserving property isolation and failing closed on
    unrecognized paths of uncertain scope.
    """
    if not conflict_field_path or not property_path:
        return False

    c = conflict_field_path.strip().lower()
    p = property_path.strip().lower()

    if c == p:
        return True

    # Strip recognized catalog prefixes
    c_norm = c
    for prefix in ("specifications.", "base_specifications."):
        if c_norm.startswith(prefix):
            c_norm = c_norm[len(prefix) :]
            break

    if c_norm == p:
        return True

    # Root container conflict affects all specification properties
    if c in ("specifications", "base_specifications") or c_norm in (
        "specifications",
        "base_specifications",
        "",
    ):
        return True

    cfg = _PROPERTY_SPEC_MAP.get(p)
    if not cfg:
        return c_norm == p

    prop_domain: str = cfg["domain"]
    prop_targets: set[str] = cfg["targets"]

    # Normalize collection-element indexing: camera.rear_cameras[0] -> camera.rear_cameras
    c_clean = re.sub(r"\[\d+\]", "", c_norm)

    # network_configuration belongs only to network comparisons. SKU/region
    # conflicts remain conservative: identity may depend on that disputed mapping.
    if c_clean == "network_configuration":
        return prop_domain == "network"

    segments = [s for s in c_clean.split(".") if s]
    if not segments:
        return True

    conf_domain = segments[0]

    # Single-segment container/ancestor matching (e.g. 'sensors', 'soc', 'camera')
    if len(segments) == 1:
        if conf_domain == prop_domain:
            return True
        if prop_domain == "memory" and conf_domain == "memory_storage":
            return True
        if prop_domain == "network" and conf_domain in ("network_configuration", "connectivity"):
            return True
        # Unrecognized domain path: fail closed at entity level
        return conf_domain not in _KNOWN_DOMAINS

    # Multi-segment matching
    field_part = ".".join(segments[1:])
    domain_match = (
        conf_domain == prop_domain
        or (prop_domain == "memory" and conf_domain == "memory_storage")
        or (prop_domain == "network" and conf_domain == "connectivity")
    )
    if domain_match:
        if (
            field_part in prop_targets
            or segments[1] in prop_targets
            or c_clean in prop_targets
            or c_clean == p
        ):
            return True
        known_fields = _KNOWN_FIELDS_BY_DOMAIN.get(conf_domain, set())
        # Recognized sibling in same domain returns False; unrecognized fails closed
        return not (segments[1] in known_fields or field_part in known_fields)

    # Completely unrecognized path: fail closed at entity level
    return conf_domain not in _KNOWN_DOMAINS


_TEST_ONLY_ITEM_LIMITATION = (
    "TEST-ONLY CATALOG: fixture comparison, not production OEM truth or verified reference data."
)
_CONSENSUS_LIMITATION = (
    "Shared-model candidate consensus where a reference value is present; "
    "exact variant identity is not established."
)


def _withhold_ambiguous_mismatch(item: SpecificationComparisonItem) -> SpecificationComparisonItem:
    """Under an unresolved variant, never assert a mismatch.

    The catalogued candidates are not proof of complete regional coverage, so a value
    differing from their consensus may belong to an uncatalogued variant. A match with
    every catalogued candidate stays a labeled consensus; a difference becomes ambiguous.
    """
    limitations = item.limitations + (_CONSENSUS_LIMITATION,)
    if item.outcome != ComparisonOutcome.DIFFERS_FROM_REFERENCE:
        return item.model_copy(update={"limitations": limitations})
    return item.model_copy(
        update={
            "outcome": ComparisonOutcome.VARIANT_AMBIGUOUS,
            "reason": (
                "Observed value differs from the shared reference of the catalogued candidate "
                "variants, but exact variant identity and catalog coverage are not established; "
                "no mismatch is asserted. " + item.reason
            ),
            "limitations": limitations
            + ("Mismatch verdict withheld: variant coverage is incomplete or unresolved.",),
        }
    )


class SpecificationComparator:
    """Evaluates observed device properties against trustworthy OEM reference specifications."""

    def __init__(self, catalog: ReferenceCatalog | None = None) -> None:
        self.catalog = catalog or ReferenceCatalog()

    def compare(
        self,
        resolution: DeviceResolutionResult,
        observed_properties: dict[str, Any],
        *,
        device_id: str = "device-unknown",
        evidence_records: list[EvidenceRecord] | None = None,
        diagnostic_results: list[DiagnosticResult] | None = None,
    ) -> SpecificationComparisonReport:
        """Compatibility API for UNVERIFIED caller properties, never Probe ingestion.

        Canonical evidence requires DiagnosticEvidenceAdapter. Previously ignored
        arguments now fail explicitly, including explicitly supplied empty lists.
        """
        if evidence_records is not None or diagnostic_results is not None:
            raise ValueError("Use DiagnosticEvidenceAdapter for canonical diagnostic evidence.")
        report = self._compare_properties(resolution, observed_properties, device_id=device_id)
        return report.model_copy(
            update={
                "honesty_disclaimer": "Caller-supplied unverified observations; no authenticated Probe attribution. "
                + report.honesty_disclaimer,
            }
        )

    def _compare_properties(
        self,
        resolution: DeviceResolutionResult,
        observed_properties: dict[str, Any],
        *,
        device_id: str,
    ) -> SpecificationComparisonReport:
        return SpecificationComparator(self.catalog.snapshot())._compare_snapshot(
            resolution, observed_properties, device_id=device_id
        )

    def _compare_snapshot(
        self,
        resolution: DeviceResolutionResult,
        observed_properties: dict[str, Any],
        *,
        device_id: str,
    ) -> SpecificationComparisonReport:
        """Internal rule evaluation; caller owns admission and traceability."""
        observed_properties = dict(observed_properties)
        for key in ("cpu_cores", "core_count", "rear_camera_count", "camera_rear_count"):
            if key not in observed_properties:
                continue
            value = observed_properties.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 2147483647
                or not math.isfinite(value)
                or value != int(value)
                or (key in ("cpu_cores", "core_count") and value == 0)
            ):
                observed_properties[key] = None
        for key in ("feature_nfc", "feature_barometer", "feature_5g_mmwave"):
            value = observed_properties.get(key)
            if not isinstance(value, (bool, int, float)) or value not in (0, 1):
                observed_properties[key] = None
        items: list[SpecificationComparisonItem] = []
        eval_time = datetime.now(UTC)

        # 1. Check resolution status
        invalid_relationship = (
            resolution.resolved_variant is not None
            and resolution.resolved_model is not None
            and resolution.resolved_variant.model_id != resolution.resolved_model.model_id
        )
        if invalid_relationship or resolution.status in (
            ResolutionStatus.UNKNOWN_DEVICE,
            ResolutionStatus.UNSUPPORTED_DEVICE,
            ResolutionStatus.CONFLICTING_IDENTIFIERS,
            ResolutionStatus.MULTIPLE_CANDIDATES,
        ):
            # No reference specifications available to compare
            report_item = SpecificationComparisonItem(
                property_path="device.specifications",
                observed_value=None,
                reference_value=None,
                comparison_method=ComparisonMethod.EXACT_MATCH,
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason=(
                    f"Reference specifications unavailable because device resolution status is '{resolution.status.value}'. "
                    f"Reason: {resolution.reason}"
                ),
                limitations=(f"Unresolved device status: {resolution.status.value}",),
                source_ids=(),
            )
            return self._build_report(resolution, device_id, eval_time, [report_item])

        # Determine specs to compare
        target_variant: DeviceVariantReference | None = resolution.resolved_variant
        candidate_variants: tuple[DeviceVariantReference, ...] = ()
        if resolution.resolved_model is not None:
            candidate_variants = self.catalog.find_variants_for_model(
                resolution.resolved_model.model_id
            )

        # 2. Evaluate Display: Resolution
        self._compare_display_resolution(
            target_variant, candidate_variants, observed_properties, items
        )

        # 3. Evaluate Display: Refresh Rate
        self._compare_display_refresh_rate(
            target_variant, candidate_variants, observed_properties, items
        )

        # 4. Evaluate Battery: Rated Capacity
        self._compare_battery_capacity(
            target_variant, candidate_variants, observed_properties, items
        )

        # 5. Evaluate SoC: Core Count & Architecture
        self._compare_soc_properties(target_variant, candidate_variants, observed_properties, items)

        # 6. Evaluate RAM Capacity
        self._compare_ram_capacity(target_variant, candidate_variants, observed_properties, items)

        # 7. Evaluate Sensors Presence (Fingerprint, Barometer, NFC)
        self._compare_sensors_presence(
            target_variant, candidate_variants, observed_properties, items
        )

        # 8. Evaluate Camera Arrangement
        self._compare_cameras(target_variant, candidate_variants, observed_properties, items)

        # 9. Evaluate Variant-Specific Network Features
        self._compare_network_configuration(
            target_variant, candidate_variants, observed_properties, items
        )

        if target_variant is None and candidate_variants:
            items = [_withhold_ambiguous_mismatch(item) for item in items]
        return self._build_report(resolution, device_id, eval_time, items)

    def _build_report(
        self,
        resolution: DeviceResolutionResult,
        device_id: str,
        eval_time: datetime,
        items: list[SpecificationComparisonItem],
    ) -> SpecificationComparisonReport:
        """Single exit for every report so test-only labeling cannot be skipped."""
        if self.catalog.test_only:
            items = [
                item.model_copy(
                    update={"limitations": item.limitations + (_TEST_ONLY_ITEM_LIMITATION,)}
                )
                for item in items
            ]
        report = SpecificationComparisonReport(
            report_id=str(uuid4()),
            device_id=device_id,
            resolution=resolution,
            evaluated_at=eval_time,
            items=tuple(items),
        )
        if self.catalog.test_only:
            report = report.model_copy(
                update={
                    "honesty_disclaimer": "TEST-ONLY CATALOG: fixture comparisons, not production OEM truth. "
                    + report.honesty_disclaimer
                }
            )
        return report

    # ----------------------------------------------------------
    # Conflict Detection and Domain Comparison Routines
    # ----------------------------------------------------------

    def _get_applicable_conflicts(
        self,
        property_path: str,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        model_id: str | None,
    ) -> list[ReferenceConflict]:
        """Find unresolved catalog reference conflicts affecting this property and entity."""
        conflicts = self.catalog.all_conflicts()
        if not conflicts:
            return []

        applicable: list[ReferenceConflict] = []
        for c in conflicts:
            # 1. Entity scope check
            if c.target_entity_type == "variant":
                if target_variant is not None:
                    if c.target_entity_id != target_variant.variant_id:
                        continue
                elif candidate_variants:
                    if c.target_entity_id not in {v.variant_id for v in candidate_variants}:
                        continue
                else:
                    continue
            elif c.target_entity_type == "model":
                if model_id is not None:
                    if c.target_entity_id != model_id:
                        continue
                else:
                    continue
            elif c.target_entity_type == "manufacturer":
                model = self.catalog.get_model(model_id) if model_id else None
                if model is None or model.manufacturer_id != c.target_entity_id:
                    continue
            else:
                continue

            # 2. Property path matching
            if not _property_matches_conflict(property_path, c.field_path):
                continue

            # 3. Equivalence check (exclude identical/non-conflicting assertions)
            val_a = c.source_a_value.strip().lower()
            val_b = c.source_b_value.strip().lower()
            if c.source_a_id == c.source_b_id and val_a == val_b:
                continue
            if val_a == val_b:
                continue

            applicable.append(c)

        return applicable

    def _reference_item(
        self,
        property_path: str,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        *,
        unit: str | None = None,
        method: ComparisonMethod = ComparisonMethod.EXACT_MATCH,
        model_id: str | None = None,
    ) -> SpecificationComparisonItem:
        """Use only a property established for every applicable catalog candidate."""
        effective_model_id = (
            model_id
            if model_id is not None
            else (
                target_variant.model_id
                if target_variant
                else (candidate_variants[0].model_id if candidate_variants else None)
            )
        )

        applicable_conflicts = self._get_applicable_conflicts(
            property_path, target_variant, candidate_variants, effective_model_id
        )
        if applicable_conflicts:
            all_sources: set[str] = set()
            conflict_limitations: list[str] = []
            for c in applicable_conflicts:
                all_sources.add(c.source_a_id)
                all_sources.add(c.source_b_id)
                conflict_limitations.append(
                    f"Reference conflict ({c.conflict_id}): Source '{c.source_a_id}' ('{c.source_a_value}') "
                    f"vs Source '{c.source_b_id}' ('{c.source_b_value}'). {c.conflict_notes}"
                )
            sorted_sources = tuple(
                sorted(sid for sid in all_sources if self.catalog.get_source(sid) is not None)
            )
            if len(applicable_conflicts) == 1:
                c0 = applicable_conflicts[0]
                reason = (
                    f"Reference specification for '{property_path}' is disputed between conflicting sources "
                    f"({c0.source_a_id} claims '{c0.source_a_value}' vs {c0.source_b_id} claims '{c0.source_b_value}'); "
                    "no authoritative reference specification is available."
                )
            else:
                reason = (
                    f"Reference specification for '{property_path}' is disputed across "
                    f"{len(applicable_conflicts)} conflicting source assertions; "
                    "no authoritative reference specification is available."
                )

            return SpecificationComparisonItem(
                property_path=property_path,
                observed_value=None,
                reference_value=None,
                unit=unit,
                applicable_variant_id=target_variant.variant_id if target_variant else None,
                comparison_method=method,
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason=reason,
                limitations=tuple(conflict_limitations),
                source_ids=sorted_sources,
            )

        variants = (target_variant,) if target_variant else candidate_variants
        values = [_reference_value(v, property_path) for v in variants]
        sources = tuple(
            sorted(
                {
                    sid
                    for v in variants
                    for sid in (
                        v.source_ids
                        if property_path.startswith("network.")
                        else v.specifications.source_ids
                    )
                    if self.catalog.get_source(sid) is not None
                }
            )
        )
        for variant, value in zip(variants, values, strict=True):
            model = self.catalog.get_model(variant.model_id)
            citations = (
                variant.source_ids
                if property_path.startswith("network.")
                else variant.specifications.source_ids
            )
            authoritative = (
                bool(citations)
                and self.catalog.get_variant(variant.variant_id) == variant
                and model is not None
                and (not model.is_synthetic or self.catalog.test_only)
            )
            try:
                self.catalog.validate_variant_lineage(variant)
            except CatalogIntegrityError:
                authoritative = False
            for sid in citations:
                source = self.catalog.get_source(sid)
                if (
                    source is None
                    or (
                        source.is_synthetic
                        and (not self.catalog.test_only or model is None or not model.is_synthetic)
                    )
                    or not self.catalog.test_only
                    and not any(
                        claim.entity_id == variant.variant_id
                        and claim.property_path == property_path
                        and claim.reference_value_json
                        == json.dumps(value, sort_keys=True, separators=(",", ":"))
                        for claim in source.verified_claims
                    )
                ):
                    authoritative = False
            if not authoritative:
                return SpecificationComparisonItem(
                    property_path=property_path,
                    unit=unit,
                    comparison_method=method,
                    outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                    reference_value=None,
                    reason="Reference authority is missing, synthetic, unverified for this exact claim, or inconsistent with the catalog.",
                    source_ids=sources,
                    limitations=(
                        "No verified source support for every contributing candidate and exact value.",
                    ),
                )
        if not values or all(value is None for value in values):
            outcome = ComparisonOutcome.REFERENCE_UNAVAILABLE
            reason = "Reference specification unavailable for this property."
            reference = None
        elif any(value != values[0] for value in values):
            outcome = ComparisonOutcome.VARIANT_AMBIGUOUS
            reason = "Candidate variants differ or lack this property; exact variant required."
            reference = None
        else:
            outcome = ComparisonOutcome.INSUFFICIENT_EVIDENCE
            reason = "Comparable observation was not supplied." + (
                " Reference is shared-model candidate consensus; variant identity remains ambiguous."
                if target_variant is None
                else ""
            )
            reference = values[0]
        return SpecificationComparisonItem(
            property_path=property_path,
            reference_value=reference,
            unit=unit,
            applicable_variant_id=target_variant.variant_id if target_variant else None,
            comparison_method=method,
            outcome=outcome,
            reason=reason,
            source_ids=sources,
        )

    def _incomparable_measurement(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
        *,
        property_path: str,
        observation_keys: tuple[str, ...],
        unit: str,
        reason: str,
    ) -> None:
        item = self._reference_item(property_path, target_variant, candidate_variants, unit=unit)
        if item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE:
            items.append(item.model_copy(update={"limitations": item.limitations + (reason,)}))
            return
        if item.outcome == ComparisonOutcome.INSUFFICIENT_EVIDENCE:
            has_observation = any(observed.get(key) is not None for key in observation_keys)
            item = item.model_copy(
                update={
                    "outcome": (
                        ComparisonOutcome.NOT_COMPARABLE
                        if has_observation
                        else ComparisonOutcome.INSUFFICIENT_EVIDENCE
                    ),
                    "reason": reason,
                    "limitations": (
                        "No comparable physical measurement is established. Original telemetry remains in diagnostic evidence with its own units.",
                    ),
                }
            )
        items.append(item)

    def _compare_display_resolution(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        self._incomparable_measurement(
            target_variant,
            candidate_variants,
            observed,
            items,
            property_path="display.resolution",
            observation_keys=("width", "height", "display_width", "display_height", "mode_count")
            + tuple(f"mode{i}_{part}" for i in range(8) for part in ("width", "height", "rate")),
            unit="pixels",
            reason="Active display dimensions and OS-supported modes do not identify the physical panel's native resolution. No validated native-panel measurement is available; orientation is not a hardware mismatch.",
        )

    def _compare_display_refresh_rate(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        self._incomparable_measurement(
            target_variant,
            candidate_variants,
            observed,
            items,
            property_path="display.refresh_rate_hz",
            observation_keys=("refresh_rate", "mode_count")
            + tuple(f"mode{i}_{part}" for i in range(8) for part in ("width", "height", "rate")),
            unit="Hz",
            reason="An active refresh rate does not establish maximum refresh capability. The flat mode observations lack validated units and evidence binding; no arbitrary in-range rate proves supported capability.",
        )

    def _compare_battery_capacity(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        self._incomparable_measurement(
            target_variant,
            candidate_variants,
            observed,
            items,
            property_path="battery.rated_capacity_mah",
            observation_keys=("charge_counter",),
            unit="mAh",
            reason="Probe charge_counter measures remaining charge in uAh, not OEM-rated design capacity. No measurement of rated capacity is available. Remaining charge establishes neither battery health nor OEM origin.",
        )

    def _compare_soc_properties(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        property_path = "soc.core_count"
        reference = self._reference_item(property_path, target_variant, candidate_variants)
        if reference.outcome in (
            ComparisonOutcome.VARIANT_AMBIGUOUS,
            ComparisonOutcome.REFERENCE_UNAVAILABLE,
        ):
            if reference.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE:
                obs_cores = _extract_observed_number(
                    observed.get("cpu_cores", observed.get("core_count"))
                )
                if obs_cores is not None:
                    reference = reference.model_copy(update={"observed_value": int(obs_cores)})
            items.append(reference)
            return
        obs_cores = _extract_observed_number(observed.get("cpu_cores", observed.get("core_count")))

        ref_specs = (
            [target_variant.specifications]
            if target_variant
            else [v.specifications for v in candidate_variants]
        )
        socs = [s.soc for s in ref_specs if s.soc]
        if not socs:
            return

        ref_soc = socs[0]
        if obs_cores is None:
            items.append(
                SpecificationComparisonItem(
                    property_path=property_path,
                    observed_value=None,
                    reference_value=ref_soc.core_count,
                    unit="count",
                    applicable_variant_id=target_variant.variant_id if target_variant else None,
                    comparison_method=ComparisonMethod.EXACT_MATCH,
                    outcome=ComparisonOutcome.INSUFFICIENT_EVIDENCE,
                    reason="Observed CPU core count was not reported.",
                    limitations=(),
                    source_ids=reference.source_ids,
                )
            )
        else:
            is_match = int(obs_cores) == ref_soc.core_count
            items.append(
                SpecificationComparisonItem(
                    property_path=property_path,
                    observed_value=int(obs_cores),
                    reference_value=ref_soc.core_count,
                    unit="count",
                    applicable_variant_id=target_variant.variant_id if target_variant else None,
                    comparison_method=ComparisonMethod.EXACT_MATCH,
                    outcome=(
                        ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                        if is_match
                        else ComparisonOutcome.DIFFERS_FROM_REFERENCE
                    ),
                    reason=(
                        f"Observed {int(obs_cores)} CPU cores matches reference {ref_soc.core_count} cores."
                        if is_match
                        else f"Observed {int(obs_cores)} cores differs from reference {ref_soc.core_count} cores."
                    ),
                    limitations=(),
                    source_ids=reference.source_ids,
                )
            )

    def _compare_ram_capacity(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        self._incomparable_measurement(
            target_variant,
            candidate_variants,
            observed,
            items,
            property_path="memory.ram_total_bytes",
            observation_keys=("ram_total",),
            unit="bytes",
            reason="ram_total is OS-visible memory accessible to the kernel, not installed physical RAM. No validated installed-memory measurement or model-specific reservation mapping is available; no percentage allowance applies.",
        )

    def _compare_sensors_presence(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        for name in ("barometer", "nfc"):
            item = self._reference_item(
                f"sensors.{name}_present",
                target_variant,
                candidate_variants,
                method=ComparisonMethod.CAPABILITY_PRESENCE,
            )
            if item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE:
                value = observed.get(f"feature_{name}")
                valid = isinstance(value, (bool, int, float)) and value in (0, 1, True, False)
                if valid:
                    item = item.model_copy(update={"observed_value": bool(value)})
                items.append(item)
                continue
            if item.outcome == ComparisonOutcome.INSUFFICIENT_EVIDENCE:
                value = observed.get(f"feature_{name}")
                # Probe emits numeric booleans; EvidenceRecord normalizes them to float.
                # Arbitrary strings/objects must never become a truthy declaration.
                valid = isinstance(value, (bool, int, float)) and value in (0, 1)
                if valid:
                    item = item.model_copy(
                        update={
                            "observed_value": bool(value),
                            "outcome": (
                                ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                                if bool(value) == item.reference_value
                                else ComparisonOutcome.DIFFERS_FROM_REFERENCE
                            ),
                            "reason": f"Runtime {name} feature declaration ({bool(value)}) compared with reference declaration ({item.reference_value}).",
                        }
                    )
                else:
                    item = item.model_copy(
                        update={
                            "reason": f"Valid feature_{name} capability declaration unavailable; an enabled setting is not hardware-presence evidence.",
                        }
                    )
                item = item.model_copy(
                    update={
                        "limitations": (
                            "A system feature declaration does not verify physical function, component identity or OEM origin.",
                        )
                    }
                )
            items.append(item)

    def _compare_cameras(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        property_path = "camera.rear_cameras_count"
        reference = self._reference_item(property_path, target_variant, candidate_variants)
        if reference.outcome in (
            ComparisonOutcome.VARIANT_AMBIGUOUS,
            ComparisonOutcome.REFERENCE_UNAVAILABLE,
        ):
            if reference.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE:
                obs_rear_count = _extract_observed_number(
                    observed.get("rear_camera_count", observed.get("camera_rear_count"))
                )
                if obs_rear_count is not None:
                    reference = reference.model_copy(update={"observed_value": int(obs_rear_count)})
            items.append(reference)
            return
        obs_rear_count = _extract_observed_number(
            observed.get("rear_camera_count", observed.get("camera_rear_count"))
        )

        ref_specs = (
            [target_variant.specifications]
            if target_variant
            else [v.specifications for v in candidate_variants]
        )
        camera_specs = [s.camera for s in ref_specs if s.camera]
        if not camera_specs:
            return

        ref_camera = camera_specs[0]
        ref_count = len(ref_camera.rear_cameras)

        if obs_rear_count is None:
            items.append(
                SpecificationComparisonItem(
                    property_path=property_path,
                    observed_value=None,
                    reference_value=ref_count,
                    unit="count",
                    applicable_variant_id=target_variant.variant_id if target_variant else None,
                    comparison_method=ComparisonMethod.EXACT_MATCH,
                    outcome=ComparisonOutcome.INSUFFICIENT_EVIDENCE,
                    reason="Rear camera count telemetry was not captured.",
                    limitations=(),
                    source_ids=reference.source_ids,
                )
            )
        else:
            is_match = int(obs_rear_count) == ref_count
            items.append(
                SpecificationComparisonItem(
                    property_path=property_path,
                    observed_value=int(obs_rear_count),
                    reference_value=ref_count,
                    unit="count",
                    applicable_variant_id=target_variant.variant_id if target_variant else None,
                    comparison_method=ComparisonMethod.EXACT_MATCH,
                    outcome=(
                        ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                        if is_match
                        else ComparisonOutcome.DIFFERS_FROM_REFERENCE
                    ),
                    reason=(
                        f"Observed rear camera count ({int(obs_rear_count)}) matches reference ({ref_count}). "
                        f"Camera presence does NOT identify camera module or prove OEM origin."
                        if is_match
                        else f"Observed rear camera count ({int(obs_rear_count)}) differs from reference ({ref_count})."
                    ),
                    limitations=(
                        "Capturing an image or reporting a camera sensor count does not verify module authenticity.",
                    ),
                    source_ids=reference.source_ids,
                )
            )

    def _compare_network_configuration(
        self,
        target_variant: DeviceVariantReference | None,
        candidate_variants: tuple[DeviceVariantReference, ...],
        observed: dict[str, Any],
        items: list[SpecificationComparisonItem],
    ) -> None:
        property_path = "network.5g_mmwave_supported"
        reference = self._reference_item(property_path, target_variant, candidate_variants)
        if reference.outcome in (
            ComparisonOutcome.VARIANT_AMBIGUOUS,
            ComparisonOutcome.REFERENCE_UNAVAILABLE,
        ):
            obs_mmwave = observed.get("feature_5g_mmwave")
            if obs_mmwave is not None:
                reference = reference.model_copy(update={"observed_value": bool(obs_mmwave)})
            items.append(reference)
            return
        obs_mmwave = observed.get("feature_5g_mmwave")

        if obs_mmwave is None:
            items.append(reference)
            return

        if reference.reference_value is not None:
            ref_has_mmwave = reference.reference_value
            is_match = bool(obs_mmwave) == ref_has_mmwave
            consensus_note = (
                " Reference is shared-model candidate consensus; variant identity remains ambiguous."
                if target_variant is None
                else ""
            )
            items.append(
                SpecificationComparisonItem(
                    property_path=property_path,
                    observed_value=bool(obs_mmwave),
                    reference_value=ref_has_mmwave,
                    applicable_variant_id=target_variant.variant_id if target_variant else None,
                    comparison_method=ComparisonMethod.CAPABILITY_PRESENCE,
                    outcome=(
                        ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                        if is_match
                        else ComparisonOutcome.DIFFERS_FROM_REFERENCE
                    ),
                    reason=(
                        f"5G mmWave support ({bool(obs_mmwave)}) matches the catalog reference.{consensus_note}"
                        if is_match
                        else f"5G mmWave support differs: observed {bool(obs_mmwave)}, reference {ref_has_mmwave}.{consensus_note}"
                    ),
                    limitations=(),
                    source_ids=reference.source_ids,
                )
            )
        else:
            items.append(reference.model_copy(update={"observed_value": bool(obs_mmwave)}))
