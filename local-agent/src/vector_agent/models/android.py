"""Pydantic response models for Android device API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AndroidDeviceResponse(BaseModel):
    """API response representing an Android device and its connection state."""

    device_id: str
    """Internal transient identifier (not the ADB serial)."""

    connection_state: str
    """ADB device state: DEVICE | UNAUTHORIZED | OFFLINE | NO_DEVICE | MULTIPLE_DEVICES | ERROR."""

    adb_available: bool
    message: str

    # Identity — only present when state is DEVICE (authorized)
    manufacturer: str | None = None
    model: str | None = None
    device_codename: str | None = None
    android_version: str | None = None
    sdk_level: int | None = None
    brand: str | None = None

    discovered_at: datetime


class AndroidDeviceListResponse(BaseModel):
    """API response for GET /api/v1/devices/android."""

    devices: list[AndroidDeviceResponse]
    count: int
    state: str
    """Top-level discovery state: NO_DEVICE | UNAUTHORIZED | OFFLINE | DEVICE | MULTIPLE_DEVICES | ERROR."""
    message: str
    adb_available: bool


class BatteryTelemetryField(BaseModel):
    """A single battery telemetry field with its value."""

    label: str
    value: Any
    unit: str | None = None


class BatteryTelemetryResponse(BaseModel):
    """API response for GET /api/v1/devices/android/{device_id}/battery."""

    device_id: str
    status: str
    """PASS | INCONCLUSIVE | ERROR. PASS means telemetry was collected successfully."""

    status_note: str
    """Explains what PASS means — explicitly not battery health assessment."""

    confidence: float | None
    """None when collection confidence has not been empirically calibrated."""

    # Telemetry fields — None if unavailable
    level_pct: int | None = None
    charging_state: str | None = None
    health_state: str | None = None
    plugged: str | None = None
    voltage_v: float | None = None
    temperature_c: float | None = None
    technology: str | None = None
    present: bool | None = None

    # Evidence metadata
    evidence_source: str
    collection_method: str
    collected_at: datetime

    error: str | None = None
