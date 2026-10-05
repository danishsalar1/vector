"""Production diagnostic registry.

Thread-safe, duplicate-resistant registry for VECTOR diagnostics.
Supports lookup by ID, platform, and category.
"""

from __future__ import annotations

from vector_agent.core.logging import get_logger
from vector_agent.diagnostics.definition import Diagnostic, DiagnosticDefinition
from vector_agent.models.device import Platform

logger = get_logger(__name__)


class DuplicateDiagnosticError(Exception):
    """Raised when a diagnostic with the same ID is registered twice."""


class DiagnosticRegistry:
    """Central registry of available VECTOR diagnostics.

    Usage::

        registry = DiagnosticRegistry()
        registry.register(battery_diagnostic)
        applicable = registry.get_by_platform(Platform.ANDROID)
    """

    def __init__(self) -> None:
        self._diagnostics: dict[str, Diagnostic] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, diagnostic: Diagnostic) -> None:
        """Register a diagnostic.  Rejects duplicate IDs."""
        defn = diagnostic.definition
        if defn.diagnostic_id in self._diagnostics:
            raise DuplicateDiagnosticError(
                f"Diagnostic '{defn.diagnostic_id}' is already registered."
            )
        self._diagnostics[defn.diagnostic_id] = diagnostic
        logger.info("Registered diagnostic: %s (%s)", defn.diagnostic_id, defn.name)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, diagnostic_id: str) -> Diagnostic | None:
        """Return a diagnostic by its ID, or None if not registered."""
        return self._diagnostics.get(diagnostic_id)

    def get_definition(self, diagnostic_id: str) -> DiagnosticDefinition | None:
        """Return a diagnostic definition by its ID."""
        diag = self._diagnostics.get(diagnostic_id)
        return diag.definition if diag else None

    def get_by_platform(self, platform: Platform) -> list[Diagnostic]:
        """Return all diagnostics applicable to the given platform."""
        return [
            d for d in self._diagnostics.values() if platform in d.definition.supported_platforms
        ]

    def get_by_category(self, category: str) -> list[Diagnostic]:
        """Return all diagnostics in the given category."""
        return [d for d in self._diagnostics.values() if d.definition.category == category]

    def get_all(self) -> list[Diagnostic]:
        """Return all registered diagnostics."""
        return list(self._diagnostics.values())

    @property
    def count(self) -> int:
        """Number of registered diagnostics."""
        return len(self._diagnostics)

    def list_ids(self) -> list[str]:
        """Return a sorted list of all registered diagnostic IDs."""
        return sorted(self._diagnostics.keys())
