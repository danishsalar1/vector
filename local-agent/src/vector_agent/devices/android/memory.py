"""Android memory telemetry parsing and data structures.

Uses safe read-only 'cat /proc/meminfo' to extract live kernel memory
telemetry from Android devices.

Invariants:
- Read-only fixed path; no arbitrary file cat API.
- Bounded parsing; handles whitespace, unit conversions, and kernel variations.
- Does not fabricate MemAvailable if missing on older kernels.
- Memory utilization is NOT interpreted as RAM hardware failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)

# Matches 'Key: 123456 kB'
_MEMINFO_LINE_PATTERN = re.compile(
    r"^([A-Za-z0-9_()]+):\s*(\d+)\s*([A-Za-z]+)?$",
)


@dataclass(frozen=True)
class MemoryTelemetry:
    """Normalized live memory telemetry from /proc/meminfo."""

    mem_total_bytes: int
    mem_free_bytes: int | None
    mem_available_bytes: int | None
    collected_at: datetime


@dataclass(frozen=True)
class MemoryTelemetryResult:
    """Result of memory telemetry collection, including evidence metadata."""

    telemetry: MemoryTelemetry | None
    status: str  # "PASS" | "INCONCLUSIVE" | "RESTRICTED" | "UNSUPPORTED" | "ERROR"
    confidence: float  # 0.0 - 1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


def parse_proc_meminfo(
    stdout: str,
    stderr: str = "",
    return_code: int = 0,
    truncated: bool = False,
    collected_at: datetime | None = None,
) -> MemoryTelemetryResult:
    """Parse '/proc/meminfo' output into MemoryTelemetryResult.

    Args:
        stdout: Content of /proc/meminfo.
        stderr: Subprocess stderr.
        return_code: Subprocess return code.
        truncated: True if output was truncated by subprocess policy.
        collected_at: Timestamp of collection.

    Returns:
        MemoryTelemetryResult with status, confidence, and telemetry if valid.
    """
    ts = collected_at or datetime.now(UTC)
    evidence_source = "ADB / /proc/meminfo"
    collection_method = "adb shell cat /proc/meminfo"

    if truncated:
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Memory telemetry output was truncated.",
            collected_at=ts,
        )

    lower_err = (stderr + " " + stdout).lower()
    if "permission denied" in lower_err or "securityexception" in lower_err:
        return MemoryTelemetryResult(
            telemetry=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Memory telemetry access restricted by platform permissions.",
            collected_at=ts,
        )

    if return_code != 0:
        if "no such file or directory" in lower_err or "not found" in lower_err:
            return MemoryTelemetryResult(
                telemetry=None,
                status="UNSUPPORTED",
                confidence=0.0,
                evidence_source=evidence_source,
                collection_method=collection_method,
                error="/proc/meminfo is not available on this device.",
                collected_at=ts,
            )
        return MemoryTelemetryResult(
            telemetry=None,
            status="ERROR",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"cat /proc/meminfo exited with return code {return_code}.",
            collected_at=ts,
        )

    stripped = stdout.strip()
    if not stripped:
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="/proc/meminfo returned empty output.",
            collected_at=ts,
        )

    # Keys consumed by VECTOR
    consumed_keys = frozenset({"MemTotal", "MemFree", "MemAvailable"})
    seen_values: dict[str, int] = {}

    for line in stripped.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        match = _MEMINFO_LINE_PATTERN.match(line_clean)
        if not match:
            # Check if line began with MemTotal but was malformed
            if line_clean.startswith("MemTotal:"):
                return MemoryTelemetryResult(
                    telemetry=None,
                    status="INCONCLUSIVE",
                    confidence=0.0,
                    evidence_source=evidence_source,
                    collection_method=collection_method,
                    error="MemTotal line is malformed in /proc/meminfo.",
                    collected_at=ts,
                )
            continue

        key, val_str, unit_str = match.groups()
        if key not in consumed_keys:
            continue

        # Strictly require standard 'kB' unit (case-insensitive)
        if unit_str is None or unit_str.lower() != "kb":
            if key == "MemTotal":
                return MemoryTelemetryResult(
                    telemetry=None,
                    status="INCONCLUSIVE",
                    confidence=0.0,
                    evidence_source=evidence_source,
                    collection_method=collection_method,
                    error=f"MemTotal has invalid or missing unit '{unit_str}'; expected 'kB'.",
                    collected_at=ts,
                )
            # Omit optional field if unit is invalid or missing
            continue

        try:
            val = int(val_str)
        except ValueError:
            if key == "MemTotal":
                return MemoryTelemetryResult(
                    telemetry=None,
                    status="INCONCLUSIVE",
                    confidence=0.0,
                    evidence_source=evidence_source,
                    collection_method=collection_method,
                    error="MemTotal numeric value is malformed.",
                    collected_at=ts,
                )
            continue

        bytes_val = val * 1024

        # Duplicate key handling:
        # Identical duplicate values are tolerated; conflicting duplicates return INCONCLUSIVE.
        if key in seen_values:
            if seen_values[key] != bytes_val:
                return MemoryTelemetryResult(
                    telemetry=None,
                    status="INCONCLUSIVE",
                    confidence=0.0,
                    evidence_source=evidence_source,
                    collection_method=collection_method,
                    error=f"Conflicting duplicate entries for {key} in /proc/meminfo.",
                    collected_at=ts,
                )
        else:
            seen_values[key] = bytes_val

    if "MemTotal" not in seen_values:
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="MemTotal not found or unparseable in /proc/meminfo.",
            collected_at=ts,
        )

    mem_total = seen_values["MemTotal"]
    mem_free = seen_values.get("MemFree")
    mem_available = seen_values.get("MemAvailable")

    # Coherence checks:
    # MemTotal must be positive.
    # MemFree and MemAvailable must be non-negative and not exceed MemTotal.
    if mem_total <= 0:
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="MemTotal value is non-positive or impossible.",
            collected_at=ts,
        )

    if mem_free is not None and (mem_free < 0 or mem_free > mem_total):
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="MemFree value is out of coherent bounds.",
            collected_at=ts,
        )

    if mem_available is not None and (mem_available < 0 or mem_available > mem_total):
        return MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="MemAvailable value is out of coherent bounds.",
            collected_at=ts,
        )

    telemetry = MemoryTelemetry(
        mem_total_bytes=mem_total,
        mem_free_bytes=mem_free,
        mem_available_bytes=mem_available,
        collected_at=ts,
    )

    return MemoryTelemetryResult(
        telemetry=telemetry,
        status="PASS",
        confidence=1.0,
        evidence_source=evidence_source,
        collection_method=collection_method,
        error=None,
        collected_at=ts,
    )
