"""Input validation utilities.

All external inputs that flow into subprocess arguments
must be validated here before use.
"""

from __future__ import annotations

import re

# ADB serial numbers are typically hex strings or IP:port addresses.
_SAFE_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")

# iOS UDID: 25-char or 40-char hex.
_SAFE_UDID_RE = re.compile(r"^[A-Fa-f0-9\-]{20,50}$")


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
    """Validate and return an iOS UDID."""
    if not udid:
        raise ValidationError("iOS UDID must not be empty.")
    # Strip hyphens for length check.
    stripped = udid.replace("-", "")
    if not (20 <= len(stripped) <= 50):
        raise ValidationError(f"iOS UDID length is unexpected: {len(stripped)} chars.")
    if not _SAFE_UDID_RE.match(udid):
        raise ValidationError(f"iOS UDID contains unexpected characters: {udid!r}.")
    return udid


_uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_scan_id(scan_id: str) -> str:
    """Validate a VECTOR scan ID (UUID format)."""
    if not _uuid_re.match(scan_id.lower()):
        raise ValidationError(f"Invalid scan_id format: {scan_id!r}")
    return scan_id.lower()
