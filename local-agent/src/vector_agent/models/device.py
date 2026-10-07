"""VECTOR Pydantic models for devices and capabilities.

These are the canonical data structures shared by:
- Device bridges (Android, iOS)
- Diagnostic engine
- API layer
- Intelligence engine (via serialization)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

# ============================================================
# Enumerations
# ============================================================


class Platform(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    UNKNOWN = "UNKNOWN"


class ConnectionState(StrEnum):
    """Connection state for a detected device."""

    CONNECTED = "CONNECTED"
    UNAUTHORIZED = "UNAUTHORIZED"
    OFFLINE = "OFFLINE"
    MISSING_DRIVER = "MISSING_DRIVER"
    ADB_NOT_FOUND = "ADB_NOT_FOUND"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    NOT_TRUSTED = "NOT_TRUSTED"
    PAIRING_REQUIRED = "PAIRING_REQUIRED"
    DRIVER_MISSING = "DRIVER_MISSING"
    LIBIMOBILEDEVICE_MISSING = "LIBIMOBILEDEVICE_MISSING"
    RESTRICTED_INFORMATION = "RESTRICTED_INFORMATION"
    UNKNOWN = "UNKNOWN"


class DeviceAuthorizationState(StrEnum):
    """Platform-neutral authorization state for a detected device."""

    UNKNOWN = "UNKNOWN"
    AUTHORIZED = "AUTHORIZED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    RESTRICTED = "RESTRICTED"


class PairingState(StrEnum):
    """Result state for explicit device pairing operation."""

    PAIRED = "PAIRED"
    ALREADY_PAIRED = "ALREADY_PAIRED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    RESTRICTED = "RESTRICTED"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class DevicePairResponse(BaseModel):
    """Response returned by explicit device pairing action."""

    device_id: str
    status: PairingState
    message: str


class CapabilityStatus(StrEnum):
    """Whether a hardware capability is present on a device."""

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    RESTRICTED = "RESTRICTED"
    NOT_REPORTED = "NOT_REPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class VerificationLevel(StrEnum):
    """Verification level for capability knowledge or diagnostic observations.

    LEVEL 1 - RUNTIME_DETECTION: Feature declared/observed at runtime via OS or system services.
    LEVEL 2 - FUNCTIONAL_VERIFICATION: Component produced valid operational samples or responses.
    LEVEL 3 - REFERENCE_COMPARISON: Hardware presence evaluated against trusted factory specification.
    """

    RUNTIME_DETECTION = "RUNTIME_DETECTION"
    FUNCTIONAL_VERIFICATION = "FUNCTIONAL_VERIFICATION"
    REFERENCE_COMPARISON = "REFERENCE_COMPARISON"


class DiagnosticStatus(StrEnum):
    """Result status for an individual diagnostic test."""

    PASS = "PASS"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    RESTRICTED = "RESTRICTED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"


class AutomationLevel(StrEnum):
    """How automated a given diagnostic is."""

    AUTOMATIC = "AUTOMATIC"
    PARTIALLY_AUTOMATIC = "PARTIALLY_AUTOMATIC"
    ASSISTED = "ASSISTED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceSourceType(StrEnum):
    """Where evidence for a diagnostic was collected from."""

    ADB_GETPROP = "ADB_GETPROP"
    ADB_DUMPSYS = "ADB_DUMPSYS"
    ADB_SHELL = "ADB_SHELL"
    ANDROID_SYSTEM_SERVICE = "ANDROID_SYSTEM_SERVICE"
    VECTOR_PROBE = "VECTOR_PROBE"
    LIBIMOBILEDEVICE = "LIBIMOBILEDEVICE"
    IDEVICEINFO = "IDEVICEINFO"
    IDEVICEDIAGNOSTICS = "IDEVICEDIAGNOSTICS"
    DEVICE_METADATA = "DEVICE_METADATA"
    BENCHMARK = "BENCHMARK"
    USER_ASSISTED = "USER_ASSISTED"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"


class ScanState(StrEnum):
    """Lifecycle state of a VECTOR scan."""

    IDLE = "IDLE"
    DISCOVERING = "DISCOVERING"
    CONNECTED = "CONNECTED"
    PROFILING = "PROFILING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    SCORING = "SCORING"
    REPORTING = "REPORTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DISCONNECTED = "DISCONNECTED"


class ScanLifecycleState(StrEnum):
    """Canonical lifecycle state of a VECTOR scan session."""

    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TrustEngineStatus(StrEnum):
    """Readiness state of the Trust Intelligence engine.

    While NOT_READY, trust_score must remain None on ScanSummary.
    This prevents placeholder fuzzy inference from being exposed
    as a legitimate Trust Score.
    """

    NOT_READY = "NOT_READY"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"


# ============================================================
# Device models
# ============================================================


class DeviceIdentity(BaseModel):
    """Identified properties of a connected device."""

    platform: Platform = Platform.UNKNOWN
    manufacturer: str | None = None
    model: str | None = None
    marketing_name: str | None = None

    # Android-specific
    android_version: str | None = None
    android_sdk_level: int | None = None
    build_fingerprint: str | None = None
    brand: str | None = None
    device_codename: str | None = None

    # iOS-specific
    ios_version: str | None = None
    product_type: str | None = None
    build_version: str | None = None
    device_class: str | None = None
    hardware_model: str | None = None
    cpu_architecture: str | None = None

    # Connection
    serial: str | None = None  # Masked/hashed in logs; never exposed raw in API.
    udid: str | None = None  # iOS UDID – same treatment.

    # Discovery timestamp
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ============================================================
# Evidence model
# ============================================================


class EvidenceRecord(BaseModel):
    """A single piece of diagnostic evidence.

    Every diagnostic result must be backed by one or more EvidenceRecords.
    Synthetic evidence is clearly labeled and never mixed with real hardware evidence.
    """

    evidence_id: UUID = Field(default_factory=uuid4)
    diagnostic_id: str
    device_id: str
    source_type: EvidenceSourceType
    source_name: str
    """e.g., 'adb getprop ro.product.model', 'dumpsys battery'"""
    collection_method: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_value: str | None = None
    normalized_value: float | None = None
    unit: str | None = None
    reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    """Estimated reliability of this evidence source (0.0 = unreliable, 1.0 = fully trusted). None when unmodeled."""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    """Confidence in the interpretation of this evidence. None when unmodeled."""
    metadata: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = False
    error: str | None = None


# ============================================================
# Capability and Device models
# ============================================================


class CapabilityEntry(BaseModel):
    """A single capability entry in a device's capability profile."""

    name: str
    status: CapabilityStatus
    verification_level: VerificationLevel | None = None
    """Level 1 (Runtime Detection), Level 2 (Functional Verification), or Level 3 (Reference Comparison).
    None when status is NOT_REPORTED or UNKNOWN (no verification performed)."""
    source: str | None = None
    """Where we determined this capability status from."""
    note: str | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class DeviceCapabilityProfile(BaseModel):
    """Full capability profile for a connected device.

    Built automatically from device discovery before the test plan is created.
    """

    device_id: str
    platform: Platform
    capabilities: dict[str, CapabilityEntry] = Field(default_factory=dict)
    profiled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    profile_complete: bool = False
    """True if runtime capability discovery completed without truncation,
    timeout, or empty/unparseable output. Skips unparseable lines gracefully
    if valid features are extracted. False indicates an incomplete or truncated
    snapshot that may be retried."""
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get(self, capability_name: str) -> CapabilityStatus:
        """Return status for a canonical capability name.

        Platform-neutral lookup only; does not inspect platform-specific metadata.
        """
        entry = self.capabilities.get(capability_name)
        if entry:
            return entry.status
        return CapabilityStatus.UNKNOWN

    def get_entry(self, capability_name: str) -> CapabilityEntry | None:
        return self.capabilities.get(capability_name)

    def is_present(self, capability_name: str) -> bool:
        """Check if capability was declared PRESENT by the OS/runtime.

        Note: Level 1 Runtime Detection only. Declares observation from the OS,
        NOT functional hardware verification (Level 2).
        """
        return self.get(capability_name) == CapabilityStatus.PRESENT


