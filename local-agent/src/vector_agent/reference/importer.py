"""Controlled, atomic reference catalog importer.

Features:
- Strong schema validation against CATALOG_SCHEMA_VERSION ("vector-catalog-v1")
- Atomic transaction: stages all records into an isolated catalog before committing
- Fail-closed: invalid records, unit mismatches, or orphan citations abort the entire import
- Idempotent: re-importing identical payloads is safe and non-duplicating
- Conflict detection: preserves conflicting source claims as ReferenceConflict records
- Bounded payload protection against memory exhaustion
"""

from __future__ import annotations

import copy
from typing import Any

from vector_agent.models.reference import (
    CATALOG_SCHEMA_VERSION,
    DeviceModelReference,
    DeviceVariantReference,
    ManufacturerReference,
    PerformanceMetricReference,
    ReferenceConflict,
    ReferenceSource,
)

from .catalog import CatalogIntegrityError, ReferenceCatalog

MAX_IMPORT_SOURCES = 1000
MAX_IMPORT_ENTITIES = 5000


class CatalogImportError(ValueError):
    """Raised when catalog import validation or integrity checks fail."""


def import_catalog_payload(
    payload: dict[str, Any],
    target_catalog: ReferenceCatalog,
    *,
    curator_authorized: bool = False,
) -> dict[str, int]:
    """Atomically import a catalog payload.

    ``verified_claims`` are source-inspection records that unlock definitive
    production comparisons. An ordinary import is untrusted and may not carry
    them; only a caller that explicitly asserts ``curator_authorized=True`` (a
    reviewed curation workflow) or a test-only catalog may. This flag is a
    process-local contract, not cryptographic attestation.
    """
    # Keep clone, validation and replacement within one transaction. RLock allows
    # existing registration/query helpers to be reused without lost updates.
    with target_catalog._lock:
        return _import_locked(payload, target_catalog, curator_authorized=curator_authorized)


