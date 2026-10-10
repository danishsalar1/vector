"""Phase 8F Stage 2B-2: pre-8F Probe debt FG-01, FG-02, FG-06 and FG-13.

Original definitions (formal Phase 8B gate, recorded in STATUS.md):

* FG-01  ``ProbeService._device_locks`` kept an entry for every distinct device id,
         even unknown ones (token-gated, memory only).
* FG-02  Reason labels: user stop -> SESSION_CHANGED; desktop 900 s expiry ->
         ERROR/INVALID_RESPONSE; peer expiry -> DEVICE_UNAVAILABLE. Also cancellation,
         socket timeouts and frame expiry collapsing to generic reasons in the transport.
* FG-06  Unbounded waits on GET and ``connection()`` behind in-flight operations.
* FG-13  Broad ``except Exception`` handlers (resolve alongside FG-02).

All identifiers and timings are fabricated. Nothing here touches ADB or a device.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.probe_helpers import wire
from tests.test_phase8b_probe import (
    ARTIFACT,
    BOOTSTRAP,
    SERIAL,
    MemoryTransport,
    control_response,
    discovered,
    lifecycle,
)
from tests.test_phase8c_diagnostics import v2_lifecycle
from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState
from vector_agent.devices.android.probe_bridge import AndroidProbeBridge
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.probe import lifecycle as lifecycle_module
from vector_agent.probe.adb_transport import AdbProbeTransport
from vector_agent.probe.lifecycle import DiagnosticSessionError, ProbeService
from vector_agent.probe.protocol import ProbeErrorCode, ProbeProtocolSession, ProbeValidationError
from vector_agent.probe.transport import ProbeTransport, ProbeTransportReply
from vector_agent.probe.transport import ProbeTransportStatus as T

UNKNOWN_ID = "android-deadbeef0000"


def _age_session(connection: Any, seconds: float = 901.0) -> None:
    """Push the protocol session past its 900 s lifetime without sleeping."""
    session = connection._session
    session._created_mono -= seconds
    session._created_at -= timedelta(seconds=seconds)


def _hold(lock: threading.Lock, seconds: float) -> threading.Thread:
    """Hold ``lock`` in a background thread, returning once it is held."""
    held = threading.Event()

    def run() -> None:
        with lock:
            held.set()
            time.sleep(seconds)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert held.wait(2)
    return thread


def _wired(service: ProbeService, device_id: str) -> Any:
    """A service-created connection whose bridge/transport are fabricated (no real ADB call)."""
    connection = service.connection(device_id)
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.discover.return_value = discovered()
    bridge.bootstrap.return_value = BOOTSTRAP
    connection._bridge = bridge
    connection._artifact = ARTIFACT
    connection._factory = lambda **kwargs: MemoryTransport(**kwargs)
    return connection


def _service() -> tuple[ProbeService, Any, str]:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    return service, manager, manager.list_sessions()[0].device_id


# ====================================================================== FG-01


def test_fg01_unknown_device_ids_never_create_registry_entries() -> None:
    service, _, _ = _service()
    for i in range(500):
        with pytest.raises(ValueError):
            service.connection(f"android-{i:012x}")
    assert service._device_locks == {}
    service.close()


def test_fg01_registry_is_empty_after_a_successful_connection_call() -> None:
    service, _, dev = _service()
    assert service.connection(dev)._live()
    assert service._device_locks == {}
    service.close()


def test_fg01_registry_does_not_accumulate_across_many_devices() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    entries = [
        AdbDeviceEntry(f"FABRICATED_FG01_{i:02d}", AdbDeviceState.DEVICE, {}) for i in range(40)
    ]
    manager.reconcile_android_discovery(entries)
    connected = [x for x in manager.list_sessions() if x.connection_state.value == "CONNECTED"]
    assert len(connected) == 40
    for session in connected:
        service.connection(session.device_id).stop()
    assert service._device_locks == {}
    service.close()


def test_fg01_registry_is_cleaned_when_the_call_fails() -> None:
    service, manager, dev = _service()
    manager.mark_platform_offline(lifecycle_module.Platform.ANDROID)
    with pytest.raises(ValueError):
        service.connection(dev)
    assert service._device_locks == {}
    service.close()


def test_fg01_per_device_serialization_is_preserved_under_a_race() -> None:
    service, _, dev = _service()
    results: list[Any] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(12)

    def call() -> None:
        try:
            barrier.wait(5)
            results.append(service.connection(dev))
        except BaseException as exc:  # noqa: BLE001 - test collects any failure
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors
    assert len(results) == 12 and all(c is results[0] for c in results)
    assert len(service._workers) == 1 and len(service._connections) == 1
    assert service._device_locks == {}
    service.close()


def test_fg01_a_waiting_caller_keeps_the_entry_alive_and_mutual_exclusion_intact() -> None:
    service, _, dev = _service()
    inside, leave = threading.Event(), threading.Event()
    first_released = threading.Event()

    def waiter() -> None:
        with service._device_guard(dev, 3.0):
            inside.set()
            leave.wait(5)

    with service._device_guard(dev, 2.0):
        t = threading.Thread(target=waiter)
        t.start()
        deadline = time.monotonic() + 2
        while service._device_locks[dev].users < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service._device_locks[dev].users == 2
        first_released.set()
    # The first holder is gone, the waiter is now inside: the entry must still exist and a
    # third caller must still be excluded (a dropped entry would hand out a second lock).
    assert inside.wait(3)
    assert dev in service._device_locks and service._device_locks[dev].users == 1
    with pytest.raises(ValueError, match="busy"), service._device_guard(dev, 0.1):
        pytest.fail("mutual exclusion lost")
    assert service._device_locks[dev].users == 1
    leave.set()
    t.join(3)
    assert service._device_locks == {}
    service.close()


# ====================================================================== FG-02: lifecycle labels


def test_fg02_user_stop_during_an_in_flight_operation_is_cancelled_not_session_changed() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    entered, release = threading.Event(), threading.Event()
    transport = transports[0]

    def slow_exchange(request: Any, **_: Any) -> ProbeTransportReply:
        entered.set()
        release.wait(5)
        return ProbeTransportReply(T.RECEIVED, wire(control_response(request)))

    transport._exchange = slow_exchange  # type: ignore[method-assign]
    box: dict[str, Any] = {}
    heartbeat = threading.Thread(target=lambda: box.update(hb=connection.heartbeat()))
    heartbeat.start()
    assert entered.wait(2)
    stopper = threading.Thread(target=lambda: box.update(stop=connection.stop()))
    stopper.start()
    deadline = time.monotonic() + 2
    while not connection._cancel.is_set() and time.monotonic() < deadline:
        time.sleep(0.01)
    release.set()
    heartbeat.join(5)
    stopper.join(5)

    assert box["hb"].reason == R.CANCELLED
    assert box["hb"].reason != R.SESSION_CHANGED
    assert (box["stop"].availability, box["stop"].reason) == (A.DISCONNECTED, R.STOPPED)
    assert connection.state().reason == R.STOPPED


def test_fg02_state_after_a_completed_user_stop_keeps_stopped() -> None:
    connection, _, _, _ = lifecycle()
    connection.connect()
    assert connection.stop().reason == R.STOPPED
    after = connection.state()
    assert (after.availability, after.reason) == (A.DISCONNECTED, R.STOPPED)
    assert connection.heartbeat().reason == R.STOPPED
    assert connection.discover().reason == R.STOPPED


def test_fg02_owner_change_is_still_session_changed() -> None:
    connection, manager, _, _ = lifecycle()
    connection.connect()
    manager.mark_platform_offline(lifecycle_module.Platform.ANDROID)
    state = connection.state()
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.SESSION_CHANGED)


def test_fg02_stop_never_masks_a_failed_cleanup() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()

    def broken() -> None:
        raise ConnectionError("fabricated")

    transports[0]._cleanup = broken  # type: ignore[method-assign]
    connection.stop()
    assert connection.state().reason == R.TOOL_ERROR


def test_fg02_desktop_session_lifetime_expiry_is_session_expired_on_the_control_path() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    _age_session(connection)
    state = connection.heartbeat()
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.SESSION_EXPIRED)
    assert state.reason != R.INVALID_RESPONSE
    assert not state.transport_connected
    assert transports[0].cleaned == 1


def test_fg02_desktop_session_lifetime_expiry_is_session_expired_on_the_diagnostic_path() -> None:
    connection, _, _ = v2_lifecycle()
    _age_session(connection)
    with pytest.raises(DiagnosticSessionError) as raised:
        connection.diagnostic(O.START_CHALLENGE, "touch")
    assert raised.value.reason == R.SESSION_EXPIRED
    assert (connection._state.availability, connection._state.reason) == (
        A.DISCONNECTED,
        R.SESSION_EXPIRED,
    )


def test_fg02_transport_timeout_after_lifetime_ended_is_session_expired() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()

    def exchange(request: Any, **_: Any) -> ProbeTransportReply:
        _age_session(connection)
        return ProbeTransportReply(T.TIMEOUT)

    transports[0]._exchange = exchange  # type: ignore[method-assign]
    assert connection.heartbeat().reason == R.SESSION_EXPIRED


def test_fg02_ordinary_transport_timeout_stays_timeout() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    transports[0].outcome = T.TIMEOUT
    state = connection.heartbeat()
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.TIMEOUT)


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("EXPIRED", R.SESSION_EXPIRED),
        ("REQUIRED", R.DEVICE_UNAVAILABLE),
        ("DENIED", R.DEVICE_UNAVAILABLE),
        ("NOT_STARTED", R.DEVICE_UNAVAILABLE),
        ("RESTRICTED", R.DEVICE_UNAVAILABLE),
        (BOOTSTRAP, R.DEVICE_UNAVAILABLE),
        (OSError("fabricated"), R.DEVICE_UNAVAILABLE),
        (TimeoutError("fabricated"), R.DEVICE_UNAVAILABLE),
        (ValueError("fabricated"), R.DEVICE_UNAVAILABLE),
    ],
    ids=lambda v: v if isinstance(v, str) else type(v).__name__,
)
def test_fg02_peer_expiry_needs_the_apps_own_record(evidence: Any, expected: R) -> None:
    connection, _, bridge, transports = lifecycle()
    connection.connect()
    transports[0].outcome = T.UNAVAILABLE
    if isinstance(evidence, BaseException):
        bridge.bootstrap.side_effect = evidence
    else:
        bridge.bootstrap.return_value = evidence
    state = connection.heartbeat()
    assert (state.availability, state.reason) == (A.DISCONNECTED, expected)


def test_fg02_peer_expiry_record_is_not_consulted_for_other_failures() -> None:
    connection, _, bridge, transports = lifecycle()
    connection.connect()
    transports[0].outcome = T.TIMEOUT
    bridge.bootstrap.return_value = "EXPIRED"
    calls = bridge.bootstrap.call_count
    assert connection.heartbeat().reason == R.TIMEOUT
    assert bridge.bootstrap.call_count == calls


def test_fg02_peer_expiry_record_is_not_consulted_after_a_stop_or_owner_change() -> None:
    connection, manager, bridge, transports = lifecycle()
    connection.connect()
    transports[0].outcome = T.UNAVAILABLE
    bridge.bootstrap.return_value = "EXPIRED"
    manager.mark_platform_offline(lifecycle_module.Platform.ANDROID)
    calls = bridge.bootstrap.call_count
    assert connection.heartbeat().reason == R.SESSION_CHANGED
    assert bridge.bootstrap.call_count == calls


def test_fg02_peer_expiry_on_the_diagnostic_path() -> None:
    connection, _, ts = v2_lifecycle()
    connection._bridge.bootstrap.return_value = "EXPIRED"
    ts[0].outcome = T.UNAVAILABLE
    with pytest.raises(DiagnosticSessionError) as raised:
        connection.diagnostic(O.START_CHALLENGE, "touch")
    assert raised.value.reason == R.SESSION_EXPIRED


def test_fg02_in_flight_query_interrupted_by_stop_is_cancelled_not_session_changed() -> None:
    """The branch for an ACTIVE state (CONNECTED) whose operation a stop interrupted."""
    connection, _, _, _ = lifecycle()
    connection.connect()
    assert connection._state.availability == A.CONNECTED
    entered, release = threading.Event(), threading.Event()

    def slow_action() -> Any:
        entered.set()
        release.wait(5)
        return connection._state

    box: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: box.update(result=connection._guarded(slow_action)))
    worker.start()
    assert entered.wait(2)
    # Cancel without completing stop(): the operation lock is still held by the worker.
    connection._cancel.set()
    release.set()
    worker.join(5)
    assert (box["result"].availability, box["result"].reason) == (A.DISCONNECTED, R.CANCELLED)


def test_fg02_failure_after_a_requested_stop_is_cancelled_never_session_expired() -> None:
    """A request that finds the transport already closed by a stop is CANCELLED."""
    connection, _, _, transports = lifecycle()
    connection.connect()
    connection._cancel.set()  # what stop() does first
    transports[0]._closed.set()  # and the transport closing under the pending request
    assert connection._control(O.HEARTBEAT) is False
    assert (connection._state.availability, connection._state.reason) == (
        A.DISCONNECTED,
        R.CANCELLED,
    )
    assert connection._state.reason != R.SESSION_EXPIRED


def test_fg02_peer_evidence_is_never_read_when_the_connection_is_not_live() -> None:
    connection, manager, bridge, _ = lifecycle()
    connection.connect()
    bridge.bootstrap.return_value = "EXPIRED"
    assert connection._peer_recorded_expiry() is True
    calls = bridge.bootstrap.call_count
    manager.mark_platform_offline(lifecycle_module.Platform.ANDROID)
    assert connection._peer_recorded_expiry() is False
    connection._cancel.set()
    assert connection._peer_recorded_expiry() is False
    assert bridge.bootstrap.call_count == calls


def test_fg06_stop_within_reports_incomplete_while_an_operation_is_in_flight() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    holder = _hold(connection._operation, 1.5)
    start = time.monotonic()
    assert connection.stop_within(0.1) is False
    assert time.monotonic() - start < 1.0
    # Resources were still released immediately, even though the state drop is pending.
    assert connection._cancel.is_set() and transports[0].cleaned == 1
    holder.join(5)
    assert connection.stop_within(1.0) is True
    assert (connection._state.availability, connection._state.reason) == (A.DISCONNECTED, R.STOPPED)


# ====================================================================== FG-02: transport labels


class FaultTransport(ProbeTransport):
    """Fixture adapter whose exchange runs an injected fault, with real base-class handling."""

    def __init__(self, fault: Any) -> None:
        self.session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
        super().__init__(session=self.session, current_device_epoch=lambda: 3)
        self.fault = fault
        self.request_envelope = self.session.create_request(O.HELLO, current_device_epoch=3)

    def _exchange(self, request: Any, **kwargs: Any) -> ProbeTransportReply:
        return self.fault(self, request, kwargs["cancellation"])  # type: ignore[no-any-return]

    def _cleanup(self) -> None:
        return None

    def run(self, cancel: threading.Event | None = None) -> T:
        result = self.request(
            self.request_envelope, timeout_seconds=2, cancellation=cancel or threading.Event()
        )
        return result.status


def _raising(error: BaseException) -> Any:
    def fault(transport: FaultTransport, request: Any, cancellation: Any) -> ProbeTransportReply:
        raise error

    return fault


def _cancelled_then_raising(error: BaseException) -> Any:
    def fault(transport: FaultTransport, request: Any, cancellation: Any) -> ProbeTransportReply:
        transport._closed.set()  # what close() does first: the exchange is being cancelled
        raise error

    return fault


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("x"),
        ConnectionAbortedError("x"),
        OSError("closed socket"),
        TimeoutError("x"),
        RuntimeError("x"),
        ProbeValidationError(ProbeErrorCode.SESSION_CLOSED),
        ProbeValidationError(ProbeErrorCode.EXPIRED),
    ],
    ids=lambda e: type(e).__name__ + getattr(e, "code", ""),
)
def test_fg02_any_failure_during_a_cancelled_exchange_is_cancelled(error: BaseException) -> None:
    assert FaultTransport(_cancelled_then_raising(error)).run() == T.CANCELLED


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionError("x"), T.UNAVAILABLE),
        (TimeoutError("x"), T.TIMEOUT),
        (RuntimeError("x"), T.ERROR),
        (ProbeValidationError(ProbeErrorCode.SESSION_CLOSED), T.CLOSED),
        (ProbeValidationError(ProbeErrorCode.EXPIRED), T.TIMEOUT),
    ],
    ids=lambda e: type(e).__name__ + getattr(e, "code", ""),
)
def test_fg02_without_cancellation_the_specific_reason_is_kept(
    error: BaseException, expected: T
) -> None:
    assert FaultTransport(_raising(error)).run() == expected


def test_fg02_caller_cancellation_event_alone_marks_the_exchange_cancelled() -> None:
    cancel = threading.Event()

    def fault(transport: FaultTransport, request: Any, cancellation: Any) -> ProbeTransportReply:
        cancel.set()
        raise ConnectionError("fabricated")

    assert FaultTransport(fault).run(cancel) == T.CANCELLED


def test_fg02_socket_timeout_while_connecting_is_timeout_not_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45679

    def slow_connect(address: Any, timeout: Any) -> Any:
        raise TimeoutError("fabricated connect timeout")

    monkeypatch.setattr(socket, "create_connection", slow_connect)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    with pytest.raises(TimeoutError):
        AdbProbeTransport(
            session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
        )
    bridge.remove_forward.assert_called_once_with(45679)


def test_fg02_connect_refused_is_still_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45680

    def refused(address: Any, timeout: Any) -> Any:
        raise ConnectionRefusedError("fabricated")

    monkeypatch.setattr(socket, "create_connection", refused)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    with pytest.raises(ConnectionError):
        AdbProbeTransport(
            session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
        )


def test_fg02_connect_timeout_maps_to_timeout_in_the_lifecycle() -> None:
    connection, _, _, _ = lifecycle()

    def factory(**kwargs: Any) -> Any:
        raise TimeoutError("fabricated")

    connection._factory = factory
    state = connection.connect()
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.TIMEOUT)


def test_fg02_real_socket_close_during_a_read_reports_cancelled() -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45681
    original = socket.create_connection
    socket.create_connection = lambda address, timeout: client  # type: ignore[assignment]
    try:
        session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
        transport = AdbProbeTransport(
            session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
        )
    finally:
        socket.create_connection = original  # type: ignore[assignment]
    request = session.create_request(O.HELLO, current_device_epoch=3)
    box: dict[str, T] = {}
    worker = threading.Thread(
        target=lambda: box.update(
            status=transport.request(
                request, timeout_seconds=5, cancellation=threading.Event()
            ).status
        )
    )
    worker.start()
    time.sleep(0.3)  # request sent, peer silent: the reader is blocked in recv
    transport.close()
    worker.join(5)
    peer.close()
    assert box["status"] == T.CANCELLED


# ====================================================================== FG-06


def test_fg06_get_state_does_not_wait_behind_an_in_flight_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle_module, "STATE_WAIT_SECONDS", 0.2)
    service, _, dev = _service()
    connection = service.connection(dev)
    holder = _hold(connection._operation, 3.0)
    start = time.monotonic()
    state = service.get_state(dev)
    elapsed = time.monotonic() - start
    assert elapsed < 1.5
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.STOPPED)
    holder.join(5)
    service.close()


def test_fg06_busy_get_returns_the_last_committed_state_not_a_fabricated_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle_module, "STATE_WAIT_SECONDS", 0.1)
    service, _, dev = _service()
    connection = _wired(service, dev)
    connection.connect()
    committed = connection.state()
    assert committed.availability == A.CONNECTED
    holder = _hold(connection._operation, 1.0)
    assert service.get_state(dev) == committed
    holder.join(5)
    service.close()


def test_fg06_get_state_is_normal_when_idle() -> None:
    service, _, dev = _service()
    connection = _wired(service, dev)
    connection.connect()
    state = service.get_state(dev)
    assert state.availability == A.CONNECTED and state.transport_connected
    service.close()


def test_fg06_connection_does_not_wait_unboundedly_for_a_closing_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle_module, "CONNECTION_WAIT_SECONDS", 0.3)
    service, _, dev = _service()
    old = service.connection(dev)
    holder = _hold(old._operation, 3.0)  # an in-flight operation that cannot be interrupted
    old._cancel.set()
    start = time.monotonic()
    with pytest.raises(ValueError, match="still closing"):
        service.connection(dev)
    assert time.monotonic() - start < 2.0
    # The unfinished predecessor stays tracked so cleanup is retried, never orphaned.
    assert service._connections.get(dev) is old
    assert service._device_locks == {}
    holder.join(5)
    replacement = service.connection(dev)
    assert replacement is not old and replacement._live()
    service.close()


def test_fg06_connection_does_not_wait_unboundedly_for_the_device_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle_module, "CONNECTION_WAIT_SECONDS", 0.3)
    service, _, dev = _service()
    release = threading.Event()
    entered = threading.Event()

    def occupy() -> None:
        with service._device_guard(dev, 2.0):
            entered.set()
            release.wait(5)

    t = threading.Thread(target=occupy, daemon=True)
    t.start()
    assert entered.wait(2)
    start = time.monotonic()
    with pytest.raises(ValueError, match="busy"):
        service.connection(dev)
    assert time.monotonic() - start < 2.0
    release.set()
    t.join(5)
    assert service._device_locks == {}
    assert service.connection(dev)._live()
    service.close()


def test_fg06_other_devices_are_never_delayed_by_a_stuck_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle_module, "CONNECTION_WAIT_SECONDS", 0.3)
    _, manager, _, _ = lifecycle()
    manager.reconcile_android_discovery(
        [
            AdbDeviceEntry("FABRICATED_FG06_A", AdbDeviceState.DEVICE, {}),
            AdbDeviceEntry("FABRICATED_FG06_B", AdbDeviceState.DEVICE, {}),
        ]
    )
    service = ProbeService(manager)
    ids = {s.raw_serial: s.device_id for s in manager.list_sessions()}
    stuck = service.connection(ids["FABRICATED_FG06_A"])
    holder = _hold(stuck._operation, 2.0)
    stuck._cancel.set()
    start = time.monotonic()
    other = service.connection(ids["FABRICATED_FG06_B"])
    assert other._live() and time.monotonic() - start < 1.0
    holder.join(5)
    service.close()


# ====================================================================== FG-13


def test_fg13_unexpected_exception_still_fails_closed_and_logs_only_its_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection, _, bridge, transports = lifecycle()
    connection.connect()
    secret = "PRIVATE_SERIAL_PATH_MARKER"
    bridge.discover.side_effect = RuntimeError(secret)
    with caplog.at_level(logging.DEBUG):
        state = connection.discover()
    assert (state.availability, state.reason) == (A.ERROR, R.INVALID_RESPONSE)
    assert secret not in caplog.text and secret not in state.model_dump_json()
    assert "RuntimeError" in caplog.text
    assert transports[0].cleaned == 1  # the session was torn down, not left open


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        # EXPIRED without a session that really outlived its lifetime is NOT claimed as expiry.
        (ProbeValidationError(ProbeErrorCode.EXPIRED), R.INVALID_RESPONSE),
        (ProbeValidationError(ProbeErrorCode.REPLAY), R.INVALID_RESPONSE),
        (ValueError("x"), R.INVALID_RESPONSE),
        (OSError("output rejected"), R.INVALID_RESPONSE),
        (ConnectionError("x"), R.DEVICE_UNAVAILABLE),
        (TimeoutError("x"), R.TIMEOUT),
        (FileNotFoundError("x"), R.TOOL_UNAVAILABLE),
    ],
    ids=lambda v: v if isinstance(v, R) else type(v).__name__ + getattr(v, "code", ""),
)
def test_fg13_expected_failure_families_have_explicit_reasons(error: Exception, reason: R) -> None:
    connection, _, bridge, _ = lifecycle()
    bridge.discover.side_effect = error
    assert connection.discover().reason == reason


def test_fg13_expected_failures_are_not_logged_as_unexpected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection, _, bridge, _ = lifecycle()
    bridge.discover.side_effect = ValueError("x")
    with caplog.at_level(logging.DEBUG):
        connection.discover()
    assert "unexpected" not in caplog.text.lower()


@pytest.mark.parametrize("error", [OSError("x"), ValueError("x"), RuntimeError("x")])
def test_fg13_stop_app_failure_is_visible_as_tool_error_never_silent(error: Exception) -> None:
    connection, _, bridge, _ = lifecycle()
    connection.connect()
    bridge.stop.side_effect = error
    state = connection.stop(stop_app=True)
    assert (state.availability, state.reason) == (A.ERROR, R.TOOL_ERROR)


@pytest.mark.parametrize("error", [ConnectionError("x"), ValueError("x"), OSError("x")])
def test_fg13_forward_cleanup_failure_is_flagged_and_reported(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45682
    bridge.remove_forward.side_effect = error
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    assert transport.close() == T.ERROR
    assert transport.cleanup_failed is True
    peer.close()


def test_fg13_unexpected_cleanup_exception_still_reports_error_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45683
    bridge.remove_forward.side_effect = RuntimeError("PRIVATE")
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    assert transport.close() == T.ERROR
    peer.close()


# ====================================================================== invariants


def test_identity_and_cleanup_never_cross_devices() -> None:
    """Stopping one device's connection never touches another device's connection/forward."""
    _, manager, _, _ = lifecycle()
    manager.reconcile_android_discovery(
        [
            AdbDeviceEntry("FABRICATED_INV_A", AdbDeviceState.DEVICE, {}),
            AdbDeviceEntry("FABRICATED_INV_B", AdbDeviceState.DEVICE, {}),
        ]
    )
    service = ProbeService(manager)
    ids = {s.raw_serial: s.device_id for s in manager.list_sessions()}
    a = service.connection(ids["FABRICATED_INV_A"])
    b = service.connection(ids["FABRICATED_INV_B"])
    a.stop()
    assert b._live() and service._connections[ids["FABRICATED_INV_B"]] is b
    assert SERIAL not in repr(b._state)
    service.close()


def test_stop_never_uninstalls_anything() -> None:
    """Probe stop only force-stops the app; no failure path reaches an uninstall."""
    connection, _, bridge, _ = lifecycle()
    connection.connect()
    bridge.stop.side_effect = OSError("fabricated")
    connection.stop(stop_app=True)
    names = {name for name in dir(bridge) if not name.startswith("_")}
    assert not {n for n in names if "uninstall" in n.lower() or "remove_package" in n.lower()}
    assert {c[0] for c in bridge.method_calls} <= {
        "discover",
        "stop",
        "bootstrap",
        "launch",
        "forward",
        "remove_forward",
    }
