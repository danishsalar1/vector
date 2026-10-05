"""Android storage telemetry parsing and data structures.

Uses safe read-only 'df -k /data' to extract live filesystem telemetry
for the primary Android user data filesystem.

Invariants:
- Read-only; no filesystem mutation.
- Bounded parsing; handles whitespace and line wraps.
- Validates coherence; impossible values result in INCONCLUSIVE, not hardware FAIL.
- Privacy-safe; never inspects user filenames or private storage paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StorageTelemetry:
    """Normalized live storage telemetry for the primary data filesystem."""

    total_bytes: int
    used_bytes: int
    available_bytes: int
    utilization_percent: float | None
    logical_target: str
    collected_at: datetime


@dataclass(frozen=True)
class StorageTelemetryResult:
    """Result of storage telemetry collection, including evidence metadata."""

    telemetry: StorageTelemetry | None
    status: str  # "PASS" | "INCONCLUSIVE" | "RESTRICTED" | "UNSUPPORTED" | "ERROR"
    confidence: float  # 0.0 - 1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


def parse_storage_df(
    stdout: str,
    stderr: str = "",
    return_code: int = 0,
    truncated: bool = False,
    collected_at: datetime | None = None,
) -> StorageTelemetryResult:
    """Parse 'df -k /data' output into StorageTelemetryResult.

    Args:
        stdout: Standard output from 'df -k /data'.
        stderr: Standard error from command execution.
        return_code: Process return code.
        truncated: True if output was truncated by subprocess policy.
        collected_at: Timestamp of collection (defaults to now).

    Returns:
        StorageTelemetryResult with status, confidence, and telemetry if valid.
    """
    ts = collected_at or datetime.now(UTC)
    evidence_source = "ADB / df -k /data"
    collection_method = "adb shell df -k /data"

    if truncated:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Storage telemetry output was truncated.",
            collected_at=ts,
        )

    # Check for security / permission denial
    lower_err = (stderr + " " + stdout).lower()
    if "permission denied" in lower_err or "securityexception" in lower_err:
        return StorageTelemetryResult(
            telemetry=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Storage telemetry access restricted by platform permissions.",
            collected_at=ts,
        )

    if return_code != 0:
        if "not found" in lower_err:
            return StorageTelemetryResult(
                telemetry=None,
                status="UNSUPPORTED",
                confidence=0.0,
                evidence_source=evidence_source,
                collection_method=collection_method,
                error="df command is not available on this device.",
                collected_at=ts,
            )
        return StorageTelemetryResult(
            telemetry=None,
            status="ERROR",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"df command exited with return code {return_code}.",
            collected_at=ts,
        )

    stripped = stdout.strip()
    if not stripped:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="df returned empty output.",
            collected_at=ts,
        )

    # Parse lines and tokenize.
    # Handle toybox, toolbox, and coreutils formats, including wrapped long device names.
    # Typical header: Filesystem 1K-blocks Used Available Use% Mounted on
    # Row: /dev/block/dm-46 111582236 25642188 85806652 23% /data
    # Or wrapped:
    # /dev/block/bootdevice/by-name/userdata
    #                      111582236 25642188 85806652 23% /data
    lines = stripped.splitlines()
    all_tokens: list[str] = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        # Skip header lines
        if any(h in parts[0].lower() for h in ("filesystem", "1k-blocks", "1024-blocks")):
            continue
        all_tokens.extend(parts)

    # Search for token sequence ending with "/data" (or "/data/")
    target_idx = -1
    for i, tok in enumerate(all_tokens):
        if tok == "/data" or tok == "/data/":
            target_idx = i
            break

    if target_idx == -1:
        # Fallback: line containing "/data" as the final token
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="No storage entry for /data was found.",
            collected_at=ts,
        )

    # We expect before target_idx:
    # ... [total_k, used_k, avail_k, use_pct, "/data"]
    if target_idx < 4:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Insufficient columns in df output for /data.",
            collected_at=ts,
        )

    total_k_str = all_tokens[target_idx - 4]
    used_k_str = all_tokens[target_idx - 3]
    avail_k_str = all_tokens[target_idx - 2]
    pct_str = all_tokens[target_idx - 1]

    try:
        total_k = int(total_k_str)
        used_k = int(used_k_str)
        avail_k = int(avail_k_str)
    except ValueError:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Malformed numeric storage metrics in df output.",
            collected_at=ts,
        )

    # Utilization percent parsing
    util_pct: float | None = None
    if pct_str.endswith("%"):
        try:
            util_pct = float(pct_str[:-1])
        except ValueError:
            util_pct = None

    total_bytes = total_k * 1024
    used_bytes = used_k * 1024
    available_bytes = avail_k * 1024

    # Validation:
    # total must be positive, used/available must not be negative
    # Internal coherence: neither used nor available can exceed total
    if total_bytes <= 0 or used_bytes < 0 or available_bytes < 0:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Impossible or negative storage values encountered.",
            collected_at=ts,
        )

    if used_bytes > total_bytes or available_bytes > total_bytes:
        return StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Storage capacity values are internally contradictory (used or available exceeds total).",
            collected_at=ts,
        )

    # If utilization percent was not reported directly, compute it
    if util_pct is None and total_bytes > 0:
        util_pct = round((used_bytes / total_bytes) * 100.0, 1)

    telemetry = StorageTelemetry(
        total_bytes=total_bytes,
        used_bytes=used_bytes,
        available_bytes=available_bytes,
        utilization_percent=util_pct,
        logical_target="/data",
        collected_at=ts,
    )

    return StorageTelemetryResult(
        telemetry=telemetry,
        status="PASS",
        confidence=1.0,
        evidence_source=evidence_source,
        collection_method=collection_method,
        error=None,
        collected_at=ts,
    )
