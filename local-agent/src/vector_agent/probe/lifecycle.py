"""Session-owned Probe lifecycle, separate from scan/diagnostic/provenance policy."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from vector_agent.core.logging import get_logger
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
from vector_agent.probe.protocol import ProbeErrorCode, ProbeProtocolSession, ProbeValidationError
from vector_agent.probe.transport import ProbeTransport
from vector_agent.probe.transport import ProbeTransportStatus as T

# ruff: noqa: TID252
from ..devices.session import DeviceSession, DeviceSessionManager

logger = get_logger(__name__)

CONTROL_OPERATIONS = (O.HELLO, O.GET_CAPABILITIES, O.HEARTBEAT)

# FG-06: no state query or connection hand-off waits indefinitely behind an in-flight
# operation. A GET returns the last committed state after STATE_WAIT_SECONDS; connection()
# gives a closing predecessor / a competing caller CONNECTION_WAIT_SECONDS, then fails with a
# retryable ValueError (existing 409 mapping) instead of hanging the request thread.
STATE_WAIT_SECONDS = 0.5
CONNECTION_WAIT_SECONDS = 5.0

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

    def _peer_recorded_expiry(self) -> bool:
        """True only when the Probe app's own private record says it expired the session.

        A peer-closed socket alone is indistinguishable from an unplugged cable, so
        DEVICE_UNAVAILABLE stays the default. This is a bounded, read-only ``run-as`` read of
        the app's state file; any failure to obtain that evidence is "no evidence".
        """
        if not self._live():
            return False
        try:
            return bool(self._bridge.bootstrap() == "EXPIRED")
        except (OSError, ValueError):
            return False

    def _failure(self, status: T) -> tuple[A, R]:
        """Truthful (availability, reason) for a failed exchange (FG-02).

        A requested stop explains every failure that follows it (CANCELLED); a session that
        outlived its 900 s lifetime, or that the app recorded as expired, is SESSION_EXPIRED
        rather than a generic timeout or disconnect.
        """
        if self._cancel.is_set():
            return A.DISCONNECTED, R.CANCELLED
        if status == T.TIMEOUT and self._session is not None and self._session.lifetime_exhausted():
            return A.DISCONNECTED, R.SESSION_EXPIRED
        if status == T.UNAVAILABLE and self._peer_recorded_expiry():
            return A.DISCONNECTED, R.SESSION_EXPIRED
        return TRANSPORT_FAILURES.get(status, TRANSPORT_FAILURE_DEFAULT)

    def _validation_failure(self, error: ProbeValidationError) -> tuple[A, R]:
        """The desktop protocol session itself rejected the request (FG-02)."""
        if (
            error.code == ProbeErrorCode.EXPIRED
            and self._session is not None
            and self._session.lifetime_exhausted()
        ):
            return A.DISCONNECTED, R.SESSION_EXPIRED
        return TRANSPORT_FAILURE_DEFAULT

    def _end_not_live(self) -> ProbeState:
        """Record why a connection is no longer live, without relabelling a user stop.

        Owner change is SESSION_CHANGED. A completed stop keeps STOPPED and an earlier
        recorded end keeps its own reason; an interrupted in-flight operation is CANCELLED.
        """
        if self._current_epoch() != self._epoch:
            return self._drop(A.DISCONNECTED, R.SESSION_CHANGED)
        state = self._state
        if state.availability in (A.DISCONNECTED, A.ERROR):
            return self._drop(state.availability, state.reason)
        return self._drop(A.DISCONNECTED, R.CANCELLED)

    def _guarded(self, action: Callable[[], ProbeState]) -> ProbeState:
        with self._operation:
            return self._run_guarded(action)

    def state_bounded(self, timeout: float) -> ProbeState:
        """Current state, waiting at most ``timeout`` seconds for an in-flight operation.

        If the operation is still running the last COMMITTED state is returned: never a
        guess about the outcome of the unfinished operation (FG-06).
        """
        if not self._operation.acquire(timeout=timeout):
            return self._state
        try:
            return self._run_guarded(lambda: self._state)
        finally:
            self._operation.release()

    def _run_guarded(self, action: Callable[[], ProbeState]) -> ProbeState:
        """Run ``action`` holding the operation lock; map every failure to a typed state."""
        if not self._live():
            return self._end_not_live()
        failure: tuple[A, R]
        try:
            state = action()
        except ProbeValidationError as exc:
            failure = self._validation_failure(exc)
        except ConnectionError:
            failure = (A.DISCONNECTED, R.DEVICE_UNAVAILABLE)
        except FileNotFoundError:
            failure = (A.RESTRICTED, R.TOOL_UNAVAILABLE)
        except TimeoutError:
            failure = (A.DISCONNECTED, R.TIMEOUT)
        except (OSError, ValueError):
            # Expected: bounded-subprocess/ADB errors and malformed or undecodable output.
            failure = (A.ERROR, R.INVALID_RESPONSE)
        except Exception as exc:
            # Last-resort fail-closed backstop (FG-13): the session is torn down below and
            # reported as ERROR. Only the exception TYPE is logged, never its message.
            logger.error("Probe lifecycle failed closed on unexpected %s", type(exc).__name__)
            failure = (A.ERROR, R.INVALID_RESPONSE)
        else:
            return state if self._live() else self._end_not_live()
        if not self._live():
            return self._end_not_live()
        return self._drop(*failure)

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
            state, reason = self._failure(result.status)
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
                    state, reason = self._failure(result.status)
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
            except (ConnectionError, ValueError) as exc:
                if not self._live():
                    raise self._ended() from None
                if isinstance(exc, ProbeValidationError):
                    state, reason = self._validation_failure(exc)
                    raise self._dropped(
                        state, reason, "Diagnostic unavailable; reconnect with fresh consent."
                    ) from None
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
        state = self._stop(stop_app=stop_app, wait=None)
        assert state is not None  # an unbounded wait always completes
        return state

    def stop_within(self, wait: float) -> bool:
        """Stop, waiting at most ``wait`` seconds for an in-flight operation (FG-06).

        Resources are released immediately (cancellation + transport close). Returns False if
        the in-flight operation had not finished in time, so the caller keeps tracking this
        connection and retries instead of treating it as closed.
        """
        return self._stop(stop_app=False, wait=wait) is not None

    def _stop(self, *, stop_app: bool, wait: float | None) -> ProbeState | None:
        self._cancel.set()
        # close() unblocks socket I/O without waiting for the operation lock.
        transport = self._transport
        if transport is not None and transport.close() == T.ERROR:
            self._cleanup_failed = True
        if not self._operation.acquire(timeout=-1 if wait is None else wait):
            return None
        try:
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
                except (OSError, ValueError):
                    state = self._drop(A.ERROR, R.TOOL_ERROR)
                except Exception as exc:
                    # Last-resort fail-closed backstop (FG-13): never report a clean stop.
                    logger.error("Probe stop failed closed on unexpected %s", type(exc).__name__)
                    state = self._drop(A.ERROR, R.TOOL_ERROR)
            return state
        finally:
            self._operation.release()


class _DeviceGate:
    """Per-device serialization lock plus the number of callers using it (FG-01)."""

    __slots__ = ("lock", "users")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users = 0


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
        self._device_locks: dict[str, _DeviceGate] = {}
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._workers: dict[str, threading.Thread] = {}

    @contextmanager
    def _device_guard(self, device_id: str, timeout: float) -> Iterator[None]:
        """Serialize lifecycle changes for one device, waiting at most ``timeout`` (FG-06).

        The registry entry exists only while a caller holds or awaits it and is removed with
        the last user, so it can never outgrow the callers currently in flight, whatever
        device ids are presented (FG-01).
        """
        with self._lock:
            gate = self._device_locks.get(device_id)
            if gate is None:
                gate = _DeviceGate()
                self._device_locks[device_id] = gate
            gate.users += 1
        acquired = False
        try:
            acquired = gate.lock.acquire(timeout=timeout)
            if not acquired:
                raise ValueError("Probe lifecycle is busy.")
            yield
        finally:
            if acquired:
                gate.lock.release()
            with self._lock:
                gate.users -= 1
                if gate.users == 0 and self._device_locks.get(device_id) is gate:
                    del self._device_locks[device_id]

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

            state = conn.state_bounded(STATE_WAIT_SECONDS)
            with self._lock:
                current = self._connections.get(device_id)
                if current is conn or current is None or not current._live():
                    return state

        return state

    def connection(self, device_id: str) -> ProbeConnection:
        with self._device_guard(device_id, CONNECTION_WAIT_SECONDS):
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
                    # Stay tracked until the predecessor has really closed, so a stuck
                    # cleanup is retried by the next call and never orphaned.
                    to_stop = old
                    to_join = self._workers.get(device_id)

            if to_stop is not None:
                deadline = time.monotonic() + CONNECTION_WAIT_SECONDS
                closed = to_stop.stop_within(CONNECTION_WAIT_SECONDS)
                if closed and to_join is not None:
                    to_join.join(timeout=max(0.0, deadline - time.monotonic()))
                    closed = not to_join.is_alive()
                if not closed:
                    raise ValueError("Previous Probe lifecycle is still closing.")
                with self._lock:
                    if self._connections.get(device_id) is to_stop:
                        del self._connections[device_id]
                    if self._workers.get(device_id) is to_join:
                        self._workers.pop(device_id, None)

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
