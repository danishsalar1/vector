"""OEM Device Reference Database, Component Specifications & Evidence-Based Comparison."""

from .catalog import CatalogIntegrityError, ReferenceCatalog
from .comparator import SpecificationComparator
from .evidence_adapter import DiagnosticEvidenceAdapter, DiagnosticEvidenceComparison
from .importer import CatalogImportError, import_catalog_payload
from .performance import PerformanceReferenceManager
from .resolver import DeviceResolver
from .seed import build_seed_catalog, build_seed_payload, get_coverage_inventory

__all__ = [
    "CatalogImportError",
    "CatalogIntegrityError",
    "DeviceResolver",
    "DiagnosticEvidenceAdapter",
    "DiagnosticEvidenceComparison",
    "PerformanceReferenceManager",
    "ReferenceCatalog",
    "SpecificationComparator",
    "build_seed_catalog",
    "build_seed_payload",
    "get_coverage_inventory",
    "import_catalog_payload",
]
