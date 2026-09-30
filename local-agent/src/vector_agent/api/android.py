"""Android device discovery and battery telemetry API endpoints.

GET /api/v1/devices/android
    Discovers connected Android devices via ADB.
    Returns: AndroidDeviceListResponse with typed state and minimal identity.

GET /api/v1/devices/android/{device_id}/battery
    Collects battery telemetry from an authorized Android device.
    Returns: BatteryTelemetryResponse.

Security invariants enforced:
- device_id is mapped to a validated ADB serial internally.
- No arbitrary ADB commands are accepted from callers.
- The {device_id} path parameter never becomes a shell fragment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from vector_agent.core.config import get_settings
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import (
    AdbDeviceState,
    AndroidDeviceBridge,
)
from vector_agent.models.android import (
    AndroidDeviceListResponse,
    AndroidDeviceResponse,
    BatteryTelemetryResponse,
)
from vector_agent.security.validation import validate_device_serial

logger = get_logger(__name__)

router = APIRouter(prefix="/devices/android", tags=["android"])

# ---------------------------------------------------------------------------
# Internal device registry
# ---------------------------------------------------------------------------
# Maps opaque device_id strings to validated ADB serials for the lifetime of
# the discovery session.  Never persisted; purely in-memory.
#
# This ensures the {device_id} URL parameter is NEVER passed directly to ADB.
# ---------------------------------------------------------------------------
_device_registry: dict[str, str] = {}  # device_id -> validated serial


def _get_bridge() -> AndroidDeviceBridge:
    settings = get_settings()
    return AndroidDeviceBridge(adb_path=settings.adb_path)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_device_id(serial: str) -> str:
    """Produce a deterministic, stable opaque device_id from a serial.

    Uses a simple prefix + hash to avoid exposing the real serial in URLs.
    """
    import hashlib

    hashed = hashlib.sha256(serial.encode()).hexdigest()[:12]
    return f"android-{hashed}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=AndroidDeviceListResponse)
async def discover_android_devices() -> AndroidDeviceListResponse:
    """Discover connected Android devices via ADB.

    Performs 'adb devices -l' and returns structured state.
    Does not accept arbitrary commands from the frontend.
    """
    bridge = _get_bridge()
    discovery = bridge.discover_devices()

    response_devices: list[AndroidDeviceResponse] = []

    for entry in discovery.devices:
        device_id = _make_device_id(entry.serial)

        identity_kwargs: dict[str, object] = {}
        if entry.state == AdbDeviceState.DEVICE:
            # Register validated serial for battery endpoint
            _device_registry[device_id] = entry.serial

            # Retrieve identity
            try:
                identity = bridge.get_identity(entry.serial)
                identity_kwargs = {
                    "manufacturer": identity.manufacturer,
                    "model": identity.model,
                    "device_codename": identity.device_codename,
                    "android_version": identity.android_version,
                    "sdk_level": identity.sdk_level,
                    "brand": identity.brand,
                }
            except Exception as exc:
                logger.warning("Failed to retrieve identity for device %s: %s", device_id, exc)
        else:
            # Do not register non-authorized serials for battery access
            _device_registry.pop(device_id, None)

        response_devices.append(
            AndroidDeviceResponse(
                device_id=device_id,
                connection_state=entry.state.value,
                adb_available=discovery.adb_available,
                message=discovery.message,
                discovered_at=datetime.now(UTC),
                **identity_kwargs,
            )
        )

    return AndroidDeviceListResponse(
        devices=response_devices,
        count=len(response_devices),
        state=discovery.state.value,
        message=discovery.message,
        adb_available=discovery.adb_available,
    )


@router.get("/{device_id}/battery", response_model=BatteryTelemetryResponse)
async def get_android_battery(device_id: str) -> BatteryTelemetryResponse:
    """Collect battery telemetry from an authorized Android device.

    The device_id must have been registered by a prior discovery call.
    NEVER exposes or accepts raw ADB serials from the URL.

    IMPORTANT: PASS status means battery telemetry was collected successfully.
    It does NOT represent a battery health assessment.
    """
    serial = _device_registry.get(device_id)
    if serial is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Device '{device_id}' not found in registry. "
                "Run device discovery first, or the device may have disconnected."
            ),
        )

    # Double-validate the stored serial before use
    try:
        validated_serial = validate_device_serial(serial)
    except Exception as exc:
        logger.error("Serial validation failed for device %s: %s", device_id, exc)
        raise HTTPException(status_code=500, detail="Internal serial validation error.") from exc

    bridge = _get_bridge()
    result = bridge.get_battery_telemetry(validated_serial)

    tel = result.telemetry

    return BatteryTelemetryResponse(
        device_id=device_id,
        status=result.status,
        status_note=(
            "PASS confirms successful battery telemetry collection. "
            "It does not represent full battery-health assessment."
        ),
        confidence=result.confidence,
        level_pct=tel.level if tel else None,
        charging_state=tel.status if tel else None,
        health_state=tel.health if tel else None,
        plugged=tel.plugged if tel else None,
        voltage_v=tel.voltage_volts if tel else None,
        temperature_c=tel.temperature_celsius if tel else None,
        technology=tel.technology if tel else None,
        present=tel.present if tel else None,
        evidence_source=result.evidence_source,
        collection_method=result.collection_method,
        collected_at=result.collected_at,
        error=result.error,
    )
