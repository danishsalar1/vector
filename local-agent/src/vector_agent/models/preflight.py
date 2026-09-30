"""Pydantic models for system preflight environment checks."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PreflightStatus(StrEnum):
    """Status of an individual preflight environment check."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PreflightOverall(StrEnum):
    """Overall environment readiness state."""

    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class PreflightCheck(BaseModel):
    """Individual environment or tooling readiness check."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(description="Unique identifier for the check, e.g. 'os_platform'")
    name: str = Field(description="Human-readable check title")
    category: str = Field(
        description="Subsystem category: platform | runtime | android | ios | agent"
    )
    status: PreflightStatus = Field(description="Check outcome status")
    message: str = Field(description="Explanatory or actionable message")
    required: bool = Field(
        default=False, description="Whether this check is required for basic local agent operation"
    )
    details: str | None = Field(
        default=None, description="Optional diagnostic details such as tool path or version"
    )
    detail: str | None = Field(default=None, description="Backward-compatibility alias for details")


class PreflightResponse(BaseModel):
    """Aggregate preflight response returned by /api/v1/system/preflight."""

    model_config = ConfigDict(populate_by_name=True)

    overall: PreflightOverall = Field(description="High-level readiness: READY | PARTIAL | BLOCKED")
    overall_status: PreflightOverall = Field(
        description="Explicit alias for overall readiness state"
    )
    checks: list[PreflightCheck] = Field(description="List of all evaluated checks")
    items: list[PreflightCheck] = Field(description="Backward-compatibility alias for checks")
    timestamp: datetime = Field(description="UTC timestamp when evaluation completed")