class ConnectedDevice(BaseModel):
    """A device as seen by the VECTOR agent at connection time."""

    device_id: str = Field(default_factory=lambda: str(uuid4()))
    platform: Platform = Platform.UNKNOWN
    connection_state: ConnectionState
    authorization_state: DeviceAuthorizationState = DeviceAuthorizationState.UNKNOWN
    identity: DeviceIdentity | None = None
    capability_profile: DeviceCapabilityProfile | None = None


# ============================================================
# Diagnostic result
# ============================================================


class DiagnosticResult(BaseModel):
    """Result of a single diagnostic test."""

    diagnostic_id: str
    diagnostic_name: str
    category: str
    status: DiagnosticStatus
    automation_level: AutomationLevel
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    summary: str | None = None
    """Human-readable explanation of why this status was assigned."""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None


# ============================================================
# Scan models
# ============================================================


class ScanMode(StrEnum):
    """Scan execution mode."""

    FULL_VERIFICATION = "FULL_VERIFICATION"
    CATEGORY_VERIFICATION = "CATEGORY_VERIFICATION"
    SELECTED_DIAGNOSTICS = "SELECTED_DIAGNOSTICS"
    SINGLE_COMPONENT = "SINGLE_COMPONENT"


class ScanRequest(BaseModel):
    """Request to initiate a device scan."""

    model_config = ConfigDict(extra="forbid")

    device_id: str
    """Must be a known device_id from /api/v1/devices."""
    mode: ScanMode = ScanMode.FULL_VERIFICATION
    """Scan request mode."""
    category: str | None = None
    """Category filter when mode is CATEGORY_VERIFICATION."""
    diagnostic_ids: list[str] = Field(default_factory=list)
    """Diagnostic IDs when mode is SELECTED_DIAGNOSTICS or SINGLE_COMPONENT."""


