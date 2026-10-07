"""Bounded hostile JSON and real transport-base enforcement with a fake I/O edge."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from tests.probe_helpers import EPOCH, make_case, response, wire
from vector_agent.models.probe import (
    MAX_COLLECTION_ITEMS,
    MAX_NESTING_DEPTH,
    MAX_OBJECT_KEYS,
    MAX_PROTOCOL_MESSAGE_BYTES,
    MAX_STRING_LENGTH,
    ProbeRequestEnvelope,
)
from vector_agent.probe.protocol import ProbeValidationError, decode_message, generate_nonce
from vector_agent.probe.transport import (
    ProbeCancellation,
    ProbeTransport,
    ProbeTransportReply,
    ProbeTransportStatus,
)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b'{"protocol_version":1,"protocol_version":1}',
        b'{"protocol_version":1,"extra":NaN}',
        b'{"protocol_version":1,"extra":Infinity}',
        b'{"protocol_version":1,"extra":-Infinity}',
        b'{"protocol_version":1,"extra":1e999}',
        b'{"protocol_version":1,"extra":"\\ud800"}',
        b'{"protocol_version":1}\n{}',
    ],
)
def test_malformed_json_has_safe_errors(raw: bytes, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ProbeValidationError) as caught:
        decode_message(raw)
    assert caught.value.__context__ is None
    assert not caplog.text


def test_byte_limit_exact_and_over() -> None:
    base = b'{"protocol_version":1}'
    assert decode_message(base + b" " * (MAX_PROTOCOL_MESSAGE_BYTES - len(base)))
    with pytest.raises(ProbeValidationError, match="BOUNDS_VIOLATION"):
        decode_message(base + b" " * (MAX_PROTOCOL_MESSAGE_BYTES - len(base) + 1))


@pytest.mark.parametrize("kind", ["string", "collection", "keys", "depth"])
def test_bounds_at_limit_and_over(kind: str) -> None:
    for extra in (0, 1):
        value: Any
        if kind == "string":
            value = {"protocol_version": 1, "x": "s" * (MAX_STRING_LENGTH + extra)}
        elif kind == "collection":
            value = {"protocol_version": 1, "x": [0] * (MAX_COLLECTION_ITEMS + extra)}
        elif kind == "keys":
            value = {
                "protocol_version": 1,
                **{f"key_{i}": 0 for i in range(MAX_OBJECT_KEYS - 1 + extra)},
            }
        else:
            nested: Any = 0
            for _ in range(MAX_NESTING_DEPTH - 1 + extra):
                nested = [nested]
            value = {"protocol_version": 1, "x": nested}
        if extra:
            with pytest.raises(ProbeValidationError, match="BOUNDS_VIOLATION"):
                decode_message(wire(value))
        else:
            assert decode_message(wire(value))["protocol_version"] == 1


def test_escaped_brackets_do_not_confuse_depth_scanner() -> None:
    assert (
        decode_message(wire({"protocol_version": 1, "x": '"\\' + "[" * 100}))["protocol_version"]
        == 1
    )


def test_huge_integer_and_nesting_rejected_without_parser_recursion() -> None:
    for raw in (b'{"protocol_version":1,"x":' + b"9" * 5000 + b"}", b"[" * 10000 + b"]" * 10000):
        with pytest.raises(ProbeValidationError, match="BOUNDS_VIOLATION"):
            decode_message(raw)


def test_nonce_uses_256_bit_stdlib_randomness(monkeypatch: pytest.MonkeyPatch) -> None:
    import vector_agent.probe.protocol as module

    original = module.secrets.token_urlsafe
    counts: list[int | None] = []

    def spy(nbytes: int | None = None) -> str:
        counts.append(nbytes)
        return original(nbytes)

    monkeypatch.setattr(module.secrets, "token_urlsafe", spy)
    nonces = {generate_nonce() for _ in range(64)}
    assert len(nonces) == 64
    assert {len(nonce) for nonce in nonces} == {43}
    assert counts == [32] * 64


class BoundaryTransport(ProbeTransport):
    """Only the I/O edge is fake; request/validation/cleanup are production code."""

    def __init__(
        self,
        action: Callable[[ProbeRequestEnvelope, float, ProbeCancellation], ProbeTransportReply],
    ) -> None:
        self.clock, session, self.issued_request, self.data = make_case()
        self.epoch = EPOCH
        super().__init__(
            session=session, current_device_epoch=lambda: self.epoch, monotonic=self.clock.monotonic
        )
        self.action = action
        self.calls = 0
        self.cleanup_calls = 0

    def _exchange(
        self, request: ProbeRequestEnvelope, *, deadline: float, cancellation: ProbeCancellation
    ) -> ProbeTransportReply:
        self.calls += 1
        assert deadline > self.clock.mono
        return self.action(request, deadline, cancellation)

    def _cleanup(self) -> None:
        self.cleanup_calls += 1


def test_transport_validates_actual_response() -> None:
    transport = BoundaryTransport(
        lambda *_: ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))
    )
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.RECEIVED
    assert result.response is not None
    assert result.response.observations[0].value == 3
    assert transport.issued_request.nonce not in repr(result)


@pytest.mark.parametrize(
    "status",
    [
        ProbeTransportStatus.TIMEOUT,
        ProbeTransportStatus.UNAVAILABLE,
        ProbeTransportStatus.AUTHENTICATION_FAILURE,
        ProbeTransportStatus.PROTOCOL_VIOLATION,
        ProbeTransportStatus.UNSUPPORTED_PROTOCOL,
        ProbeTransportStatus.BOUNDS_VIOLATION,
    ],
)
def test_typed_transport_failure(status: ProbeTransportStatus) -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(status))
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == status
    assert result.response is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError, ProbeTransportStatus.TIMEOUT),
        (ConnectionError, ProbeTransportStatus.UNAVAILABLE),
        (RuntimeError, ProbeTransportStatus.ERROR),
    ],
)
def test_transport_exceptions_are_safe(
    error: type[Exception], expected: ProbeTransportStatus, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "PRIVATE_SERIAL_IMEI_NONCE_MARKER"

    def fail(*_: Any) -> ProbeTransportReply:
        raise error(secret)

    transport = BoundaryTransport(fail)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == expected
    assert secret not in repr(result) + caplog.text


@pytest.mark.parametrize(
    "mutation", ["version", "epoch", "oversize", "schema", "nonce", "error_payload"]
)
def test_transport_never_accepts_unvalidated_payload(mutation: str) -> None:
    transport = BoundaryTransport(
        lambda *_: ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))
    )
    expected = ProbeTransportStatus.PROTOCOL_VIOLATION
    if mutation == "version":
        transport.data["protocol_version"] = 2
        expected = ProbeTransportStatus.UNSUPPORTED_PROTOCOL
    elif mutation == "epoch":
        transport.data["device_epoch"] += 1
    elif mutation == "nonce":
        transport.data["nonce"] = "z" * 43
    elif mutation == "schema":
        transport.data["raw_dump"] = "PRIVATE_MARKER"
    elif mutation == "oversize":
        transport.action = lambda *_: ProbeTransportReply(
            ProbeTransportStatus.RECEIVED, b" " * (MAX_PROTOCOL_MESSAGE_BYTES + 1)
        )
        expected = ProbeTransportStatus.BOUNDS_VIOLATION
    else:
        transport.action = lambda *_: ProbeTransportReply(
            ProbeTransportStatus.TIMEOUT, wire(transport.data)
        )
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == expected
    assert result.response is None


def test_late_transport_success_is_timeout() -> None:
    def late(*_: Any) -> ProbeTransportReply:
        transport.clock.advance(2)
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))

    transport = BoundaryTransport(late)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.TIMEOUT


def test_epoch_is_revalidated_after_exchange() -> None:
    def changed(*_: Any) -> ProbeTransportReply:
        transport.epoch += 1
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))

    transport = BoundaryTransport(changed)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.PROTOCOL_VIOLATION


def test_cleanup_is_idempotent_and_request_after_close_is_rejected() -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    assert transport.close() == ProbeTransportStatus.CLOSED
    assert transport.close() == ProbeTransportStatus.CLOSED
    assert transport.cleanup_calls == 1
    assert (
        transport.request(
            transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
        ).status
        == ProbeTransportStatus.CLOSED
    )
    assert transport.calls == 0


@pytest.mark.parametrize("before", [True, False])
def test_cancellation_drops_reply(before: bool) -> None:
    event = threading.Event()

    def cancel(*_: Any) -> ProbeTransportReply:
        event.set()
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))

    transport = BoundaryTransport(cancel)
    if before:
        event.set()
    result = transport.request(transport.issued_request, timeout_seconds=1, cancellation=event)
    assert result.status == ProbeTransportStatus.CANCELLED
    assert result.response is None
    assert transport.calls == (0 if before else 1)


@pytest.mark.parametrize("timeout", [True, 0, -1, 31, float("inf"), float("nan")])
def test_transport_invalid_deadlines_do_not_dispatch(timeout: Any) -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    assert (
        transport.request(
            transport.issued_request, timeout_seconds=timeout, cancellation=threading.Event()
        ).status
        == ProbeTransportStatus.BOUNDS_VIOLATION
    )
    assert transport.calls == 0


def test_concurrent_request_and_close() -> None:
    entered = threading.Event()
    release = threading.Event()
    results: list[Any] = []

    def wait_for_close(
        _: ProbeRequestEnvelope, __: float, cancellation: ProbeCancellation
    ) -> ProbeTransportReply:
        entered.set()
        assert release.wait(3)
        assert cancellation.is_cancelled()
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))

    transport = BoundaryTransport(wait_for_close)
    worker = threading.Thread(
        target=lambda: results.append(
            transport.request(
                transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
            )
        )
    )
    worker.start()
    try:
        assert entered.wait(3)
        assert (
            transport.request(
                transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
            ).status
            == ProbeTransportStatus.BUSY
        )
        transport.close()
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results[0].status == ProbeTransportStatus.CANCELLED
    assert transport.cleanup_calls == 1


def test_foreign_request_rejection_does_not_abandon_real_request() -> None:
    transport = BoundaryTransport(
        lambda *_: ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))
    )
    _, _, foreign, _ = make_case()
    rejected = transport.request(foreign, timeout_seconds=1, cancellation=threading.Event())
    assert rejected.status == ProbeTransportStatus.PROTOCOL_VIOLATION
    assert transport.calls == 0
    accepted = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert accepted.status == ProbeTransportStatus.RECEIVED


def test_abandon_does_not_clear_a_new_request() -> None:
    _, session, first, _ = make_case()
    session.abandon_request(first)
    new = session.create_request(first.operation, current_device_epoch=EPOCH, binding=first.binding)
    session.abandon_request(first)
    session.require_pending(new, current_device_epoch=EPOCH)


def test_expired_monotonic_request_never_dispatches() -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    transport.clock.mono += 30
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.TIMEOUT
    assert transport.calls == 0


def test_cleanup_failure_is_safe_and_does_not_reopen(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenCleanup(BoundaryTransport):
        def _cleanup(self) -> None:
            self.cleanup_calls += 1
            raise RuntimeError("PRIVATE_CLEANUP_MARKER")

    transport = BrokenCleanup(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    assert transport.close() == ProbeTransportStatus.ERROR
    assert transport.close() == ProbeTransportStatus.CLOSED
    assert transport.cleanup_calls == 1
    assert "PRIVATE_CLEANUP_MARKER" not in caplog.text


def test_inherited_nonce_and_payload_never_enter_parse_error_context() -> None:
    _, session, request, data = make_case()
    data["operation"] = "PRIVATE_OPERATION_MARKER"
    with pytest.raises(ProbeValidationError) as caught:
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert request.nonce not in repr(caught.value)
    assert "PRIVATE_OPERATION_MARKER" not in str(caught.value)


def test_replaced_request_reply_cannot_be_consumed_by_old_exchange() -> None:
    replacement: list[ProbeRequestEnvelope] = []

    def replace(request: ProbeRequestEnvelope, *_: Any) -> ProbeTransportReply:
        transport._session.abandon_request(request)
        new = transport._session.create_request(
            request.operation, current_device_epoch=EPOCH, binding=request.binding
        )
        replacement.append(new)
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(response(new)))

    transport = BoundaryTransport(replace)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.PROTOCOL_VIOLATION
    assert result.response is None
    new = replacement[0]
    transport._session.require_pending(new, current_device_epoch=EPOCH)
    transport.action = lambda request, *_: ProbeTransportReply(
        ProbeTransportStatus.RECEIVED, wire(response(request))
    )
    assert (
        transport.request(new, timeout_seconds=1, cancellation=threading.Event()).status
        == ProbeTransportStatus.RECEIVED
    )


def test_second_transport_cannot_dispatch_or_clear_same_session_request() -> None:
    competing_results: list[ProbeTransportStatus] = []
    first = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    second = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    # Two adapters accidentally sharing a session must still serialize dispatch.
    second._session = first._session

    def compete(*_: Any) -> ProbeTransportReply:
        competing_results.append(
            second.request(
                first.issued_request, timeout_seconds=1, cancellation=threading.Event()
            ).status
        )
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(first.data))

    first.action = compete
    result = first.request(first.issued_request, timeout_seconds=1, cancellation=threading.Event())
    assert competing_results == [ProbeTransportStatus.BUSY]
    assert second.calls == 0
    assert result.status == ProbeTransportStatus.RECEIVED


@pytest.mark.parametrize("failure", ["schema", "timeout", "exception", "cancel"])
def test_rejected_completion_burns_only_its_request_and_releases_dispatch(failure: str) -> None:
    event = threading.Event()

    def reject(*_: Any) -> ProbeTransportReply:
        if failure == "exception":
            raise RuntimeError("FABRICATED_PRIVATE_FAILURE")
        if failure == "timeout":
            return ProbeTransportReply(ProbeTransportStatus.TIMEOUT)
        if failure == "cancel":
            event.set()
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, b"{}")

    transport = BoundaryTransport(reject)
    result = transport.request(transport.issued_request, timeout_seconds=1, cancellation=event)
    assert result.status != ProbeTransportStatus.RECEIVED
    with pytest.raises(ProbeValidationError):
        transport._session.accept_response(
            wire(transport.data),
            current_device_epoch=EPOCH,
            expected_request=transport.issued_request,
        )
    new = transport._session.create_request(
        transport.issued_request.operation,
        current_device_epoch=EPOCH,
        binding=transport.issued_request.binding,
    )
    transport.action = lambda request, *_: ProbeTransportReply(
        ProbeTransportStatus.RECEIVED, wire(response(request))
    )
    assert (
        transport.request(new, timeout_seconds=1, cancellation=threading.Event()).status
        == ProbeTransportStatus.RECEIVED
    )


def test_success_cleanup_preserves_request_issued_before_finally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = BoundaryTransport(
        lambda *_: ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))
    )
    replacement: list[ProbeRequestEnvelope] = []
    finish = transport._session.finish_dispatch

    def issue_then_finish(request: ProbeRequestEnvelope) -> None:
        # Force the interleaving after acceptance and before real production cleanup.
        replacement.append(
            transport._session.create_request(
                request.operation, current_device_epoch=EPOCH, binding=request.binding
            )
        )
        finish(request)

    monkeypatch.setattr(transport._session, "finish_dispatch", issue_then_finish)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.RECEIVED
    new = replacement[0]
    transport._session.require_pending(new, current_device_epoch=EPOCH)
    assert (
        transport._session.accept_response(
            wire(response(new)), current_device_epoch=EPOCH, expected_request=new
        ).sequence_number
        == new.sequence_number
    )


@pytest.mark.parametrize("invalid", [None, {}, "PRIVATE_REQUEST_MARKER"])
def test_untyped_request_cannot_clear_pending_request(invalid: Any) -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    result = transport.request(invalid, timeout_seconds=1, cancellation=threading.Event())
    assert result.status == ProbeTransportStatus.PROTOCOL_VIOLATION
    assert transport.calls == 0
    transport._session.require_pending(transport.issued_request, current_device_epoch=EPOCH)


def test_invalid_timeout_does_not_wedge_future_creation_after_expiry() -> None:
    transport = BoundaryTransport(lambda *_: ProbeTransportReply(ProbeTransportStatus.ERROR))
    old = transport.issued_request
    result = transport.request(old, timeout_seconds=0, cancellation=threading.Event())
    assert result.status == ProbeTransportStatus.BOUNDS_VIOLATION
    assert transport.calls == 0
    transport.clock.advance(31)
    new = transport._session.create_request(
        old.operation, current_device_epoch=EPOCH, binding=old.binding
    )
    assert new.sequence_number == old.sequence_number + 1
    transport.action = lambda request, *_: ProbeTransportReply(
        ProbeTransportStatus.RECEIVED, wire(response(request))
    )
    assert (
        transport.request(new, timeout_seconds=1, cancellation=threading.Event()).status
        == ProbeTransportStatus.RECEIVED
    )
    assert transport._session._pending_mono is None


def test_old_transport_after_expiry_does_not_clear_replacement_time_or_owner() -> None:
    replacement: list[ProbeRequestEnvelope] = []

    def replace(old: ProbeRequestEnvelope, *_: Any) -> ProbeTransportReply:
        transport.clock.advance(31)
        replacement.append(
            transport._session.create_request(
                old.operation, current_device_epoch=EPOCH, binding=old.binding
            )
        )
        return ProbeTransportReply(ProbeTransportStatus.RECEIVED, wire(transport.data))

    transport = BoundaryTransport(replace)
    result = transport.request(
        transport.issued_request, timeout_seconds=1, cancellation=threading.Event()
    )
    assert result.status == ProbeTransportStatus.TIMEOUT
    new = replacement[0]
    assert transport._session._pending == new
    assert transport._session._pending_mono == transport.clock.mono
    assert transport._session._dispatch_request is None
    transport.action = lambda request, *_: ProbeTransportReply(
        ProbeTransportStatus.RECEIVED, wire(response(request))
    )
    assert (
        transport.request(new, timeout_seconds=1, cancellation=threading.Event()).status
        == ProbeTransportStatus.RECEIVED
    )
