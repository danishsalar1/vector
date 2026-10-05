"""Platform-neutral device discovery and listing API endpoints.

GET /api/v1/devices            - list currently visible devices
GET /api/v1/devices/{id}       - get specific device
GET /api/v1/devices/{id}/capabilities  - get capability profile
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from vector_agent.core.config import get_settings
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.session import (
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    device_session_manager,
)
from vector_agent.models.device import (
    ConnectedDevice,
    ConnectionState,
    DeviceCapabilityProfile,
    Platform,
)

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
    # Currently only Android is supported for discovery in Phase 2/4
    bridge = _get_android_bridge()
    discovery = bridge.discover_devices()

    from vector_agent.devices.android.bridge import AndroidIdentity

    # Pass fetchers so session manager does not depend on bridge directly
    def fetch_identity(serial: str) -> AndroidIdentity:
        return bridge.get_identity(serial)

    def fetch_capabilities(serial: str, device_id: str) -> DeviceCapabilityProfile:
        return bridge.discover_capabilities(serial, device_id=device_id)

    device_session_manager.reconcile_android_discovery(
        discovery.devices,
        adb_identity_fetcher=fetch_identity,
        adb_capability_fetcher=fetch_capabilities,
    )


@router.get("", response_model=DeviceListResponse)
async def list_devices() -> DeviceListResponse:
    """Discover and return currently connected devices across platforms."""
    # Trigger discovery first to ensure fresh state (offloaded from event loop)
    try:
        await run_in_threadpool(_trigger_discovery)
    except Exception as exc:
        logger.error("Discovery trigger failed (%s)", type(exc).__name__)
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        raise HTTPException(
            status_code=503,
            detail="Device discovery failed.",
        ) from None

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
async def get_device_capabilities(
    device_id: str,
    refresh: bool = False,
) -> DeviceCapabilityProfile:
    """Return the capability profile for a specific device.

    Requirements:
    - unknown device -> 404 Not Found
    - unauthorized device -> 403 Forbidden
    - offline device -> 400 Bad Request (cannot discover or masquerade offline device)
    - non-Android device (e.g. iOS) -> 501 Not Implemented
    - connected Android device -> runtime capability snapshot, refreshable on request
    """
    # Refresh connection state first so physically disconnected devices are reconciled to OFFLINE
    try:
        await run_in_threadpool(_trigger_discovery)
    except Exception as exc:
        logger.error(
            "Discovery trigger failed before capability check (%s)",
            type(exc).__name__,
        )
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        raise HTTPException(
            status_code=503,
            detail="Device discovery failed.",
        ) from None

    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    if session.connection_state == ConnectionState.UNAUTHORIZED:
        raise HTTPException(
            status_code=403,
            detail=f"Device '{device_id}' is unauthorized. Approve USB debugging on the device.",
        )

    if session.connection_state != ConnectionState.CONNECTED:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Device '{device_id}' is not connected (state: {session.connection_state.value}). "
                "Capabilities can only be queried on actively connected devices."
            ),
        )

    if session.platform != Platform.ANDROID:
        raise HTTPException(
            status_code=501,
            detail=f"Capability discovery for {session.platform.value} device '{device_id}' is not yet implemented.",
        )

    # Return cached profile if available and refresh was not requested
    if session.capability_profile is not None and not refresh:
        return session.capability_profile

    # Refresh via session manager (ensures thread-safe state validation and prevents stale knowledge)
    bridge = _get_android_bridge()

    def fetcher(serial: str, dev_id: str) -> DeviceCapabilityProfile:
        return bridge.discover_capabilities(serial, device_id=dev_id)

    try:
        return await run_in_threadpool(
            device_session_manager.refresh_device_capabilities,
            device_id,
            fetcher,
        )
    except DeviceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.") from exc
    except DeviceUnauthorizedError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Device '{device_id}' is unauthorized. Approve USB debugging on the device.",
        ) from exc
    except DeviceNotConnectedError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Device '{device_id}' is not connected or disconnected during capability discovery.",
        ) from exc
    except TimeoutError as exc:
        logger.error("Capability discovery timed out for device %s", device_id)
        raise HTTPException(
            status_code=504,
            detail=f"Capability discovery timed out for device '{device_id}'.",
        ) from exc
    except Exception as exc:
        logger.error("Capability discovery failed for device %s: %s", device_id, type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to discover capabilities for device '{device_id}'.",
        ) from exc
