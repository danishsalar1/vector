"""Domain models for OEM device references, component specifications, and comparisons.

Strict immutable models following Phase 8D conventions:
- Pure data contracts
- No I/O, no network calls, no guessing
- Explicit provenance and source attribution required for reference claims
- Evidence honesty: specification match != genuine/original; mismatch != counterfeit
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, StringConstraints, field_validator, model_validator

from .component import ComponentKind, DomainModel, OpaqueId

# Catalog schema version
CATALOG_SCHEMA_VERSION: Literal["vector-catalog-v1"] = "vector-catalog-v1"

# Identifiers
IdentifierSlug = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    ),
]


class SourceClassification(StrEnum):
    """Hierarchical classification of reference information sources."""

    OEM_DOCUMENTATION = "OEM_DOCUMENTATION"
    REGULATORY_FILING = "REGULATORY_FILING"
    STANDARDS_BODY = "STANDARDS_BODY"
    AUTHORIZED_TECHNICAL_RESOURCE = "AUTHORIZED_TECHNICAL_RESOURCE"
    CREDIBLE_INDEPENDENT_REFERENCE = "CREDIBLE_INDEPENDENT_REFERENCE"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


SOURCE_AUTHORITY_RANK: dict[SourceClassification, int] = {
    SourceClassification.OEM_DOCUMENTATION: 1,
    SourceClassification.REGULATORY_FILING: 2,
    SourceClassification.STANDARDS_BODY: 3,
    SourceClassification.AUTHORIZED_TECHNICAL_RESOURCE: 4,
    SourceClassification.CREDIBLE_INDEPENDENT_REFERENCE: 5,
    SourceClassification.SYNTHETIC_FIXTURE: 99,
}


def parse_utc_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except Exception as e:
            raise ValueError(f"Invalid ISO datetime string '{value}'") from e
    elif isinstance(value, datetime):
        dt = value
    else:
        raise ValueError(f"Expected datetime or ISO string, got {type(value).__name__}")
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError("A timezone-aware UTC timestamp is required.")
    return dt


def parse_optional_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as e:
            raise ValueError(f"Invalid ISO date string '{value}'") from e
    raise ValueError(f"Expected date or ISO date string, got {type(value).__name__}")


def parse_source_classification(value: Any) -> SourceClassification:
    if isinstance(value, SourceClassification):
        return value
    if isinstance(value, str):
        try:
            return SourceClassification(value)
        except Exception as e:
            raise ValueError(f"Invalid source classification: '{value}'") from e
    raise ValueError(f"Expected SourceClassification or valid string, got {type(value).__name__}")


def parse_component_kind(value: Any) -> ComponentKind:
    if isinstance(value, ComponentKind):
        return value
    if isinstance(value, str):
        try:
            return ComponentKind(value)
        except Exception as e:
            raise ValueError(f"Invalid component kind: '{value}'") from e
    raise ValueError(f"Expected ComponentKind or valid string, got {type(value).__name__}")


def to_tuple(v: Any) -> tuple[Any, ...]:
    if isinstance(v, (list, tuple)):
        return tuple(v)
    raise ValueError(f"Expected list or tuple, got {type(v).__name__}")


def unique_sorted_strings(v: Any) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)):
        t = tuple(v)
        if len(t) != len(set(t)):
            raise ValueError("Duplicate references are forbidden.")
        return tuple(sorted(t))
    raise ValueError(f"Expected list or tuple of strings, got {type(v).__name__}")


class ReferenceClaimVerification(DomainModel):
    """Local curator record binding source inspection to one exact reference value.

    This is not external attestation. Empty records mean unverified, including
    sources whose URL or publisher alone is known.
    """

    entity_id: IdentifierSlug
    property_path: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    reference_value_json: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    verified_at: Annotated[datetime, BeforeValidator(parse_utc_datetime)]
    verification_notes: Annotated[str, Field(strict=True, min_length=1, max_length=1024)]


class ReferenceSource(DomainModel):
    """Traceable, verifiable citation for any reference claim in VECTOR."""

    source_id: IdentifierSlug
    title: Annotated[str, Field(strict=True, min_length=1, max_length=256)]
    publisher: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    url_or_document_id: Annotated[str, Field(strict=True, min_length=1, max_length=512)]
    source_classification: Annotated[
        SourceClassification, BeforeValidator(parse_source_classification)
    ]
    publication_date: Annotated[date | None, BeforeValidator(parse_optional_date)] = None
    retrieved_at: Annotated[datetime, BeforeValidator(parse_utc_datetime)] | None = None
    version_or_revision: Annotated[str, Field(strict=True, max_length=64)] | None = None
    license_or_usage_constraints: Annotated[str, Field(strict=True, max_length=512)] | None = None
    provenance_notes: Annotated[str, Field(strict=True, max_length=1024)] | None = None
    is_synthetic: bool = False
    verified_claims: tuple[ReferenceClaimVerification, ...] = ()

    @field_validator("verified_claims", mode="before")
    @classmethod
    def _claim_tuple(cls, value: Any) -> Any:
        return to_tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_synthetic_flag(self) -> ReferenceSource:
        if (
            self.source_classification == SourceClassification.SYNTHETIC_FIXTURE
            and not self.is_synthetic
        ):
            raise ValueError("SYNTHETIC_FIXTURE classification requires is_synthetic=True.")
        if (
            self.is_synthetic
            and self.source_classification != SourceClassification.SYNTHETIC_FIXTURE
        ):
            raise ValueError("is_synthetic=True requires SYNTHETIC_FIXTURE classification.")
        return self


# ============================================================
# Hardware Domain Specifications
# ============================================================


class DisplayReferenceSpec(DomainModel):
    """OEM-specified display hardware properties."""

    technology: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    size_diagonal_inches: Annotated[float, Field(strict=True, ge=1.0, le=25.0)] | None = None
    resolution_width: Annotated[int, Field(strict=True, ge=100, le=10000)]
    resolution_height: Annotated[int, Field(strict=True, ge=100, le=10000)]
    refresh_rate_max_hz: Annotated[int, Field(strict=True, ge=30, le=480)]
    refresh_rate_min_hz: Annotated[int, Field(strict=True, ge=1, le=480)] | None = None
    supported_refresh_rates: tuple[int, ...] = ()
    pixel_density_ppi: Annotated[int, Field(strict=True, ge=50, le=2000)] | None = None
    hdr_standards: tuple[str, ...] = ()

    @field_validator("supported_refresh_rates", "hdr_standards", mode="before")
    @classmethod
    def _coerce_display_tuples(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v

    @model_validator(mode="after")
    def validate_refresh_rates(self) -> DisplayReferenceSpec:
        if (
            self.refresh_rate_min_hz is not None
            and self.refresh_rate_min_hz > self.refresh_rate_max_hz
        ):
            raise ValueError("refresh_rate_min_hz cannot exceed refresh_rate_max_hz.")
        if self.supported_refresh_rates:
            for rate in self.supported_refresh_rates:
                if rate < 1 or rate > 480:
                    raise ValueError(f"Refresh rate {rate} out of valid range 1-480 Hz.")
                if rate > self.refresh_rate_max_hz:
                    raise ValueError(
                        f"Supported rate {rate} exceeds max {self.refresh_rate_max_hz} Hz."
                    )
        return self


class BatteryReferenceSpec(DomainModel):
    """OEM-specified battery assembly and cell characteristics."""

    rated_capacity_mah: Annotated[int, Field(strict=True, ge=100, le=50000)]
    typical_capacity_mah: Annotated[int, Field(strict=True, ge=100, le=50000)] | None = None
    chemistry: Annotated[str, Field(strict=True, max_length=32)] | None = None
    nominal_voltage_mv: Annotated[int, Field(strict=True, ge=1000, le=20000)] | None = None
    max_charging_wattage_wired: Annotated[float, Field(strict=True, ge=1.0, le=300.0)] | None = None
    wireless_charging_supported: bool = False
    max_charging_wattage_wireless: Annotated[float, Field(strict=True, ge=1.0, le=150.0)] | None = (
        None
    )
    removable: bool = False

    @model_validator(mode="after")
    def validate_capacities(self) -> BatteryReferenceSpec:
        if (
            self.typical_capacity_mah is not None
            and self.typical_capacity_mah < self.rated_capacity_mah
        ):
            raise ValueError("Typical capacity cannot be strictly less than rated capacity.")
        return self


class SocReferenceSpec(DomainModel):
    """System-on-Chip (SoC) reference characteristics."""

    chip_maker: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    marketing_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    part_number: Annotated[str, Field(strict=True, max_length=64)] | None = None
    cpu_architecture: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    core_count: Annotated[int, Field(strict=True, ge=1, le=32)]
    gpu_model: Annotated[str, Field(strict=True, max_length=64)] | None = None
    process_node_nm: Annotated[int, Field(strict=True, ge=1, le=100)] | None = None


class MemoryStorageSpec(DomainModel):
    """Supported RAM and storage configurations."""

    ram_options_bytes: tuple[int, ...]
    storage_options_bytes: tuple[int, ...]
    ram_type: Annotated[str, Field(strict=True, max_length=32)] | None = None
    storage_type: Annotated[str, Field(strict=True, max_length=32)] | None = None
    expandable_storage: bool = False

    @field_validator("ram_options_bytes", "storage_options_bytes", mode="before")
    @classmethod
    def _coerce_memory_tuples(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v

    @field_validator("ram_options_bytes", "storage_options_bytes")
    @classmethod
    def validate_positive_capacities(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if not values:
            raise ValueError("At least one capacity option must be specified.")
        for v in values:
            if v <= 0:
                raise ValueError("Capacity must be strictly positive.")
        return tuple(sorted(values))


class CameraSensorSpec(DomainModel):
    """Individual camera sensor reference properties."""

    role: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    resolution_mp: Annotated[float, Field(strict=True, ge=0.1, le=500.0)]
    aperture_f_number: Annotated[float, Field(strict=True, ge=0.5, le=10.0)] | None = None
    focal_length_equiv_mm: Annotated[float, Field(strict=True, ge=1.0, le=1000.0)] | None = None
    sensor_model: Annotated[str, Field(strict=True, max_length=64)] | None = None
    sensor_maker: Annotated[str, Field(strict=True, max_length=64)] | None = None
    optical_image_stabilization: bool = False
    autofocus_supported: bool = True


class CameraReferenceSpec(DomainModel):
    """Device camera assembly specifications."""

    rear_cameras: tuple[CameraSensorSpec, ...] = ()
    front_cameras: tuple[CameraSensorSpec, ...] = ()
    has_flash: bool = True
    lidar_or_tof_present: bool = False

    @field_validator("rear_cameras", "front_cameras", mode="before")
    @classmethod
    def _coerce_camera_tuples(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v


class SensorReferenceSpec(DomainModel):
    """Documented hardware sensor presence."""

    fingerprint_type: Annotated[str, Field(strict=True, max_length=64)] | None = None
    accelerometer: bool = True
    gyroscope: bool = True
    magnetometer: bool = True
    barometer: bool = False
    proximity: bool = True
    ambient_light: bool = True
    nfc: bool = True
    ultra_wideband: bool = False


class ConnectivityReferenceSpec(DomainModel):
    """Documented wireless and wireline connectivity capabilities."""

    wifi_generations: tuple[str, ...] = ()
    bluetooth_version: Annotated[str, Field(strict=True, max_length=16)] | None = None
    cellular_generations: tuple[str, ...] = ("4G", "5G")
    usb_type: Annotated[str, Field(strict=True, max_length=32)] = "USB-C"
    usb_version: Annotated[str, Field(strict=True, max_length=16)] | None = None

    @field_validator("wifi_generations", "cellular_generations", mode="before")
    @classmethod
    def _coerce_conn_tuples(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v


class AudioHapticReferenceSpec(DomainModel):
    """Documented audio and haptic hardware."""

    speaker_type: Annotated[str, Field(strict=True, max_length=32)] = "stereo"
    headphone_jack_3_5mm: bool = False
    haptic_motor_type: Annotated[str, Field(strict=True, max_length=64)] | None = None


class ComponentReferenceSpec(DomainModel):
    """Reference specification for a replaceable or identity-bearing component."""

    component_kind: Annotated[ComponentKind, BeforeValidator(parse_component_kind)]
    component_role: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    part_number: Annotated[str, Field(strict=True, max_length=64)] | None = None
    documented_suppliers: tuple[str, ...] = ()
    supported_properties: dict[str, str | int | float | bool] = Field(default_factory=dict)
    source_id: IdentifierSlug
    notes: Annotated[str, Field(strict=True, max_length=512)] | None = None

    @field_validator("documented_suppliers", mode="before")
    @classmethod
    def _coerce_suppliers(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v


class DeviceSpecification(DomainModel):
    """Aggregated reference specifications for a device model or variant."""

    display: DisplayReferenceSpec | None = None
    battery: BatteryReferenceSpec | None = None
    soc: SocReferenceSpec | None = None
    memory_storage: MemoryStorageSpec | None = None
    camera: CameraReferenceSpec | None = None
    sensors: SensorReferenceSpec | None = None
    connectivity: ConnectivityReferenceSpec | None = None
    audio_haptics: AudioHapticReferenceSpec | None = None
    source_ids: tuple[IdentifierSlug, ...] = ()

    _sources = field_validator("source_ids", mode="before")(unique_sorted_strings)


# ============================================================
# Catalog Entities
# ============================================================


class ManufacturerReference(DomainModel):
    """Canonical manufacturer reference record."""

    manufacturer_id: IdentifierSlug
    canonical_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    aliases: tuple[str, ...] = ()
    source_id: IdentifierSlug
    notes: Annotated[str, Field(strict=True, max_length=512)] | None = None

    _aliases = field_validator("aliases", mode="before")(unique_sorted_strings)


class DeviceModelReference(DomainModel):
    """Canonical device model and generation reference record."""

    model_id: IdentifierSlug
    is_synthetic: bool = False
    manufacturer_id: IdentifierSlug
    marketed_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    model_family: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    generation: Annotated[str, Field(strict=True, max_length=32)] | None = None
    known_model_codes: tuple[str, ...] = ()
    device_codenames: tuple[str, ...] = ()
    source_ids: tuple[IdentifierSlug, ...] = ()
    base_specifications: DeviceSpecification | None = None
    supported_component_alternatives: tuple[ComponentReferenceSpec, ...] = ()

    _model_codes = field_validator(
        "known_model_codes", "device_codenames", "source_ids", mode="before"
    )(unique_sorted_strings)

    @field_validator("supported_component_alternatives", mode="before")
    @classmethod
    def _coerce_comp_alts(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v


class DeviceVariantReference(DomainModel):
    """Specific regional, hardware, or network revision variant of a model."""

    variant_id: IdentifierSlug
    model_id: IdentifierSlug
    region_market: Annotated[str, Field(strict=True, min_length=1, max_length=64)]
    model_codes: tuple[str, ...] = ()
    sku_numbers: tuple[str, ...] = ()
    hardware_revisions: tuple[str, ...] = ()
    network_configuration: Annotated[str, Field(strict=True, max_length=64)] | None = None
    specifications: DeviceSpecification
    supported_components: tuple[ComponentReferenceSpec, ...] = ()
    source_ids: tuple[IdentifierSlug, ...] = ()
    notes: Annotated[str, Field(strict=True, max_length=512)] | None = None

    _lists = field_validator(
        "model_codes", "sku_numbers", "hardware_revisions", "source_ids", mode="before"
    )(unique_sorted_strings)

    @field_validator("supported_components", mode="before")
    @classmethod
    def _coerce_supported_components(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v


class ReferenceConflict(DomainModel):
    """Explicit recorded conflict between two credible reference sources."""

    conflict_id: IdentifierSlug
    target_entity_type: Literal["manufacturer", "model", "variant", "component"]
    target_entity_id: IdentifierSlug
    field_path: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    source_a_id: IdentifierSlug
    source_a_value: Annotated[str, Field(strict=True, max_length=256)]
    source_b_id: IdentifierSlug
    source_b_value: Annotated[str, Field(strict=True, max_length=256)]
    conflict_notes: Annotated[str, Field(strict=True, max_length=1024)]
    recorded_at: Annotated[datetime, BeforeValidator(parse_utc_datetime)]


# ============================================================
# Device Resolution Models
# ============================================================


class ResolutionStatus(StrEnum):
    """Outcome of resolving device identity clues against reference catalog."""

    EXACT_MATCH = "EXACT_MATCH"
    MODEL_MATCH_AMBIGUOUS_VARIANT = "MODEL_MATCH_AMBIGUOUS_VARIANT"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    UNKNOWN_DEVICE = "UNKNOWN_DEVICE"
    UNSUPPORTED_DEVICE = "UNSUPPORTED_DEVICE"
    CONFLICTING_IDENTIFIERS = "CONFLICTING_IDENTIFIERS"


def parse_resolution_status(value: Any) -> ResolutionStatus:
    if isinstance(value, ResolutionStatus):
        return value
    if isinstance(value, str):
        try:
            return ResolutionStatus(value)
        except Exception as e:
            raise ValueError(f"Invalid resolution status: '{value}'") from e
    raise ValueError(f"Expected ResolutionStatus or valid string, got {type(value).__name__}")


class CandidateMatch(DomainModel):
    """Candidate match entry with supporting evidence ranking."""

    model_id: IdentifierSlug
    variant_id: IdentifierSlug | None = None
    marketed_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    confidence_rank: Annotated[int, Field(strict=True, ge=1, le=1000)]
    matched_fields: tuple[str, ...]
    unmatched_fields: tuple[str, ...] = ()
    match_notes: str = ""

    _fields = field_validator("matched_fields", "unmatched_fields", mode="before")(
        unique_sorted_strings
    )


class DeviceResolutionResult(DomainModel):
    """Outcome of resolving connected device identifiers against reference catalog."""

    status: Annotated[ResolutionStatus, BeforeValidator(parse_resolution_status)]
    resolved_model: DeviceModelReference | None = None
    resolved_variant: DeviceVariantReference | None = None
    candidate_matches: tuple[CandidateMatch, ...] = ()
    considered_fields: dict[str, str | int | None] = Field(default_factory=dict)
    reason: str
    limitations: tuple[str, ...] = ()

    @field_validator("candidate_matches", "limitations", mode="before")
    @classmethod
    def _coerce_res_tuples(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v

    @model_validator(mode="after")
    def validate_resolution_consistency(self) -> DeviceResolutionResult:
        if self.status == ResolutionStatus.EXACT_MATCH:
            if self.resolved_model is None or self.resolved_variant is None:
                raise ValueError("EXACT_MATCH requires both resolved_model and resolved_variant.")
        elif self.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT:
            if self.resolved_model is None or self.resolved_variant is not None:
                raise ValueError(
                    "MODEL_MATCH_AMBIGUOUS_VARIANT requires resolved_model and resolved_variant=None."
                )
        elif (
            self.status
            in (
                ResolutionStatus.MULTIPLE_CANDIDATES,
                ResolutionStatus.UNKNOWN_DEVICE,
                ResolutionStatus.UNSUPPORTED_DEVICE,
                ResolutionStatus.CONFLICTING_IDENTIFIERS,
            )
            and self.resolved_variant is not None
        ):
            raise ValueError(f"Status {self.status} cannot have a resolved_variant.")
        return self


# ============================================================
# Specification Comparison Models
# ============================================================


class ComparisonOutcome(StrEnum):
    """Discrete, honest outcome of comparing an observed property with reference."""

    CONSISTENT_WITH_REFERENCE = "CONSISTENT_WITH_REFERENCE"
    DIFFERS_FROM_REFERENCE = "DIFFERS_FROM_REFERENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
    VARIANT_AMBIGUOUS = "VARIANT_AMBIGUOUS"
    NOT_COMPARABLE = "NOT_COMPARABLE"


def parse_comparison_outcome(value: Any) -> ComparisonOutcome:
    if isinstance(value, ComparisonOutcome):
        return value
    if isinstance(value, str):
        try:
            return ComparisonOutcome(value)
        except Exception as e:
            raise ValueError(f"Invalid comparison outcome: '{value}'") from e
    raise ValueError(f"Expected ComparisonOutcome or valid string, got {type(value).__name__}")


class ComparisonMethod(StrEnum):
    """Evaluation method applied for comparison."""

    EXACT_MATCH = "EXACT_MATCH"
    NUMERIC_TOLERANCE = "NUMERIC_TOLERANCE"
    RANGE_BOUND = "RANGE_BOUND"
    SUBSET_MATCH = "SUBSET_MATCH"
    CAPABILITY_PRESENCE = "CAPABILITY_PRESENCE"


def parse_comparison_method(value: Any) -> ComparisonMethod:
    if isinstance(value, ComparisonMethod):
        return value
    if isinstance(value, str):
        try:
            return ComparisonMethod(value)
        except Exception as e:
            raise ValueError(f"Invalid comparison method: '{value}'") from e
    raise ValueError(f"Expected ComparisonMethod or valid string, got {type(value).__name__}")


class SpecificationComparisonItem(DomainModel):
    """Comparison evaluation for an individual hardware property."""

    property_path: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    observed_value: Any = None
    reference_value: Any = None
    unit: str | None = None
    applicable_variant_id: IdentifierSlug | None = None
    comparison_method: Annotated[ComparisonMethod, BeforeValidator(parse_comparison_method)]
    outcome: Annotated[ComparisonOutcome, BeforeValidator(parse_comparison_outcome)]
    reason: str
    limitations: tuple[str, ...] = ()
    source_ids: tuple[IdentifierSlug, ...] = ()
    honesty_warning: str = (
        "Specification consistency does NOT imply OEM genuine/originality. "
        "Specification mismatch does NOT prove counterfeit or failure."
    )

    @field_validator("limitations", mode="before")
    @classmethod
    def _coerce_comp_limits(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v

    _sources = field_validator("source_ids", mode="before")(unique_sorted_strings)


class SpecificationComparisonReport(DomainModel):
    """Consolidated Level 3 Reference Comparison report for a device session."""

    report_id: OpaqueId
    device_id: str
    resolution: DeviceResolutionResult
    evaluated_at: Annotated[datetime, BeforeValidator(parse_utc_datetime)]
    items: tuple[SpecificationComparisonItem, ...] = ()
    consistent_count: Annotated[int, Field(strict=True, ge=0)] = 0
    differs_count: Annotated[int, Field(strict=True, ge=0)] = 0
    insufficient_evidence_count: Annotated[int, Field(strict=True, ge=0)] = 0
    reference_unavailable_count: Annotated[int, Field(strict=True, ge=0)] = 0
    ambiguous_count: Annotated[int, Field(strict=True, ge=0)] = 0
    not_comparable_count: Annotated[int, Field(strict=True, ge=0)] = 0
    total_items: Annotated[int, Field(strict=True, ge=0)] = 0
    summary_verdict: str = "REFERENCE_COMPARISON_EVALUATED"
    honesty_disclaimer: str = (
        "Level 3 Reference Comparison compares observed characteristics against documented "
        "reference specifications. It does NOT evaluate component authenticity, genuine OEM provenance, "
        "or compute a trust score."
    )

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, v: Any) -> Any:
        return to_tuple(v) if isinstance(v, list) else v

    @model_validator(mode="after")
    def compute_counts(self) -> SpecificationComparisonReport:
        # Verify item count totals
        c = sum(
            1 for item in self.items if item.outcome == ComparisonOutcome.CONSISTENT_WITH_REFERENCE
        )
        d = sum(
            1 for item in self.items if item.outcome == ComparisonOutcome.DIFFERS_FROM_REFERENCE
        )
        i = sum(1 for item in self.items if item.outcome == ComparisonOutcome.INSUFFICIENT_EVIDENCE)
        u = sum(1 for item in self.items if item.outcome == ComparisonOutcome.REFERENCE_UNAVAILABLE)
        a = sum(1 for item in self.items if item.outcome == ComparisonOutcome.VARIANT_AMBIGUOUS)
        object.__setattr__(
            self,
            "not_comparable_count",
            sum(1 for item in self.items if item.outcome == ComparisonOutcome.NOT_COMPARABLE),
        )
        object.__setattr__(self, "total_items", len(self.items))
        if (
            self.consistent_count != c
            or self.differs_count != d
            or self.insufficient_evidence_count != i
            or self.reference_unavailable_count != u
            or self.ambiguous_count != a
        ):
            # Recalculate if not explicitly set
            object.__setattr__(self, "consistent_count", c)
            object.__setattr__(self, "differs_count", d)
            object.__setattr__(self, "insufficient_evidence_count", i)
            object.__setattr__(self, "reference_unavailable_count", u)
            object.__setattr__(self, "ambiguous_count", a)
        return self


# ============================================================
# Performance Reference Models
# ============================================================


class PerformanceMetricReference(DomainModel):
    """Contract for reference performance baseline metrics."""

    metric_id: IdentifierSlug
    metric_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    measurement_unit: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    test_methodology: Annotated[str, Field(strict=True, min_length=1, max_length=256)]
    applicable_model_ids: tuple[IdentifierSlug, ...]
    applicable_variant_ids: tuple[IdentifierSlug, ...] = ()
    test_conditions: Annotated[str, Field(strict=True, max_length=512)]
    reference_min: float | None = None
    reference_max: float | None = None
    reference_mean: float | None = None
    reference_std_dev: float | None = None
    sample_count: Annotated[int, Field(strict=True, ge=1)] | None = None
    source_id: IdentifierSlug
    revision_date: str | None = None
    confidence_limitations: Annotated[str, Field(strict=True, max_length=512)] | None = None

    _models = field_validator("applicable_model_ids", "applicable_variant_ids", mode="before")(
        unique_sorted_strings
    )

    @model_validator(mode="after")
    def validate_range(self) -> PerformanceMetricReference:
        if (
            self.reference_min is not None
            and self.reference_max is not None
            and self.reference_min > self.reference_max
        ):
            raise ValueError("reference_min cannot exceed reference_max.")
        if self.reference_std_dev is not None and self.reference_std_dev < 0:
            raise ValueError("reference_std_dev cannot be negative.")
        return self


class PerformanceEvaluationResult(DomainModel):
    """Evaluation outcome for an observed performance metric against reference baseline."""

    metric_id: IdentifierSlug
    observed_value: float | None = None
    unit: Annotated[str, Field(strict=True, max_length=32)]
    reference_min: float | None = None
    reference_max: float | None = None
    reference_mean: float | None = None
    outcome: Annotated[ComparisonOutcome, BeforeValidator(parse_comparison_outcome)]
    reason: str
    source_id: IdentifierSlug | None = None
    confidence_limitations: str | None = None
    disclaimer: str = (
        "Performance baseline comparison is an informational reference only. "
        "Physical qualification was NOT RUN."
    )
