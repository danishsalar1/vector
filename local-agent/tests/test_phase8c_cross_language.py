"""Permanent Java<->Python Probe v2 contract (tests/fixtures/cross_language/contract.json).

Every frame was produced by production code: requests by the Python ProbeProtocolSession,
responses by the real Android DiagnosticController, collectors and ControlProtocol (Robolectric).
These tests replay the Java bytes through the REAL ProbeConnection, AdbProbeTransport (length
framing and direction-separated HMAC), strict decoder, session pairing, schemas and evidence
mapping, while the socket peer byte-compares every request Python sends. Fixtures are never
written by a test run; see tests/cross_language_contract.py for the explicit update operation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from pydantic import ValidationError

from tests.cross_language_contract import (
    REQUESTS_PATH,
    RESPONSES_PATH,
    Frame,
    contract,
    frames,
    generate_requests,
    replay,
    scenario,
)
from vector_agent.models.device import DiagnosticStatus, EvidenceSourceType, Platform
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_diagnostics import (
    VALID_OUTCOME_REASONS,
    DiagnosticCapability,
    DiagnosticReport,
)
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.probe.lifecycle import DiagnosticSessionError, DiagnosticUnavailableError

SCENARIOS = [item["name"] for item in contract()["scenarios"]]


def java(name: str, index: int) -> Frame:
    return frames(RESPONSES_PATH)[name][index]


def report_of(frame: Frame) -> dict[str, Any]:
    diagnostic: dict[str, Any] = frame.json()["diagnostic"]
    return diagnostic


def run_contract(name: str) -> dict[int, tuple[DiagnosticReport | None, Any]]:
    """Replay one scenario through the real lifecycle, asserting every contract expectation."""
    spec = scenario(name)
    outcomes: dict[int, tuple[DiagnosticReport | None, Any]] = {}
    with replay(name) as run:
        state = run.connection.connect()
        assert (state.availability, state.transport_connected) == (A.CONNECTED, True), (
            run.peer.errors
        )
        for index, exchange in enumerate(spec["exchanges"][2:], start=2):
            operation = O(exchange["op"])
            diagnostic_id = exchange.get("diagnostic_id")
            if exchange["status"] == "UNAVAILABLE":
                with pytest.raises(DiagnosticUnavailableError):
                    run.connection.diagnostic(operation, diagnostic_id)
                outcomes[index] = (None, None)
                continue
            result = run.connection.diagnostic(operation, diagnostic_id)
            report = run.connection._diagnostic_last
            assert report is not None
            where = f"{name}#{index} {operation.value}"
            assert [report.state, report.outcome, report.reason] == exchange["report"], where
            expected = (
                DiagnosticStatus.RUNNING
                if report.state == "RUNNING"
                else DiagnosticStatus(report.outcome)
            )
            assert result.status == expected, where
            values = {m.name: m.value for m in report.metrics}
            for metric, value in exchange.get("metrics", {}).items():
                assert values.get(metric) == value, f"{where} {metric}"
            for evidence in result.evidence:
                assert evidence.metadata["authenticity"] == "UNKNOWN"
                assert evidence.metadata["qualification"] == "CODE_TESTED"
                assert evidence.confidence is None and evidence.reliability is None
                assert evidence.source_type == (
                    EvidenceSourceType.USER_ASSISTED
                    if evidence.source_name == "user_report"
                    else EvidenceSourceType.VECTOR_PROBE
                )
            outcomes[index] = (report, result)
        assert run.peer.errors == []
        assert len(run.peer.received) == len(spec["exchanges"])
        assert run.connection.state().transport_connected
    return outcomes


# ==============================================================================
# Fixture integrity: both sides pinned, reproducible, authentic, mutually echoing
# ==============================================================================


def test_committed_requests_are_reproduced_by_the_production_python_session() -> None:
    assert generate_requests() == frames(REQUESTS_PATH)


def test_every_contract_exchange_has_authentic_echoing_frames_on_both_sides() -> None:
    requests, responses = frames(REQUESTS_PATH), frames(RESPONSES_PATH)
    assert list(requests) == SCENARIOS and list(responses) == SCENARIOS
    for name in SCENARIOS:
        exchanges = scenario(name)["exchanges"]
        assert len(requests[name]) == len(responses[name]) == len(exchanges), name
        for request, response, exchange in zip(
            requests[name], responses[name], exchanges, strict=True
        ):
            assert request.authentic("request") and response.authentic("response")
            assert not request.authentic("response") and not response.authentic("request")
            sent, answered = request.json(), response.json()
            for field in (
                "protocol_version",
                "probe_session_id",
                "device_epoch",
                "binding",
                "nonce",
            ):
                assert answered[field] == sent[field], (name, field)
            assert answered["sequence_number"] == sent["sequence_number"]
            assert answered["operation"] == sent["operation"] == exchange["op"]
            assert answered["status"] == exchange["status"]


def test_legacy_fixture_files_are_extracts_of_the_genuine_transcripts() -> None:
    spec = contract()
    directory = REQUESTS_PATH.parent
    for file_name, (name, index) in spec["legacy_extracts"].items():
        assert (directory / file_name).read_bytes() == java(name, index).encoded(), file_name
    for file_name, name in spec["legacy_capabilities"].items():
        listed = json.loads((directory / file_name).read_text(encoding="utf-8"))
        assert listed == java(name, 1).json()["diagnostic_capabilities"], file_name


# ==============================================================================
# Real Java bytes through the real lifecycle, for every contract scenario
# ==============================================================================


@pytest.mark.parametrize("name", SCENARIOS)
def test_java_transcript_drives_the_real_lifecycle(name: str) -> None:
    outcomes = run_contract(name)
    passes = [r for r, _ in outcomes.values() if r is not None and r.outcome == "PASS"]
    assert all(
        r.diagnostic_id in {"storage", "touch"} or r.diagnostic_id.startswith("camera_")
        for r in passes
    )


def test_camera_outcome_reason_compatibility_from_real_java() -> None:
    outcomes = run_contract("camera")
    triples = {(r.state, r.outcome, r.reason) for r, _ in outcomes.values() if r is not None}
    assert {
        ("COMPLETED", "PASS", "CAPTURE_MATCH"),
        ("COMPLETED", "INCONCLUSIVE", "METADATA_MISMATCH"),
        ("COMPLETED", "ERROR", "INVALID_FRAME"),
        ("COMPLETED", "INCONCLUSIVE", "METADATA_UNAVAILABLE"),
        ("COMPLETED", "ERROR", "CAPTURE_ERROR"),
        ("COMPLETED", "RESTRICTED", "CAMERA_DISABLED"),
        ("COMPLETED", "INCONCLUSIVE", "CAMERA_BUSY"),
        ("COMPLETED", "ERROR", "INITIALIZATION_ERROR"),
        ("COMPLETED", "INCONCLUSIVE", "CAMERA_DISCONNECTED"),
        ("EXPIRED", "INCONCLUSIVE", "TIMEOUT"),
        ("RUNNING", "INCONCLUSIVE", "STOPPING"),
        ("CANCELLED", "INCONCLUSIVE", "CANCELLED"),
        ("COMPLETED", "RESTRICTED", "PERMISSION_REQUIRED"),
    } <= triples
    assert all(reason in VALID_OUTCOME_REASONS[outcome] for _, outcome, reason in triples)
    genuine = report_of(java("camera", 3))
    assert DiagnosticReport.model_validate_json(json.dumps(genuine)).outcome == "PASS"
    for luma in ("luma_mean", "luma_variance"):
        stripped = {**genuine, "metrics": [m for m in genuine["metrics"] if m["name"] != luma]}
        with pytest.raises(ValidationError):
            DiagnosticReport.model_validate_json(json.dumps(stripped))


# ==============================================================================
# RG-01: genuine capability registries, including real missing sensor_N entries
# ==============================================================================


def capabilities(name: str) -> dict[str, DiagnosticCapability]:
    with replay(name) as run:
        assert run.connection.connect().availability == A.CONNECTED, run.peer.errors
        return {c.diagnostic_id: c for c in run.connection.diagnostic_capabilities()}


def test_missing_sensor_registry_is_genuine_and_completes_the_handshake() -> None:
    typical, sparse = capabilities("typical_capabilities"), capabilities("sparse_capabilities")
    probed_types = {f"sensor_{i}": t for i, t in enumerate([1, 4, 2, 5, 8, 6, 9, 10, 11, 18, 19])}
    assert all(
        typical[s].available and typical[s].sensor_type == t for s, t in probed_types.items()
    )
    assert {s for s in probed_types if sparse[s].available} == {"sensor_0", "sensor_3"}
    for sensor, probed in probed_types.items():
        if sensor in {"sensor_0", "sensor_3"}:
            continue
        absent = sparse[sensor]
        assert absent.sensor_type == probed  # the probed type is named, never a reading
        assert (absent.max_range, absent.resolution, absent.reporting_mode) == (None, None, None)
    assert typical["camera_0"].available and not sparse["camera_0"].available
    assert sparse["camera_0"].camera_facing is None and sparse["camera_0"].camera_level is None
    assert not sparse["vibration"].available and not sparse["microphone"].available
    directory = REQUESTS_PATH.parent
    default = (directory / "capabilities_default.json").read_bytes()
    missing = (directory / "capabilities_missing_sensors.json").read_bytes()
    assert hashlib.sha256(default).digest() != hashlib.sha256(missing).digest()


def test_extreme_registry_completes_the_handshake_with_nulled_non_finite_ranges() -> None:
    caps = capabilities("extreme_capabilities")
    sensors = [c for c in caps if c.startswith("sensor_")]
    cameras = [c for c in caps if c.startswith("camera_")]
    assert (len(caps), len(sensors), len(cameras)) == (91, 64, 16)
    assert caps["sensor_0"].max_range == pytest.approx(3.4028234663852886e38)
    assert caps["sensor_1"].max_range is None and caps["sensor_1"].resolution is None
    assert caps["sensor_2"].max_range is None
    assert caps["sensor_10"].max_range == 4294967296.0


def test_capability_adverse_validation() -> None:
    """Hostile or malformed capability metadata fails closed."""
    with pytest.raises(ValidationError):
        DiagnosticCapability(
            diagnostic_id="sensor_0",
            available=True,
            interactive=False,
            sensor_type=1,
            max_range=float("nan"),
        )
    with pytest.raises(ValidationError):
        DiagnosticCapability(
            diagnostic_id="sensor_0",
            available=True,
            interactive=False,
            sensor_type=1,
            resolution=float("inf"),
        )
    with pytest.raises(ValidationError):
        DiagnosticCapability(diagnostic_id="touch", available=True, interactive=True, sensor_type=1)
    with pytest.raises(ValidationError):
        DiagnosticCapability(diagnostic_id="sensor_0", available=True, interactive=False)
    # The contract also admits an unavailable sensor whose type was never probed.
    assert not DiagnosticCapability(
        diagnostic_id="sensor_5", available=False, interactive=False
    ).available


# ==============================================================================
# Security checks stay in force for genuine Java bytes (HMAC, replay, session, epoch, binding)
# ==============================================================================


def test_tampered_java_frame_fails_hmac_authentication() -> None:
    def tamper(index: int, frame: Frame) -> bytes:
        encoded = bytearray(frame.encoded())
        if index == 0:
            encoded[-2] ^= 0x01
        return bytes(encoded)

    with replay("storage", responder=tamper) as run:
        state = run.connection.connect()
        assert (state.availability, state.reason) == (A.UNTRUSTED, R.AUTHENTICATION_FAILED)


def test_replayed_java_response_is_rejected() -> None:
    hello = java("storage", 0)
    with replay("storage", responder=lambda i, f: hello.encoded()) as run:
        state = run.connection.connect()
        assert (state.availability, state.reason) == (A.ERROR, R.INVALID_RESPONSE)


def test_java_response_from_another_probe_session_is_rejected() -> None:
    foreign = java("camera", 0)  # authentic frame, different probe_session_id
    assert foreign.authentic("response")
    with replay(
        "storage", responder=lambda i, f: foreign.encoded() if i == 0 else f.encoded()
    ) as run:
        state = run.connection.connect()
        assert (state.availability, state.reason) == (A.ERROR, R.INVALID_RESPONSE)


def rebound(frame: Frame) -> bytes:
    """Run 2's genuine START answer, re-signed with run 1's challenge binding."""
    data = frame.json()
    data["binding"] = java("storage", 2).json()["binding"]
    return Frame.sign("response", json.dumps(data, separators=(",", ":")).encode()).encoded()


@pytest.mark.parametrize(
    "answer",
    [lambda frame: java("storage", 2).encoded(), rebound],
    ids=["replayed-earlier-challenge", "authentic-mac-foreign-binding"],
)
def test_java_response_for_a_different_challenge_is_rejected(answer: Any) -> None:
    with replay("storage", responder=lambda i, f: answer(f) if i == 4 else f.encoded()) as run:
        run.connection.connect()
        run.connection.diagnostic(O.START_CHALLENGE, "storage")
        run.connection.diagnostic(O.FETCH_OBSERVATIONS)
        with pytest.raises(DiagnosticSessionError) as raised:
            run.connection.diagnostic(O.START_CHALLENGE, "storage")
        assert raised.value.reason == R.INVALID_RESPONSE
        assert not run.connection.state().transport_connected


def test_device_epoch_change_ends_a_genuine_session_as_session_changed() -> None:
    with replay("storage") as run:
        run.connection.connect()
        run.manager.mark_platform_offline(Platform.ANDROID)
        with pytest.raises(DiagnosticSessionError) as raised:
            run.connection.diagnostic(O.START_CHALLENGE, "storage")
        assert raised.value.reason == R.SESSION_CHANGED
        assert len(run.peer.received) == 2


# ==============================================================================
# Genuine reports as bases for strict negative schema checks
# ==============================================================================


def test_invalid_outcome_reason_combinations_rejected() -> None:
    base = report_of(java("storage", 3))
    assert DiagnosticReport.model_validate_json(json.dumps(base)).outcome == "PASS"
    for outcome, reason in (
        ("PASS", "CAMERA_DISABLED"),
        ("FAIL", "READBACK_MATCH"),
        ("UNSUPPORTED", "PERMISSION_DENIED"),
    ):
        with pytest.raises(ValidationError):
            DiagnosticReport.model_validate_json(
                json.dumps(dict(base, outcome=outcome, reason=reason))
            )


@pytest.mark.parametrize(
    "mutation",
    [
        {"drop": ("window_width", "window_height")},
        {"drop": ("display_width", "display_height")},
        {"set": {"tested_display_area_percent": 99}},
        {"set": {"tested_width": 180, "tested_height": 180}},
        {"set": {"touch_cells": 23}},
        {"drop": ("tested_window_area_percent",)},
    ],
)
def test_genuine_touch_pass_rejects_mutated_geometry(mutation: dict[str, Any]) -> None:
    base = report_of(java("touch_display", 3))
    assert DiagnosticReport.model_validate_json(json.dumps(base)).outcome == "PASS"
    metrics = [
        dict(m, value=mutation.get("set", {}).get(m["name"], m["value"]))
        for m in base["metrics"]
        if m["name"] not in mutation.get("drop", ())
    ]
    with pytest.raises(ValidationError):
        DiagnosticReport.model_validate_json(json.dumps(dict(base, metrics=metrics)))
