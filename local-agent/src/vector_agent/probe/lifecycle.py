"""Session-owned Probe lifecycle, separate from scan/diagnostic/provenance policy."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from vector_agent.devices.android.probe_bridge import (
    AndroidProbeBridge,
    ProbeBootstrap,
    TrustedProbeArtifact,
)
from vector_agent.models.device import ConnectionState, DiagnosticResult, Platform
from vector_agent.models.probe import ProbeCapabilityId, ProbeChallengeBinding, ProbeCommandStatus
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_diagnostics import DiagnosticCapability, DiagnosticReport
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.models.probe_lifecycle import ProbeState
from vector_agent.probe.adb_transport import AdbProbeTransport
from vector_agent.probe.diagnostic_evidence import diagnostic_result
from vector_agent.probe.protocol import ProbeProtocolSession
from vector_agent.probe.transport import ProbeTransport
from vector_agent.probe.transport import ProbeTransportStatus as T

# ruff: noqa: TID252
from ..devices.session import DeviceSession, DeviceSessionManager

CONTROL_OPERATIONS = (O.HELLO, O.GET_CAPABILITIES, O.HEARTBEAT)

# One transport-failure vocabulary for control and diagnostic exchanges.
TRANSPORT_FAILURES: dict[T, tuple[A, R]] = {
    T.TIMEOUT: (A.DISCONNECTED, R.TIMEOUT),
    T.UNAVAILABLE: (A.DISCONNECTED, R.DEVICE_UNAVAILABLE),
    T.CLOSED: (A.DISCONNECTED, R.SESSION_EXPIRED),
    T.UNSUPPORTED_PROTOCOL: (A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED),
    T.AUTHENTICATION_FAILURE: (A.UNTRUSTED, R.AUTHENTICATION_FAILED),
    T.CANCELLED: (A.DISCONNECTED, R.CANCELLED),
}
TRANSPORT_FAILURE_DEFAULT = (A.ERROR, R.INVALID_RESPONSE)


class DiagnosticUnavailableError(Exception):
    """Retryable: the device declined this command now (busy, cleaning up, unknown binding).

    Deliberately not a ValueError: the authenticated session stays CONNECTED and no fresh
    consent is required, unlike every DiagnosticSessionError.
    """


class DiagnosticSessionError(ValueError):
    """The diagnostic exchange ended the Probe session.

    ``reason`` equals the reason recorded in the dropped connection state. Reconnecting
    requires fresh on-device consent. Plain ValueError is reserved for caller misuse that
    is rejected before any I/O and leaves the session untouched.
    """

    def __init__(self, reason: R, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class DiagnosticTransportError(DiagnosticSessionError):
    """Transport-level failure during a diagnostic exchange (e.g. TIMEOUT, CANCELLED)."""


class DiagnosticExhaustedError(DiagnosticSessionError):
    """START answered ERROR: the device's per-session challenge budget (256) is exhausted."""

    def __init__(self, reason: R = R.SESSION_EXPIRED) -> None:
        super().__init__(
            reason, "Diagnostic challenge budget exhausted; reconnect with fresh consent."
        )


