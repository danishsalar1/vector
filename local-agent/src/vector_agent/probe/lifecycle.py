"""Session-owned Probe lifecycle, separate from scan/diagnostic/provenance policy."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from vector_agent.devices.android.probe_bridge import (
    AndroidProbeBridge,
    ProbeBootstrap,
    TrustedProbeArtifact,
)
from vector_agent.models.device import ConnectionState, Platform
from vector_agent.models.probe import ProbeCapabilityId, ProbeCommandStatus
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.models.probe_lifecycle import ProbeState
from vector_agent.probe.adb_transport import AdbProbeTransport
from vector_agent.probe.protocol import ProbeProtocolSession
from vector_agent.probe.transport import ProbeTransport
from vector_agent.probe.transport import ProbeTransportStatus as T

# ruff: noqa: TID252
from ..devices.session import DeviceSession, DeviceSessionManager

CONTROL_OPERATIONS = (O.HELLO, O.GET_CAPABILITIES, O.HEARTBEAT)


class ProbeConnection:
    """One DeviceSession object + epoch. No reopening or cross-owner cancellation.

    Public methods are serialized; stop interrupts I/O via a private cancellation
    event, then closes resources. A new connection requires fresh on-device consent.
    """

    def __init__(
        self,
        manager: DeviceSessionManager,
        owner: DeviceSession,
        bridge: AndroidProbeBridge,
        artifact: TrustedProbeArtifact | None,
        transport_factory: Callable[..., ProbeTransport] = AdbProbeTransport,
    ) -> None:
        self._manager, self._owner, self._epoch = manager, owner, owner.session_epoch
        self._bridge, self._artifact, self._factory = bridge, artifact, transport_factory
        self._operation = threading.Lock()
        self._cancel = threading.Event()
        self._transport: ProbeTransport | None = None
        self._session: ProbeProtocolSession | None = None
        self._state = ProbeState(availability=A.DISCONNECTED, reason=R.STOPPED)
        self._last_heartbeat = 0.0
        self._cleanup_failed = False

    def _current_epoch(self) -> int:
        return self._manager.probe_owner_epoch(self._owner)

    def _live(self) -> bool:
        return self._current_epoch() == self._epoch and not self._cancel.is_set()

    def _require_live(self) -> None:
        if not self._live():
            raise ConnectionError("Probe owner changed.")

    def _drop(self, state: A, reason: R) -> ProbeState:
        transport, self._transport = self._transport, None
        if self._session:
            self._session.close()
        if transport and (
            transport.close() == T.ERROR or getattr(transport, "cleanup_failed", False)
        ):
            self._cleanup_failed = True
        if self._cleanup_failed:
            self._cancel.set()
            state, reason = A.ERROR, R.TOOL_ERROR
        self._state = ProbeState(availability=state, reason=reason)
        return self._state

    def _guarded(self, action: Callable[[], ProbeState]) -> ProbeState:
        with self._operation:
            if not self._live():
                return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
            try:
                state = action()
                if not self._live():
                    return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                return state
            except ConnectionError:
                if not self._live():
                    return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                return self._drop(A.DISCONNECTED, R.DEVICE_UNAVAILABLE)
            except FileNotFoundError:
                if not self._live():
                    return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                return self._drop(A.RESTRICTED, R.TOOL_UNAVAILABLE)
            except TimeoutError:
                if not self._live():
                    return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                return self._drop(A.DISCONNECTED, R.TIMEOUT)
            except Exception:
                if not self._live():
                    return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                return self._drop(A.ERROR, R.INVALID_RESPONSE)

    def discover(self) -> ProbeState:
        def action() -> ProbeState:
            # Discovery explicitly closes any established control connection.
            self._drop(A.DISCONNECTED, R.STOPPED)
            self._state = self._bridge.discover(self._artifact)
            return self._state

        return self._guarded(action)

    def launch(self) -> ProbeState:
        def action() -> ProbeState:
            self._drop(A.DISCONNECTED, R.STOPPED)
            self._state = self._bridge.discover(self._artifact)
            if self._state.availability != A.INSTALLED_COMPATIBLE:
                return self._state
            self._require_live()
            if not self._bridge.launch():
                return self._drop(A.ERROR, R.TOOL_ERROR)
            self._state = self._state.model_copy(
                update={
                    "availability": A.CONSENT_REQUIRED,
                    "reason": R.APPROVE_ON_DEVICE,
                    "consent_required": True,
                }
            )
            return self._state

        return self._guarded(action)

    def connect(self) -> ProbeState:
        def action() -> ProbeState:
            if self._transport is not None:
                return self._state
            self._state = self._bridge.discover(self._artifact)
            if self._state.availability != A.INSTALLED_COMPATIBLE:
                return self._state
            self._require_live()
            bootstrap = self._bridge.bootstrap()
            if not isinstance(bootstrap, ProbeBootstrap):
                state, reason = {
                    "REQUIRED": (A.CONSENT_REQUIRED, R.APPROVE_ON_DEVICE),
                    "DENIED": (A.CONSENT_DENIED, R.USER_DECLINED),
                    "RESTRICTED": (A.RESTRICTED, R.DEVELOPMENT_ACCESS_REQUIRED),
                    "NOT_STARTED": (A.CONSENT_REQUIRED, R.PROBE_NOT_STARTED),
                    "EXPIRED": (A.DISCONNECTED, R.SESSION_EXPIRED),
                }[bootstrap]
                self._state = self._state.model_copy(
                    update={
                        "availability": state,
                        "reason": reason,
                        "consent_required": state == A.CONSENT_REQUIRED,
                    }
                )
                return self._state
            # Recheck after reading private bootstrap so a package update during
            # discovery cannot silently inherit the earlier identity decision.
            identity = self._bridge.discover(self._artifact)
            if identity.availability != A.INSTALLED_COMPATIBLE:
                self._state = identity
                return self._state
            self._require_live()
            self._session = ProbeProtocolSession(
                device_id=self._owner.device_id, device_epoch=self._epoch
            )
            self._transport = self._factory(
                session=self._session,
                current_device_epoch=self._current_epoch,
                bridge=self._bridge,
                bootstrap=bootstrap,
            )
            if not self._control(O.HELLO) or not self._control(O.GET_CAPABILITIES):
                return self._state
            self._state = self._state.model_copy(
                update={
                    "availability": A.CONNECTED,
                    "reason": R.NONE,
                    "transport_connected": True,
                    "consent_required": False,
                }
            )
            self._last_heartbeat = time.monotonic()
            return self._state

        return self._guarded(action)

    def _control(self, operation: O) -> bool:
        assert self._session is not None and self._transport is not None
        request = self._session.create_request(
            operation, current_device_epoch=self._current_epoch()
        )
        result = self._transport.request(request, timeout_seconds=3, cancellation=self._cancel)
        if result.status != T.RECEIVED or result.response is None:
            state, reason = {
                T.TIMEOUT: (A.DISCONNECTED, R.TIMEOUT),
                T.UNAVAILABLE: (A.DISCONNECTED, R.DEVICE_UNAVAILABLE),
                T.CLOSED: (A.DISCONNECTED, R.SESSION_EXPIRED),
                T.UNSUPPORTED_PROTOCOL: (A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED),
                T.AUTHENTICATION_FAILURE: (A.UNTRUSTED, R.AUTHENTICATION_FAILED),
                T.CANCELLED: (A.DISCONNECTED, R.CANCELLED),
            }.get(result.status, (A.ERROR, R.INVALID_RESPONSE))
            self._drop(state, reason)
            return False
        response = result.response
        if response.command_status != ProbeCommandStatus.OK:
            self._drop(
                A.RESTRICTED
                if response.command_status == ProbeCommandStatus.RESTRICTED
                else A.ERROR,
                R.DEVELOPMENT_ACCESS_REQUIRED
                if response.command_status == ProbeCommandStatus.RESTRICTED
                else R.INVALID_RESPONSE,
            )
            return False
        if operation == O.HELLO:
            hello = response.hello
            artifact = self._artifact
            if (
                hello is None
                or artifact is None
                or hello.application_version != artifact.application_version
                or hello.version_code != artifact.version_code
                or hello.protocol_versions != (1,)
                or set(hello.supported_operations) != set(CONTROL_OPERATIONS)
            ):
                self._drop(A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED)
                return False
        if operation == O.GET_CAPABILITIES:
            caps = response.capabilities
            if (
                len(caps) != 1
                or caps[0].capability_id != ProbeCapabilityId.CONTROL_CHANNEL
                or not caps[0].available
                or set(caps[0].operations) != set(CONTROL_OPERATIONS)
            ):
                self._drop(A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED)
                return False
            self._state = self._state.model_copy(update={"capabilities": caps})
        return True

    def heartbeat(self) -> ProbeState:
        def action() -> ProbeState:
            if self._transport is not None and self._control(O.HEARTBEAT):
                self._last_heartbeat = time.monotonic()
            return self._state

        return self._guarded(action)

    def state(self) -> ProbeState:
        return self._guarded(lambda: self._state)

    def tick(self) -> None:
        if not self._live():
            self.stop()
        elif self._transport is not None and time.monotonic() - self._last_heartbeat >= 5:
            self.heartbeat()

    def stop(self, *, stop_app: bool = False) -> ProbeState:
        self._cancel.set()
        # close() unblocks socket I/O without waiting for the operation lock.
        transport = self._transport
        if transport is not None and transport.close() == T.ERROR:
            self._cleanup_failed = True
        with self._operation:
            state = self._drop(A.DISCONNECTED, R.STOPPED)
            if stop_app and self._current_epoch() == self._epoch:
                try:
                    identity = self._bridge.discover(self._artifact)
                    if not identity.identity_trusted:
                        self._state = identity
                        return identity
                    if self._current_epoch() != self._epoch:
                        return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
                    if not self._bridge.stop():
                        state = self._drop(A.ERROR, R.TOOL_ERROR)
                except Exception:
                    state = self._drop(A.ERROR, R.TOOL_ERROR)
            return state


class ProbeService:
    """Bounded backend service; no transport is opened without explicit action."""

    def __init__(
        self,
        manager: DeviceSessionManager,
        *,
        adb_path: str = "adb",
        artifact: TrustedProbeArtifact | None = None,
        enabled: bool = True,
    ) -> None:
        self._manager, self._adb, self._artifact = manager, adb_path, artifact
        self._enabled = enabled
        self._connections: dict[str, ProbeConnection] = {}
        self._device_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._workers: dict[str, threading.Thread] = {}

    def _device_lock(self, device_id: str) -> threading.Lock:
        with self._lock:
            lock = self._device_locks.get(device_id)
            if lock is None:
                lock = threading.Lock()
                self._device_locks[device_id] = lock
            return lock

    def _prune_locked(self) -> None:
        """Evict dead connections and completed worker threads."""
        for did in list(self._connections.keys()):
            conn = self._connections[did]
            worker = self._workers.get(did)
            if not conn._live() and (worker is None or not worker.is_alive()):
                if worker is not None:
                    worker.join(timeout=0.01)
                    self._workers.pop(did, None)
                self._connections.pop(did, None)

    def get_state(self, device_id: str) -> ProbeState:
        """Return probe state without allocating connection or monitor thread."""
        for _ in range(2):
            with self._lock:
                if self._shutdown.is_set() or not self._enabled:
                    raise ValueError("Probe service closed.")
                self._prune_locked()
                owner = self._manager.get_session(device_id)
                if (
                    owner is None
                    or owner.platform != Platform.ANDROID
                    or owner.connection_state != ConnectionState.CONNECTED
                ):
                    raise ValueError("Android device unavailable.")
                conn = self._connections.get(device_id)
                if conn is None or not conn._live():
                    return ProbeState(availability=A.DISCONNECTED, reason=R.STOPPED)

            state = conn.state()
            with self._lock:
                current = self._connections.get(device_id)
                if current is conn or current is None or not current._live():
                    return state

        return state

    def connection(self, device_id: str) -> ProbeConnection:
        dev_lock = self._device_lock(device_id)
        with dev_lock:
            to_stop: ProbeConnection | None = None
            to_join: threading.Thread | None = None

            with self._lock:
                if self._shutdown.is_set() or not self._enabled:
                    raise ValueError("Probe service closed.")
                owner = self._manager.get_session(device_id)
                if (
                    owner is None
                    or owner.platform != Platform.ANDROID
                    or owner.connection_state != ConnectionState.CONNECTED
                ):
                    raise ValueError("Android device unavailable.")
                self._prune_locked()
                old = self._connections.get(device_id)
                if old is not None and old._live():
                    return old
                if old is not None:
                    to_stop = old
                    to_join = self._workers.pop(device_id, None)
                    self._connections.pop(device_id, None)

            if to_stop is not None:
                to_stop.stop()
                if to_join is not None:
                    to_join.join(timeout=5)
                    if to_join.is_alive():
                        raise ValueError("Previous Probe lifecycle is still closing.")

            with self._lock:
                if self._shutdown.is_set() or not self._enabled:
                    raise ValueError("Probe service closed.")
                owner = self._manager.get_session(device_id)
                if (
                    owner is None
                    or owner.platform != Platform.ANDROID
                    or owner.connection_state != ConnectionState.CONNECTED
                ):
                    raise ValueError("Android device unavailable.")
                self._prune_locked()
                existing = self._connections.get(device_id)
                if existing is not None and existing._live():
                    return existing

                active = [c for c in self._connections.values() if c._live()]
                if len(active) >= 16 and (
                    device_id not in self._connections or not self._connections[device_id]._live()
                ):
                    raise ValueError("Probe connection limit reached.")

                bridge = AndroidProbeBridge(serial=owner.raw_serial or "", adb_path=self._adb)
                connection = ProbeConnection(self._manager, owner, bridge, self._artifact)
                self._connections[device_id] = connection
                worker = threading.Thread(
                    target=self._monitor,
                    args=(connection, device_id),
                    daemon=True,
                    name="vector-probe-lifecycle",
                )
                self._workers[device_id] = worker
                worker.start()
                return connection

    def _monitor(self, connection: ProbeConnection, device_id: str) -> None:
        while not self._shutdown.wait(1):
            connection.tick()
            if not connection._live():
                return

    def close(self) -> None:
        self._shutdown.set()
        with self._lock:
            connections = tuple(self._connections.values())
            workers = tuple(self._workers.values())
            self._connections.clear()
            self._workers.clear()
            self._device_locks.clear()
        for connection in connections:
            connection.stop()
        for worker in workers:
            worker.join(timeout=5)
