"""Exercise untrusted wire bytes through real schema and session validation."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from tests.probe_helpers import EPOCH, make_case, response, wire
from vector_agent.models.probe import MAX_SEQUENCE_NUMBER, ProbeOperation
from vector_agent.probe.protocol import (
    CLOCK_SKEW_SECONDS,
    MAX_SESSION_REQUESTS,
    MESSAGE_TTL_SECONDS,
    SESSION_MAX_DURATION_SECONDS,
    ProbeErrorCode,
    ProbeValidationError,
    parse_request,
    parse_response,
)


@pytest.mark.parametrize("operation", list(ProbeOperation))
def test_v1_round_trip_and_acceptance(operation: ProbeOperation) -> None:
    _, session, request, data = make_case(operation)
    assert parse_request(request.model_dump_json().encode()) == request
    accepted = session.accept_response(
        wire(data), current_device_epoch=EPOCH, expected_request=request
    )
    assert accepted.operation == operation
    assert accepted.protocol_version == 1


@pytest.mark.parametrize("version", [0, 2, 99, -1])
def test_unsupported_version_never_downgrades(version: int) -> None:
    _, session, request, data = make_case()
    data["protocol_version"] = version
    with pytest.raises(ProbeValidationError) as caught:
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    assert caught.value.code == ProbeErrorCode.UNSUPPORTED_PROTOCOL


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_version", True),
        ("protocol_version", "1"),
        ("protocol_version", 1.0),
        ("operation", "EXECUTE_SHELL"),
        ("operation", "heartbeat"),
        ("probe_session_id", "real-looking-serial"),
        ("probe_session_id", ""),
        ("probe_session_id", "11111111-1111-1111-1111-111111111111"),
        ("device_epoch", True),
        ("device_epoch", -1),
        ("device_epoch", 7.0),
        ("device_epoch", "7"),
        ("sequence_number", True),
        ("sequence_number", -1),
        ("sequence_number", MAX_SEQUENCE_NUMBER + 1),
        ("sequence_number", 0.0),
        ("nonce", "short"),
        ("nonce", "a" * 44),
        ("nonce", "a" * 42 + "\n"),
        ("status", "PASS"),
        ("status", "FAIL"),
        ("status", "VERIFIED_GENUINE"),
        ("binding", None),
        ("issued_at", "2026-10-06T12:00:00"),
        ("issued_at", "2026-10-06T14:00:00+02:00"),
        ("issued_at", 1791288000),
        ("probe_build", {"artifact_sha256": "fake-serial"}),
    ],
)
def test_reject_invalid_fields(field: str, value: Any) -> None:
    _, session, request, data = make_case()
    data[field] = value
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize("field", ["scan_id", "attempt_id", "challenge_id", "diagnostic_id"])
@pytest.mark.parametrize("malformed", [False, "", "../private", "\n", "x" * 100])
def test_invalid_binding_identifiers(field: str, malformed: Any) -> None:
    _, session, request, data = make_case()
    data["binding"][field] = malformed
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize("field", ["scan_id", "attempt_id", "challenge_id", "diagnostic_id"])
def test_valid_but_wrong_binding_rejected(field: str) -> None:
    _, session, request, data = make_case()
    data["binding"][field] = "different_test" if field == "diagnostic_id" else str(uuid4())
    with pytest.raises(ProbeValidationError) as caught:
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    assert caught.value.code == ProbeErrorCode.BINDING_MISMATCH


@pytest.mark.parametrize(
    "field",
    ["protocol_version", "probe_session_id", "binding", "nonce", "probe_build", "observations"],
)
def test_missing_required_attribution(field: str) -> None:
    _, session, request, data = make_case()
    del data[field]
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize(
    "field",
    ["command", "script", "url", "path", "intent", "metadata", "device_id", "serial", "confidence"],
)
def test_extra_fields_rejected(field: str) -> None:
    _, session, request, data = make_case()
    data[field] = "FORBIDDEN_PRIVATE_MARKER"
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_duplicate_and_rollback_sequences_rejected() -> None:
    _, session, request, data = make_case()
    session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    with pytest.raises(ProbeValidationError, match="REPLAY"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    next_request = session.create_request(
        request.operation, binding=request.binding, current_device_epoch=EPOCH
    )
    session.accept_response(
        wire(response(next_request)), current_device_epoch=EPOCH, expected_request=next_request
    )
    with pytest.raises(ProbeValidationError, match="REPLAY"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_old_nonce_cannot_be_relabelled_with_current_sequence() -> None:
    _, session, request, data = make_case()
    session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    next_request = session.create_request(
        request.operation, binding=request.binding, current_device_epoch=EPOCH
    )
    data["sequence_number"] = next_request.sequence_number
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_random_generator_collision_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _, session, request, data = make_case()
    session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    monkeypatch.setattr("vector_agent.probe.protocol.generate_nonce", lambda: request.nonce)
    with pytest.raises(ProbeValidationError, match="REPLAY"):
        session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)


def test_rejected_response_does_not_consume_good_pending_request() -> None:
    _, session, request, data = make_case()
    wrong = dict(data, probe_session_id=str(uuid4()))
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(wrong), current_device_epoch=EPOCH, expected_request=request)
    assert (
        session.accept_response(
            wire(data), current_device_epoch=EPOCH, expected_request=request
        ).status
        == "OK"
    )


def test_wrong_session_cannot_substitute() -> None:
    _, _, request, data = make_case()
    _, other_session, _, _ = make_case()
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        other_session.accept_response(
            wire(data), current_device_epoch=EPOCH, expected_request=request
        )


@pytest.mark.parametrize("epoch", [EPOCH + 1, True, "7", -1])
def test_live_epoch_change_invalidates_session(epoch: Any) -> None:
    _, session, request, data = make_case()
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        session.accept_response(wire(data), current_device_epoch=epoch, expected_request=request)
    with pytest.raises(ProbeValidationError, match="SESSION_CLOSED"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_peer_epoch_change_rejected() -> None:
    _, session, request, data = make_case()
    data["device_epoch"] += 1
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize("offset", [-60, CLOCK_SKEW_SECONDS + 1])
def test_unreasonable_response_timestamp(offset: int) -> None:
    clock, session, request, data = make_case()
    data["issued_at"] = (clock.now + timedelta(seconds=offset)).isoformat()
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_expiry_and_monotonic_deadline() -> None:
    clock, session, request, data = make_case()
    clock.advance(MESSAGE_TTL_SECONDS)
    with pytest.raises(ProbeValidationError, match="EXPIRED"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    clock, session, request, data = make_case()
    clock.mono += MESSAGE_TTL_SECONDS
    with pytest.raises(ProbeValidationError, match="EXPIRED"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_response_cannot_extend_request_expiry() -> None:
    clock, session, request, data = make_case()
    data["expires_at"] = (clock.now + timedelta(seconds=MESSAGE_TTL_SECONDS + 1)).isoformat()
    with pytest.raises(ProbeValidationError, match="INVALID_TIME"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize("wall", [True, False])
def test_clock_rollback_closes_session(wall: bool) -> None:
    clock, session, request, data = make_case()
    if wall:
        clock.now -= timedelta(seconds=1)
    else:
        clock.mono -= 1
    with pytest.raises(ProbeValidationError, match="INVALID_TIME"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_session_age_limit() -> None:
    clock, session, request, _ = make_case()
    session.abandon_request(request)
    clock.advance(SESSION_MAX_DURATION_SECONDS)
    with pytest.raises(ProbeValidationError, match="EXPIRED"):
        session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)


def test_single_pending_and_abandoned_requests() -> None:
    _, session, request, data = make_case()
    with pytest.raises(ProbeValidationError, match="REQUEST_PENDING"):
        session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
    session.abandon_request(request)
    next_request = session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
    assert next_request.sequence_number > request.sequence_number
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_replay_history_is_bounded_without_evicting() -> None:
    _, session, request, _ = make_case(ProbeOperation.HEARTBEAT)
    session.abandon_request(request)
    for _ in range(MAX_SESSION_REQUESTS - 1):
        request = session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
        session.abandon_request(request)
    with pytest.raises(ProbeValidationError, match="BOUNDS_VIOLATION"):
        session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)


def test_capability_response_is_typed_and_operation_scoped() -> None:
    _, session, request, data = make_case(ProbeOperation.GET_CAPABILITIES)
    data["capabilities"] = [
        {"capability_id": "CONTROL_CHANNEL", "available": True, "operations": ["HEARTBEAT"]}
    ]
    assert (
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
        .capabilities[0]
        .available
    )
    data["operation"] = "HEARTBEAT"
    with pytest.raises(ProbeValidationError):
        parse_response(wire(data))


def test_closed_session_stays_closed() -> None:
    _, session, request, data = make_case()
    session.close()
    session.close()
    with pytest.raises(ProbeValidationError, match="SESSION_CLOSED"):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_nonce_only_in_wire_not_repr() -> None:
    _, _, request, data = make_case()
    assert request.nonce not in repr(request)
    assert request.nonce not in repr(parse_response(wire(data)))
    assert json.loads(request.model_dump_json())["nonce"] == request.nonce


def test_max_signed_sequence_schema_boundary() -> None:
    _, _, request, data = make_case()
    data["sequence_number"] = MAX_SEQUENCE_NUMBER
    assert parse_response(wire(data)).sequence_number == MAX_SEQUENCE_NUMBER


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
def test_already_expired_response_and_reversed_window(field: str) -> None:
    clock, session, request, data = make_case()
    if field == "expires_at":
        data[field] = clock.now.isoformat()
    else:
        data["issued_at"] = (clock.now - timedelta(seconds=2)).isoformat()
        data["expires_at"] = (clock.now - timedelta(seconds=1)).isoformat()
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


@pytest.mark.parametrize("invalid_epoch", [True, -1, "7", MAX_SEQUENCE_NUMBER + 1])
def test_invalid_desktop_session_epoch(invalid_epoch: Any) -> None:
    from vector_agent.probe.protocol import ProbeProtocolSession

    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=invalid_epoch)


def test_raw_device_identifier_cannot_become_session_identity() -> None:
    from vector_agent.probe.protocol import ProbeProtocolSession

    with pytest.raises(ProbeValidationError) as caught:
        ProbeProtocolSession(device_id="FABRICATED_RAW_SERIAL", device_epoch=7)
    assert "FABRICATED_RAW_SERIAL" not in str(caught.value)


def test_exactly_one_concurrent_response_is_accepted() -> None:
    from concurrent.futures import ThreadPoolExecutor

    _, session, request, data = make_case()

    def accept() -> bool:
        try:
            session.accept_response(
                wire(data), current_device_epoch=EPOCH, expected_request=request
            )
        except ProbeValidationError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: accept(), range(2))) == [False, True]


@pytest.mark.parametrize("path", ["operations", "capability_id", "available", "duplicate"])
def test_invalid_capability_descriptor(path: str) -> None:
    _, session, request, data = make_case(ProbeOperation.GET_CAPABILITIES)
    capability: dict[str, Any] = {
        "capability_id": "CONTROL_CHANNEL",
        "available": True,
        "operations": ["HEARTBEAT"],
    }
    data["capabilities"] = [capability]
    if path == "operations":
        capability[path] = ["EXECUTE_SHELL"]
    elif path == "capability_id":
        capability[path] = "GENUINE_BATTERY"
    elif path == "available":
        capability[path] = 1
    else:
        data["capabilities"] *= 2
    with pytest.raises(ProbeValidationError):
        session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_simultaneous_issuance_allows_only_one_outstanding_request() -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    _, session, request, _ = make_case()
    session.abandon_request(request)
    barrier = threading.Barrier(2, timeout=3)

    def issue() -> str:
        barrier.wait()
        try:
            session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
        except ProbeValidationError as exc:
            return exc.code.value
        return "ISSUED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: issue(), range(2))) == ["ISSUED", "REQUEST_PENDING"]


def test_one_session_success_does_not_consume_another_sessions_pending_request() -> None:
    _, first, first_request, first_data = make_case()
    _, second, second_request, second_data = make_case()
    first.accept_response(
        wire(first_data), current_device_epoch=EPOCH, expected_request=first_request
    )
    second.require_pending(second_request, current_device_epoch=EPOCH)
    assert (
        second.accept_response(
            wire(second_data), current_device_epoch=EPOCH, expected_request=second_request
        ).probe_session_id
        == second.probe_session_id
    )


@pytest.mark.parametrize("clock_mode", ["wall", "monotonic", "both"])
def test_expired_pending_replacement_rejects_late_reply(clock_mode: str) -> None:
    clock, session, old, old_data = make_case()
    if clock_mode in ("wall", "both"):
        clock.now += timedelta(seconds=MESSAGE_TTL_SECONDS + 1)
    if clock_mode in ("monotonic", "both"):
        clock.mono += MESSAGE_TTL_SECONDS + 1
    new = session.create_request(old.operation, current_device_epoch=EPOCH, binding=old.binding)
    assert new.sequence_number == old.sequence_number + 1
    assert new.nonce != old.nonce
    assert session._pending_mono == clock.mono
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        session.accept_response(wire(old_data), current_device_epoch=EPOCH, expected_request=old)
    assert session._pending == new
    assert (
        session.accept_response(
            wire(response(new)), current_device_epoch=EPOCH, expected_request=new
        ).sequence_number
        == new.sequence_number
    )
    assert session._pending is None
    assert session._pending_mono is None


def test_expiry_and_stale_cleanup_preserve_exact_dispatch_ownership() -> None:
    clock, session, old, _ = make_case()
    session.claim_dispatch(old, current_device_epoch=EPOCH)
    clock.advance(MESSAGE_TTL_SECONDS + 1)
    new = session.create_request(old.operation, current_device_epoch=EPOCH, binding=old.binding)
    assert session._dispatch_request == old
    with pytest.raises(ProbeValidationError, match="REQUEST_PENDING"):
        session.claim_dispatch(new, current_device_epoch=EPOCH)
    assert session.abandon_request(old) is False
    session.finish_dispatch(old)
    session.claim_dispatch(new, current_device_epoch=EPOCH)
    session.finish_dispatch(old)
    assert session.abandon_request(old) is False
    assert session._dispatch_request == new
    assert session._pending == new
    assert session._pending_mono == clock.mono
    session.accept_response(wire(response(new)), current_device_epoch=EPOCH, expected_request=new)
    session.finish_dispatch(new)
    assert session._pending is None
    assert session._pending_mono is None
    assert session._dispatch_request is None


def test_live_pending_request_still_blocks_and_preserves_timestamp() -> None:
    clock, session, request, data = make_case()
    started = session._pending_mono
    clock.advance(MESSAGE_TTL_SECONDS - 1)
    with pytest.raises(ProbeValidationError, match="REQUEST_PENDING"):
        session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
    assert session._pending == request
    assert session._pending_mono == started
    session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)
    assert session._pending_mono is None


@pytest.mark.parametrize("invalid", [None, {}, "FABRICATED_REQUEST"])
def test_abandon_invalid_owner_fails_closed(invalid: Any) -> None:
    _, session, request, data = make_case()
    started = session._pending_mono
    with pytest.raises(ProbeValidationError, match="MALFORMED_MESSAGE"):
        session.abandon_request(invalid)
    assert session._pending == request
    assert session._pending_mono == started
    session.accept_response(wire(data), current_device_epoch=EPOCH, expected_request=request)


def test_abandon_requires_owner_and_reports_exact_removal() -> None:
    _, session, request, _ = make_case()
    started = session._pending_mono
    with pytest.raises(TypeError):
        session.abandon_request()
    assert session._pending == request
    assert session._pending_mono == started
    _, _, foreign, _ = make_case()
    assert session.abandon_request(foreign) is False
    assert session.abandon_request(request) is True
    assert session._pending is None
    assert session._pending_mono is None
    assert session.abandon_request(request) is False


def test_pending_timestamp_initialized_and_cleared_on_close() -> None:
    from tests.probe_helpers import DEVICE_ID, Clock
    from vector_agent.probe.protocol import ProbeProtocolSession

    clock = Clock()
    session = ProbeProtocolSession(
        device_id=DEVICE_ID, device_epoch=EPOCH, clock=clock.wall, monotonic=clock.monotonic
    )
    assert session._pending is None
    assert session._pending_mono is None
    request = session.create_request(ProbeOperation.HEARTBEAT, current_device_epoch=EPOCH)
    session.claim_dispatch(request, current_device_epoch=EPOCH)
    assert session._pending_mono == clock.mono
    session.close()
    session.close()
    session.finish_dispatch(request)
    assert session._pending is None
    assert session._pending_mono is None
    assert session._dispatch_request is None
