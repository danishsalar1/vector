"""Synthetic fixtures exercise production validation, transport and ownership.

No fixture is physical-device qualification.
"""

from __future__ import annotations

import hmac
import json
import socket
import struct
import threading
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.probe_helpers import Clock, wire
from tests.test_phase8b_probe import BOOTSTRAP, MemoryTransport, control_response, lifecycle
from vector_agent.models.device import DiagnosticStatus, EvidenceSourceType, Platform
from vector_agent.models.probe import ProbeChallengeBinding
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_diagnostics import DiagnosticReport, touch_area_percent
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.probe.adb_transport import AdbProbeTransport
from vector_agent.probe.lifecycle import (
    DiagnosticExhaustedError,
    DiagnosticSessionError,
    DiagnosticTransportError,
    DiagnosticUnavailableError,
)
from vector_agent.probe.protocol import ProbeProtocolSession, ProbeValidationError, parse_response
from vector_agent.probe.transport import ProbeTransportStatus as T

# A realistic full-screen run: 1080x2400 display, 1080x2340 app window, 1080x2200 grid.
TESTED, WINDOW, DISPLAY = (1080, 2200), (1080, 2340), (1080, 2400)


def touch_metrics(
    *,
    tested: tuple[int, int] = TESTED,
    window: tuple[int, int] = WINDOW,
    display: tuple[int, int] = DISPLAY,
    cells: int = 24,
    without: tuple[str, ...] = (),
    **overrides: Any,
) -> list[dict[str, Any]]:
    """Geometry-consistent touch evidence; overrides replace values, without drops metrics."""
    values: dict[str, tuple[Any, str]] = {
        "touch_cells": (cells, "count"),
        "cell_coverage_percent": ((200 * cells + 24) // 48, "percent"),
        "max_contacts": (2, "count"),
        "tested_width": (tested[0], "pixels"),
        "tested_height": (tested[1], "pixels"),
        "window_width": (window[0], "pixels"),
        "window_height": (window[1], "pixels"),
        "display_width": (display[0], "pixels"),
        "display_height": (display[1], "pixels"),
        "tested_window_area_percent": (touch_area_percent(*tested, *window), "percent"),
        "tested_display_area_percent": (touch_area_percent(*tested, *display), "percent"),
        "layout_generation": (1, "count"),
    }
    for name, value in overrides.items():
        values[name] = (value, values[name][1])
    return [metric(name, v, unit) for name, (v, unit) in values.items() if name not in without]


def report(diagnostic: str = "touch", **changes: Any) -> dict[str, Any]:
    metrics = touch_metrics() if diagnostic == "touch" else []
    result: dict[str, Any] = {
        "schema_version": 1,
        "diagnostic_id": diagnostic,
        "state": "COMPLETED",
        "outcome": "PASS",
        "reason": "TOUCH_COVERED",
        "elapsed_ms": 1500,
        "metrics": metrics,
    }
    result.update(changes)
    return result


def metric(name: str, value: Any, unit: str) -> dict[str, Any]:
    return {"name": name, "value": value, "unit": unit}


def parse(value: dict[str, Any]) -> DiagnosticReport:
    return DiagnosticReport.model_validate_json(json.dumps(value), strict=True)


@pytest.mark.parametrize(
    "id",
    [
        "battery",
        "system",
        "display",
        "speaker",
        "microphone",
        "vibration",
        "sensor_0",
        "connectivity",
        "audio_routes",
        "pixels",
    ],
)
def test_telemetry_or_human_confirmation_cannot_be_promoted_to_pass(id: str) -> None:
    with pytest.raises(ValidationError):
        parse(report(id, metrics=[]))


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "RUNNING"},
        {"state": "CANCELLED"},
        {"state": "EXPIRED"},
        {"elapsed_ms": 60001},
        {"metrics": []},
        {"reason": "USER_REPORTED"},
        {"authenticity": "VERIFIED_GENUINE"},
        {"schema_version": 2},
        {"outcome": "VERIFIED_GENUINE"},
        {"metrics": [metric("touch_cells", 23, "count"), metric("max_contacts", 2, "count")]},
        {"metrics": [metric("touch_cells", 24, "percent"), metric("max_contacts", 2, "count")]},
        {"metrics": [metric("touch_cells", True, "count"), metric("max_contacts", 2, "count")]},
        {"metrics": [metric("touch_cells", 24, "count"), metric("touch_cells", 24, "count")]},
        {"metrics": [metric("touch_cells", 25, "count"), metric("max_contacts", 2, "count")]},
        {"metrics": [metric("touch_cells", 24, "count"), metric("max_contacts", 0, "count")]},
    ],
)
def test_partial_conflicting_unknown_or_malformed_results_are_rejected(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        parse(report(**changes))


def test_scoped_camera_and_storage_predicates_require_all_evidence() -> None:
    cases = [
        report(
            "camera_0",
            reason="CAPTURE_MATCH",
            metrics=[
                metric("capture_completed", 1, "boolean"),
                metric("frame_metadata_match", 1, "boolean"),
                metric("frame_width", 640, "pixels"),
                metric("frame_height", 480, "pixels"),
                metric("frame_bytes", 460800, "bytes"),
                metric("luma_mean", 117.25, "unitless"),
                metric("luma_variance", 811.5, "unitless"),
            ],
        ),
        report(
            "storage",
            reason="READBACK_MATCH",
            metrics=[
                metric("bytes_written", 65536, "bytes"),
                metric("bytes_read", 65536, "bytes"),
                metric("readback_match", 1, "boolean"),
            ],
        ),
    ]
    for case in cases:
        assert parse(case).outcome == "PASS"
        for index in range(len(case["metrics"])):
            broken = {**case, "metrics": case["metrics"][:index] + case["metrics"][index + 1 :]}
            with pytest.raises(ValidationError):
                parse(broken)


@pytest.mark.parametrize(
    "outcome,reason",
    [
        ("UNSUPPORTED", "HARDWARE_ABSENT"),
        ("RESTRICTED", "PERMISSION_DENIED"),
        ("ERROR", "INITIALIZATION_ERROR"),
        ("INCONCLUSIVE", "CAMERA_BUSY"),
    ],
)
def test_execution_and_availability_outcomes_are_not_hardware_failure(
    outcome: str, reason: str
) -> None:
    assert parse(report("camera_0", outcome=outcome, reason=reason, metrics=[])).outcome == outcome


def v2_lifecycle() -> tuple[Any, Any, list[MemoryTransport]]:
    connection, manager, _, transports = lifecycle()
    connection._artifact = connection._artifact.model_copy(
        update={"application_version": "0.2.0", "version_code": 2, "protocol_version": 2}
    )
    original = connection._factory

    def factory(**kwargs: Any) -> MemoryTransport:
        t = original(**kwargs)

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            data["observations"] = []
            data["diagnostic_capabilities"] = []
            data["diagnostic"] = None
            if data["operation"] == "HELLO":
                data["hello"].update(
                    application_version="0.2.0",
                    version_code=2,
                    protocol_versions=[2],
                    supported_operations=list(O),
                )
            elif data["operation"] == "GET_CAPABILITIES":
                data["diagnostic_capabilities"] = [
                    {
                        "diagnostic_id": "touch",
                        "available": True,
                        "interactive": True,
                        "sensor_type": None,
                    }
                ]
            elif data["binding"]:
                data["diagnostic"] = report(
                    state="RUNNING",
                    outcome="INCONCLUSIVE",
                    reason="COLLECTING",
                    elapsed_ms=0,
                    metrics=[],
                )
            return data

        t.mutate = mutate
        return t

    connection._factory = factory
    assert connection.connect().transport_connected
    return connection, manager, transports


def terminal(transport: MemoryTransport, payload: dict[str, Any]) -> None:
    previous = transport.mutate

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        data = previous(data)
        if data["binding"]:
            data["diagnostic"] = payload
        return data

    transport.mutate = mutate


def test_start_poll_interpretation_and_heartbeat_remain_connected() -> None:
    c, _, transports = v2_lifecycle()
    assert c.diagnostic_capabilities()[0].diagnostic_id == "touch"
    assert c.diagnostic(O.START_CHALLENGE, "touch").status == DiagnosticStatus.RUNNING
    assert c.heartbeat().transport_connected
    terminal(transports[0], report())
    result = c.diagnostic(O.FETCH_OBSERVATIONS)
    assert result.status == DiagnosticStatus.PASS
    assert len(result.evidence) == 12
    assert all(
        e.source_type == EvidenceSourceType.VECTOR_PROBE
        and e.confidence is None
        and e.reliability is None
        for e in result.evidence
    )
    assert all(
        e.metadata["authenticity"] == "UNKNOWN" and e.metadata["qualification"] == "CODE_TESTED"
        for e in result.evidence
    )
    assert c.diagnostic(O.FETCH_OBSERVATIONS).status == DiagnosticStatus.PASS
    c.stop()


def test_repeated_start_and_poll_retarget_are_rejected_without_wire_io() -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    before = len(ts[0].operations)
    for operation, name in [(O.START_CHALLENGE, "touch"), (O.FETCH_OBSERVATIONS, "camera_0")]:
        with pytest.raises(ValueError):
            c.diagnostic(operation, name)
    assert len(ts[0].operations) == before
    c.stop()


@pytest.mark.parametrize("state,reason", [("CANCELLED", "CANCELLED"), ("EXPIRED", "TIMEOUT")])
def test_cancel_or_expiry_preserves_partial_without_pass(state: str, reason: str) -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    terminal(
        ts[0],
        report(
            state=state,
            outcome="INCONCLUSIVE",
            reason=reason,
            metrics=[metric("touch_cells", 5, "count")],
        ),
    )
    result = c.diagnostic(O.CANCEL_CHALLENGE if state == "CANCELLED" else O.FETCH_OBSERVATIONS)
    assert result.status == DiagnosticStatus.INCONCLUSIVE
    assert result.evidence[0].normalized_value == 5
    c.stop()


def test_stale_terminal_mutation_drops_connection() -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    terminal(ts[0], report())
    c.diagnostic(O.FETCH_OBSERVATIONS)
    terminal(ts[0], report(elapsed_ms=1600))
    with pytest.raises(ValueError):
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert not c.state().transport_connected


def test_epoch_change_during_response_blocks_evidence_and_does_not_affect_second_device() -> None:
    c, manager, ts = v2_lifecycle()
    other, _, _ = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    other.diagnostic(O.START_CHALLENGE, "touch")
    old = ts[0].mutate

    def change(data: dict[str, Any]) -> dict[str, Any]:
        manager.mark_platform_offline(Platform.ANDROID)
        return old(data)

    ts[0].mutate = change
    with pytest.raises(ValueError):
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert other.heartbeat().transport_connected
    c.stop()
    other.stop()


@pytest.mark.parametrize(
    "status",
    [T.UNAVAILABLE, T.TIMEOUT, T.AUTHENTICATION_FAILURE, T.BOUNDS_VIOLATION, T.CLOSED, T.CANCELLED],
)
def test_transport_failure_never_returns_hardware_result(status: T) -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    ts[0].outcome = status
    with pytest.raises(ValueError):
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert not c.state().transport_connected


def make_request() -> tuple[ProbeProtocolSession, Any, dict[str, Any]]:
    clock = Clock()
    s = ProbeProtocolSession(
        device_id="android-0123456789ab",
        device_epoch=1,
        protocol_version=2,
        clock=clock.wall,
        monotonic=clock.monotonic,
    )
    b = ProbeChallengeBinding(
        scan_id=str(uuid4()),
        diagnostic_id="touch",
        attempt_id=str(uuid4()),
        challenge_id=str(uuid4()),
        collection_not_before=clock.now,
    )
    r = s.create_request(O.FETCH_OBSERVATIONS, current_device_epoch=1, binding=b)
    data = control_response(r)
    data.update(observations=[], diagnostic=report(), diagnostic_capabilities=[])
    return s, r, data


@pytest.mark.parametrize(
    "mutation", ["mac", "oversize", "malformed", "duplicate", "unknown", "binding", "none"]
)
def test_v2_uses_real_hmac_socket_and_strict_ingestion(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    s, request, data = make_request()
    client, peer = socket.socketpair()
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    bridge = MagicMock()
    bridge.forward.return_value = 12345
    transport = AdbProbeTransport(
        session=s, current_device_epoch=lambda: 1, bridge=bridge, bootstrap=BOOTSTRAP
    )
    if mutation == "unknown":
        data["diagnostic"]["private_serial"] = "FORBIDDEN"
    if mutation == "binding":
        data["binding"]["challenge_id"] = str(uuid4())
    raw = wire(data)
    if mutation == "malformed":
        raw = b"{"
    if mutation == "duplicate":
        raw = raw[:-1] + b',"status":"OK"}'
    signature = hmac.digest(BOOTSTRAP.key, b"response\0" + raw, "sha256")
    if mutation == "mac":
        signature = b"x" * 32
    peer.sendall(struct.pack("!I", 65537 if mutation == "oversize" else len(raw)) + signature + raw)
    try:
        result = transport.request(request, timeout_seconds=1, cancellation=threading.Event())
        assert (result.status == T.RECEIVED) == (mutation == "none")
        if mutation == "none":
            assert result.response is not None and result.response.diagnostic is not None
            assert result.response.diagnostic.outcome == "PASS"
    finally:
        transport.close()
        peer.close()
    bridge.remove_forward.assert_called_once_with(12345)


def test_protocol_version_and_replay_are_not_silently_downgraded() -> None:
    s, request, data = make_request()
    with pytest.raises(ProbeValidationError):
        parse_response(wire(data))
    assert (
        s.accept_response(wire(data), current_device_epoch=1, expected_request=request).diagnostic
        is not None
    )
    with pytest.raises(ProbeValidationError):
        s.accept_response(wire(data), current_device_epoch=1, expected_request=request)


def test_missing_battery_values_remain_missing() -> None:
    parsed = parse(
        report(
            "battery",
            outcome="INCONCLUSIVE",
            reason="TELEMETRY_ONLY",
            metrics=[metric("charge_counter", None, "uAh")],
        )
    )
    assert parsed.metrics[0].value is None


def test_storage_fail_acceptance() -> None:
    parsed = parse(
        report(
            "storage",
            outcome="FAIL",
            reason="READBACK_MISMATCH",
            metrics=[
                metric("bytes_written", 65536, "bytes"),
                metric("bytes_read", 65536, "bytes"),
                metric("readback_match", 0, "boolean"),
            ],
        )
    )
    assert parsed.outcome == "FAIL"
    assert parsed.reason == "READBACK_MISMATCH"


@pytest.mark.parametrize(
    "outcome,reason",
    [
        ("UNSUPPORTED", "READBACK_MATCH"),
        ("RESTRICTED", "TOUCH_COVERED"),
        ("ERROR", "CAPTURE_MATCH"),
        ("PASS", "PERMISSION_DENIED"),
        ("FAIL", "READBACK_MATCH"),
    ],
)
def test_contradictory_outcome_reason_rejected(outcome: str, reason: str) -> None:
    with pytest.raises(ValidationError, match="invalid for outcome"):
        parse(report("storage", outcome=outcome, reason=reason, metrics=[]))


def test_human_report_cannot_claim_pass_even_with_metrics() -> None:
    with pytest.raises(ValidationError):
        parse(
            report(
                "pixels",
                outcome="PASS",
                reason="TOUCH_COVERED",
                metrics=[
                    metric("patterns_viewed", 5, "count"),
                    metric("user_report", 1, "boolean"),
                ],
            )
        )


def test_start_cancel_immediate_start_unavailable_preserves_session() -> None:
    from vector_agent.probe.lifecycle import DiagnosticUnavailableError

    c, _, transports = v2_lifecycle()
    t = transports[0]
    base_mutate = t.mutate
    c.diagnostic(O.START_CHALLENGE, "touch")
    terminal(
        t,
        report(
            state="CANCELLED",
            outcome="INCONCLUSIVE",
            reason="CANCELLED",
            elapsed_ms=50,
            metrics=[],
        ),
    )
    c.diagnostic(O.CANCEL_CHALLENGE)
    assert not c._diagnostic_running

    def busy_mutate(data: dict[str, Any]) -> dict[str, Any]:
        data = base_mutate(data)
        if data.get("operation") == "START_CHALLENGE":
            data["status"] = "UNAVAILABLE"
            data["diagnostic"] = None
        return data

    t.mutate = busy_mutate
    with pytest.raises(DiagnosticUnavailableError):
        c.diagnostic(O.START_CHALLENGE, "touch")

    assert c.state().transport_connected
    t.mutate = base_mutate
    res = c.diagnostic(O.START_CHALLENGE, "touch")
    assert res.status == DiagnosticStatus.RUNNING
    c.stop()


# Literal cross-language vector, pinned identically in DiagnosticProtocolTest.java: the
# requests are this production session's bytes; the response is Java ControlProtocol's.
PINNED_HELLO = b'{"protocol_version":2,"probe_session_id":"5e55a000-0000-4000-8000-0000000000aa","device_epoch":3,"binding":null,"nonce":"pinned0000000000000000000000000000000000001","sequence_number":0,"issued_at":"2026-10-09T00:00:00Z","expires_at":"2026-10-09T00:00:30Z","operation":"HELLO"}'
PINNED_START = b'{"protocol_version":2,"probe_session_id":"5e55a000-0000-4000-8000-0000000000aa","device_epoch":3,"binding":{"scan_id":"5e55a000-0000-4000-8000-0000000000b1","diagnostic_id":"storage","attempt_id":"5e55a000-0000-4000-8000-0000000000b2","challenge_id":"5e55a000-0000-4000-8000-0000000000b3","collection_not_before":"2026-10-09T00:00:00Z"},"nonce":"pinned0000000000000000000000000000000000002","sequence_number":1,"issued_at":"2026-10-09T00:00:00Z","expires_at":"2026-10-09T00:00:30Z","operation":"START_CHALLENGE"}'
PINNED_START_RESPONSE = b'{"protocol_version":2,"probe_session_id":"5e55a000-0000-4000-8000-0000000000aa","device_epoch":3,"binding":{"scan_id":"5e55a000-0000-4000-8000-0000000000b1","diagnostic_id":"storage","attempt_id":"5e55a000-0000-4000-8000-0000000000b2","challenge_id":"5e55a000-0000-4000-8000-0000000000b3","collection_not_before":"2026-10-09T00:00:00Z"},"nonce":"pinned0000000000000000000000000000000000002","sequence_number":1,"issued_at":"2026-10-09T00:00:00Z","expires_at":"2026-10-09T00:00:30Z","operation":"START_CHALLENGE","status":"OK","diagnostic_capabilities":[],"diagnostic":{"schema_version":1,"diagnostic_id":"storage","state":"RUNNING","outcome":"INCONCLUSIVE","reason":"COLLECTING","elapsed_ms":100,"metrics":[]},"probe_build":null,"observations":[],"capabilities":[]}'


def test_pinned_v2_golden_vector() -> None:
    from datetime import UTC, datetime
    from unittest.mock import patch
    from uuid import UUID

    from vector_agent.probe import protocol

    clock = Clock()
    clock.now = datetime(2026, 10, 9, tzinfo=UTC)
    nonces = iter(range(1, 10))
    with (
        patch.object(protocol, "uuid4", lambda: UUID("5e55a000-0000-4000-8000-0000000000aa")),
        patch.object(protocol, "generate_nonce", lambda: f"pinned{next(nonces):037d}"),
    ):
        session = ProbeProtocolSession(
            device_id="android-0123456789ab",
            device_epoch=3,
            protocol_version=2,
            clock=clock.wall,
            monotonic=clock.monotonic,
        )
        hello = session.create_request(O.HELLO, current_device_epoch=3)
        assert hello.model_dump_json().encode("utf-8") == PINNED_HELLO
        session.abandon_request(hello)
        binding = ProbeChallengeBinding(
            scan_id="5e55a000-0000-4000-8000-0000000000b1",
            diagnostic_id="storage",
            attempt_id="5e55a000-0000-4000-8000-0000000000b2",
            challenge_id="5e55a000-0000-4000-8000-0000000000b3",
            collection_not_before=clock.now,
        )
        start = session.create_request(O.START_CHALLENGE, current_device_epoch=3, binding=binding)
    assert start.model_dump_json().encode("utf-8") == PINNED_START
    key = bytes(range(1, 33))
    assert (
        hmac.digest(key, b"request\0" + PINNED_START, "sha256").hex()
        == "ee14950c059cf98edc6488038d9950b1dc2ebefa347ea2a15a6848da642bc149"
    )
    assert (
        hmac.digest(key, b"response\0" + PINNED_START_RESPONSE, "sha256").hex()
        == "334d004eb33fb9e6be039f4e1d868752d052f795a83d76ef98a5aacaac98e72b"
    )
    accepted = session.accept_response(
        PINNED_START_RESPONSE, current_device_epoch=3, expected_request=start
    )
    assert accepted.diagnostic is not None
    assert (accepted.diagnostic.state, accepted.diagnostic.reason) == ("RUNNING", "COLLECTING")
    assert accepted.binding == start.binding


# ==============================================================================
# TG-01: touch PASS requires complete, recomputed, display-relative geometry
# ==============================================================================


def touch_pass(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return report("touch", metrics=metrics)


def test_touch_area_percent_rounds_half_up_in_exact_integers() -> None:
    # Hand-computed literals, independent of the production helper used by fixtures.
    assert touch_area_percent(1080, 2200, 1080, 2340) == 94  # 94.017
    assert touch_area_percent(1080, 2200, 1080, 2400) == 92  # 91.667
    assert touch_area_percent(1, 3, 2, 4) == 38  # 37.5 rounds up, never to even
    assert touch_area_percent(1, 1, 2, 1) == 50
    assert touch_area_percent(200, 200, 1080, 2400) == 2  # 1.543


def test_touch_pass_accepts_complete_consistent_geometry() -> None:
    parsed = parse(touch_pass(touch_metrics()))
    assert parsed.outcome == "PASS" and parsed.reason == "TOUCH_COVERED"


@pytest.mark.parametrize(
    "name",
    [
        "touch_cells",
        "cell_coverage_percent",
        "max_contacts",
        "tested_width",
        "tested_height",
        "window_width",
        "window_height",
        "display_width",
        "display_height",
        "tested_window_area_percent",
        "tested_display_area_percent",
        "layout_generation",
    ],
)
def test_touch_pass_requires_every_geometry_metric(name: str) -> None:
    with pytest.raises(ValidationError):
        parse(touch_pass(touch_metrics(without=(name,))))
    with pytest.raises(ValidationError):
        parse(touch_pass(touch_metrics(**{name: None})))


@pytest.mark.parametrize(
    "name", ["tested_width", "tested_height", "window_width", "window_height", "display_width"]
)
def test_touch_pass_rejects_zero_dimensions(name: str) -> None:
    with pytest.raises(ValidationError):
        parse(touch_pass(touch_metrics(**{name: 0})))


@pytest.mark.parametrize(
    "changes",
    [
        {"tested_window_area_percent": 100},
        {"tested_window_area_percent": 93},
        {"tested_display_area_percent": 100},
        {"tested_display_area_percent": 91},
        {"tested_window_area_percent": 94.0},
    ],
)
def test_touch_pass_rejects_fabricated_or_inconsistent_percentages(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        parse(touch_pass(touch_metrics(**changes)))


@pytest.mark.parametrize("tested", [(199, 2400), (1080, 199)])
def test_touch_pass_rejects_rectangle_below_minimum_size(tested: tuple[int, int]) -> None:
    # Window and display equal the grid, so only the 200 px minimum can reject it.
    case = touch_metrics(tested=tested, window=tested, display=tested)
    assert {m["name"]: m["value"] for m in case}["tested_display_area_percent"] == 100
    with pytest.raises(ValidationError):
        parse(touch_pass(case))


def test_touch_pass_rejects_grid_outside_its_window() -> None:
    # Percentages are consistent and >= 75% of the display; only containment fails.
    case = touch_metrics(tested=(1100, 2000), window=(1080, 2340), display=(1100, 2400))
    values = {m["name"]: m["value"] for m in case}
    assert values["tested_display_area_percent"] == 83
    assert values["tested_window_area_percent"] == 87
    with pytest.raises(ValidationError):
        parse(touch_pass(case))


def test_touch_pass_rejects_window_larger_than_display() -> None:
    case = touch_metrics(tested=(1000, 2000), window=(1100, 2340), display=(1080, 2400))
    assert {m["name"]: m["value"] for m in case}["tested_display_area_percent"] == 77
    with pytest.raises(ValidationError):
        parse(touch_pass(case))


def test_split_screen_window_coverage_does_not_overstate_touchscreen_coverage() -> None:
    # Half-height multi-window: 98% of the app window, 48% of the physical display.
    case = touch_metrics(tested=(1080, 1150), window=(1080, 1170), display=(1080, 2400))
    values = {m["name"]: m["value"] for m in case}
    assert values["tested_window_area_percent"] == 98
    assert values["tested_display_area_percent"] == 48
    with pytest.raises(ValidationError):
        parse(touch_pass(case))
    partial = report("touch", outcome="INCONCLUSIVE", reason="PARTIAL", metrics=case)
    assert parse(partial).reason == "PARTIAL"


@pytest.mark.parametrize(
    "changes",
    [
        {"cells": 23},
        {"cell_coverage_percent": 96},
        {"max_contacts": 0},
        {"layout_generation": 0},
    ],
)
def test_touch_pass_rejects_partial_coverage_or_no_contact(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        parse(touch_pass(touch_metrics(**changes)))


@pytest.mark.parametrize("legacy", ["coverage_percent", "tested_area_percent"])
def test_obsolete_touch_metrics_are_rejected(legacy: str) -> None:
    with pytest.raises(ValidationError):
        parse(touch_pass([*touch_metrics(), metric(legacy, 100, "percent")]))


def test_partial_touch_report_may_lack_unmeasured_geometry() -> None:
    case = touch_metrics(cells=5, window_width=None, window_height=None)
    parsed = parse(report("touch", outcome="INCONCLUSIVE", reason="PARTIAL", metrics=case))
    assert parsed.outcome == "INCONCLUSIVE"


# ==============================================================================
# Camera PASS carries frame content evidence (luma), not only metadata
# ==============================================================================


@pytest.mark.parametrize("missing", ["luma_mean", "luma_variance"])
def test_camera_pass_requires_luma_statistics(missing: str) -> None:
    metrics = [
        metric("capture_completed", 1, "boolean"),
        metric("frame_metadata_match", 1, "boolean"),
        metric("frame_width", 640, "pixels"),
        metric("frame_height", 480, "pixels"),
        metric("frame_bytes", 460800, "bytes"),
        metric("luma_mean", 117.25, "unitless"),
        metric("luma_variance", 811.5, "unitless"),
    ]
    case = report("camera_0", reason="CAPTURE_MATCH", metrics=metrics)
    assert parse(case).outcome == "PASS"
    dropped = [m for m in metrics if m["name"] != missing]
    for broken in (dropped, [*dropped, metric(missing, None, "unitless")]):
        with pytest.raises(ValidationError):
            parse({**case, "metrics": broken})


# ==============================================================================
# TG-05 / TG-11: cancellation reports cleanup truthfully (STOPPING, CLEANUP_ERROR)
# ==============================================================================


@pytest.mark.parametrize(
    "state,outcome,reason",
    [
        ("RUNNING", "INCONCLUSIVE", "STOPPING"),
        ("CANCELLED", "ERROR", "CLEANUP_ERROR"),
        ("EXPIRED", "ERROR", "CLEANUP_ERROR"),
        ("CANCELLED", "INCONCLUSIVE", "CANCELLED"),
        ("EXPIRED", "INCONCLUSIVE", "TIMEOUT"),
    ],
)
def test_interruption_and_cleanup_states_are_accepted(
    state: str, outcome: str, reason: str
) -> None:
    parsed = parse(report("storage", state=state, outcome=outcome, reason=reason, metrics=[]))
    assert (parsed.state, parsed.outcome, parsed.reason) == (state, outcome, reason)


@pytest.mark.parametrize(
    "state,outcome,reason",
    [
        ("COMPLETED", "INCONCLUSIVE", "STOPPING"),
        ("RUNNING", "ERROR", "CLEANUP_ERROR"),
        ("CANCELLED", "ERROR", "EXECUTION_ERROR"),
        ("CANCELLED", "INCONCLUSIVE", "TIMEOUT"),
        ("EXPIRED", "INCONCLUSIVE", "CANCELLED"),
        ("CANCELLED", "INCONCLUSIVE", "STOPPING"),
    ],
)
def test_contradictory_interruption_states_are_rejected(
    state: str, outcome: str, reason: str
) -> None:
    with pytest.raises(ValidationError):
        parse(report("storage", state=state, outcome=outcome, reason=reason, metrics=[]))


def answer(transport: MemoryTransport, **by_operation: tuple[str, Any]) -> None:
    """Script (status, diagnostic) per operation on top of the transport's existing replies."""
    previous = transport.mutate

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        data = previous(data)
        if data["operation"] in by_operation:
            data["status"], data["diagnostic"] = by_operation[data["operation"]]
        return data

    transport.mutate = mutate


def stopping(**changes: Any) -> dict[str, Any]:
    base = report(
        "touch",
        state="RUNNING",
        outcome="INCONCLUSIVE",
        reason="STOPPING",
        elapsed_ms=400,
        metrics=touch_metrics(cells=5),
    )
    return {**base, **changes}


def test_cancel_reports_stopping_then_truthful_cleanup_failure() -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    cleanup_failed = stopping(state="CANCELLED", outcome="ERROR", reason="CLEANUP_ERROR")
    answer(ts[0], CANCEL_CHALLENGE=("OK", stopping()), FETCH_OBSERVATIONS=("OK", cleanup_failed))
    cancelling = c.diagnostic(O.CANCEL_CHALLENGE)
    assert cancelling.status == DiagnosticStatus.RUNNING and c._diagnostic_running
    final = c.diagnostic(O.FETCH_OBSERVATIONS)
    assert final.status == DiagnosticStatus.ERROR
    assert final.summary.startswith("CLEANUP_ERROR")
    assert final.evidence[0].normalized_value == 5
    assert c.state().transport_connected and not c._diagnostic_running
    c.stop()


@pytest.mark.parametrize(
    "follow_up",
    [
        stopping(reason="COLLECTING", elapsed_ms=500),
        stopping(state="CANCELLED", reason="CANCELLED", metrics=touch_metrics(cells=6)),
        stopping(state="COMPLETED", outcome="INCONCLUSIVE", reason="PARTIAL"),
    ],
)
def test_evidence_is_frozen_once_stopping(follow_up: dict[str, Any]) -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    answer(ts[0], CANCEL_CHALLENGE=("OK", stopping()), FETCH_OBSERVATIONS=("OK", follow_up))
    c.diagnostic(O.CANCEL_CHALLENGE)
    with pytest.raises(DiagnosticSessionError) as raised:
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert raised.value.reason == R.INVALID_RESPONSE
    assert not c.state().transport_connected


# ==============================================================================
# TG-04: only START reports budget exhaustion; it ends the session as SESSION_EXPIRED
# ==============================================================================


def test_exhausted_start_ends_session_as_expired() -> None:
    c, _, ts = v2_lifecycle()
    answer(ts[0], START_CHALLENGE=("ERROR", None))
    with pytest.raises(DiagnosticExhaustedError) as raised:
        c.diagnostic(O.START_CHALLENGE, "touch")
    assert isinstance(raised.value, DiagnosticSessionError)
    assert raised.value.reason == R.SESSION_EXPIRED
    state = c.state()
    assert (state.availability, state.reason) == (A.DISCONNECTED, R.SESSION_EXPIRED)
    assert not state.transport_connected


@pytest.mark.parametrize("operation", [O.FETCH_OBSERVATIONS, O.CANCEL_CHALLENGE])
def test_error_status_outside_start_is_a_protocol_violation(operation: O) -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    answer(ts[0], **{operation.value: ("ERROR", None)})
    with pytest.raises(DiagnosticSessionError) as raised:
        c.diagnostic(operation)
    assert not isinstance(raised.value, DiagnosticExhaustedError)
    assert raised.value.reason == R.INVALID_RESPONSE
    state = c.state()
    assert (state.availability, state.reason) == (A.ERROR, R.INVALID_RESPONSE)


# ==============================================================================
# TG-05: one exception contract; exact transport reasons (RG-08 fidelity)
# ==============================================================================


@pytest.mark.parametrize(
    "status,availability,reason",
    [
        (T.TIMEOUT, A.DISCONNECTED, R.TIMEOUT),
        (T.UNAVAILABLE, A.DISCONNECTED, R.DEVICE_UNAVAILABLE),
        (T.CLOSED, A.DISCONNECTED, R.SESSION_EXPIRED),
        (T.CANCELLED, A.DISCONNECTED, R.CANCELLED),
        (T.AUTHENTICATION_FAILURE, A.UNTRUSTED, R.AUTHENTICATION_FAILED),
        (T.UNSUPPORTED_PROTOCOL, A.INSTALLED_INCOMPATIBLE, R.VERSION_NOT_SUPPORTED),
        (T.PROTOCOL_VIOLATION, A.ERROR, R.INVALID_RESPONSE),
        (T.BOUNDS_VIOLATION, A.ERROR, R.INVALID_RESPONSE),
        (T.BUSY, A.ERROR, R.INVALID_RESPONSE),
        (T.ERROR, A.ERROR, R.INVALID_RESPONSE),
    ],
)
def test_diagnostic_transport_failure_keeps_exact_reason(
    status: T, availability: A, reason: R
) -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    ts[0].outcome = status
    with pytest.raises(DiagnosticTransportError) as raised:
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert raised.value.reason == reason
    state = c.state()
    assert (state.availability, state.reason) == (availability, reason)


def test_session_error_reason_is_the_recorded_reason_when_transport_cleanup_fails() -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    ts[0].outcome = T.TIMEOUT

    def broken_cleanup() -> None:
        raise ConnectionError("forward cleanup failed")

    ts[0]._cleanup = broken_cleanup  # type: ignore[method-assign]
    with pytest.raises(DiagnosticTransportError) as raised:
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert raised.value.reason == R.TOOL_ERROR
    assert (c._state.availability, c._state.reason) == (A.ERROR, R.TOOL_ERROR)


@pytest.mark.parametrize("entry", ["diagnostic", "capabilities"])
def test_owner_change_is_a_typed_session_error_not_connection_error(entry: str) -> None:
    c, manager, ts = v2_lifecycle()
    sent = len(ts[0].operations)
    manager.mark_platform_offline(Platform.ANDROID)
    with pytest.raises(DiagnosticSessionError) as raised:
        if entry == "diagnostic":
            c.diagnostic(O.START_CHALLENGE, "touch")
        else:
            c.diagnostic_capabilities()
    assert raised.value.reason == R.SESSION_CHANGED
    assert len(ts[0].operations) == sent
    assert (c._state.availability, c._state.reason) == (A.DISCONNECTED, R.SESSION_CHANGED)


def test_stopped_connection_keeps_its_recorded_reason() -> None:
    c, _, _ = v2_lifecycle()
    c.stop()
    with pytest.raises(DiagnosticSessionError) as raised:
        c.diagnostic(O.START_CHALLENGE, "touch")
    assert raised.value.reason == R.STOPPED
    assert c._state.reason == R.STOPPED


def test_unavailable_fetch_is_retryable_and_keeps_session_and_binding() -> None:
    c, _, ts = v2_lifecycle()
    c.diagnostic(O.START_CHALLENGE, "touch")
    binding = c._diagnostic_binding
    answer(ts[0], FETCH_OBSERVATIONS=("UNAVAILABLE", None))
    with pytest.raises(DiagnosticUnavailableError):
        c.diagnostic(O.FETCH_OBSERVATIONS)
    assert not issubclass(DiagnosticUnavailableError, ValueError)
    assert c.state().transport_connected and c._diagnostic_binding == binding
    c.stop()


def test_caller_misuse_is_plain_value_error_without_wire_io() -> None:
    c, _, ts = v2_lifecycle()
    sent = len(ts[0].operations)
    calls = (
        lambda: c.diagnostic(O.HEARTBEAT),
        lambda: c.diagnostic(O.FETCH_OBSERVATIONS),
        lambda: c.diagnostic(O.START_CHALLENGE, "camera_9"),
    )
    for call in calls:
        with pytest.raises(ValueError) as raised:
            call()
        assert not isinstance(raised.value, DiagnosticSessionError)
    assert len(ts[0].operations) == sent and c.state().transport_connected
    c.stop()


# ==============================================================================
# TG-05 / TG-07: missing values are labelled by cause; rejected samples are counted
# ==============================================================================


def evidence_errors(case: dict[str, Any]) -> dict[str, str | None]:
    from vector_agent.probe.diagnostic_evidence import diagnostic_result

    parsed = parse(case)
    binding = ProbeChallengeBinding(
        scan_id=str(uuid4()),
        diagnostic_id=parsed.diagnostic_id,
        attempt_id=str(uuid4()),
        challenge_id=str(uuid4()),
        collection_not_before=Clock().now,
    )
    result = diagnostic_result(
        parsed, device_id="android-0123456789ab", epoch=1, session_id=str(uuid4()), binding=binding
    )
    return {e.source_name: e.error for e in result.evidence}


def test_missing_values_are_labelled_by_cause() -> None:
    no_samples = report(
        "sensor_0",
        outcome="INCONCLUSIVE",
        reason="NO_SAMPLES",
        metrics=[
            metric("sample_count", 0, "count"),
            metric("rejected_samples", 3, "count"),
            metric("axis0_min", None, "m_s2"),
        ],
    )
    assert evidence_errors(no_samples) == {
        "sample_count": None,
        "rejected_samples": None,
        "axis0_min": "NO_SAMPLES_OBSERVED",
    }
    silent_mic = report(
        "microphone",
        outcome="INCONCLUSIVE",
        reason="USER_REPORTED",
        metrics=[
            metric("audio_samples", 0, "count"),
            metric("audio_peak", None, "unitless"),
            metric("audio_rms", None, "unitless"),
            metric("user_report", 0, "boolean"),
        ],
    )
    assert evidence_errors(silent_mic)["audio_rms"] == "NO_SAMPLES_OBSERVED"
    assert evidence_errors(silent_mic)["audio_peak"] == "NO_SAMPLES_OBSERVED"
    cancelled = report(
        "touch",
        state="CANCELLED",
        outcome="INCONCLUSIVE",
        reason="CANCELLED",
        metrics=[metric("window_width", None, "pixels")],
    )
    assert evidence_errors(cancelled) == {"window_width": "INTERRUPTED_BEFORE_MEASUREMENT"}
    running = report(
        "battery",
        state="RUNNING",
        outcome="INCONCLUSIVE",
        reason="COLLECTING",
        metrics=[metric("cycle_count", None, "count")],
    )
    assert evidence_errors(running) == {"cycle_count": "NOT_YET_MEASURED"}
    telemetry = report(
        "battery",
        outcome="INCONCLUSIVE",
        reason="TELEMETRY_ONLY",
        metrics=[metric("cycle_count", None, "count")],
    )
    assert evidence_errors(telemetry) == {"cycle_count": "UNSUPPORTED_MEASUREMENT"}


def test_rejected_samples_is_bounded_sensor_evidence() -> None:
    sensor = report(
        "sensor_0",
        outcome="INCONCLUSIVE",
        reason="SAMPLES_OBSERVED",
        metrics=[metric("sample_count", 2, "count"), metric("rejected_samples", 1, "count")],
    )
    assert parse(sensor).reason == "SAMPLES_OBSERVED"
    for bad in (-1, 1.5):
        with pytest.raises(ValidationError):
            parse({**sensor, "metrics": [metric("rejected_samples", bad, "count")]})
    battery = report(
        "battery",
        outcome="INCONCLUSIVE",
        reason="TELEMETRY_ONLY",
        metrics=[metric("rejected_samples", 1, "count")],
    )
    with pytest.raises(ValidationError):
        parse(battery)


# ==============================================================================
# TG-06: the developer console reports rejections instead of exiting
# ==============================================================================


def console_with(error: Exception) -> tuple[Any, Any]:
    from vector_agent.devices.session import DeviceSessionManager
    from vector_agent.probe.lifecycle import ProbeConnection, ProbeService

    connection = MagicMock(spec=ProbeConnection)
    connection.diagnostic.side_effect = error
    service = MagicMock(spec=ProbeService)
    service.connection.return_value = connection
    return DeviceSessionManager(), service


def test_console_reports_retryable_unavailable_and_keeps_running() -> None:
    from vector_agent.probe.developer import UNAVAILABLE_MESSAGE, run_command

    manager, service = console_with(DiagnosticUnavailableError("busy"))
    selected, text = run_command(
        ["start", "storage"], manager=manager, service=service, selected="android-0123456789ab"
    )
    assert (selected, text) == ("android-0123456789ab", UNAVAILABLE_MESSAGE)
    assert "still connected" in text


@pytest.mark.parametrize(
    "error,shown",
    [
        (DiagnosticExhaustedError(), "SESSION_EXPIRED"),
        (DiagnosticTransportError(R.TIMEOUT, "late"), "TIMEOUT"),
        (DiagnosticSessionError(R.SESSION_CHANGED, "gone"), "SESSION_CHANGED"),
    ],
)
def test_console_names_the_reason_a_session_ended(error: Exception, shown: str) -> None:
    from vector_agent.probe.developer import run_command

    manager, service = console_with(error)
    _, text = run_command(
        ["poll"], manager=manager, service=service, selected="android-0123456789ab"
    )
    assert f"({shown})" in text and "fresh on-device consent" in text


def test_console_rejects_unknown_or_unselected_commands_without_raising() -> None:
    from vector_agent.probe.developer import REJECTED_MESSAGE, run_command

    manager, service = console_with(ValueError())
    unselected = run_command(["poll"], manager=manager, service=service, selected=None)
    unknown = run_command(["shell", "id"], manager=manager, service=service, selected="x")
    assert unselected[1] == REJECTED_MESSAGE and unknown[1] == REJECTED_MESSAGE
    service.connection.return_value.diagnostic.assert_not_called()