class DiagnosticApplicability(StrEnum):
    """Truthful classification of a diagnostic's applicability for a device."""

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"
    RESTRICTED = "RESTRICTED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED_BY_PREREQUISITE = "BLOCKED_BY_PREREQUISITE"
    UNKNOWN = "UNKNOWN"


class PlannedDiagnostic(BaseModel):
    """Planning classification for a single diagnostic."""

    model_config = ConfigDict(frozen=True)

    diagnostic_id: str
    applicability: DiagnosticApplicability
    reason: str | None = None


class ScanPlan(BaseModel):
    """Immutable plan derived from device capabilities and diagnostic registry.

    Contains only opaque device_id (never raw serial).
    Fully immutable once produced (frozen model with immutable tuples).
    Carries planning_session_epoch to detect reconnects before execution.
    """

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    platform: Platform
    mode: ScanMode
    diagnostics_requested: tuple[str, ...] = Field(default_factory=tuple)
    diagnostics_planned: tuple[str, ...] = Field(default_factory=tuple)
    diagnostics_skipped: tuple[str, ...] = Field(default_factory=tuple)
    planned_items: tuple[PlannedDiagnostic, ...] = Field(default_factory=tuple)
    planning_session_epoch: int = 0
    capability_profiled_at: datetime | None = None
    registry_diagnostic_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def skip_reasons(self) -> dict[str, str]:
        """Safe skip reasons dynamically derived from planned items."""
        return {
            item.diagnostic_id: item.reason
            for item in self.planned_items
            if item.reason is not None and item.applicability != DiagnosticApplicability.APPLICABLE
        }

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_planned(self) -> int:
        return len(self.diagnostics_planned)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_skipped(self) -> int:
        return len(self.diagnostics_skipped)

    def is_planned(self, diagnostic_id: str) -> bool:
        return diagnostic_id in self.diagnostics_planned


class ScanSummary(BaseModel):
    """Top-level scan record."""

    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    state: ScanLifecycleState = ScanLifecycleState.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    plan: ScanPlan | None = None
    diagnostic_results: list[DiagnosticResult] = Field(default_factory=list)
    trust_engine_status: TrustEngineStatus = TrustEngineStatus.NOT_READY
    """Trust engine readiness.  While NOT_READY, trust_score MUST be None."""
    trust_score: float | None = None
    trust_confidence: float | None = None
    error: str | None = None