def _history_continues(previous: DiagnosticReport, report: DiagnosticReport) -> bool:
    """A challenge's report may only extend its own history.

    Elapsed time never decreases and a terminal report is immutable. Once STOPPING, the
    evidence is frozen and collection cannot resume: only STOPPING again or the
    interrupted terminal state (CANCELLED or EXPIRED) may follow.
    """
    if report.elapsed_ms < previous.elapsed_ms:
        return False
    if previous.state != "RUNNING":
        return bool(report == previous)
    if previous.reason == "STOPPING":
        return report.metrics == previous.metrics and (
            report.state in {"CANCELLED", "EXPIRED"}
            or (report.state == "RUNNING" and report.reason == "STOPPING")
        )
    return True


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
        self._diagnostic_capabilities: tuple[DiagnosticCapability, ...] = ()
        self._diagnostic_binding: ProbeChallengeBinding | None = None
        self._diagnostic_running = False
        self._diagnostic_last: DiagnosticReport | None = None

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
        self._diagnostic_capabilities = ()
        self._diagnostic_binding = None
        self._diagnostic_last = None
        self._diagnostic_running = False
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
                device_id=self._owner.device_id,
                device_epoch=self._epoch,
                protocol_version=self._artifact.protocol_version if self._artifact else 1,
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
            state, reason = TRANSPORT_FAILURES.get(result.status, TRANSPORT_FAILURE_DEFAULT)
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
                or hello.protocol_versions != (artifact.protocol_version,)
                or set(hello.supported_operations)
                != (set(O) if artifact.protocol_version == 2 else set(CONTROL_OPERATIONS))
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
            if self._artifact is not None and self._artifact.protocol_version == 2:
                if not response.diagnostic_capabilities:
                    self._drop(A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED)
                    return False
                self._diagnostic_capabilities = response.diagnostic_capabilities
        return True

    def _dropped(
        self,
        state: A,
        reason: R,
        message: str,
        kind: type[DiagnosticSessionError] = DiagnosticSessionError,
    ) -> DiagnosticSessionError:
        """Drop the session; the error carries the recorded reason (TOOL_ERROR if cleanup failed)."""
        self._drop(state, reason)
        return kind(self._state.reason, message)

    def _ended(self) -> DiagnosticSessionError:
        """Typed error for a connection that is no longer live.

        An owner epoch change is recorded as SESSION_CHANGED. A stop() still waiting for
        this operation is recorded as CANCELLED. A completed stop() or failed cleanup has
        already recorded its own reason, which is preserved.
        """
        if self._current_epoch() != self._epoch:
            self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
        elif self._state.availability == A.CONNECTED:
            self._drop(A.DISCONNECTED, R.CANCELLED)
        reason = self._state.reason
        return DiagnosticSessionError(
            reason, f"Probe session ended ({reason.value}); reconnect with fresh consent."
        )

    def diagnostic_capabilities(self) -> tuple[DiagnosticCapability, ...]:
        with self._operation:
            if not self._live():
                raise self._ended()
            if self._state.availability != A.CONNECTED:
                raise ValueError("Probe not connected.")
            return self._diagnostic_capabilities

    def diagnostic(self, operation: O, diagnostic_id: str | None = None) -> DiagnosticResult:
        """Trusted in-process entry; binding is generated here, never caller supplied.

        Each exchange retains the 3-second transport budget. It never waits for
        physical interaction. The service monitor remains responsible for liveness.

        Raises DiagnosticUnavailableError (retryable, session kept), DiagnosticSessionError
        (session dropped; ``reason`` is the recorded drop reason) or plain ValueError
        (caller misuse rejected before any I/O; session untouched).
        """
        with self._operation:
            if not self._live():
                raise self._ended()
            if (
                self._state.availability != A.CONNECTED
                or self._session is None
                or self._transport is None
                or self._artifact is None
                or self._artifact.protocol_version != 2
            ):
                raise ValueError("Diagnostic protocol unavailable.")
            if operation not in (O.START_CHALLENGE, O.FETCH_OBSERVATIONS, O.CANCEL_CHALLENGE):
                raise ValueError("Unsupported diagnostic operation.")
            if operation == O.START_CHALLENGE:
                if self._diagnostic_running:
                    raise ValueError("Diagnostic already running.")
                if diagnostic_id not in {c.diagnostic_id for c in self._diagnostic_capabilities}:
                    raise ValueError("Diagnostic not advertised.")
                assert diagnostic_id is not None
                self._diagnostic_binding = ProbeChallengeBinding(
                    scan_id=str(uuid4()),
                    diagnostic_id=diagnostic_id,
                    attempt_id=str(uuid4()),
                    challenge_id=str(uuid4()),
                    collection_not_before=datetime.now(UTC),
                )
                self._diagnostic_last = None
            elif diagnostic_id is not None:
                raise ValueError("Polling cannot change diagnostic ownership.")
            binding = self._diagnostic_binding
            if binding is None:
                raise ValueError("No diagnostic started.")
            try:
                request = self._session.create_request(
                    operation, current_device_epoch=self._current_epoch(), binding=binding
                )
                result = self._transport.request(
                    request, timeout_seconds=3, cancellation=self._cancel
                )
                if not self._live():
                    raise self._ended()
                if result.status != T.RECEIVED or result.response is None:
                    state, reason = TRANSPORT_FAILURES.get(result.status, TRANSPORT_FAILURE_DEFAULT)
                    raise self._dropped(
                        state,
                        reason,
                        f"Diagnostic exchange failed: {reason.value}.",
                        DiagnosticTransportError,
                    )
                status = result.response.command_status
                if status == ProbeCommandStatus.UNAVAILABLE:
                    if operation == O.START_CHALLENGE:
                        self._diagnostic_binding = None
                    raise DiagnosticUnavailableError(
                        "Device diagnostic unavailable or cleaning up; retryable without re-consent."
                    )
                if status == ProbeCommandStatus.ERROR:
                    # The Probe answers ERROR only to START once its challenge budget is spent.
                    if operation == O.START_CHALLENGE:
                        self._drop(A.DISCONNECTED, R.SESSION_EXPIRED)
                        raise DiagnosticExhaustedError(self._state.reason)
                    raise self._dropped(
                        *TRANSPORT_FAILURE_DEFAULT, "Device answered ERROR outside START."
                    )
                if status != ProbeCommandStatus.OK or result.response.diagnostic is None:
                    raise self._dropped(*TRANSPORT_FAILURE_DEFAULT, "Diagnostic exchange rejected.")
                report = result.response.diagnostic
                previous = self._diagnostic_last
                if previous is not None and not _history_continues(previous, report):
                    raise self._dropped(*TRANSPORT_FAILURE_DEFAULT, "Diagnostic history changed.")
                self._diagnostic_last = report
                self._diagnostic_running = report.state == "RUNNING"
                return diagnostic_result(
                    report,
                    device_id=self._owner.device_id,
                    epoch=self._epoch,
                    session_id=self._session.probe_session_id,
                    binding=binding,
                )
            except (DiagnosticUnavailableError, DiagnosticSessionError):
                raise
            except (ConnectionError, ValueError):
                if not self._live():
                    raise self._ended() from None
                raise self._dropped(
                    *TRANSPORT_FAILURE_DEFAULT,
                    "Diagnostic unavailable; reconnect with fresh consent.",
                ) from None

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
