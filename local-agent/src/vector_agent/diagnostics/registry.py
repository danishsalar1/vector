"""Production diagnostic registry.

Thread-safe, duplicate-resistant registry for VECTOR diagnostics.
Supports lookup by ID, platform, and category.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from vector_agent.core.logging import get_logger
from vector_agent.diagnostics.definition import Diagnostic, DiagnosticDefinition
from vector_agent.models.device import Platform

if TYPE_CHECKING:
    from vector_agent.devices.android.bridge import AndroidDeviceBridge

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
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, diagnostic: Diagnostic) -> None:
        """Register a diagnostic.  Rejects duplicate IDs."""
        with self._lock:
            defn = diagnostic.definition
            if defn.diagnostic_id in self._diagnostics:
                raise DuplicateDiagnosticError(
                    f"Diagnostic '{defn.diagnostic_id}' is already registered."
                )
            self._diagnostics[defn.diagnostic_id] = diagnostic
            logger.info("Registered diagnostic: %s (%s)", defn.diagnostic_id, defn.name)

    def clear(self) -> None:
        """Clear all registered diagnostics (used for testing)."""
        with self._lock:
            self._diagnostics.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, diagnostic_id: str) -> Diagnostic | None:
        """Return a diagnostic by its ID, or None if not registered."""
        with self._lock:
            return self._diagnostics.get(diagnostic_id)

    def get_definition(self, diagnostic_id: str) -> DiagnosticDefinition | None:
        """Return a diagnostic definition by its ID."""
        with self._lock:
            diag = self._diagnostics.get(diagnostic_id)
            return diag.definition if diag else None

    def get_by_platform(self, platform: Platform) -> list[Diagnostic]:
        """Return all diagnostics applicable to the given platform."""
        with self._lock:
            return [
                d
                for d in self._diagnostics.values()
                if platform in d.definition.supported_platforms
            ]

    def get_by_category(self, category: str) -> list[Diagnostic]:
        """Return all diagnostics in the given category."""
        with self._lock:
            return [d for d in self._diagnostics.values() if d.definition.category == category]

    def get_all(self) -> list[Diagnostic]:
        """Return all registered diagnostics."""
        with self._lock:
            return list(self._diagnostics.values())

    def get_definitions(self) -> list[DiagnosticDefinition]:
        """Return all registered diagnostic definitions."""
        with self._lock:
            return [d.definition for d in self._diagnostics.values()]

    def get_definitions_by_platform(self, platform: Platform) -> list[DiagnosticDefinition]:
        """Return diagnostic definitions applicable to the given platform."""
        with self._lock:
            return [
                d.definition
                for d in self._diagnostics.values()
                if platform in d.definition.supported_platforms
            ]

    def get_definitions_by_category(self, category: str) -> list[DiagnosticDefinition]:
        """Return diagnostic definitions in the given category."""
        with self._lock:
            return [
                d.definition
                for d in self._diagnostics.values()
                if d.definition.category == category
            ]

    @property
    def count(self) -> int:
        """Number of registered diagnostics."""
        with self._lock:
            return len(self._diagnostics)

    def list_ids(self) -> list[str]:
        """Return a sorted list of all registered diagnostic IDs."""
        with self._lock:
            return sorted(self._diagnostics.keys())


def create_default_registry(
    bridge: AndroidDeviceBridge | None = None,
) -> DiagnosticRegistry:
    """Create and return a DiagnosticRegistry pre-populated with standard diagnostics."""
    registry = DiagnosticRegistry()
    from vector_agent.devices.android.bridge import AndroidDeviceBridge
    from vector_agent.diagnostics.battery.battery_diagnostic import BatteryTelemetryDiagnostic
    from vector_agent.diagnostics.camera.camera_diagnostic import CameraInventoryDiagnostic
    from vector_agent.diagnostics.display.display_diagnostic import DisplayMetricsDiagnostic
    from vector_agent.diagnostics.memory.memory_diagnostic import MemoryTelemetryDiagnostic
    from vector_agent.diagnostics.storage.storage_diagnostic import StorageTelemetryDiagnostic
    from vector_agent.diagnostics.thermal.thermal_diagnostic import ThermalTelemetryDiagnostic

    if bridge is None:
        from vector_agent.core.config import get_settings

        bridge = AndroidDeviceBridge(adb_path=get_settings().adb_path)

    registry.register(BatteryTelemetryDiagnostic(bridge))
    registry.register(StorageTelemetryDiagnostic(bridge))
    registry.register(MemoryTelemetryDiagnostic(bridge))
    registry.register(ThermalTelemetryDiagnostic(bridge))
    registry.register(DisplayMetricsDiagnostic(bridge))
    registry.register(CameraInventoryDiagnostic(bridge))
    return registry
