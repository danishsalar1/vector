"""Fabricated control-plane fixtures shared by Phase 8A tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from vector_agent.models.probe import ProbeChallengeBinding, ProbeOperation, ProbeRequestEnvelope
from vector_agent.probe.protocol import ProbeProtocolSession

DEVICE_ID = "android-0123456789ab"
EPOCH = 7


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 12, tzinfo=UTC)
        self.mono = 100.0

    def wall(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.mono += seconds


def observation(now: datetime) -> dict[str, Any]:
    return {
        "observation_id": str(uuid4()),
        "observation_type": "SAMPLE_COUNT",
        "collector_id": "probe_control",
        "value": 3,
        "unit": "count",
        "collection_started_at": now.isoformat(),
        "collection_completed_at": now.isoformat(),
        "complete": True,
        "limitations": [],
    }


def response(request: ProbeRequestEnvelope) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(request.model_dump_json())
    data.update(
        status="OK",
        probe_build={"artifact_sha256": "a" * 64},
        capabilities=[],
        observations=[],
    )
    if request.operation == ProbeOperation.FETCH_OBSERVATIONS:
        data["observations"] = [observation(request.issued_at)]
    return data


def wire(data: object) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def make_case(
    operation: ProbeOperation = ProbeOperation.FETCH_OBSERVATIONS,
) -> tuple[Clock, ProbeProtocolSession, ProbeRequestEnvelope, dict[str, Any]]:
    clock = Clock()
    session = ProbeProtocolSession(
        device_id=DEVICE_ID, device_epoch=EPOCH, clock=clock.wall, monotonic=clock.monotonic
    )
    binding = None
    if operation in (
        ProbeOperation.START_CHALLENGE,
        ProbeOperation.CANCEL_CHALLENGE,
        ProbeOperation.FETCH_OBSERVATIONS,
    ):
        binding = ProbeChallengeBinding(
            scan_id=str(uuid4()),
            diagnostic_id="probe_control",
            attempt_id=str(uuid4()),
            challenge_id=str(uuid4()),
            collection_not_before=clock.now,
        )
    request = session.create_request(operation, current_device_epoch=EPOCH, binding=binding)
    return clock, session, request, response(request)
