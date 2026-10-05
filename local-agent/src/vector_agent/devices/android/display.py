"""Android display metrics parsing and data structures.

Uses safe read-only 'wm size' and 'wm density' to extract physical and
override display metrics from Android devices.

Invariants:
- Read-only; never mutates display resolution or density overrides.
- Keeps physical metrics distinct from logical/override metrics.
- Validates plausible display ranges.
- PASS confirms valid display metrics retrieval; does not verify panel defects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)

# Patterns for 'wm size':
# "Physical size: 1080x2400"
# "Override size: 720x1600"
_PHYSICAL_SIZE_PATTERN = re.compile(
    r"Physical\s+size\s*:\s*(\d+)\s*x\s*(\d+)",
    re.IGNORECASE,
)
_OVERRIDE_SIZE_PATTERN = re.compile(
    r"Override\s+size\s*:\s*(\d+)\s*x\s*(\d+)",
    re.IGNORECASE,
)

# Patterns for 'wm density':
# "Physical density: 440"
# "Override density: 320"
_PHYSICAL_DENSITY_PATTERN = re.compile(
    r"Physical\s+density\s*:\s*(\d+)",
    re.IGNORECASE,
)
_OVERRIDE_DENSITY_PATTERN = re.compile(
    r"Override\s+density\s*:\s*(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DisplayMetrics:
    """Normalized live display metrics from window manager."""

    physical_width: int
    physical_height: int
    physical_density: int
    override_width: int | None
    override_height: int | None
    override_density: int | None
    collected_at: datetime


@dataclass(frozen=True)
class DisplayMetricsResult:
    """Result of display metrics collection, including evidence metadata."""

    metrics: DisplayMetrics | None
    status: str  # "PASS" | "INCONCLUSIVE" | "RESTRICTED" | "UNSUPPORTED" | "ERROR"
    confidence: float  # 0.0 - 1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


def parse_display_metrics(
    size_stdout: str,
    density_stdout: str,
    size_rc: int = 0,
    density_rc: int = 0,
    size_stderr: str = "",
    density_stderr: str = "",
    truncated: bool = False,
    collected_at: datetime | None = None,
) -> DisplayMetricsResult:
    """Parse 'wm size' and 'wm density' outputs into DisplayMetricsResult.

    Args:
        size_stdout: Output of 'wm size'.
        density_stdout: Output of 'wm density'.
        size_rc: Return code of 'wm size'.
        density_rc: Return code of 'wm density'.
        size_stderr: Stderr of 'wm size'.
        density_stderr: Stderr of 'wm density'.
        truncated: True if either command output was truncated.
        collected_at: Timestamp of collection.

    Returns:
        DisplayMetricsResult with normalized metrics or safe failure status.
    """
    ts = collected_at or datetime.now(UTC)
    evidence_source = "ADB / wm size + wm density"
    collection_method = "adb shell wm size; wm density"

    if truncated:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Display metrics output was truncated.",
            collected_at=ts,
        )

    combined_err = (
        size_stderr + " " + density_stderr + " " + size_stdout + " " + density_stdout
    ).lower()

    # Permission check
    if "permission denial" in combined_err or "securityexception" in combined_err:
        return DisplayMetricsResult(
            metrics=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Window manager access restricted by platform permissions.",
            collected_at=ts,
        )

    # Missing tool check
    if "not found" in combined_err:
        return DisplayMetricsResult(
            metrics=None,
            status="UNSUPPORTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="wm command is not available on this device.",
            collected_at=ts,
        )

    # Exit code check
    if size_rc != 0 or density_rc != 0:
        return DisplayMetricsResult(
            metrics=None,
            status="ERROR",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"wm command exited with non-zero code (size={size_rc}, density={density_rc}).",
            collected_at=ts,
        )

    size_clean = size_stdout.strip()
    density_clean = density_stdout.strip()
    if not size_clean or not density_clean:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="wm size or density returned empty output.",
            collected_at=ts,
        )

    # Parse physical size
    phys_size_match = _PHYSICAL_SIZE_PATTERN.search(size_clean)
    if not phys_size_match:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Could not parse physical display size.",
            collected_at=ts,
        )

    try:
        pw = int(phys_size_match.group(1))
        ph = int(phys_size_match.group(2))
    except ValueError:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Physical display size values were malformed.",
            collected_at=ts,
        )

    # Parse override size if present
    ow: int | None = None
    oh: int | None = None
    override_size_match = _OVERRIDE_SIZE_PATTERN.search(size_clean)
    if override_size_match:
        try:
            ow = int(override_size_match.group(1))
            oh = int(override_size_match.group(2))
        except ValueError:
            ow, oh = None, None

    # Parse physical density
    phys_density_match = _PHYSICAL_DENSITY_PATTERN.search(density_clean)
    if not phys_density_match:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Could not parse physical display density.",
            collected_at=ts,
        )

    try:
        pd = int(phys_density_match.group(1))
    except ValueError:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Physical display density value was malformed.",
            collected_at=ts,
        )

    # Parse override density if present
    od: int | None = None
    override_density_match = _OVERRIDE_DENSITY_PATTERN.search(density_clean)
    if override_density_match:
        try:
            od = int(override_density_match.group(1))
        except ValueError:
            od = None

    # Range and sanity validation
    # Plausible phone/tablet physical resolution: 100 to 20,000 pixels
    # Plausible density: 50 to 2,000 dpi
    if pw <= 0 or ph <= 0 or pd <= 0:
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Display dimensions or density must be positive.",
            collected_at=ts,
        )

    if not (100 <= pw <= 20000 and 100 <= ph <= 20000 and 50 <= pd <= 2000):
        return DisplayMetricsResult(
            metrics=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Display metrics values are outside plausible hardware bounds.",
            collected_at=ts,
        )

    metrics = DisplayMetrics(
        physical_width=pw,
        physical_height=ph,
        physical_density=pd,
        override_width=ow,
        override_height=oh,
        override_density=od,
        collected_at=ts,
    )

    return DisplayMetricsResult(
        metrics=metrics,
        status="PASS",
        confidence=1.0,
        evidence_source=evidence_source,
        collection_method=collection_method,
        error=None,
        collected_at=ts,
    )
