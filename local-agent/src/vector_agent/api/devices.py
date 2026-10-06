"""Platform-neutral device discovery, listing, and explicit pairing API endpoints.

GET /api/v1/devices                      - list currently visible devices across platforms
GET /api/v1/devices/{device_id}          - get specific device by opaque device_id
POST /api/v1/devices/{device_id}/pair    - explicit user-initiated pairing for an iOS device
GET /api/v1/devices/{device_id}/capabilities - get capability profile (Android runtime discovery)
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from vector_agent.core.config import get_settings
from vector_agent.core.logging import get_logger
from vector_agent.devices.android.bridge import AdbDeviceState, AndroidDeviceBridge
from vector_agent.devices.ios.bridge import IOSCommandStatus, IOSDeviceBridge, IOSToolchainStatus
from vector_agent.devices.session import (
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceUnauthorizedError,
    device_session_manager,
)
from vector_agent.models.device import (
    ConnectedDevice,
    ConnectionState,
    DeviceAuthorizationState,
    DeviceCapabilityProfile,
    DevicePairResponse,
    PairingState,
    Platform,
)
from vector_agent.scan.service import scan_service
from vector_agent.security.validation import validate_ios_udid

logger = get_logger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])

# Per-device pairing locks to prevent concurrent pairing races
_pairing_meta_lock = threading.Lock()
_pairing_device_locks: dict[str, threading.Lock] = {}


def _get_device_pairing_lock(device_id: str) -> threading.Lock:
    with _pairing_meta_lock:
        if device_id not in _pairing_device_locks:
            _pairing_device_locks[device_id] = threading.Lock()
        return _pairing_device_locks[device_id]


class DeviceListResponse(BaseModel):
    devices: list[ConnectedDevice]
    count: int
    provider_statuses: dict[str, str] | None = None


def _get_android_bridge() -> AndroidDeviceBridge:
    settings = get_settings()
    return AndroidDeviceBridge(adb_path=settings.adb_path)


def _get_ios_bridge() -> IOSDeviceBridge:
    settings = get_settings()
    return IOSDeviceBridge(settings=settings)


def _trigger_discovery() -> dict[str, str]:
    """Triggers discovery on all available bridges and reconciles sessions."""
    provider_statuses: dict[str, str] = {}
    android_error = False
    ios_error = False

    # 1. Android discovery
    try:
        bridge = _get_android_bridge()
        discovery = bridge.discover_devices()

        if not discovery.adb_available:
            logger.info("Android toolchain (adb) unavailable on host.")
            device_session_manager.mark_platform_offline(Platform.ANDROID)
            provider_statuses["android"] = "UNAVAILABLE"
        elif discovery.state == AdbDeviceState.ERROR:
            logger.warning("Android discovery returned error: %s", discovery.message)
            device_session_manager.mark_platform_offline(Platform.ANDROID)
            provider_statuses["android"] = "ERROR"
            android_error = True
        else:
            from vector_agent.devices.android.bridge import AndroidIdentity

            def fetch_identity(serial: str) -> AndroidIdentity:
                return bridge.get_identity(serial)

            def fetch_capabilities(serial: str, device_id: str) -> DeviceCapabilityProfile:
                return bridge.discover_capabilities(serial, device_id=device_id)

            device_session_manager.reconcile_android_discovery(
                discovery.devices,
                adb_identity_fetcher=fetch_identity,
                adb_capability_fetcher=fetch_capabilities,
            )
            provider_statuses["android"] = "AVAILABLE"
    except (FileNotFoundError, OSError):
        logger.info("Android toolchain (adb) unavailable on host.")
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        provider_statuses["android"] = "UNAVAILABLE"
    except Exception as exc:
        logger.warning("Android discovery failed (%s)", type(exc).__name__)
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        provider_statuses["android"] = "ERROR"
        android_error = True

    # 2. iOS discovery
    try:
        ios_bridge = _get_ios_bridge()
        if not ios_bridge.is_available():
            device_session_manager.mark_platform_offline(Platform.IOS)
            provider_statuses["ios"] = "UNAVAILABLE"
        else:
            disc_res = ios_bridge.discover_devices_result()
            if disc_res.status == IOSToolchainStatus.AVAILABLE:
                device_session_manager.reconcile_ios_discovery(
                    disc_res.udids,
                    pair_state_fetcher=ios_bridge.validate_pairing,
                    identity_fetcher=ios_bridge.get_identity,
                )
                provider_statuses["ios"] = "AVAILABLE"
            elif disc_res.status == IOSToolchainStatus.UNAVAILABLE:
                device_session_manager.mark_platform_offline(Platform.IOS)
                provider_statuses["ios"] = "UNAVAILABLE"
            else:
                logger.warning("iOS discovery returned error: %s", disc_res.status.value)
                device_session_manager.mark_platform_offline(Platform.IOS)
                provider_statuses["ios"] = "ERROR"
                ios_error = True
    except (FileNotFoundError, OSError):
        logger.info("iOS toolchain unavailable on host.")
        device_session_manager.mark_platform_offline(Platform.IOS)
        provider_statuses["ios"] = "UNAVAILABLE"
    except Exception as exc:
        logger.warning("iOS discovery failed (%s)", type(exc).__name__)
        device_session_manager.mark_platform_offline(Platform.IOS)
        provider_statuses["ios"] = "ERROR"
        ios_error = True

    if android_error and ios_error:
        raise RuntimeError("Device discovery failed on all active providers.")

    return provider_statuses


@router.get("", response_model=DeviceListResponse)
async def list_devices() -> DeviceListResponse:
    """Discover and return currently connected devices across platforms."""
    # Trigger discovery first to ensure fresh state (offloaded from event loop)
    provider_statuses: dict[str, str] = {}
    try:
        provider_statuses = await run_in_threadpool(_trigger_discovery)
    except Exception as exc:
        logger.error("Discovery trigger failed (%s)", type(exc).__name__)
        device_session_manager.mark_platform_offline(Platform.ANDROID)
        device_session_manager.mark_platform_offline(Platform.IOS)
        raise HTTPException(
            status_code=503,
            detail="Device discovery failed.",
        ) from None

    sessions = device_session_manager.list_sessions()
    devices = [session.to_connected_device() for session in sessions]
    return DeviceListResponse(
        devices=devices,
        count=len(devices),
        provider_statuses=provider_statuses if isinstance(provider_statuses, dict) else None,
    )


@router.get("/{device_id}", response_model=ConnectedDevice)
async def get_device(device_id: str) -> ConnectedDevice:
    """Return details for a specific connected device by its opaque device_id."""
    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    return session.to_connected_device()


@router.post("/{device_id}/pair", response_model=DevicePairResponse)
async def pair_device(device_id: str) -> DevicePairResponse:
    """Explicit user-initiated pairing for an iOS device.

    Security & Privacy Invariants:
    - Opaque device_id only; never accepts raw UDID.
    - Explicit user action only; never triggered automatically on discovery or scans.
    - Prohibits pairing during an active scan (409 Conflict).
    - Prevents simultaneous pairing attempts on the same device (409 Conflict).
    - Non-mutating validation-before-pair prevents touching existing pair records.
    - Stale session epoch safety: results from disconnected/reconnected devices are discarded.
    - Never exposes raw UDID, passcodes, or pairing secrets.
    """
    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    if session.platform != Platform.IOS:
        raise HTTPException(
            status_code=400,
            detail=f"Pairing is not supported for {session.platform.value} devices. Use USB debugging authorization on the device.",
        )

    if session.connection_state == ConnectionState.OFFLINE:
        raise HTTPException(
            status_code=400,
            detail=f"Device '{device_id}' is offline and cannot be paired.",
        )

    # Fast-path idempotency check on session state
    if (
        session.connection_state == ConnectionState.CONNECTED
        and session.authorization_state == DeviceAuthorizationState.AUTHORIZED
    ):
        return DevicePairResponse(
            device_id=device_id,
            status=PairingState.ALREADY_PAIRED,
            message="Device is already paired and trusted.",
        )

    # Check if a scan is active on the device
    if scan_service.has_active_scan(device_id):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pair device '{device_id}' while a scan is active.",
        )

    raw_udid = session.raw_serial
    if not raw_udid:
        raise HTTPException(
            status_code=400,
            detail=f"Device '{device_id}' has no active identifier for pairing.",
        )

    # Defensively validate identifier to guarantee valid syntax and avoid 500
    try:
        validate_ios_udid(raw_udid)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Device '{device_id}' has an invalid identifier for pairing.",
        ) from exc

    dev_lock = _get_device_pairing_lock(device_id)
    acquired = dev_lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail=f"A pairing operation is already in progress for device '{device_id}'.",
        )

    try:
        expected_epoch = session.session_epoch
        expected_serial = raw_udid
        ios_bridge = _get_ios_bridge()

        # Step 1: Validate pairing first inside lock (M7)
        val_res = await run_in_threadpool(ios_bridge.validate_pairing, expected_serial)
        if hasattr(val_res, "status"):
            val_status = val_res.status
            conn_state = val_res.connection_state
            auth_state = val_res.authorization_state
            val_msg = val_res.message
        else:
            val_status = None
            conn_state, auth_state, val_msg = val_res

        # Explicit timeout handling: typed status ONLY (F7)
        if val_status == IOSCommandStatus.TIMEOUT:
            return DevicePairResponse(
                device_id=device_id,
                status=PairingState.ERROR,
                message=val_msg or "Pairing validation timed out.",
            )

        if conn_state == ConnectionState.OFFLINE:
            return DevicePairResponse(
                device_id=device_id,
                status=PairingState.DEVICE_DISCONNECTED,
                message=val_msg or "Device is disconnected or offline.",
            )

        if auth_state == DeviceAuthorizationState.AUTHORIZED:
            try:
                identity = await run_in_threadpool(ios_bridge.get_identity, expected_serial)
            except Exception:
                identity = None
            device_session_manager.apply_device_pair_success(
                device_id,
                expected_epoch=expected_epoch,
                expected_serial=expected_serial,
                identity=identity,
            )
            return DevicePairResponse(
                device_id=device_id,
                status=PairingState.ALREADY_PAIRED,
                message="Device is already paired and trusted.",
            )

        if auth_state != DeviceAuthorizationState.AUTHORIZATION_REQUIRED:
            # UNKNOWN, RESTRICTED, or any other non-AUTHORIZATION_REQUIRED state:
            # NEVER execute pair_device!
            if auth_state == DeviceAuthorizationState.RESTRICTED:
                pair_status = PairingState.RESTRICTED
            elif val_status == IOSCommandStatus.ERROR:
                pair_status = PairingState.ERROR
            else:
                pair_status = PairingState.INCONCLUSIVE

            return DevicePairResponse(
                device_id=device_id,
                status=pair_status,
                message=val_msg
                or f"Pairing validation returned state {auth_state.value}; pairing command aborted.",
            )

        # Step 2: Only call pair_device when validation explicitly indicates pairing is required
        status, msg = await run_in_threadpool(ios_bridge.pair_device, expected_serial)

        if status in (PairingState.PAIRED, PairingState.ALREADY_PAIRED):
            # Fetch allowlisted identity outside global session lock
            try:
                identity = await run_in_threadpool(ios_bridge.get_identity, expected_serial)
            except Exception:
                identity = None

            applied = device_session_manager.apply_device_pair_success(
                device_id,
                expected_epoch=expected_epoch,
                expected_serial=expected_serial,
                identity=identity,
            )
            if not applied:
                # L7: Check if concurrent discovery advanced session and it is already authorized
                curr_sess = device_session_manager.get_session(device_id)
                if (
                    curr_sess
                    and curr_sess.raw_serial == expected_serial
                    and curr_sess.authorization_state == DeviceAuthorizationState.AUTHORIZED
                ):
                    return DevicePairResponse(
                        device_id=device_id,
                        status=PairingState.ALREADY_PAIRED,
                        message="Device is already paired and trusted.",
                    )
                return DevicePairResponse(
                    device_id=device_id,
                    status=PairingState.DEVICE_DISCONNECTED,
                    message="Device disconnected or session changed during pairing.",
                )

        return DevicePairResponse(
            device_id=device_id,
            status=status,
            message=msg,
        )
    finally:
        dev_lock.release()


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
        device_session_manager.mark_platform_offline(Platform.IOS)
        raise HTTPException(
            status_code=503,
            detail="Device discovery failed.",
        ) from None

    session = device_session_manager.get_session(device_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    if session.platform != Platform.ANDROID:
        raise HTTPException(
            status_code=501,
            detail=f"Capability discovery for {session.platform.value} device '{device_id}' is not yet implemented.",
        )

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
