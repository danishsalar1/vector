"""Platform-neutral device discovery and listing API endpoints.

GET /api/v1/devices            - list currently visible devices
GET /api/v1/devices/{id}       - get specific device
GET /api/v1/devices/{id}/capabilities  - get capability profile
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vector_agent.core.config import get_settings
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.session import device_session_manager
from vector_agent.models.device import ConnectedDevice, DeviceCapabilityProfile, Platform

logger = get_logger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceListResponse(BaseModel):
    devices: list[ConnectedDevice]
    count: int


def _get_android_bridge() -> AndroidDeviceBridge:
    settings = get_settings()
    return AndroidDeviceBridge(adb_path=settings.adb_path)


def _trigger_discovery() -> None:
    """Triggers discovery on all available bridges and reconciles sessions."""
    # Currently only Android is supported for discovery in Phase 2
    bridge = _get_android_bridge()
    discovery = bridge.discover_devices()

    from vector_agent.devices.android.bridge import AndroidIdentity

    # We pass a fetcher so the session manager doesn't depend on the bridge directly
    def fetch_identity(serial: str) -> AndroidIdentity:
        return bridge.get_identity(serial)

    device_session_manager.reconcile_android_discovery(
        discovery.devices, adb_identity_fetcher=fetch_identity
    )


@router.get("", response_model=DeviceListResponse)
async def list_devices() -> DeviceListResponse:
    """Discover and return currently connected devices across platforms."""
    # Trigger discovery first to ensure fresh state
    try:
        _trigger_discovery()
    except Exception as exc:
        logger.error("Discovery trigger failed: %s", exc)
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        raise HTTPException(
            status_code=503,
            detail=f"Device discovery failed: {exc}",
        ) from exc

    sessions = device_session_manager.list_sessions()
    devices = [session.to_connected_device() for session in sessions]
    return DeviceListResponse(devices=devices, count=len(devices))


@router.get("/{device_id}", response_model=ConnectedDevice)
async def get_device(device_id: str) -> ConnectedDevice:
    """Return details for a specific connected device by its opaque device_id."""
    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    return session.to_connected_device()


@router.get("/{device_id}/capabilities", response_model=DeviceCapabilityProfile)
async def get_device_capabilities(device_id: str) -> DeviceCapabilityProfile:
    """Return the capability profile for a specific device."""
    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    # Capability discovery is intentionally not implemented in Phase 2.
    # Return 501 Not Implemented so callers are not misled into thinking
    # the device does not exist (404) or that it has zero capabilities (200).
    raise HTTPException(
        status_code=501,
        detail=f"Capability discovery for device '{device_id}' is not yet implemented.",
    )
