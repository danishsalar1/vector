"""Version 2 Probe diagnostic payloads: closed vocabulary, bounded numeric evidence.

These schemas authenticate nothing by themselves. Only the existing session and
HMAC transport ingestion path may attribute them to a connected device.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DiagnosticName = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^(battery|system|storage|display|connectivity|audio_routes|pixels|touch|speaker|microphone|vibration|sensor_[0-9]{1,2}|camera_[0-9]{1,2}|camera_unavailable)$",
        max_length=32,
    ),
]


class DiagnosticModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class DiagnosticCapability(DiagnosticModel):
    diagnostic_id: DiagnosticName
    available: bool
    interactive: bool
    sensor_type: Annotated[int, Field(ge=1, le=2**31 - 1)] | None = None
    reporting_mode: Annotated[int, Field(ge=0, le=16)] | None = None
    max_range: Annotated[float, Field(ge=0.0, le=3.5e38)] | None = None
    resolution: Annotated[float, Field(ge=0.0, le=3.5e38)] | None = None
    camera_facing: Annotated[int, Field(ge=0, le=8)] | None = None
    camera_level: Annotated[int, Field(ge=0, le=8)] | None = None
    flash_available: bool | None = None
    autofocus_available: bool | None = None

    @model_validator(mode="after")
    def sensor_context(self) -> Self:
        for field_name in ("max_range", "resolution"):
            val = getattr(self, field_name)
            if val is not None and not math.isfinite(val):
                raise ValueError(f"{field_name} must be finite.")
        if self.diagnostic_id.startswith("sensor_"):
            if self.available and self.sensor_type is None:
                raise ValueError("Available sensor capability must provide sensor_type.")
        elif self.sensor_type is not None:
            raise ValueError("Non-sensor diagnostic must not specify sensor_type.")
        return self


CONNECTIVITY_FEATURES: tuple[str, ...] = (
    "feature_wifi",
    "feature_bluetooth",
    "feature_bluetooth_le",
    "feature_nfc",
    "feature_gps",
    "feature_usb_host",
    "feature_usb_accessory",
    "feature_telephony",
    "feature_fingerprint",
    "feature_face",
    "feature_iris",
    "feature_camera_any",
    "feature_microphone",
    "feature_accelerometer",
    "feature_gyroscope",
    "feature_compass",
    "feature_light",
    "feature_proximity",
    "feature_barometer",
    "feature_multitouch",
    "feature_audio_output",
)

# Units are tied to metric names; no peer-defined strings or metadata escape hatch.
METRICS: dict[str, str] = {
    "battery_level": "count",
    "battery_scale": "count",
    "battery_status": "enum",
    "power_source": "enum",
    "battery_temperature": "deci_celsius",
    "battery_voltage": "mV",
    "battery_health": "enum",
    "charge_counter": "uAh",
    "current_now": "uA",
    "current_average": "uA",
    "capacity_percent": "percent",
    "cycle_count": "count",
    "ram_total": "bytes",
    "ram_available": "bytes",
    "ram_threshold": "bytes",
    "low_memory": "boolean",
    "thermal_status": "enum",
    "storage_total": "bytes",
    "storage_available": "bytes",
    "bytes_written": "bytes",
    "bytes_read": "bytes",
    "readback_match": "boolean",
    "width": "pixels",
    "height": "pixels",
    "refresh_rate": "Hz",
    "rotation": "enum",
    "mode_count": "count",
    "brightness": "level_255",
    "route_count": "count",
    "wifi_enabled": "boolean",
    "nfc_enabled": "boolean",
    "gps_provider": "boolean",
    "usb_devices": "count",
    "sensor_type": "enum",
    "sensor_accuracy": "enum",
    "registered": "boolean",
    "sample_count": "count",
    "camera_facing": "enum",
    "camera_level": "enum",
    "flash_available": "boolean",
    "autofocus_available": "boolean",
    "frame_width": "pixels",
    "frame_height": "pixels",
    "frame_bytes": "bytes",
    "capture_completed": "boolean",
    "af_state": "enum",
    "frame_metadata_match": "boolean",
    "luma_mean": "unitless",
    "luma_variance": "unitless",
    "tone_submitted": "boolean",
    "effect_scheduled": "boolean",
    "audio_samples": "count",
    "audio_peak": "unitless",
    "audio_rms": "unitless",
    "user_report": "boolean",
    "patterns_viewed": "count",
    "touch_cells": "count",
    "max_contacts": "count",
    "cell_coverage_percent": "percent",
    "tested_width": "pixels",
    "tested_height": "pixels",
    "window_width": "pixels",
    "window_height": "pixels",
    "display_width": "pixels",
    "display_height": "pixels",
    "tested_window_area_percent": "percent",
    "tested_display_area_percent": "percent",
    "layout_generation": "count",
    "rejected_samples": "count",
}
for _key in tuple(METRICS)[:11]:
    METRICS["end_" + _key] = METRICS[_key]
for _index in range(8):
    METRICS.update(
        {
            f"mode{_index}_width": "pixels",
            f"mode{_index}_height": "pixels",
            f"mode{_index}_rate": "Hz",
        }
    )
for _index in range(24):
    METRICS.update({f"route{_index}_type": "enum", f"route{_index}_input": "boolean"})
for _index in range(21):
    METRICS[f"feature{_index}"] = "boolean"
for _feat in CONNECTIVITY_FEATURES:
    METRICS[_feat] = "boolean"

SENSOR_UNITS = {
    "m_s2",
    "rad_s",
    "uT",
    "unitless",
    "lux",
    "cm",
    "hPa",
    "celsius",
    "percent",
    "count",
}

# Touch PASS policy, mirrored exactly by DiagnosticJob.Touch on the Probe. The window is the
# app window hosting the grid; the display is the physical display in the current rotation.
# Coverage of the app window alone never stands in for coverage of the touchscreen.
TOUCH_GRID_CELLS = 24
TOUCH_MIN_TESTED_PIXELS = 200
TOUCH_MIN_DISPLAY_AREA_PERCENT = 75
TOUCH_GEOMETRY = (
    "tested_width",
    "tested_height",
    "window_width",
    "window_height",
    "display_width",
    "display_height",
)


def touch_area_percent(width: int, height: int, outer_width: int, outer_height: int) -> int:
    """Round-half-up area percentage in exact integer arithmetic (identical in Java)."""
    part = width * height
    whole = outer_width * outer_height
    return (200 * part + whole) // (2 * whole)


def _touch_pass_evidence(values: dict[str, int | float | None]) -> bool:
    """Every geometry fact present, consistent, recomputed and large enough for PASS."""
    dims = [values.get(name) for name in TOUCH_GEOMETRY]
    counts = [values.get(name) for name in ("touch_cells", "max_contacts", "layout_generation")]
    percents = [
        values.get(name)
        for name in (
            "cell_coverage_percent",
            "tested_window_area_percent",
            "tested_display_area_percent",
        )
    ]
    if any(type(value) is not int for value in (*dims, *counts, *percents)):
        return False
    tested_w, tested_h, window_w, window_h, display_w, display_h = (int(v or 0) for v in dims)
    cells, contacts, layouts = (int(v or 0) for v in counts)
    cell_percent, window_percent, display_percent = (int(v or 0) for v in percents)
    return (
        min(tested_w, tested_h) >= TOUCH_MIN_TESTED_PIXELS
        and tested_w <= window_w <= display_w
        and tested_h <= window_h <= display_h
        and cells == TOUCH_GRID_CELLS
        and cell_percent == 100
        and contacts >= 1
        and layouts >= 1
        and window_percent == touch_area_percent(tested_w, tested_h, window_w, window_h)
        and display_percent == touch_area_percent(tested_w, tested_h, display_w, display_h)
        and display_percent >= TOUCH_MIN_DISPLAY_AREA_PERCENT
    )


class DiagnosticMetric(DiagnosticModel):
    name: Annotated[str, StringConstraints(max_length=32)]
    value: Annotated[int | float, Field(ge=-(2**53), le=2**53)] | None
    unit: Annotated[str, StringConstraints(max_length=16)]

    @model_validator(mode="after")
    def vocabulary(self) -> Self:
        axis = re.fullmatch(r"axis[0-2]_(min|max|mean)", self.name) is not None
        if (axis and self.unit not in SENSOR_UNITS) or (
            not axis and METRICS.get(self.name) != self.unit
        ):
            raise ValueError("Unknown metric or mismatched unit.")
        if self.value is not None:
            if self.unit == "boolean" and (type(self.value) is not int or self.value not in (0, 1)):
                raise ValueError("Boolean observations must be 0 or 1.")
            if (
                self.unit in {"count", "bytes", "pixels", "enum", "level_255"}
                and type(self.value) is not int
                and not axis
            ):
                raise ValueError("Discrete observations require integers.")
            if self.name in {"audio_rms", "audio_peak"} and not 0 <= self.value <= 1:
                raise ValueError("Audio level out of range.")
            if self.name == "touch_cells" and not 0 <= self.value <= 24:
                raise ValueError("Touch coverage out of range.")
            if self.name == "max_contacts" and not 0 <= self.value <= 32:
                raise ValueError("Contact count out of range.")
            if (
                self.name
                in {
                    "cell_coverage_percent",
                    "tested_window_area_percent",
                    "tested_display_area_percent",
                }
                and not 0 <= self.value <= 100
            ):
                raise ValueError("Coverage percent out of range.")
            if (self.name in TOUCH_GEOMETRY or self.name == "layout_generation") and self.value < 0:
                raise ValueError("Tested geometry cannot be negative.")
            if self.name == "luma_mean" and not 0 <= self.value <= 255:
                raise ValueError("Luma mean out of range.")
            if self.name == "luma_variance" and self.value < 0:
                raise ValueError("Luma variance cannot be negative.")
        return self


VALID_OUTCOME_REASONS: dict[str, set[str]] = {
    "PASS": {"READBACK_MATCH", "TOUCH_COVERED", "CAPTURE_MATCH"},
    "FAIL": {"READBACK_MISMATCH"},
    "UNSUPPORTED": {
        "HARDWARE_ABSENT",
        "API_UNSUPPORTED",
        "SAMPLING_UNSUPPORTED",
        "CAPTURE_FORMAT_UNSUPPORTED",
        "AUDIO_FORMAT_UNSUPPORTED",
        "CAMERA_UNAVAILABLE",
    },
    "RESTRICTED": {
        "PERMISSION_DENIED",
        "PERMISSION_REQUIRED",
        "CAMERA_DISABLED",
        "POLICY_RESTRICTED",
    },
    "ERROR": {
        "EXECUTION_ERROR",
        "CLEANUP_ERROR",
        "INITIALIZATION_ERROR",
        "READ_ERROR",
        "WRITE_ERROR",
        "INVALID_FRAME",
        "CAPTURE_ERROR",
    },
    "INCONCLUSIVE": {
        "COLLECTING",
        "STOPPING",
        "CANCELLED",
        "TIMEOUT",
        "USER_UNCERTAIN",
        "USER_REPORTED",
        "PARTIAL",
        "TELEMETRY_ONLY",
        "CAPABILITY_ONLY",
        "REGISTRATION_REJECTED",
        "SAMPLES_OBSERVED",
        "NO_SAMPLES",
        "INSUFFICIENT_SPACE",
        "METADATA_UNAVAILABLE",
        "CAMERA_DISCONNECTED",
        "CAMERA_BUSY",
        "METADATA_MISMATCH",
        "RESOURCE_BUSY",
    },
}


class DiagnosticReport(DiagnosticModel):
    schema_version: Literal[1]
    diagnostic_id: DiagnosticName
    state: Literal["RUNNING", "COMPLETED", "CANCELLED", "EXPIRED"]
    outcome: Literal["PASS", "FAIL", "UNSUPPORTED", "RESTRICTED", "INCONCLUSIVE", "ERROR"]
    reason: Literal[
        "COLLECTING",
        "STOPPING",
        "HARDWARE_ABSENT",
        "API_UNSUPPORTED",
        "PERMISSION_DENIED",
        "PERMISSION_REQUIRED",
        "CAMERA_DISABLED",
        "POLICY_RESTRICTED",
        "EXECUTION_ERROR",
        "CLEANUP_ERROR",
        "CANCELLED",
        "TIMEOUT",
        "USER_UNCERTAIN",
        "USER_REPORTED",
        "TOUCH_COVERED",
        "PARTIAL",
        "TELEMETRY_ONLY",
        "SAMPLING_UNSUPPORTED",
        "REGISTRATION_REJECTED",
        "SAMPLES_OBSERVED",
        "NO_SAMPLES",
        "CAPABILITY_ONLY",
        "INSUFFICIENT_SPACE",
        "READBACK_MATCH",
        "READBACK_MISMATCH",
        "INITIALIZATION_ERROR",
        "AUDIO_FORMAT_UNSUPPORTED",
        "READ_ERROR",
        "WRITE_ERROR",
        "CAPTURE_FORMAT_UNSUPPORTED",
        "INVALID_FRAME",
        "METADATA_UNAVAILABLE",
        "CAPTURE_ERROR",
        "CAMERA_DISCONNECTED",
        "CAMERA_BUSY",
        "CAMERA_UNAVAILABLE",
        "CAPTURE_MATCH",
        "METADATA_MISMATCH",
        "RESOURCE_BUSY",
    ]
    elapsed_ms: Annotated[int, Field(ge=0, le=60000)]
    metrics: Annotated[tuple[DiagnosticMetric, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def predicates(self) -> Self:
        values = {m.name: m.value for m in self.metrics}
        if len(values) != len(self.metrics):
            raise ValueError("Duplicate metrics.")
        if self.reason not in VALID_OUTCOME_REASONS[self.outcome]:
            raise ValueError(f"Reason {self.reason} is invalid for outcome {self.outcome}.")
        groups = {
            "battery": set(tuple(METRICS)[:12]) | {"end_" + k for k in tuple(METRICS)[:11]},
            "system": {
                "ram_total",
                "ram_available",
                "ram_threshold",
                "low_memory",
                "thermal_status",
            },
            "storage": {
                "storage_total",
                "storage_available",
                "bytes_written",
                "bytes_read",
                "readback_match",
            },
            "display": {"width", "height", "refresh_rate", "rotation", "mode_count", "brightness"}
            | {k for k in METRICS if re.fullmatch(r"mode[0-7]_(width|height|rate)", k)},
            "connectivity": {"wifi_enabled", "nfc_enabled", "gps_provider", "usb_devices"}
            | set(CONNECTIVITY_FEATURES)
            | {f"feature{i}" for i in range(21)},
            "audio_routes": {"route_count"} | {k for k in METRICS if k.startswith("route")},
            "touch": {
                "touch_cells",
                "max_contacts",
                "cell_coverage_percent",
                "tested_window_area_percent",
                "tested_display_area_percent",
                "layout_generation",
                *TOUCH_GEOMETRY,
            },
            "pixels": {"patterns_viewed", "user_report"},
            "speaker": {"tone_submitted", "user_report"},
            "vibration": {"effect_scheduled", "user_report"},
            "microphone": {"audio_samples", "audio_peak", "audio_rms", "user_report"},
            "sensor": {
                "sensor_type",
                "sensor_accuracy",
                "registered",
                "sample_count",
                "rejected_samples",
            }
            | {f"axis{i}_{s}" for i in range(3) for s in ("min", "max", "mean")},
            "camera": {
                "camera_facing",
                "camera_level",
                "flash_available",
                "autofocus_available",
                "frame_width",
                "frame_height",
                "frame_bytes",
                "capture_completed",
                "af_state",
                "frame_metadata_match",
                "luma_mean",
                "luma_variance",
            },
        }
        group = (
            "sensor"
            if self.diagnostic_id.startswith("sensor_")
            else "camera"
            if self.diagnostic_id.startswith("camera_")
            else self.diagnostic_id
        )
        if not values.keys() <= groups[group]:
            raise ValueError("Metric does not belong to this diagnostic.")
        for key in (
            "bytes_written",
            "bytes_read",
            "frame_width",
            "frame_height",
            "frame_bytes",
            "sample_count",
            "audio_samples",
            "rejected_samples",
        ):
            quantity = values.get(key)
            if quantity is not None and quantity < 0:
                raise ValueError("Negative collection quantity.")
        if self.reason == "USER_REPORTED" and values.get("user_report") is None:
            raise ValueError("User report missing.")
        if self.state == "COMPLETED" and self.reason in {
            "COLLECTING",
            "STOPPING",
            "CANCELLED",
            "TIMEOUT",
        }:
            raise ValueError("Terminal state and reason disagree.")
        # STOPPING: cancellation accepted, owned resources still being released; evidence frozen.
        if self.state == "RUNNING" and (
            self.outcome != "INCONCLUSIVE" or self.reason not in {"COLLECTING", "STOPPING"}
        ):
            raise ValueError("Running collection cannot conclude.")
        # An interrupted job reports either a clean interruption or a truthful cleanup failure.
        if self.state in {"CANCELLED", "EXPIRED"} and (self.outcome, self.reason) not in {
            ("INCONCLUSIVE", "CANCELLED" if self.state == "CANCELLED" else "TIMEOUT"),
            ("ERROR", "CLEANUP_ERROR"),
        }:
            raise ValueError("Interrupted collection cannot conclude.")
        if self.outcome in {"PASS", "FAIL"}:
            if self.state != "COMPLETED":
                raise ValueError("Functional conclusion requires completion.")
            valid = False
            if self.diagnostic_id == "storage":
                valid = (
                    values.get("bytes_written") == 65536
                    and values.get("bytes_read") is not None
                    and values.get("readback_match") == (1 if self.outcome == "PASS" else 0)
                    and self.reason
                    == ("READBACK_MATCH" if self.outcome == "PASS" else "READBACK_MISMATCH")
                )
                if self.outcome == "PASS":
                    valid = valid and values.get("bytes_read") == 65536
            elif self.diagnostic_id == "touch":
                valid = (
                    self.outcome == "PASS"
                    and self.reason == "TOUCH_COVERED"
                    and _touch_pass_evidence(values)
                )
            elif self.diagnostic_id.startswith("camera_"):
                # Luma statistics prove the captured frame carried pixel data, not only metadata.
                valid = (
                    self.outcome == "PASS"
                    and self.reason == "CAPTURE_MATCH"
                    and values.get("capture_completed") == 1
                    and values.get("frame_metadata_match") == 1
                    and all(
                        (values.get(k) or 0) > 0
                        for k in ("frame_width", "frame_height", "frame_bytes")
                    )
                    and values.get("luma_mean") is not None
                    and values.get("luma_variance") is not None
                )
            if not valid:
                raise ValueError("Functional conclusion lacks its specific predicate.")
        if "user_report" in values and self.outcome != "INCONCLUSIVE":
            raise ValueError("Human reports cannot create a measured hardware verdict.")
        return self
