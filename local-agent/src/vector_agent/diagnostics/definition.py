"""Production diagnostic definition and protocol.

DiagnosticDefinition: metadata describing a diagnostic's identity, applicability,
and execution constraints.

Diagnostic: protocol for a runnable diagnostic that produces a DiagnosticResult.

These are platform-neutral. Android/iOS-specific behaviour belongs in concrete
implementations, not in this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticResult,
    Platform,
)


@dataclass(frozen=True)
class DiagnosticDefinition:
    """Metadata for a single VECTOR diagnostic.

    Immutable after creation.  Registered once and queried by the scan planner
    or registry.  Fields are the minimum required by the production contract.
    """

    diagnostic_id: str
    """Unique stable identifier, e.g. 'battery_telemetry'."""

    name: str
    """Human-readable name, e.g. 'Battery Telemetry Verification'."""

    category: str
    """Diagnostic category, e.g. 'battery', 'identity', 'sensors'."""

    supported_platforms: frozenset[Platform] = field(
        default_factory=lambda: frozenset({Platform.ANDROID, Platform.IOS})
    )
    """Platforms on which this diagnostic is applicable."""

    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    """Capability names the device must expose for this diagnostic to run.

    Empty means no capability gate — the diagnostic determines its own
    applicability.  Capability discovery is not built yet; this field
    prepares the contract without adding a runtime dependency.
    """

    automation_level: AutomationLevel = AutomationLevel.AUTOMATIC
    """Whether this diagnostic runs without user interaction."""

    timeout_seconds: float = 30.0
    """Maximum wall-clock time for a single execution."""


class Diagnostic(Protocol):
    """Protocol that every runnable diagnostic must satisfy.

    The contract is intentionally small so that adding diagnostic #31
    is routine rather than requiring framework-wide changes.

    Future extensions (event streams, progress callbacks) can be added
    via optional mixin protocols without breaking existing implementations.
    """

    @property
    def definition(self) -> DiagnosticDefinition:
        """Return the static metadata for this diagnostic."""
        ...

    def is_supported(self, platform: Platform) -> bool:
        """Return True if this diagnostic can run on the given platform.

        Implementations may apply additional runtime checks beyond the
        platform gate (e.g., required capabilities, ADB availability).
        """
        ...

    def execute(self, *, device_id: str, serial: str) -> DiagnosticResult:
        """Run the diagnostic and return a structured result.

        Args:
            device_id: Opaque VECTOR device identifier (safe for API/logs).
            serial: Validated platform-specific device identifier (internal
                    use only — never exposed in API responses).

        Returns:
            DiagnosticResult backed by EvidenceRecord(s).

        The implementation must:
        - Populate at least one EvidenceRecord on success.
        - Return INCONCLUSIVE when evidence is insufficient rather than
          fabricating a PASS or FAIL.
        - Return ERROR when the diagnostic itself crashes, not when the
          device lacks the capability (that is UNSUPPORTED).
        - Set started_at / completed_at / duration_seconds on the result.
        """
        ...
