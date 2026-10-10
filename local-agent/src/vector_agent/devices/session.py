"""Device session management and abstraction."""

from __future__ import annotations

import hashlib
import threading
import time
import typing
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from vector_agent.core.logging import get_logger
from vector_agent.models.device import (
    ConnectedDevice,
    ConnectionState,
    DeviceAuthorizationState,
    DeviceCapabilityProfile,
    DeviceIdentity,
    Platform,
)
from vector_agent.security.validation import validate_ios_udid

logger = get_logger(__name__)


class DeviceSessionError(Exception):
    """Base error for device session operations."""


class DeviceNotFoundError(DeviceSessionError, KeyError, ValueError):
    """Device session does not exist."""


class DeviceUnauthorizedError(DeviceSessionError, PermissionError, ValueError):
    """Device session is not authorized for operations."""


class DeviceNotConnectedError(DeviceSessionError, ConnectionError, ValueError):
    """Device session is not connected or disconnected during an operation."""


class DeviceSession(BaseModel):
    """VECTOR's current knowledge about one discovered device."""

    device_id: str
    platform: Platform
    connection_state: ConnectionState
    authorization_state: DeviceAuthorizationState = DeviceAuthorizationState.UNKNOWN
    last_seen: datetime
    identity: DeviceIdentity | None = None
    capability_profile: DeviceCapabilityProfile | None = None
    raw_serial: str | None = Field(default=None, exclude=True, repr=False)
    last_capability_attempt_mono: float | None = Field(default=None, exclude=True, repr=False)
    session_epoch: int = Field(default=0, exclude=True, repr=False)
    last_identity_epoch: int | None = Field(default=None, exclude=True, repr=False)

    def to_connected_device(self) -> ConnectedDevice:
        """Convert to the API-facing model, masking raw_serial.

        An offline or unauthorized device must not masquerade as having
        active connected capability knowledge.
        """
        active_capability_profile = (
            self.capability_profile if self.connection_state == ConnectionState.CONNECTED else None
        )
        return ConnectedDevice(
            device_id=self.device_id,
            platform=self.platform,
            connection_state=self.connection_state,
            authorization_state=self.authorization_state,
            identity=self.identity,
            capability_profile=active_capability_profile,
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
        self,
        adb_devices: list[typing.Any],
        adb_identity_fetcher: typing.Any = None,
        adb_capability_fetcher: typing.Any = None,
        capability_retry_interval_seconds: float = 30.0,
    ) -> None:
        """Update sessions from an Android ADB discovery run.

        Safe concurrency design:
        1. Under lock: update states, clear stale profiles on reconnect, snapshot devices needing fetch
        2. Release lock
        3. Perform slow ADB identity and capability discovery calls outside lock
        4. Re-acquire lock: apply results only if session still exists, is CONNECTED, and has matching serial

        Args:
            adb_devices: List of AdbDeviceEntry objects.
            adb_identity_fetcher: Function that takes a serial and returns AndroidIdentity.
            adb_capability_fetcher: Function that takes (serial, device_id) and returns DeviceCapabilityProfile.
            capability_retry_interval_seconds: Minimum interval in seconds between discovery attempts for incomplete/failed profiles.
        """
        now = datetime.now(UTC)
        now_mono = time.monotonic()
        discovered_ids: set[str] = set()
        needs_identity: list[
            tuple[str, DeviceSession, str, int]
        ] = []  # (device_id, session, serial, epoch)
        needs_capabilities: list[
            tuple[str, DeviceSession, str, int]
        ] = []  # (device_id, session, serial, epoch)

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
                auth_state = (
                    DeviceAuthorizationState.AUTHORIZED
                    if conn_state == ConnectionState.CONNECTED
                    else DeviceAuthorizationState.AUTHORIZATION_REQUIRED
                    if conn_state == ConnectionState.UNAUTHORIZED
                    else DeviceAuthorizationState.UNKNOWN
                )

                if device_id in self._sessions:
                    session = self._sessions[device_id]
                    prev_state = session.connection_state
                    if prev_state != conn_state:
                        session.session_epoch += 1
                    session.connection_state = conn_state
                    session.authorization_state = auth_state
                    session.last_seen = now

                    # Clear capability profile and reset attempt tracker if reconnecting from non-CONNECTED state
                    if (
                        prev_state != ConnectionState.CONNECTED
                        and conn_state == ConnectionState.CONNECTED
                    ):
                        session.capability_profile = None
                        session.last_capability_attempt_mono = None

                    if conn_state == ConnectionState.CONNECTED:
                        if session.identity is None and adb_identity_fetcher:
                            needs_identity.append(
                                (device_id, session, entry.serial, session.session_epoch)
                            )
                        if adb_capability_fetcher:
                            is_incomplete = (
                                session.capability_profile is None
                                or not session.capability_profile.profile_complete
                            )
                            if is_incomplete:
                                can_attempt = (
                                    session.last_capability_attempt_mono is None
                                    or (now_mono - session.last_capability_attempt_mono)
                                    >= capability_retry_interval_seconds
                                )
                                if can_attempt:
                                    session.last_capability_attempt_mono = now_mono
                                    needs_capabilities.append(
                                        (device_id, session, entry.serial, session.session_epoch)
                                    )
                else:
                    new_session = DeviceSession(
                        device_id=device_id,
                        platform=Platform.ANDROID,
                        connection_state=conn_state,
                        authorization_state=auth_state,
                        last_seen=now,
                        identity=None,
                        capability_profile=None,
                        raw_serial=entry.serial,
                        last_capability_attempt_mono=now_mono
                        if (conn_state == ConnectionState.CONNECTED and adb_capability_fetcher)
                        else None,
                        session_epoch=0,
                    )
                    self._sessions[device_id] = new_session
                    if conn_state == ConnectionState.CONNECTED:
                        if adb_identity_fetcher:
                            needs_identity.append(
                                (device_id, new_session, entry.serial, new_session.session_epoch)
                            )
                        if adb_capability_fetcher:
                            needs_capabilities.append(
                                (device_id, new_session, entry.serial, new_session.session_epoch)
                            )

            # Mark devices not seen in this discovery cycle as OFFLINE
            for dev_id, session in self._sessions.items():
                if session.platform == Platform.ANDROID and dev_id not in discovered_ids:
                    if session.connection_state != ConnectionState.OFFLINE:
                        session.session_epoch += 1
                    session.connection_state = ConnectionState.OFFLINE
                    session.authorization_state = DeviceAuthorizationState.UNKNOWN
                    session.last_capability_attempt_mono = None

        # Step 2 & 3: Execute blocking discovery calls OUTSIDE global lock
        fetched_identities: list[tuple[str, DeviceSession, str, int, DeviceIdentity]] = []
        for dev_id, expected_session, serial, expected_epoch in needs_identity:
            try:
                ident = adb_identity_fetcher(serial)
                if ident:
                    fetched_identities.append(
                        (
                            dev_id,
                            expected_session,
                            serial,
                            expected_epoch,
                            DeviceIdentity(
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
                            ),
                        )
                    )
            except (RuntimeError, ValueError, TimeoutError, OSError) as exc:
                logger.warning(
                    "Identity fetch failed for device %s (%s)",
                    dev_id,
                    type(exc).__name__,
                )

        fetched_capabilities: list[
            tuple[str, DeviceSession, str, int, DeviceCapabilityProfile]
        ] = []
        for dev_id, expected_session, serial, expected_epoch in needs_capabilities:
            try:
                cap = adb_capability_fetcher(serial, dev_id)
                if cap:
                    fetched_capabilities.append(
                        (
                            dev_id,
                            expected_session,
                            serial,
                            expected_epoch,
                            cap,
                        )
                    )
            except (RuntimeError, ValueError, TimeoutError, OSError) as exc:
                logger.warning(
                    "Capability discovery failed for device %s (%s)",
                    dev_id,
                    type(exc).__name__,
                )

        # Step 4 & 5: Re-acquire lock and apply results safely (guard against stale/concurrent transitions)
        with self._lock:
            for (
                dev_id,
                expected_session,
                expected_serial,
                expected_epoch,
                ident_dto,
            ) in fetched_identities:
                current_session = self._sessions.get(dev_id)
                if (
                    current_session is expected_session
                    and current_session.session_epoch == expected_epoch
                    and current_session.connection_state == ConnectionState.CONNECTED
                    and current_session.get_serial_for_diagnostic() == expected_serial
                ):
                    current_session.identity = ident_dto

            for (
                dev_id,
                expected_session,
                expected_serial,
                expected_epoch,
                cap_prof,
            ) in fetched_capabilities:
                current_session = self._sessions.get(dev_id)
                if (
                    current_session is expected_session
                    and current_session.session_epoch == expected_epoch
                    and current_session.connection_state == ConnectionState.CONNECTED
                    and current_session.get_serial_for_diagnostic() == expected_serial
                ):
                    current_session.capability_profile = cap_prof

    def refresh_device_capabilities(
        self,
        device_id: str,
        fetcher: typing.Callable[[str, str], DeviceCapabilityProfile],
    ) -> DeviceCapabilityProfile:
        """Refresh capability knowledge for an active, connected session.

        Does NOT hold global session lock during the blocking discovery call.

        Args:
            device_id: Opaque device ID.
            fetcher: Callable taking (raw_serial, device_id) and returning DeviceCapabilityProfile.

        Returns:
            Updated DeviceCapabilityProfile.

        Raises:
            DeviceNotFoundError: If device is not found.
            DeviceUnauthorizedError: If device is unauthorized.
            DeviceNotConnectedError: If device is not connected or disconnected.
        """
        # Step 1: Under lock: validate session and snapshot state
        with self._lock:
            session = self._sessions.get(device_id)
            if not session:
                raise DeviceNotFoundError(f"Device '{device_id}' not found.")
            if session.connection_state == ConnectionState.UNAUTHORIZED:
                raise DeviceUnauthorizedError(f"Device '{device_id}' is unauthorized.")
            if session.connection_state != ConnectionState.CONNECTED:
                raise DeviceNotConnectedError(
                    f"Device '{device_id}' is not connected (state: {session.connection_state.value})."
                )
            serial = session.get_serial_for_diagnostic()
            if not serial:
                raise DeviceNotConnectedError(
                    f"Device '{device_id}' has no active serial for diagnostics."
                )

            # Clear capability profile while refreshing so stale data is not visible
            session.capability_profile = None
            session.last_capability_attempt_mono = time.monotonic()
            expected_session = session
            expected_serial = serial
            expected_epoch = session.session_epoch

        # Step 2 & 3: Perform blocking capability discovery outside lock
        # Any exception here propagates to caller, leaving profile as None (unavailable)
        profile = fetcher(expected_serial, device_id)

        # Step 4 & 5: Re-acquire lock and apply result only if session identity and state are unchanged
        with self._lock:
            current_session = self._sessions.get(device_id)
            if (
                current_session is expected_session
                and current_session.session_epoch == expected_epoch
                and current_session.connection_state == ConnectionState.CONNECTED
                and current_session.get_serial_for_diagnostic() == expected_serial
            ):
                current_session.capability_profile = profile
                current_session.last_seen = datetime.now(UTC)
                return profile
            else:
                raise DeviceNotConnectedError(
                    f"Device '{device_id}' disconnected or changed state during capability discovery."
                )

    def reconcile_ios_discovery(
        self,
        discovered_udids: list[str],
        pair_state_fetcher: typing.Callable[
            [str], tuple[ConnectionState, DeviceAuthorizationState, str]
        ],
        identity_fetcher: typing.Callable[[str], DeviceIdentity | None] | None = None,
    ) -> None:
        """Update sessions from an iOS USB discovery run.

        Safe concurrency design:
        1. Under lock: update last_seen, snapshot devices needing pairing/identity checks.
        2. Release lock.
        3. Perform idevicepair validate and allowlisted ideviceinfo calls outside lock.
        4. Re-acquire lock: apply results safely (guarding against stale epochs / disconnects).
        """
        now = datetime.now(UTC)
        discovered_ids: set[str] = set()
        needs_check: list[
            tuple[str, DeviceSession, str, int]
        ] = []  # (device_id, session, udid, epoch)

        # Defensively revalidate IDs (F6)
        valid_udids: list[str] = []
        for raw_u in discovered_udids:
            try:
                valid_udids.append(validate_ios_udid(raw_u))
            except Exception:
                continue

        with self._lock:
            for udid in valid_udids:
                device_id = self._make_device_id(Platform.IOS, udid)
                discovered_ids.add(device_id)

                if device_id in self._sessions:
                    session = self._sessions[device_id]
                    session.last_seen = now
                    needs_check.append((device_id, session, udid, session.session_epoch))
                else:
                    new_session = DeviceSession(
                        device_id=device_id,
                        platform=Platform.IOS,
                        connection_state=ConnectionState.UNAUTHORIZED,
                        authorization_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                        last_seen=now,
                        identity=None,
                        capability_profile=None,
                        raw_serial=udid,
                        session_epoch=0,
                    )
                    self._sessions[device_id] = new_session
                    needs_check.append((device_id, new_session, udid, new_session.session_epoch))

            # Mark iOS devices not seen in this discovery cycle as OFFLINE
            for dev_id, session in self._sessions.items():
                if session.platform == Platform.IOS and dev_id not in discovered_ids:
                    if session.connection_state != ConnectionState.OFFLINE:
                        session.session_epoch += 1
                    session.connection_state = ConnectionState.OFFLINE
                    session.authorization_state = DeviceAuthorizationState.UNKNOWN
                    session.last_capability_attempt_mono = None

        # Step 2 & 3: Execute slow pairing validation and identity queries OUTSIDE lock
        checked_pairs: list[
            tuple[str, DeviceSession, str, int, ConnectionState, DeviceAuthorizationState]
        ] = []
        for dev_id, expected_session, udid, expected_epoch in needs_check:
            try:
                conn_state, auth_state, _ = pair_state_fetcher(udid)
                checked_pairs.append(
                    (dev_id, expected_session, udid, expected_epoch, conn_state, auth_state)
                )
            except Exception as exc:
                logger.warning(
                    "iOS pairing validation failed for device %s (%s)",
                    dev_id,
                    type(exc).__name__,
                )

        needs_identity: list[tuple[str, DeviceSession, str, int]] = []
        for (
            dev_id,
            expected_session,
            udid,
            expected_epoch,
            conn_state,
            auth_state,
        ) in checked_pairs:
            needs_refresh = (
                expected_session.identity is None
                or expected_session.connection_state == ConnectionState.OFFLINE
                or expected_session.last_identity_epoch != expected_session.session_epoch
            )
            if (
                conn_state == ConnectionState.CONNECTED
                and auth_state == DeviceAuthorizationState.AUTHORIZED
                and identity_fetcher
                and needs_refresh
            ):
                needs_identity.append((dev_id, expected_session, udid, expected_epoch))

        fetched_identities: list[tuple[str, DeviceSession, str, int, DeviceIdentity]] = []
        if identity_fetcher is not None:
            for dev_id, expected_session, udid, expected_epoch in needs_identity:
                try:
                    ident = identity_fetcher(udid)
                    if ident:
                        fetched_identities.append(
                            (dev_id, expected_session, udid, expected_epoch, ident)
                        )
                except Exception as exc:
                    logger.warning(
                        "iOS identity fetch failed for device %s (%s)",
                        dev_id,
                        type(exc).__name__,
                    )

        # Step 4: Re-acquire lock and apply results safely
        with self._lock:
            ident_by_dev_id = {
                dev_id: ident_dto for dev_id, _, _, _, ident_dto in fetched_identities
            }

            for (
                dev_id,
                expected_session,
                expected_udid,
                expected_epoch,
                conn_state,
                auth_state,
            ) in checked_pairs:
                current_session = self._sessions.get(dev_id)
                if (
                    current_session is expected_session
                    and current_session.session_epoch == expected_epoch
                    and current_session.raw_serial == expected_udid
                ):
                    prev_state = current_session.connection_state
                    if prev_state != conn_state:
                        current_session.session_epoch += 1
                    current_session.connection_state = conn_state
                    current_session.authorization_state = auth_state
                    if auth_state == DeviceAuthorizationState.AUTHORIZED:
                        if dev_id in ident_by_dev_id:
                            current_session.identity = ident_by_dev_id[dev_id]
                            current_session.last_identity_epoch = current_session.session_epoch
                        elif any(item[0] == dev_id for item in needs_identity):
                            # Identity refresh was attempted on reconnect/epoch advance but failed:
                            # Do not present stale identity
                            current_session.identity = None
                            current_session.last_identity_epoch = None
                    else:
                        current_session.identity = None
                        current_session.last_identity_epoch = None

    def apply_device_pair_success(
        self,
        device_id: str,
        expected_epoch: int,
        expected_serial: str | None = None,
        identity: DeviceIdentity | None = None,
    ) -> bool:
        """Apply successful pairing to a session under lock.

        Validates that session still matches expected device_id, epoch, and serial.
        Increments session_epoch to invalidate any pre-pairing scan plans.
        Returns True if applied, False if session epoch/state changed (stale).
        """
        with self._lock:
            session = self._sessions.get(device_id)
            if (
                session is not None
                and session.session_epoch == expected_epoch
                and (expected_serial is None or session.raw_serial == expected_serial)
            ):
                session.connection_state = ConnectionState.CONNECTED
                session.authorization_state = DeviceAuthorizationState.AUTHORIZED
                session.session_epoch += 1
                session.identity = identity
                session.last_identity_epoch = session.session_epoch if identity else None
                session.last_seen = datetime.now(UTC)
                return True
            return False

    def bound_device_target(
        self, device_id: str, *, expected_session: DeviceSession, expected_epoch: int
    ) -> tuple[Platform, str | None] | None:
        """Atomic snapshot for a presence probe of the device a scan is bound to.

        Returns (platform, internal serial) only while ``expected_session`` is still the very
        same object, at ``expected_epoch`` and CONNECTED; otherwise None (the manager already
        knows the device went away or changed). The serial is for the platform tool only.
        """
        with self._lock:
            current = self._sessions.get(device_id)
            if (
                current is not expected_session
                or current.session_epoch != expected_epoch
                or current.connection_state != ConnectionState.CONNECTED
            ):
                return None
            return current.platform, current.get_serial_for_diagnostic()

    def mark_device_lost(
        self,
        device_id: str,
        *,
        expected_session: DeviceSession,
        expected_epoch: int,
        expected_serial: str,
        new_state: ConnectionState,
    ) -> bool:
        """Record a CONFIRMED loss of one specific device (never a whole platform).

        Applied only if the session is still the very same object, still at the epoch and
        serial the caller observed, and still CONNECTED. Mirrors discovery reconciliation
        (new state + epoch advance) so a later reconnect starts a fresh epoch. Returns False
        if anything changed in the meantime: the caller must then re-read the session.
        """
        if new_state not in (ConnectionState.OFFLINE, ConnectionState.UNAUTHORIZED):
            raise ValueError("A lost device can only become OFFLINE or UNAUTHORIZED.")
        with self._lock:
            current = self._sessions.get(device_id)
            if (
                current is not expected_session
                or current.session_epoch != expected_epoch
                or current.raw_serial != expected_serial
                or current.connection_state != ConnectionState.CONNECTED
            ):
                return False
            current.session_epoch += 1
            current.connection_state = new_state
            current.authorization_state = (
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED
                if new_state == ConnectionState.UNAUTHORIZED
                else DeviceAuthorizationState.UNKNOWN
            )
            current.last_capability_attempt_mono = None
            return True

    def mark_platform_offline(self, platform: Platform) -> None:
        """Mark all active sessions for a platform as OFFLINE when discovery fails."""
        with self._lock:
            for session in self._sessions.values():
                if (
                    session.platform == platform
                    and session.connection_state == ConnectionState.CONNECTED
                ):
                    session.session_epoch += 1
                    session.connection_state = ConnectionState.OFFLINE
                    session.authorization_state = DeviceAuthorizationState.UNKNOWN
                    session.last_capability_attempt_mono = None

    def get_session(self, device_id: str) -> DeviceSession | None:
        """Retrieve a session by its opaque device_id."""
        with self._lock:
            return self._sessions.get(device_id)

    def probe_owner_epoch(self, owner: DeviceSession) -> int:
        """Atomic live ownership check, including replacement after clear/restart."""
        with self._lock:
            current = self._sessions.get(owner.device_id)
            if (
                current is not owner
                or current.platform != Platform.ANDROID
                or current.connection_state != ConnectionState.CONNECTED
                or current.authorization_state != DeviceAuthorizationState.AUTHORIZED
            ):
                return -1
            return current.session_epoch

    def list_sessions(self) -> list[DeviceSession]:
        """List all current device sessions."""
        with self._lock:
            return list(self._sessions.values())


# Global singleton for the app lifecycle
device_session_manager = DeviceSessionManager()
