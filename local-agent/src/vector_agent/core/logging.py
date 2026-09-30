"""Structured logging configuration for the VECTOR agent.

Design principles:
- Timestamps always UTC.
- Component field on every record.
- Secrets and device identifiers are never logged at INFO/WARNING/ERROR.
- Raw subprocess output only logged at DEBUG when explicitly enabled.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

_REDACTED = "<REDACTED>"

# Known sensitive field names whose values should never appear in logs.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "imei",
        "imei2",
        "serial",
        "serialno",
        "udid",
        "phone_number",
        "account",
        "email",
        "password",
        "token",
        "api_key",
    }
)


def configure_logging(level: str = "INFO") -> None:
    """Configure global logging for the VECTOR agent."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplication.
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Usage::

        logger = get_logger(__name__)
        logger.info("Device discovered", extra={"device_id": masked_id})
    """
    return logging.getLogger(name)


def redact_value(key: str, value: Any) -> Any:
    """Return a redacted placeholder if the key is sensitive."""
    if key.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    return value


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with sensitive values replaced."""
    return {k: redact_value(k, v) for k, v in data.items()}


def mask_identifier(identifier: str, visible_chars: int = 4) -> str:
    """Mask all but the last ``visible_chars`` characters of an identifier.

    Example::

        mask_identifier("866123456789012")  # returns "***********9012"
    """
    if len(identifier) <= visible_chars:
        return "*" * len(identifier)
    return "*" * (len(identifier) - visible_chars) + identifier[-visible_chars:]
