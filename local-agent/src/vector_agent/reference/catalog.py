"""In-memory thread-safe OEM Device Reference Catalog.

Provides indexing, lookup, versioning, conflict tracking, and validation for:
- Manufacturers
- Device models
- Device variants
- Component specifications
- Performance metric references
- Reference sources
"""

from __future__ import annotations

import copy
import threading
from typing import Any

from pydantic import BaseModel

from vector_agent.models.reference import (
    DeviceModelReference,
    DeviceVariantReference,
    ManufacturerReference,
    PerformanceMetricReference,
    ReferenceConflict,
    ReferenceSource,
)


class CatalogIntegrityError(ValueError):
    """Raised when catalog relationships or referential integrity fail."""


class ReferenceCatalog:
    """Thread-safe reference database for validated OEM hardware specifications."""

    def __init__(self, *, test_only: bool = False) -> None:
        self.test_only = test_only
        self._lock = threading.RLock()
        self._sources: dict[str, ReferenceSource] = {}
        self._manufacturers: dict[str, ManufacturerReference] = {}
        self._manufacturer_aliases: dict[str, str] = {}  # alias.lower() -> manufacturer_id
        self._models: dict[str, DeviceModelReference] = {}
        self._models_by_mfg: dict[str, list[str]] = {}  # mfg_id -> [model_ids]
        self._variants: dict[str, DeviceVariantReference] = {}
        self._variants_by_model: dict[str, list[str]] = {}  # model_id -> [variant_ids]
        self._conflicts: list[ReferenceConflict] = []
        self._performance_metrics: dict[str, PerformanceMetricReference] = {}

    def _validate_citations(self, record: BaseModel, *, synthetic: bool = False) -> None:
        """Walk all nested records so specification/component citations cannot escape."""
        for name in type(record).model_fields:
            value = getattr(record, name)
            if name in ("source_id", "source_ids"):
                for sid in (value,) if name == "source_id" else value:
                    source = self._sources.get(sid)
                    if source is None:
                        raise CatalogIntegrityError(f"Record cites unknown source '{sid}'.")
                    if source.is_synthetic and not synthetic:
                        raise CatalogIntegrityError(
                            "Synthetic citation cannot support a real entity."
                        )
            elif isinstance(value, BaseModel):
                self._validate_citations(value, synthetic=synthetic)
            elif isinstance(value, tuple):
                for child in value:
                    if isinstance(child, BaseModel):
                        self._validate_citations(child, synthetic=synthetic)

    def snapshot(self) -> ReferenceCatalog:
        """Detached, point-in-time state; nested component mappings are copied too."""
        with self._lock:
            result = ReferenceCatalog(test_only=self.test_only)
            for key, value in vars(self).items():
                if key != "_lock":
                    setattr(result, key, copy.deepcopy(value))
            return result

    def validate_variant_lineage(self, variant: DeviceVariantReference) -> None:
        """Recheck parent/citation integrity at a defensive comparison boundary."""
        with self._lock:
            model = self._models.get(variant.model_id)
            manufacturer = self._manufacturers.get(model.manufacturer_id) if model else None
            if (
                model is None
                or manufacturer is None
                or self._variants.get(variant.variant_id) != variant
            ):
                raise CatalogIntegrityError("Variant lineage is absent or inconsistent.")
            if model.is_synthetic and not self.test_only:
                raise CatalogIntegrityError("Synthetic lineage is not a production reference.")
            for record in (manufacturer, model, variant):
                self._validate_citations(record, synthetic=model.is_synthetic)

    # ----------------------------------------------------------
    # Registration with validation
    # ----------------------------------------------------------

    def register_source(self, source: ReferenceSource) -> None:
        """Register a validated citation source."""
        with self._lock:
            if source.is_synthetic and not self.test_only:
                raise CatalogIntegrityError(
                    "Synthetic sources require an explicit test-only catalog."
                )
            existing = self._sources.get(source.source_id)
            if existing is not None and existing != source:
                raise CatalogIntegrityError(
                    f"Conflicting source registered with ID '{source.source_id}'."
                )
            self._sources[source.source_id] = source.model_copy(deep=True)

    def register_manufacturer(self, mfg: ManufacturerReference) -> None:
        """Register a canonical manufacturer and index aliases."""
        with self._lock:
            self._validate_citations(mfg, synthetic=self.test_only)
            for alias in (mfg.canonical_name, *mfg.aliases):
                owner = self._manufacturer_aliases.get(alias.lower())
                if owner is not None and owner != mfg.manufacturer_id:
                    raise CatalogIntegrityError(
                        "Manufacturer alias already belongs to another entity."
                    )
            if mfg.source_id not in self._sources:
                raise CatalogIntegrityError(
                    f"Manufacturer '{mfg.manufacturer_id}' cites unknown source '{mfg.source_id}'."
                )
            existing = self._manufacturers.get(mfg.manufacturer_id)
            if existing is not None and existing != mfg:
                raise CatalogIntegrityError(
                    f"Conflicting manufacturer registered with ID '{mfg.manufacturer_id}'."
                )
            self._manufacturers[mfg.manufacturer_id] = mfg.model_copy(deep=True)
            self._manufacturer_aliases[mfg.canonical_name.lower()] = mfg.manufacturer_id
            for alias in mfg.aliases:
                self._manufacturer_aliases[alias.lower()] = mfg.manufacturer_id

    def register_model(self, model: DeviceModelReference) -> None:
        """Register a device model and link to manufacturer."""
        with self._lock:
            if model.is_synthetic and not self.test_only:
                raise CatalogIntegrityError(
                    "Synthetic model requires an explicit test-only catalog."
                )
            self._validate_citations(model, synthetic=model.is_synthetic)
            if model.manufacturer_id not in self._manufacturers:
                raise CatalogIntegrityError(
                    f"Model '{model.model_id}' cites unknown manufacturer '{model.manufacturer_id}'."
                )
            self._validate_citations(
                self._manufacturers[model.manufacturer_id], synthetic=model.is_synthetic
            )
            for sid in model.source_ids:
                if sid not in self._sources:
                    raise CatalogIntegrityError(
                        f"Model '{model.model_id}' cites unknown source '{sid}'."
                    )
            for comp in model.supported_component_alternatives:
                if comp.source_id not in self._sources:
                    raise CatalogIntegrityError(
                        f"Model '{model.model_id}' component '{comp.component_role}' cites unknown source '{comp.source_id}'."
                    )
            existing = self._models.get(model.model_id)
            if existing is not None and existing != model:
                raise CatalogIntegrityError(
                    f"Conflicting model registered with ID '{model.model_id}'."
                )
            self._models[model.model_id] = model.model_copy(deep=True)
            model_list = self._models_by_mfg.setdefault(model.manufacturer_id, [])
            if model.model_id not in model_list:
                model_list.append(model.model_id)

    def register_variant(self, variant: DeviceVariantReference) -> None:
        """Register a device variant and link to parent model."""
        with self._lock:
            if variant.model_id not in self._models:
                raise CatalogIntegrityError(
                    f"Variant '{variant.variant_id}' cites unknown model '{variant.model_id}'."
                )
            self._validate_citations(variant, synthetic=self._models[variant.model_id].is_synthetic)
            for sid in variant.source_ids:
                if sid not in self._sources:
                    raise CatalogIntegrityError(
                        f"Variant '{variant.variant_id}' cites unknown source '{sid}'."
                    )
            for comp in variant.supported_components:
                if comp.source_id not in self._sources:
                    raise CatalogIntegrityError(
                        f"Variant '{variant.variant_id}' component '{comp.component_role}' cites unknown source '{comp.source_id}'."
                    )
            existing = self._variants.get(variant.variant_id)
            if existing is not None and existing != variant:
                raise CatalogIntegrityError(
                    f"Conflicting variant registered with ID '{variant.variant_id}'."
                )
            self._variants[variant.variant_id] = variant.model_copy(deep=True)
            var_list = self._variants_by_model.setdefault(variant.model_id, [])
            if variant.variant_id not in var_list:
                var_list.append(variant.variant_id)

    def register_conflict(self, conflict: ReferenceConflict) -> None:
        """Record an explicit conflict between two reference sources."""
        with self._lock:
            targets = {
                "manufacturer": self._manufacturers,
                "model": self._models,
                "variant": self._variants,
            }
            # Components have roles, not globally unique catalog IDs in v1.
            if conflict.target_entity_type == "component":
                raise CatalogIntegrityError(
                    "Component conflicts require an entity-scoped target; standalone component IDs are not modeled."
                )
            if conflict.target_entity_id not in targets[conflict.target_entity_type]:
                raise CatalogIntegrityError("Conflict target does not exist.")
            if not conflict.field_path.strip():
                raise CatalogIntegrityError("Conflict path must not be blank.")
            for existing in self._conflicts:
                if existing.conflict_id == conflict.conflict_id and existing != conflict:
                    raise CatalogIntegrityError("Conflicting duplicate conflict ID.")
            if (
                conflict.source_a_id not in self._sources
                or conflict.source_b_id not in self._sources
            ):
                raise CatalogIntegrityError(
                    f"Conflict '{conflict.conflict_id}' cites unknown source ID."
                )
            if conflict not in self._conflicts:
                self._conflicts.append(conflict)

    def register_performance_metric(self, metric: PerformanceMetricReference) -> None:
        """Register a performance metric reference."""
        with self._lock:
            self._validate_citations(metric, synthetic=self.test_only)
            if metric.source_id not in self._sources:
                raise CatalogIntegrityError(
                    f"Metric '{metric.metric_id}' cites unknown source '{metric.source_id}'."
                )
            for mid in metric.applicable_model_ids:
                if mid not in self._models:
                    raise CatalogIntegrityError(
                        f"Metric '{metric.metric_id}' cites unknown model '{mid}'."
                    )
            for vid in metric.applicable_variant_ids:
                variant = self._variants.get(vid)
                if variant is None or variant.model_id not in metric.applicable_model_ids:
                    raise CatalogIntegrityError(
                        "Performance variant must belong to an applicable model."
                    )
            existing = self._performance_metrics.get(metric.metric_id)
            if existing is not None and existing != metric:
                raise CatalogIntegrityError(
                    f"Conflicting metric registered with ID '{metric.metric_id}'."
                )
            self._performance_metrics[metric.metric_id] = metric.model_copy(deep=True)

    # ----------------------------------------------------------
    # Queries & Lookups
    # ----------------------------------------------------------

    def get_source(self, source_id: str) -> ReferenceSource | None:
        with self._lock:
            return self._sources.get(source_id)

    def get_manufacturer(self, manufacturer_id: str) -> ManufacturerReference | None:
        with self._lock:
            return self._manufacturers.get(manufacturer_id)

    def find_manufacturer_by_name_or_alias(self, query: str) -> ManufacturerReference | None:
        """Case-insensitive manufacturer resolution by canonical name or known alias."""
        with self._lock:
            q = query.strip().lower()
            mfg_id = self._manufacturer_aliases.get(q)
            if mfg_id:
                return self._manufacturers.get(mfg_id)
            # Direct ID match
            if q in self._manufacturers:
                return self._manufacturers[q]
            return None

    def get_model(self, model_id: str) -> DeviceModelReference | None:
        with self._lock:
            return copy.deepcopy(self._models.get(model_id))

    def find_models_for_manufacturer(
        self, manufacturer_id: str
    ) -> tuple[DeviceModelReference, ...]:
        with self._lock:
            model_ids = self._models_by_mfg.get(manufacturer_id, [])
            return tuple(copy.deepcopy(self._models[mid]) for mid in sorted(model_ids))

    def get_variant(self, variant_id: str) -> DeviceVariantReference | None:
        with self._lock:
            return copy.deepcopy(self._variants.get(variant_id))

    def find_variants_for_model(self, model_id: str) -> tuple[DeviceVariantReference, ...]:
        with self._lock:
            variant_ids = self._variants_by_model.get(model_id, [])
            return tuple(copy.deepcopy(self._variants[vid]) for vid in sorted(variant_ids))

    def all_models(self) -> tuple[DeviceModelReference, ...]:
        with self._lock:
            return tuple(copy.deepcopy(self._models[mid]) for mid in sorted(self._models))

    def all_variants(self) -> tuple[DeviceVariantReference, ...]:
        with self._lock:
            return tuple(copy.deepcopy(self._variants[vid]) for vid in sorted(self._variants))

    def all_manufacturers(self) -> tuple[ManufacturerReference, ...]:
        with self._lock:
            return tuple(self._manufacturers[mid] for mid in sorted(self._manufacturers))

    def all_sources(self) -> tuple[ReferenceSource, ...]:
        with self._lock:
            return tuple(self._sources[sid] for sid in sorted(self._sources))

    def get_conflicts_for_entity(
        self, entity_type: str, entity_id: str
    ) -> tuple[ReferenceConflict, ...]:
        with self._lock:
            matches = [
                c
                for c in self._conflicts
                if c.target_entity_type == entity_type and c.target_entity_id == entity_id
            ]
            return tuple(matches)

    def get_performance_metric(self, metric_id: str) -> PerformanceMetricReference | None:
        with self._lock:
            return self._performance_metrics.get(metric_id)

    def export_summary(self) -> dict[str, Any]:
        """Summary metrics of catalog contents."""
        with self._lock:
            # Non-synthetic classification and retrieval metadata do not verify claim support.
            unverified_sources = sum(
                1 for s in self._sources.values() if not s.is_synthetic and not s.verified_claims
            )
            synthetic_sources = sum(1 for s in self._sources.values() if s.is_synthetic)
            return {
                "manufacturers_count": len(self._manufacturers),
                "models_count": len(self._models),
                "variants_count": len(self._variants),
                "sources_count": len(self._sources),
                "verified_sources_count": sum(
                    1 for s in self._sources.values() if not s.is_synthetic and s.verified_claims
                ),
                "unverified_sources_count": unverified_sources,
                "synthetic_sources_count": synthetic_sources,
                "conflicts_count": len(self._conflicts),
                "performance_metrics_count": len(self._performance_metrics),
            }

    def all_conflicts(self) -> tuple[ReferenceConflict, ...]:
        with self._lock:
            return tuple(self._conflicts)

    get_all_conflicts = all_conflicts
    get_all_manufacturers = all_manufacturers
    get_all_variants = all_variants
    get_all_models = all_models
    get_all_sources = all_sources
    summary = export_summary