def _import_locked(
    payload: dict[str, Any], target_catalog: ReferenceCatalog, *, curator_authorized: bool = False
) -> dict[str, int]:
    """Validate and atomically apply an import payload to the target catalog.

    Returns summary of imported entity counts.
    """
    if not isinstance(payload, dict):
        raise CatalogImportError("Import payload must be a JSON dictionary.")

    version = payload.get("schema_version")
    if version != CATALOG_SCHEMA_VERSION:
        raise CatalogImportError(
            f"Unsupported catalog schema version '{version}'. Expected '{CATALOG_SCHEMA_VERSION}'."
        )

    sources_raw = payload.get("sources", [])
    manufacturers_raw = payload.get("manufacturers", [])
    models_raw = payload.get("models", [])
    variants_raw = payload.get("variants", [])
    conflicts_raw = payload.get("conflicts", [])
    performance_raw = payload.get("performance_metrics", [])

    if any(
        not isinstance(rows, list)
        for rows in (
            sources_raw,
            manufacturers_raw,
            models_raw,
            variants_raw,
            conflicts_raw,
            performance_raw,
        )
    ):
        raise CatalogImportError("Catalog sections must be JSON arrays.")

    total_entities = (
        len(sources_raw)
        + len(manufacturers_raw)
        + len(models_raw)
        + len(variants_raw)
        + len(conflicts_raw)
        + len(performance_raw)
    )
    if len(sources_raw) > MAX_IMPORT_SOURCES:
        raise CatalogImportError(
            f"Sources count {len(sources_raw)} exceeds safe limit {MAX_IMPORT_SOURCES}."
        )

    if total_entities > MAX_IMPORT_ENTITIES:
        raise CatalogImportError(
            f"Payload contains {total_entities} entities, exceeding maximum allowed {MAX_IMPORT_ENTITIES}."
        )

    if not (curator_authorized or target_catalog.test_only):
        for idx, s_data in enumerate(sources_raw):
            if isinstance(s_data, dict) and s_data.get("verified_claims"):
                raise CatalogImportError(
                    f"Invalid source record at index {idx}: an untrusted import cannot supply "
                    "verified_claims; curator authorization is required."
                )

    # 1. Stage in an isolated catalog clone to ensure atomicity
    staging = ReferenceCatalog(test_only=target_catalog.test_only)

    # Copy existing records into staging to test cumulative consistency
    with target_catalog._lock:
        for s in target_catalog.all_sources():
            staging.register_source(s)
        for m in target_catalog.all_manufacturers():
            staging.register_manufacturer(m)
        for mod in target_catalog.all_models():
            staging.register_model(mod)
        for var in target_catalog.all_variants():
            staging.register_variant(var)
        for c in target_catalog._conflicts:
            staging.register_conflict(c)
        for p in target_catalog._performance_metrics.values():
            staging.register_performance_metric(p)

    try:
        # Register sources
        for idx, s_data in enumerate(sources_raw):
            try:
                src = ReferenceSource.model_validate(s_data)
                staging.register_source(src)
            except Exception as e:
                raise CatalogImportError(f"Invalid source record at index {idx}: {e}") from e

        # Register manufacturers
        for idx, m_data in enumerate(manufacturers_raw):
            try:
                mfg = ManufacturerReference.model_validate(m_data)
                staging.register_manufacturer(mfg)
            except Exception as e:
                raise CatalogImportError(f"Invalid manufacturer record at index {idx}: {e}") from e

        # Register models
        for idx, mod_data in enumerate(models_raw):
            try:
                mod = DeviceModelReference.model_validate(mod_data)
                staging.register_model(mod)
            except Exception as e:
                raise CatalogImportError(f"Invalid model record at index {idx}: {e}") from e

        # Register variants
        for idx, var_data in enumerate(variants_raw):
            try:
                var = DeviceVariantReference.model_validate(var_data)
                staging.register_variant(var)
            except Exception as e:
                raise CatalogImportError(f"Invalid variant record at index {idx}: {e}") from e

        # Register conflicts
        for idx, c_data in enumerate(conflicts_raw):
            try:
                conf = ReferenceConflict.model_validate(c_data)
                staging.register_conflict(conf)
            except Exception as e:
                raise CatalogImportError(f"Invalid conflict record at index {idx}: {e}") from e

        # Register performance metrics
        for idx, p_data in enumerate(performance_raw):
            try:
                perf = PerformanceMetricReference.model_validate(p_data)
                staging.register_performance_metric(perf)
            except Exception as e:
                raise CatalogImportError(
                    f"Invalid performance metric record at index {idx}: {e}"
                ) from e

    except CatalogIntegrityError as e:
        raise CatalogImportError(f"Catalog integrity check failed during staging: {e}") from e

    # 2. Atomically commit staging state to target_catalog
    with target_catalog._lock:
        target_catalog._sources = copy.deepcopy(staging._sources)
        target_catalog._manufacturers = copy.deepcopy(staging._manufacturers)
        target_catalog._manufacturer_aliases = copy.deepcopy(staging._manufacturer_aliases)
        target_catalog._models = copy.deepcopy(staging._models)
        target_catalog._models_by_mfg = copy.deepcopy(staging._models_by_mfg)
        target_catalog._variants = copy.deepcopy(staging._variants)
        target_catalog._variants_by_model = copy.deepcopy(staging._variants_by_model)
        target_catalog._conflicts = copy.deepcopy(staging._conflicts)
        target_catalog._performance_metrics = copy.deepcopy(staging._performance_metrics)

    return {
        "sources_imported": len(sources_raw),
        "manufacturers_imported": len(manufacturers_raw),
        "models_imported": len(models_raw),
        "variants_imported": len(variants_raw),
        "conflicts_imported": len(conflicts_raw),
        "performance_metrics_imported": len(performance_raw),
    }
