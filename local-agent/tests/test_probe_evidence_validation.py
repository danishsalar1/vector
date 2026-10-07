"""Raw candidates traverse the entire production ingestion boundary."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

import pytest

from tests.probe_helpers import DEVICE_ID, EPOCH, make_case, response, wire
from vector_agent.evidence.validation import ingest_probe_response
from vector_agent.models.device import DiagnosticResult, EvidenceRecord, EvidenceSourceType
from vector_agent.models.probe import ProbeOperation
from vector_agent.probe.protocol import ProbeValidationError


def test_attribution_is_local_and_no_confidence_or_nonce_fabricated() -> None:
    _, session, request, data = make_case()
    result = ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    observation = result.observations[0]
    assert observation.device_id == DEVICE_ID
    assert observation.device_epoch == EPOCH
    assert observation.binding == request.binding
    assert observation.source == EvidenceSourceType.VECTOR_PROBE
    assert observation.confidence is None
    assert observation.reliability is None
    assert observation.protocol_version == 1
    assert observation.probe_build is not None
    assert observation.collector_id == "probe_control"
    assert observation.value == 3
    assert request.nonce not in str(asdict(observation))
    assert not isinstance(observation, EvidenceRecord | DiagnosticResult)
    assert not hasattr(observation, "status")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("value", True),
        ("value", "3"),
        ("value", 3.5),
        ("value", -1),
        ("value", float("nan")),
        ("value", float("inf")),
        ("value", float("-inf")),
        ("observation_type", "CAMERA_IMAGE"),
        ("observation_type", "GENUINE_PART"),
        ("observation_type", "LOCATION_HISTORY"),
        ("unit", "mAh"),
        ("collector_id", "other_diagnostic"),
        ("complete", 1),
        ("confidence", 1.0),
        ("reliability", 1.0),
        ("metadata", {"serial": "PRIVATE_MARKER"}),
        ("raw_value", "PRIVATE_MARKER"),
        ("raw_image", "image_bytes"),
        ("limitations", ["Some arbitrary private content"]),
    ],
)
def test_invalid_observation_rejected(key: str, value: Any) -> None:
    _, session, request, data = make_case()
    data["observations"][0][key] = value
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )


@pytest.mark.parametrize(
    "key",
    [
        "collector_id",
        "observation_id",
        "observation_type",
        "collection_started_at",
        "collection_completed_at",
        "unit",
        "complete",
        "limitations",
    ],
)
def test_missing_observation_attribution_rejected(key: str) -> None:
    _, session, request, data = make_case()
    del data["observations"][0][key]
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )


def test_partial_collection_remains_explicit() -> None:
    _, session, request, data = make_case()
    data["observations"][0].update(complete=False, limitations=["PARTIAL_COLLECTION"])
    result = ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    assert not result.observations[0].complete
    assert result.observations[0].limitations == ("PARTIAL_COLLECTION",)


@pytest.mark.parametrize(
    ("complete", "limitations"),
    [(False, []), (True, ["PARTIAL_COLLECTION"]), (False, ["INTERRUPTED", "INTERRUPTED"])],
)
def test_completeness_must_not_contradict_limitations(
    complete: bool, limitations: list[str]
) -> None:
    _, session, request, data = make_case()
    data["observations"][0].update(complete=complete, limitations=limitations)
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )


@pytest.mark.parametrize(
    ("key", "offset"),
    [
        ("collection_started_at", -1),
        ("collection_completed_at", -1),
        ("collection_completed_at", 1),
    ],
)
def test_collection_window_binding(key: str, offset: int) -> None:
    clock, session, request, data = make_case()
    data["observations"][0][key] = (clock.now + timedelta(seconds=offset)).isoformat()
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )


def test_repeated_observation_cannot_be_repackaged_with_fresh_nonce() -> None:
    _, session, request, data = make_case()
    ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    next_request = session.create_request(
        request.operation, current_device_epoch=EPOCH, binding=request.binding
    )
    next_data = response(next_request)
    next_data["observations"] = data["observations"]
    with pytest.raises(ProbeValidationError, match="REPLAY"):
        ingest_probe_response(
            wire(next_data),
            session=session,
            current_device_epoch=EPOCH,
            expected_request=next_request,
        )


def test_duplicate_observation_in_same_response_rejected() -> None:
    _, session, request, data = make_case()
    data["observations"] *= 2
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )


@pytest.mark.parametrize("status", ["RESTRICTED", "UNAVAILABLE", "CANCELLED", "ERROR"])
def test_failure_cannot_smuggle_observations(status: str) -> None:
    _, session, request, data = make_case()
    data["status"] = status
    with pytest.raises(ProbeValidationError):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )
    data["observations"] = []
    result = ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    assert result.command_status == status
    assert not result.observations


def test_responsiveness_never_creates_diagnostic_pass() -> None:
    _, session, request, data = make_case(ProbeOperation.HEARTBEAT)
    result = ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    assert result.command_status == "OK"
    assert result.observations == ()
    assert not isinstance(result, EvidenceRecord | DiagnosticResult)
    assert "PASS" not in repr(result)


def test_existing_evidence_sources_preserved() -> None:
    previous = {
        "ADB_GETPROP",
        "ADB_DUMPSYS",
        "ADB_SHELL",
        "ANDROID_SYSTEM_SERVICE",
        "LIBIMOBILEDEVICE",
        "IDEVICEINFO",
        "IDEVICEDIAGNOSTICS",
        "DEVICE_METADATA",
        "BENCHMARK",
        "USER_ASSISTED",
        "SYNTHETIC_TEST_ONLY",
    }
    assert {source.value for source in EvidenceSourceType} == previous | {"VECTOR_PROBE"}
    for source in previous:
        assert EvidenceSourceType(source).value == source


@pytest.mark.parametrize(
    ("kind", "value", "unit"),
    [("CONTROL_ACKNOWLEDGEMENT", True, None), ("COLLECTION_DURATION", 1.25, "ms")],
)
def test_other_control_observations_are_accepted_without_health_verdict(
    kind: str, value: Any, unit: str | None
) -> None:
    _, session, request, data = make_case()
    data["observations"][0].update(observation_type=kind, value=value, unit=unit)
    data["probe_build"] = None
    result = ingest_probe_response(
        wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
    )
    assert result.observations[0].value == value
    assert result.observations[0].probe_build is None
    assert result.observations[0].confidence is None


def test_observation_replay_store_cannot_grow_without_bound() -> None:
    from tests.probe_helpers import observation
    from vector_agent.probe.protocol import MAX_SESSION_OBSERVATIONS

    clock, session, request, data = make_case()
    for batch in range(MAX_SESSION_OBSERVATIONS // 32):
        if batch:
            request = session.create_request(
                request.operation, current_device_epoch=EPOCH, binding=request.binding
            )
            data = response(request)
        data["observations"] = [observation(clock.now) for _ in range(32)]
        accepted = ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )
        assert len(accepted.observations) == 32
    request = session.create_request(
        request.operation, current_device_epoch=EPOCH, binding=request.binding
    )
    with pytest.raises(ProbeValidationError, match="BOUNDS_VIOLATION"):
        ingest_probe_response(
            wire(response(request)),
            session=session,
            current_device_epoch=EPOCH,
            expected_request=request,
        )


@pytest.mark.parametrize("entry", ["ingestion", "session"])
def test_expected_request_is_required_and_omission_preserves_pending(entry: str) -> None:
    _, session, request, data = make_case()
    with pytest.raises(TypeError):
        if entry == "ingestion":
            ingest_probe_response(wire(data), session=session, current_device_epoch=EPOCH)
        else:
            session.accept_response(wire(data), current_device_epoch=EPOCH)
    assert session._pending == request
    assert (
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )
        .observations[0]
        .value
        == 3
    )


@pytest.mark.parametrize("owner", [None, {}, "FABRICATED_OWNER"])
def test_ingestion_invalid_owner_cannot_bypass_binding(owner: Any) -> None:
    _, session, request, data = make_case()
    with pytest.raises(ProbeValidationError, match="MALFORMED_MESSAGE"):
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=owner
        )
    assert session._pending == request
    assert (
        ingest_probe_response(
            wire(data), session=session, current_device_epoch=EPOCH, expected_request=request
        )
        .observations[0]
        .value
        == 3
    )


def test_stale_ingestion_owner_cannot_consume_replacement_response() -> None:
    clock, session, old, _ = make_case()
    clock.advance(31)
    new = session.create_request(old.operation, current_device_epoch=EPOCH, binding=old.binding)
    data = wire(response(new))
    with pytest.raises(ProbeValidationError, match="BINDING_MISMATCH"):
        ingest_probe_response(
            data, session=session, current_device_epoch=EPOCH, expected_request=old
        )
    assert session._pending == new
    assert session._pending_mono == clock.mono
    assert (
        ingest_probe_response(
            data, session=session, current_device_epoch=EPOCH, expected_request=new
        )
        .observations[0]
        .value
        == 3
    )
