"""Input validation utilities.

All external inputs that flow into subprocess arguments
must be validated here before use.
"""

from __future__ import annotations

import re

# ADB serial numbers are typically hex strings or IP:port addresses.
_SAFE_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")

# iOS UDID: modern and legacy forms (hex or alphanumeric with optional hyphens, 16-64 chars).
# Must start and end with alphanumeric character (no option-like prefixes or trailing hyphens).
# Uses \Z to prohibit trailing newline characters.
_SAFE_UDID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{14,62}[A-Za-z0-9]\Z")


class ValidationError(ValueError):
    """Raised when an external input fails validation."""


def validate_device_serial(serial: str) -> str:
    """Validate and return an Android device serial number.

    Raises ValidationError if the serial does not match the expected pattern.
    This prevents command injection if a serial is ever interpolated into a command array.
    """
    if not serial:
        raise ValidationError("Device serial must not be empty.")
    if not _SAFE_SERIAL_RE.match(serial):
        raise ValidationError(
            "Device serial contains unexpected characters. "
            "Expected alphanumeric, dash, dot, colon, or underscore (max 64 chars)."
        )
    return serial


def validate_ios_udid(udid: str) -> str:
    """Validate and return an iOS UDID.

    Enforces safe identifier characters and bounded length for command arguments.
    Never exposes raw input in error messages.
    """
    if not udid:
        raise ValidationError("iOS UDID must not be empty.")
    if any(c in udid for c in "\r\n\0\t "):
        raise ValidationError("iOS UDID contains invalid control or whitespace characters.")
    if udid.startswith("-") or udid.endswith("-") or "--" in udid:
        raise ValidationError("iOS UDID contains invalid hyphen placement or option prefix.")
    stripped = udid.replace("-", "")
    if not (16 <= len(stripped) <= 64):
        raise ValidationError(f"iOS UDID length is unexpected: {len(stripped)} chars.")
    if not stripped.isalnum():
        raise ValidationError("iOS UDID must contain alphanumeric characters.")
    if not _SAFE_UDID_RE.match(udid):
        raise ValidationError("iOS UDID contains unexpected characters.")
    return udid


_uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_scan_id(scan_id: str) -> str:
    """Validate a VECTOR scan ID (UUID format)."""
    if not _uuid_re.match(scan_id.lower()):
        raise ValidationError(f"Invalid scan_id format: {scan_id!r}")
    return scan_id.lower()
