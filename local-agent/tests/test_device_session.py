"""Tests for DeviceSession and DeviceSessionManager."""

from datetime import UTC, datetime

import pytest

from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState, AndroidIdentity
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.models.device import ConnectedDevice, ConnectionState, Platform


@pytest.fixture
def session_manager() -> DeviceSessionManager:
    return DeviceSessionManager()


def test_device_id_privacy(session_manager: DeviceSessionManager) -> None:
    """Ensure opaque device IDs do not leak raw serials."""
    raw_serial = "12345ABC"
    device_id = session_manager._make_device_id(Platform.ANDROID, raw_serial)

    assert "android-" in device_id
    assert raw_serial not in device_id
    assert raw_serial.lower() not in device_id.lower()

    # Should be deterministic
    assert device_id == session_manager._make_device_id(Platform.ANDROID, raw_serial)


def test_stale_device_id_never_retargets(session_manager: DeviceSessionManager) -> None:
    """Ensure distinct serials produce distinct IDs and never retarget another device."""
    id_1 = session_manager._make_device_id(Platform.ANDROID, "SERIAL_A")
    id_2 = session_manager._make_device_id(Platform.ANDROID, "SERIAL_B")
    assert id_1 != id_2

    # Reconnecting with same serial yields identical ID
    assert id_1 == session_manager._make_device_id(Platform.ANDROID, "SERIAL_A")


def test_reconcile_android_discovery_new_device(session_manager: DeviceSessionManager) -> None:
    """Test reconciling a newly discovered device."""
    entries = [AdbDeviceEntry(serial="SERIAL1", state=AdbDeviceState.DEVICE, qualifiers={})]

    def mock_fetcher(serial: str) -> AndroidIdentity:
        return AndroidIdentity(
            serial=serial,
            manufacturer="Google",
            model="Pixel 6",
            device_codename="oriole",
            android_version="13",
            sdk_level=33,
            brand="google",
            retrieved_at=datetime.now(UTC),
        )

    session_manager.reconcile_android_discovery(entries, mock_fetcher)

    sessions = session_manager.list_sessions()
    assert len(sessions) == 1
    session = sessions[0]

    assert session.platform == Platform.ANDROID
    assert session.connection_state == ConnectionState.CONNECTED
    assert session.raw_serial == "SERIAL1"
    assert session.identity is not None
    assert session.identity.model == "Pixel 6"
    assert session.identity.device_codename == "oriole"
    assert session.identity.brand == "google"


def test_reconcile_android_discovery_update_offline(session_manager: DeviceSessionManager) -> None:
    """Test devices going offline when no longer discovered."""
    entries = [AdbDeviceEntry(serial="SERIAL1", state=AdbDeviceState.DEVICE, qualifiers={})]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    # Re-discover with empty list
    session_manager.reconcile_android_discovery([], lambda s: None)

    sessions = session_manager.list_sessions()
    assert len(sessions) == 1
    session = sessions[0]

    assert session.connection_state == ConnectionState.OFFLINE
    assert session.raw_serial == "SERIAL1"


def test_api_conversion(session_manager: DeviceSessionManager) -> None:
    """Test converting DeviceSession to ConnectedDevice hides raw serial and preserves platform."""
    entries = [AdbDeviceEntry(serial="SECRET_SERIAL", state=AdbDeviceState.DEVICE, qualifiers={})]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    session = session_manager.list_sessions()[0]
    connected = session.to_connected_device()

    # Explicit platform must be preserved
    assert connected.platform == Platform.ANDROID
    assert connected.device_id == session.device_id
    assert connected.connection_state == ConnectionState.CONNECTED

    # ConnectedDevice does NOT have raw_serial as a model field
    assert "raw_serial" not in ConnectedDevice.model_fields
    assert not hasattr(connected, "raw_serial")
    dump = connected.model_dump()
    assert "raw_serial" not in dump
    assert "SECRET_SERIAL" not in connected.model_dump_json()
    assert "SECRET_SERIAL" not in repr(connected)


def test_raw_serial_boundary(session_manager: DeviceSessionManager) -> None:
    """Test that DeviceSession itself protects raw_serial from serialization and repr logging."""
    entries = [
        AdbDeviceEntry(serial="CONFIDENTIAL_SERIAL_99", state=AdbDeviceState.DEVICE, qualifiers={})
    ]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    session = session_manager.list_sessions()[0]
    assert session.raw_serial == "CONFIDENTIAL_SERIAL_99"

    # raw_serial must be excluded from model_dump and model_dump_json
    dump = session.model_dump()
    assert "raw_serial" not in dump
    assert "CONFIDENTIAL_SERIAL_99" not in session.model_dump_json()

    # repr must not leak serial into logs
    assert "CONFIDENTIAL_SERIAL_99" not in repr(session)


def test_get_serial_for_diagnostic_safety(session_manager: DeviceSessionManager) -> None:
    """Privileged diagnostic serial access must only succeed when actively CONNECTED."""
    entries = [AdbDeviceEntry(serial="SERIAL1", state=AdbDeviceState.DEVICE, qualifiers={})]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    session = session_manager.list_sessions()[0]
    assert session.connection_state == ConnectionState.CONNECTED
    assert session.get_serial_for_diagnostic() == "SERIAL1"

    # Disappear -> OFFLINE
    session_manager.reconcile_android_discovery([], lambda s: None)
    assert session.connection_state == ConnectionState.OFFLINE
    assert session.get_serial_for_diagnostic() is None


def test_unauthorized_session_cannot_expose_serial(session_manager: DeviceSessionManager) -> None:
    """Unauthorized devices must not expose serial for diagnostics."""
    entries = [
        AdbDeviceEntry(serial="UNAUTH_SERIAL", state=AdbDeviceState.UNAUTHORIZED, qualifiers={})
    ]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    session = session_manager.list_sessions()[0]
    assert session.connection_state == ConnectionState.UNAUTHORIZED
    assert session.identity is None
    assert session.get_serial_for_diagnostic() is None


def test_mark_platform_offline(session_manager: DeviceSessionManager) -> None:
    """When discovery fails, mark_platform_offline sets active sessions to OFFLINE."""
    entries = [AdbDeviceEntry(serial="SERIAL1", state=AdbDeviceState.DEVICE, qualifiers={})]
    session_manager.reconcile_android_discovery(entries, lambda s: None)

    session = session_manager.list_sessions()[0]
    assert session.connection_state == ConnectionState.CONNECTED

    session_manager.mark_platform_offline(Platform.ANDROID)
    assert session.connection_state == ConnectionState.OFFLINE
