"""Diagnostic event taxonomy and event model.

Locked event concepts:
- scan.started
- diagnostic.started
- diagnostic.progress
- diagnostic.evidence
- diagnostic.completed
- diagnostic.failed
- diagnostic.inconclusive
- scan.completed
- scan.failed

NO FAKE PROGRESS:
Do NOT emit fake percentages, timer-based progress, artificial delays, or
simulated component completion. If a diagnostic cannot produce meaningful
intermediate progress, progress remains None.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from vector_agent.models.device import DiagnosticResult, EvidenceRecord


class DiagnosticEventType(StrEnum):
    """Locked diagnostic event concepts."""

    SCAN_STARTED = "scan.started"
    DIAGNOSTIC_STARTED = "diagnostic.started"
    DIAGNOSTIC_PROGRESS = "diagnostic.progress"
    DIAGNOSTIC_EVIDENCE = "diagnostic.evidence"
    DIAGNOSTIC_COMPLETED = "diagnostic.completed"
    DIAGNOSTIC_FAILED = "diagnostic.failed"
    DIAGNOSTIC_INCONCLUSIVE = "diagnostic.inconclusive"
    SCAN_COMPLETED = "scan.completed"
    SCAN_FAILED = "scan.failed"


class DiagnosticEvent(BaseModel):
    """Structured diagnostic event representing actual engine state.

    Carries safe, normalized payloads:
    - Opaque device_id (never raw serial)
    - Normalized EvidenceRecord / DiagnosticResult
    - Safe message or reason
    - No raw serial, no raw ADB stderr, no secrets
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    scan_id: str
    device_id: str
    event_type: DiagnosticEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    diagnostic_id: str | None = None
    progress: float | None = None
    """Safe normalized progress (0.0 to 1.0) ONLY if truly known.
    Must remain None if intermediate progress cannot be truthfully measured.
    """
    evidence: EvidenceRecord | None = None
    result: DiagnosticResult | None = None
    message: str | None = None

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"Progress must be between 0.0 and 1.0, got {v}")
        return v

    def to_public_dict(self) -> dict[str, Any]:
        """Convert to a serializable dictionary safe for public API exposure."""
        data = self.model_dump(mode="json")
        # Explicitly ensure raw_serial or serial never appears in the dump
        data.pop("raw_serial", None)
        data.pop("serial", None)
        return data
