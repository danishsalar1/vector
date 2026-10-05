"""Device session management and abstraction."""

from __future__ import annotations

import hashlib
import threading
import typing
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from vector_agent.models.device import (
    ConnectedDevice,
    ConnectionState,
    DeviceIdentity,
    Platform,
)


class DeviceSession(BaseModel):
    """VECTOR's current knowledge about one discovered device."""

    device_id: str
    platform: Platform
    connection_state: ConnectionState
    last_seen: datetime
    identity: DeviceIdentity | None = None
    raw_serial: str | None = Field(default=None, exclude=True, repr=False)

    def to_connected_device(self) -> ConnectedDevice:
        """Convert to the API-facing model, masking raw_serial."""
        return ConnectedDevice(
            device_id=self.device_id,
            platform=self.platform,
            connection_state=self.connection_state,
            identity=self.identity,
        )

    def get_serial_for_diagnostic(self) -> str | None:
        """Return raw serial only if session is actively connected and authorized."""
        if self.connection_state == ConnectionState.CONNECTED:
            return self.raw_serial
        return None


class DeviceSessionManager:
    """Manages active device sessions in a thread-safe manner."""

    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}
        self._lock = threading.RLock()

    def _make_device_id(self, platform: Platform, serial: str) -> str:
        """Produce a deterministic, stable opaque device_id from platform and serial."""
        hashed = hashlib.sha256(f"{platform.value}:{serial}".encode()).hexdigest()[:12]
        return f"{platform.value.lower()}-{hashed}"

    def clear(self) -> None:
        """Clear all active sessions (used primarily for testing)."""
        with self._lock:
            self._sessions.clear()

    def reconcile_android_discovery(
        self, adb_devices: list[typing.Any], adb_identity_fetcher: typing.Any = None
    ) -> None:
        """Update sessions from an Android ADB discovery run.

        Args:
            adb_devices: List of AdbDeviceEntry objects.
            adb_identity_fetcher: Function that takes a serial and returns AndroidIdentity.
        """
        now = datetime.now(UTC)
        discovered_ids = set()

        with self._lock:
            for entry in adb_devices:
                device_id = self._make_device_id(Platform.ANDROID, entry.serial)
                discovered_ids.add(device_id)

                # Map AdbDeviceState string to ConnectionState
                state_val = entry.state.value.upper()
                conn_state = (
                    ConnectionState.CONNECTED
                    if state_val == "DEVICE"
                    else ConnectionState(state_val)
                    if state_val in [e.value for e in ConnectionState]
                    else ConnectionState.UNKNOWN
                )

                if device_id in self._sessions:
                    session = self._sessions[device_id]
                    # Update state and last_seen
                    session.connection_state = conn_state
                    session.last_seen = now

                    # Fetch identity if we transitioned to CONNECTED and don't have it
                    if (
                        conn_state == ConnectionState.CONNECTED
                        and session.identity is None
                        and adb_identity_fetcher
                    ):
                        try:
                            identity = adb_identity_fetcher(entry.serial)
                            session.identity = DeviceIdentity(
                                platform=Platform.ANDROID,
                                manufacturer=identity.manufacturer,
                                model=identity.model,
                                marketing_name=None,
                                android_version=identity.android_version,
                                android_sdk_level=identity.sdk_level,
                                build_fingerprint=None,
                                brand=identity.brand,
                                device_codename=identity.device_codename,
                                ios_version=None,
                                product_type=None,
                                serial=None,  # Never raw serial here
                                udid=None,
                                discovered_at=identity.retrieved_at,
                            )
                        except Exception:
                            pass
                else:
                    # New session
                    identity = None
                    if conn_state == ConnectionState.CONNECTED and adb_identity_fetcher:
                        try:
                            ident = adb_identity_fetcher(entry.serial)
                            identity = DeviceIdentity(
                                platform=Platform.ANDROID,
                                manufacturer=ident.manufacturer,
                                model=ident.model,
                                marketing_name=None,
                                android_version=ident.android_version,
                                android_sdk_level=ident.sdk_level,
                                build_fingerprint=None,
                                brand=ident.brand,
                                device_codename=ident.device_codename,
                                ios_version=None,
                                product_type=None,
                                serial=None,
                                udid=None,
                                discovered_at=ident.retrieved_at,
                            )
                        except Exception:
                            pass

                    self._sessions[device_id] = DeviceSession(
                        device_id=device_id,
                        platform=Platform.ANDROID,
                        connection_state=conn_state,
                        last_seen=now,
                        identity=identity,
                        raw_serial=entry.serial,
                    )

            # Mark devices not seen in this discovery cycle as OFFLINE
            for device_id, session in self._sessions.items():
                if session.platform == Platform.ANDROID and device_id not in discovered_ids:
                    session.connection_state = ConnectionState.OFFLINE

    def mark_platform_offline(self, platform: Platform) -> None:
        """Mark all active sessions for a platform as OFFLINE when discovery fails."""
        with self._lock:
            for session in self._sessions.values():
                if (
                    session.platform == platform
                    and session.connection_state == ConnectionState.CONNECTED
                ):
                    session.connection_state = ConnectionState.OFFLINE

    def get_session(self, device_id: str) -> DeviceSession | None:
        """Retrieve a session by its opaque device_id."""
        with self._lock:
            return self._sessions.get(device_id)

    def list_sessions(self) -> list[DeviceSession]:
        """List all current device sessions."""
        with self._lock:
            return list(self._sessions.values())


# Global singleton for the app lifecycle
device_session_manager = DeviceSessionManager()
