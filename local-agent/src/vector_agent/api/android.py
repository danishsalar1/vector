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

from fastapi import APIRouter, HTTPException

from vector_agent.core.config import get_settings
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import (
    AndroidDeviceBridge,
    AndroidIdentity,
)
from vector_agent.devices.session import device_session_manager
from vector_agent.models.android import (
    AndroidDeviceListResponse,
    AndroidDeviceResponse,
    BatteryTelemetryResponse,
)
from vector_agent.models.device import ConnectionState, Platform
from vector_agent.security.validation import validate_device_serial

logger = get_logger(__name__)

router = APIRouter(prefix="/devices/android", tags=["android"])


def _get_bridge() -> AndroidDeviceBridge:
    settings = get_settings()
    return AndroidDeviceBridge(adb_path=settings.adb_path)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=AndroidDeviceListResponse)
def discover_android_devices() -> AndroidDeviceListResponse:
    """Discover connected Android devices via ADB.

    Performs 'adb devices -l' and returns structured state.
    Does not accept arbitrary commands from the frontend.
    """
    bridge = _get_bridge()
    discovery = bridge.discover_devices()

    def fetch_identity(serial: str) -> AndroidIdentity:
        return bridge.get_identity(serial)

    device_session_manager.reconcile_android_discovery(
        discovery.devices, adb_identity_fetcher=fetch_identity
    )

    response_devices: list[AndroidDeviceResponse] = []

    # We reconstruct the response from sessions to ensure consistency
    sessions = [s for s in device_session_manager.list_sessions() if s.platform == Platform.ANDROID]
    for session in sessions:
        identity_kwargs = {}
        if session.identity:
            identity_kwargs = {
                "manufacturer": session.identity.manufacturer,
                "model": session.identity.model,
                "device_codename": session.identity.device_codename,
                "android_version": session.identity.android_version,
                "sdk_level": session.identity.android_sdk_level,
                "brand": session.identity.brand,
            }

        # Map ConnectionState to legacy AdbDeviceState
        legacy_state = session.connection_state.value
        if session.connection_state.value == "CONNECTED":
            legacy_state = "DEVICE"

        response_devices.append(
            AndroidDeviceResponse(
                device_id=session.device_id,
                connection_state=legacy_state,
                adb_available=discovery.adb_available,
                message=discovery.message,
                discovered_at=session.last_seen,
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
def get_android_battery(device_id: str) -> BatteryTelemetryResponse:
    """Collect battery telemetry from an authorized Android device.

    The device_id must have been registered by a prior discovery call.
    NEVER exposes or accepts raw ADB serials from the URL.

    IMPORTANT: PASS status means battery telemetry was collected successfully.
    It does NOT represent a battery health assessment.
    """
    session = device_session_manager.get_session(device_id)
    if session is None or session.platform != Platform.ANDROID:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Device '{device_id}' not found in registry. "
                "Run device discovery first, or the device may have disconnected."
            ),
        )

    if session.connection_state == ConnectionState.UNAUTHORIZED:
        raise HTTPException(
            status_code=403,
            detail=f"Device '{device_id}' is unauthorized. Approve USB debugging on the device.",
        )

    if session.connection_state != ConnectionState.CONNECTED:
        raise HTTPException(
            status_code=404,
            detail=f"Device '{device_id}' is not connected (state: {session.connection_state.value}).",
        )

    serial = session.get_serial_for_diagnostic()
    if serial is None:
        raise HTTPException(
            status_code=404,
            detail=f"Device '{device_id}' is not available for diagnostics.",
        )

    # Double-validate the stored serial before use
    try:
        validated_serial = validate_device_serial(serial)
    except Exception as exc:
        logger.error("Serial validation failed for device %s: %s", device_id, exc)
        raise HTTPException(status_code=500, detail="Internal serial validation error.") from exc

    bridge = _get_bridge()
    epoch = session.session_epoch
    result = bridge.get_battery_telemetry(validated_serial)
    if session.session_epoch != epoch or session.connection_state != ConnectionState.CONNECTED:
        raise HTTPException(status_code=409, detail="Device session changed during collection.")

    tel = result.telemetry

    return BatteryTelemetryResponse(
        device_id=device_id,
        status=result.status,
        status_note=(
            "PASS confirms successful battery telemetry collection. "
            "It does not represent full battery-health assessment."
        ),
        confidence=None,
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
