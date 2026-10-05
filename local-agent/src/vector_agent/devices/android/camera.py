"""Android camera inventory parsing and data structures.

Uses safe read-only 'dumpsys media.camera' to extract camera device inventory
(device count and lens facing) from Android devices.

Invariants:
- Inventory only; never opens camera, captures images, or triggers camera app.
- Strictly privacy-safe; actively discards client history, package names, and PIDs.
- Raw dumpsys output is never placed into evidence records or logs.
- Zero cameras handled conservatively as INCONCLUSIVE, never hardware FAIL.
- PASS confirms valid camera inventory retrieval; does not verify image quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)

MAX_CAMERA_DEVICE_COUNT = 64

# Patterns to match number of cameras
_NUM_CAMERAS_PATTERN = re.compile(
    r"Number of (?:normal )?camera devices:\s*(\d+)",
    re.IGNORECASE,
)

# Pattern to match camera block headers:
# "Device 0 (v3.4):" or "Device 0 is closed, no client instance" or "Device 0:"
# "Camera ID: 0" or "Camera [0]:" or "Camera device 0:"
_CAMERA_HEADER_PATTERN = re.compile(
    r"^(?:Device\s+([A-Za-z0-9_-]+)(?:\s*\([^)]*\))?(?:\s+is\s+closed|\s*:|\s*$)|Camera\s*ID[:\s]+([A-Za-z0-9_-]+)|Camera\s*\[([A-Za-z0-9_-]+)\]|Camera\s*device\s+([A-Za-z0-9_-]+)(?:\s*\([^)]*\))?(?:\s*:|\s*$))",
    re.IGNORECASE,
)

_IGNORED_DEVICE_TOKENS = frozenset(
    {"provider", "service", "manager", "client", "instance", "info", "device", "hal"}
)

# Pattern to match facing line within a camera section:
# "Facing: BACK" or "Facing: 0" (0=BACK, 1=FRONT, 2=EXTERNAL)
_FACING_PATTERN = re.compile(
    r"(?:facing|lens_facing|camera\s+\w+\s+facing)[:\s]+([A-Za-z0-9_]+)",
    re.IGNORECASE,
)

# Facing normalization
_FACING_MAP: dict[str, str] = {
    "0": "BACK",
    "back": "BACK",
    "rear": "BACK",
    "1": "FRONT",
    "front": "FRONT",
    "2": "EXTERNAL",
    "external": "EXTERNAL",
}


@dataclass(frozen=True)
class CameraDeviceEntry:
    """A single normalized camera device entry."""

    camera_id: str
    facing: str | None  # "BACK" | "FRONT" | "EXTERNAL" | None


@dataclass(frozen=True)
class CameraInventory:
    """Normalized live camera inventory from media.camera service."""

    camera_count: int
    cameras: list[CameraDeviceEntry]
    collected_at: datetime


@dataclass(frozen=True)
class CameraInventoryResult:
    """Result of camera inventory collection, including evidence metadata."""

    inventory: CameraInventory | None
    status: str  # "PASS" | "INCONCLUSIVE" | "RESTRICTED" | "UNSUPPORTED" | "ERROR"
    confidence: float  # 0.0 - 1.0
    evidence_source: str
    collection_method: str
    error: str | None
    collected_at: datetime


def parse_camera_inventory(
    stdout: str,
    stderr: str = "",
    return_code: int = 0,
    truncated: bool = False,
    collected_at: datetime | None = None,
) -> CameraInventoryResult:
    """Parse 'dumpsys media.camera' output into CameraInventoryResult.

    Crucial Privacy Guarantee:
    Active client sections, package names, client PIDs, and session logs
    are filtered out immediately in memory and never preserved or exposed.

    Args:
        stdout: Standard output from 'dumpsys media.camera'.
        stderr: Subprocess stderr.
        return_code: Subprocess return code.
        truncated: True if output was truncated by subprocess policy.
        collected_at: Timestamp of collection.

    Returns:
        CameraInventoryResult with normalized inventory or safe failure status.
    """
    ts = collected_at or datetime.now(UTC)
    evidence_source = "ADB / dumpsys media.camera"
    collection_method = "adb shell dumpsys media.camera"

    if truncated:
        return CameraInventoryResult(
            inventory=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Camera inventory output was truncated; unable to verify complete inventory.",
            collected_at=ts,
        )

    lower_text = (stderr + " " + stdout).lower()

    if (
        "can't find service" in lower_text
        or "service not found" in lower_text
        or "does not exist" in lower_text
    ):
        return CameraInventoryResult(
            inventory=None,
            status="UNSUPPORTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Camera service is not available on this device.",
            collected_at=ts,
        )

    if "permission denial" in lower_text or "securityexception" in lower_text:
        return CameraInventoryResult(
            inventory=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Camera service access restricted by platform permissions.",
            collected_at=ts,
        )

    if return_code != 0:
        return CameraInventoryResult(
            inventory=None,
            status="ERROR",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"dumpsys media.camera exited with return code {return_code}.",
            collected_at=ts,
        )

    stripped = stdout.strip()
    if not stripped:
        return CameraInventoryResult(
            inventory=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="dumpsys media.camera returned empty output.",
            collected_at=ts,
        )

    # Privacy and noise filter:
    # If the output contains active clients (e.g. "Active Camera Clients:"),
    # we completely ignore lines in that section until a recognized section header
    # or camera device block resumes.
    lines = stripped.splitlines()
    in_client_section = False

    explicit_count: int | None = None
    discovered_cameras: list[CameraDeviceEntry] = []
    current_cam_id: str | None = None
    current_cam_facing: str | None = None

    def _flush_current_cam() -> None:
        nonlocal current_cam_id, current_cam_facing
        if current_cam_id is not None:
            clean_id = re.sub(r"[^A-Za-z0-9_-]", "", current_cam_id)
            if (
                clean_id
                and clean_id.lower() not in _IGNORED_DEVICE_TOKENS
                and not any(c.camera_id == clean_id for c in discovered_cameras)
            ):
                discovered_cameras.append(
                    CameraDeviceEntry(camera_id=clean_id, facing=current_cam_facing)
                )
        current_cam_id = None
        current_cam_facing = None

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        lower_line = line_clean.lower()

        # Detect active client section or user session info and suppress
        if any(
            marker in lower_line
            for marker in (
                "active camera client",
                "client history",
                "active clients",
                "camera clients:",
            )
        ):
            in_client_section = True
            _flush_current_cam()
            continue

        if in_client_section:
            # Check if we exited client section (new major section or camera device header)
            if (
                line_clean.startswith("==")
                or line_clean.startswith("--")
                or "camera hal device info" in lower_line
                or "camera provider" in lower_line
                or _CAMERA_HEADER_PATTERN.match(line_clean)
                or _NUM_CAMERAS_PATTERN.search(line_clean)
            ):
                in_client_section = False
            else:
                continue

        # Look for explicit camera count
        count_match = _NUM_CAMERAS_PATTERN.search(line_clean)
        if count_match:
            try:
                cnt = int(count_match.group(1))
                if cnt < 0 or cnt > MAX_CAMERA_DEVICE_COUNT:
                    return CameraInventoryResult(
                        inventory=None,
                        status="INCONCLUSIVE",
                        confidence=0.0,
                        evidence_source=evidence_source,
                        collection_method=collection_method,
                        error=f"Camera count {cnt} exceeds sanity bound [0, {MAX_CAMERA_DEVICE_COUNT}].",
                        collected_at=ts,
                    )
                if explicit_count is None or cnt > explicit_count:
                    explicit_count = cnt
            except ValueError:
                pass

        # Check for camera header
        header_match = _CAMERA_HEADER_PATTERN.match(line_clean)
        if header_match:
            # Capture non-empty group
            candidate_id: str | None = None
            for grp in header_match.groups():
                if grp:
                    candidate_id = grp
                    break
            if candidate_id and candidate_id.lower() not in _IGNORED_DEVICE_TOKENS:
                _flush_current_cam()
                current_cam_id = candidate_id
                continue

        # If inside a camera section, look for facing
        if current_cam_id is not None and current_cam_facing is None:
            facing_match = _FACING_PATTERN.search(line_clean)
            if facing_match:
                raw_facing = facing_match.group(1).lower()
                current_cam_facing = _FACING_MAP.get(raw_facing, raw_facing.upper())

    _flush_current_cam()

    # Unparseable camera output (no count and no devices) -> INCONCLUSIVE with inventory=None
    if explicit_count is None and not discovered_cameras:
        return CameraInventoryResult(
            inventory=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Could not parse camera count or camera devices from camera service output.",
            collected_at=ts,
        )

    # Zero detected cameras explicitly reported:
    # Zero detected cameras must NOT automatically become hardware FAIL.
    # Without trusted factory reference data, zero cameras is INCONCLUSIVE.
    if explicit_count == 0:
        return CameraInventoryResult(
            inventory=CameraInventory(camera_count=0, cameras=[], collected_at=ts),
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error="Camera service reported 0 camera devices. Inconclusive without reference specification.",
            collected_at=ts,
        )

    # Explicit count > 0 but zero camera device records parsed -> INCONCLUSIVE
    # NEVER synthesize camera IDs (e.g. range(final_count)).
    if explicit_count is not None and explicit_count > 0 and not discovered_cameras:
        return CameraInventoryResult(
            inventory=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=f"Camera service reported {explicit_count} devices, but zero camera device records could be parsed.",
            collected_at=ts,
        )

    # Count consistency: if both explicit count and parsed records exist, they must agree.
    if explicit_count is not None and explicit_count != len(discovered_cameras):
        return CameraInventoryResult(
            inventory=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source=evidence_source,
            collection_method=collection_method,
            error=(
                f"Camera count mismatch: reported {explicit_count} devices, "
                f"but parsed {len(discovered_cameras)} distinct camera records."
            ),
            collected_at=ts,
        )

    final_count = len(discovered_cameras)
    inventory = CameraInventory(
        camera_count=final_count,
        cameras=discovered_cameras,
        collected_at=ts,
    )

    return CameraInventoryResult(
        inventory=inventory,
        status="PASS",
        confidence=1.0,
        evidence_source=evidence_source,
        collection_method=collection_method,
        error=None,
        collected_at=ts,
    )
