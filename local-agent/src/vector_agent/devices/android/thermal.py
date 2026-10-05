"""Android thermal telemetry parsing and data structures.

Uses safe read-only 'dumpsys thermalservice' to extract live thermal status
and sensor telemetry from Android devices.

Invariants:
- Read-only service query; no shell globs over /sys.
- Normalizes thermal status codes and unambiguous Celsius temperatures.
- Does not guess Celsius vs millidegrees if ambiguous.
- Does not invent temperature health thresholds or hardware failure from heat.
- Missing service yields UNSUPPORTED; permission block yields RESTRICTED.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)

# Android ThermalService Status definitions (android.os.Temperature / IThermalService)
THERMAL_STATUS_LABELS: dict[int, str] = {
    0: "NONE",
    1: "LIGHT",
    2: "MODERATE",
    3: "SEVERE",
    4: "CRITICAL",
    5: "EMERGENCY",
    6: "SHUTDOWN",
}

# Regex to extract thermal status
_THERMAL_STATUS_PATTERN = re.compile(
    r"(?:Current\s+Thermal\s+Status|thermal\s+status|ThermalStatus)\s*:\s*(\d+)",
    re.IGNORECASE,
)

# Regex to extract Temperature object fields from dumpsys thermalservice
# Example: Temperature{mValue=32.5, mType=3, mName=cpu-0-0-usr, mStatus=0}
_TEMP_OBJECT_PATTERN = re.compile(
    r"Temperature\{([^}]+)\}",
)


@dataclass(frozen=True)
class ThermalSensorSample:
    """A single normalized thermal sensor reading."""

    name: str
    temperature_celsius: float
    sensor_type: str | None = None
    status_code: int | None = None


@dataclass(frozen=True)
class ThermalTelemetry:
    """Normalized live thermal telemetry from dumpsys thermalservice."""

    thermal_status_code: int | None
    thermal_status_label: str | None
    sensor_count: int
    sensors: list[ThermalSensorSample]
    collected_at: datetime


@dataclass(frozen=True)
class ThermalTelemetryResult:
    """Result of thermal telemetry collection, including evidence metadata."""

    telemetry: ThermalTelemetry | None
    status: str  # "PASS" | "INCONCLUSIVE" | "RESTRICTED" | "UNSUPPORTED" | "ERROR"
    confidence: float  # 0.0 - 1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


def parse_dumpsys_thermal(
    stdout: str,
    stderr: str = "",
    return_code: int = 0,
    truncated: bool = False,
    collected_at: datetime | None = None,
) -> ThermalTelemetryResult:
    """Parse 'dumpsys thermalservice' output into ThermalTelemetryResult.

    Args:
        stdout: Standard output from 'dumpsys thermalservice'.
        stderr: Subprocess stderr.
        return_code: Subprocess return code.
        truncated: True if output was truncated by subprocess policy.
        collected_at: Timestamp of collection.

    Returns:
        ThermalTelemetryResult with status, confidence, and telemetry if valid.
    """
    ts = collected_at or datetime.now(UTC)
    evidence_source = "ADB / dumpsys thermalservice"
    collection_method = "adb shell dumpsys thermalservice"

    if truncated:
        return ThermalTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Thermal telemetry output was truncated.",
            collected_at=ts,
        )

    lower_text = (stderr + " " + stdout).lower()

    # Check for service absence
    if (
        "can't find service" in lower_text
        or "service not found" in lower_text
        or "does not exist" in lower_text
    ):
        return ThermalTelemetryResult(
            telemetry=None,
            status="UNSUPPORTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Thermal service is not available on this device.",
            collected_at=ts,
        )

    # Check for permission denial
    if "permission denial" in lower_text or "securityexception" in lower_text:
        return ThermalTelemetryResult(
            telemetry=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Thermal service access restricted by platform permissions.",
            collected_at=ts,
        )

    if return_code != 0:
        return ThermalTelemetryResult(
            telemetry=None,
            status="ERROR",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"dumpsys thermalservice exited with return code {return_code}.",
            collected_at=ts,
        )

    stripped = stdout.strip()
    if not stripped:
        return ThermalTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="dumpsys thermalservice returned empty output.",
            collected_at=ts,
        )

    # Parse thermal status code
    status_code: int | None = None
    status_label: str | None = None
    status_match = _THERMAL_STATUS_PATTERN.search(stripped)
    if status_match:
        try:
            status_code = int(status_match.group(1))
            status_label = THERMAL_STATUS_LABELS.get(status_code, "UNKNOWN")
        except ValueError:
            status_code = None

    # Parse individual sensor readings with section-aware deduplication
    # Map (name, sensor_type) -> (ThermalSensorSample, priority)
    # Priority: HAL=2, CACHED=1, UNKNOWN=0
    deduped_sensors: dict[tuple[str, str | None], tuple[ThermalSensorSample, int]] = {}
    current_section = "UNKNOWN"

    for line in stripped.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        line_lower = line_clean.lower()
        if "current temperatures from hal" in line_lower:
            current_section = "HAL"
        elif "cached temperatures" in line_lower:
            current_section = "CACHED"

        priority = 2 if current_section == "HAL" else (1 if current_section == "CACHED" else 0)

        for match in _TEMP_OBJECT_PATTERN.finditer(line_clean):
            props_str = match.group(1)
            # Parse key=value pairs inside Temperature{...}
            props: dict[str, str] = {}
            for pair in props_str.split(","):
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    props[k.strip()] = v.strip()

            raw_val = props.get("mValue")
            name = props.get("mName", "unknown")
            raw_type = props.get("mType")
            raw_status = props.get("mStatus")

            if raw_val is None:
                continue

            try:
                temp_c = float(raw_val)
            except ValueError:
                continue

            # Must be finite (rejects NaN, +inf, -inf)
            if not math.isfinite(temp_c):
                continue

            # In Android thermalservice, mValue is documented as floating-point Celsius.
            # Plausibility sanity filter: standard operating sensor range (-30C to 150C).
            # Values outside this range (e.g. millidegree numbers like 35000 or negative errors like -999)
            # must NOT be guessed as millidegrees vs Celsius; skip them to maintain truthfulness.
            if temp_c < -30.0 or temp_c > 150.0:
                continue

            sensor_status: int | None = None
            if raw_status:
                try:
                    sensor_status = int(raw_status)
                except ValueError:
                    sensor_status = None

            sample = ThermalSensorSample(
                name=name,
                temperature_celsius=round(temp_c, 2),
                sensor_type=raw_type,
                status_code=sensor_status,
            )

            sensor_key = (name, raw_type)
            if sensor_key in deduped_sensors:
                _, existing_priority = deduped_sensors[sensor_key]
                if priority > existing_priority:
                    deduped_sensors[sensor_key] = (sample, priority)
            else:
                deduped_sensors[sensor_key] = (sample, priority)

    sensors: list[ThermalSensorSample] = [sample for sample, _ in deduped_sensors.values()]

    # Check if we obtained enough valid thermal telemetry
    if status_code is None and not sensors:
        return ThermalTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Could not parse recognized thermal status or sensor readings.",
            collected_at=ts,
        )

    telemetry = ThermalTelemetry(
        thermal_status_code=status_code,
        thermal_status_label=status_label,
        sensor_count=len(sensors),
        sensors=sensors,
        collected_at=ts,
    )

    return ThermalTelemetryResult(
        telemetry=telemetry,
        status="PASS",
        confidence=1.0,
        evidence_source=evidence_source,
        collection_method=collection_method,
        error=None,
        collected_at=ts,
    )
