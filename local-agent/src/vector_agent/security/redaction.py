"""Identifier redaction utilities.

Sensitive device identifiers must never appear in logs, fixtures,
or API responses without sanitization.
"""

from __future__ import annotations

import hashlib
import re

# Patterns that look like real device identifiers.
_IMEI_PATTERN = re.compile(r"\b\d{15}\b")
_SERIAL_PATTERNS = [
    re.compile(r"\b[A-Z0-9]{6,20}\b"),  # broad serial pattern – context-dependent
]


def mask_identifier(identifier: str, visible_chars: int = 4) -> str:
    """Mask all but the last ``visible_chars`` of an identifier.

    Example::

        mask_identifier("866123456789012")  # -> "***********9012"
    """
    if not identifier:
        return ""
    n = len(identifier)
    if n <= visible_chars:
        return "*" * n
    return "*" * (n - visible_chars) + identifier[-visible_chars:]


def hash_identifier(identifier: str) -> str:
    """Return a stable SHA-256 hex digest of the identifier (first 16 chars).

    Use when persistent pseudonymous identity is needed for correlation.
    """
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


def redact_imei(text: str) -> str:
    """Replace 15-digit IMEI-like sequences in text with a redaction marker."""
    return _IMEI_PATTERN.sub("<IMEI:REDACTED>", text)


def sanitize_fixture(data: str) -> str:
    """Redact potential identifiers from fixture/log strings.

    Conservative – replaces patterns that resemble IMEIs.
    """
    return redact_imei(data)
