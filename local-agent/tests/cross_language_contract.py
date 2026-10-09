"""Deterministic Java<->Python Probe v2 contract support (not a test module).

contract.json is the hand-maintained specification. python_requests.json holds the framed
requests the production Python session emits for it; java_responses.json holds the framed
responses the real Android controller and ControlProtocol emitted for exactly those requests.

Ordinary test runs only READ the fixtures. After an approved protocol change, regenerate the
Python side with (from local-agent):

    uv run python -m tests.cross_language_contract --write-requests

then regenerate the Java side with (from android-probe):

    gradle testDebugUnitTest -Pvector.updateCrossLanguageFixtures=true
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import socket
import struct
import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

from tests.probe_helpers import Clock
from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState
from vector_agent.devices.android.probe_bridge import (
    AndroidProbeBridge,
    ProbeBootstrap,
    TrustedProbeArtifact,
)
from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.models.probe import ProbeChallengeBinding
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe_lifecycle import ProbeAvailability, ProbeReason, ProbeState
from vector_agent.probe import lifecycle, protocol
from vector_agent.probe.lifecycle import ProbeConnection
from vector_agent.probe.protocol import ProbeProtocolSession

FIXTURES = Path(__file__).parent / "fixtures" / "cross_language"
CONTRACT_PATH = FIXTURES / "contract.json"
REQUESTS_PATH = FIXTURES / "python_requests.json"
RESPONSES_PATH = FIXTURES / "java_responses.json"
FABRICATED_SERIAL = "FABRICATED_8C_CONTRACT"
CHALLENGE_OPERATIONS = {O.START_CHALLENGE, O.CANCEL_CHALLENGE, O.FETCH_OBSERVATIONS}
ARTIFACT = TrustedProbeArtifact(
    apk_sha256="a" * 64,
    signer_sha256="b" * 64,
    protocol_version=2,
    application_version="0.2.0",
    version_code=2,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def contract() -> dict[str, Any]:
    data: dict[str, Any] = load_json(CONTRACT_PATH)
    return data


def scenario(name: str) -> dict[str, Any]:
    for item in contract()["scenarios"]:
        if item["name"] == name:
            return dict(item)
    raise KeyError(name)


def key() -> bytes:
    return bytes.fromhex(contract()["key_hex"])


@dataclass(frozen=True)
class Frame:
    """One length-prefixed, direction-MACed wire frame (the AdbProbeTransport format)."""

    payload: bytes
    mac: bytes

    @classmethod
    def sign(cls, direction: str, payload: bytes) -> Frame:
        return cls(
            payload, hmac.digest(key(), direction.encode("ascii") + b"\0" + payload, "sha256")
        )

    @classmethod
    def parse(cls, item: dict[str, str]) -> Frame:
        return cls(item["payload"].encode("utf-8"), bytes.fromhex(item["mac"]))

    def encoded(self) -> bytes:
        return struct.pack("!I", len(self.payload)) + self.mac + self.payload

    def authentic(self, direction: str) -> bool:
        return hmac.compare_digest(self.mac, Frame.sign(direction, self.payload).mac)

    def json(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.payload)
        return loaded

    def as_fixture(self) -> dict[str, str]:
        return {"mac": self.mac.hex(), "payload": self.payload.decode("utf-8")}


def frames(path: Path) -> dict[str, list[Frame]]:
    return {
        name: [Frame.parse(item) for item in items]
        for name, items in load_json(path)["scenarios"].items()
    }


def fabricated_owner() -> tuple[DeviceSessionManager, DeviceSession]:
    manager = DeviceSessionManager()
    manager.reconcile_android_discovery(
        [AdbDeviceEntry(FABRICATED_SERIAL, AdbDeviceState.DEVICE, {})]
    )
    return manager, manager.list_sessions()[0]


class _FrozenDatetime(datetime):
    """Contract time for lifecycle's datetime.now(UTC) (collection_not_before)."""

    frozen: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return cls.frozen


@contextmanager
def deterministic(name: str) -> Iterator[Clock]:
    """Pin every production source of time and randomness for one scenario session.

    Session id, nonces, binding identifiers and timestamps come from contract.json; the
    production request builders, serializers and validators are otherwise untouched.
    """
    spec = contract()
    index = [s["name"] for s in spec["scenarios"]].index(name) + 1
    item = scenario(name)
    clock = Clock()
    clock.now = datetime.fromisoformat(spec["issued_at"].replace("Z", "+00:00"))
    _FrozenDatetime.frozen = clock.now
    nonces = iter(range(1, 10**6))
    identifiers = iter(range(1, 10**6))

    def session_factory(**kwargs: Any) -> ProbeProtocolSession:
        return ProbeProtocolSession(**kwargs, clock=clock.wall, monotonic=clock.monotonic)

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(protocol, "generate_nonce", lambda: f"s{index:02d}n{next(nonces):039d}")
        )
        stack.enter_context(patch.object(protocol, "uuid4", lambda: UUID(item["session_id"])))
        stack.enter_context(
            patch.object(
                lifecycle,
                "uuid4",
                lambda: UUID(f"{next(identifiers):08x}-cafe-4000-8000-{index:012x}"),
            )
        )
        stack.enter_context(patch.object(lifecycle, "datetime", _FrozenDatetime))
        stack.enter_context(patch.object(lifecycle, "ProbeProtocolSession", session_factory))
        yield clock


def binding_like_lifecycle(diagnostic_id: str) -> ProbeChallengeBinding:
    """Exactly the construction in ProbeConnection.diagnostic (call order matters)."""
    return ProbeChallengeBinding(
        scan_id=str(lifecycle.uuid4()),
        diagnostic_id=diagnostic_id,
        attempt_id=str(lifecycle.uuid4()),
        challenge_id=str(lifecycle.uuid4()),
        collection_not_before=lifecycle.datetime.now(UTC),
    )


def generate_requests() -> dict[str, list[Frame]]:
    """Requests the production session emits for every contract exchange, in order."""
    generated: dict[str, list[Frame]] = {}
    for item in contract()["scenarios"]:
        _, owner = fabricated_owner()
        with deterministic(item["name"]):
            session = lifecycle.ProbeProtocolSession(
                device_id=owner.device_id, device_epoch=owner.session_epoch, protocol_version=2
            )
            binding: ProbeChallengeBinding | None = None
            sent: list[Frame] = []
            for exchange in item["exchanges"]:
                operation = O(exchange["op"])
                if operation == O.START_CHALLENGE:
                    binding = binding_like_lifecycle(exchange["diagnostic_id"])
                request = session.create_request(
                    operation,
                    current_device_epoch=owner.session_epoch,
                    binding=binding if operation in CHALLENGE_OPERATIONS else None,
                )
                session.abandon_request(request)
                sent.append(Frame.sign("request", request.model_dump_json().encode("utf-8")))
        generated[item["name"]] = sent
    return generated


Responder = Callable[[int, Frame], bytes | None]


@dataclass
class DevicePeer:
    """Fake Probe socket: byte-compares each Python request, answers with Java's frame."""

    sock: socket.socket
    expected: list[Frame]
    answers: list[Frame]
    responder: Responder | None = None
    received: list[Frame] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    thread: threading.Thread | None = None

    def _read(self, size: int) -> bytes | None:
        data = bytearray()
        while len(data) < size:
            block = self.sock.recv(size - len(data))
            if not block:
                return None
            data.extend(block)
        return bytes(data)

    def serve(self) -> None:
        try:
            while True:
                head = self._read(36)
                if head is None:
                    return
                payload = self._read(struct.unpack("!I", head[:4])[0]) or b""
                frame = Frame(payload, head[4:36])
                index = len(self.received)
                self.received.append(frame)
                if index >= len(self.expected) or frame != self.expected[index]:
                    self.errors.append(f"request {index} differs from python_requests.json")
                    return
                if not frame.authentic("request"):
                    self.errors.append(f"request {index} has an invalid request MAC")
                    return
                answer = (
                    self.responder(index, self.answers[index])
                    if self.responder
                    else self.answers[index].encoded()
                )
                if answer is None:
                    return
                self.sock.sendall(answer)
        except OSError:
            return
        finally:
            self.sock.close()

    def start(self) -> None:
        self.thread = threading.Thread(target=self.serve, name="contract-peer", daemon=True)
        self.thread.start()


@dataclass
class Replay:
    connection: ProbeConnection
    manager: DeviceSessionManager
    peer: DevicePeer
    bridge: MagicMock


@contextmanager
def replay(
    name: str,
    *,
    answers: list[Frame] | None = None,
    responder: Responder | None = None,
) -> Iterator[Replay]:
    """Real ProbeConnection + AdbProbeTransport against a socket peer replaying Java bytes."""
    expected = frames(REQUESTS_PATH)[name]
    java = answers if answers is not None else frames(RESPONSES_PATH)[name]
    manager, owner = fabricated_owner()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.discover.return_value = ProbeState(
        availability=ProbeAvailability.INSTALLED_COMPATIBLE,
        reason=ProbeReason.NONE,
        installed=True,
        identity_trusted=True,
        protocol_compatible=True,
        protocol_version=2,
        application_version="0.2.0",
    )
    bridge.bootstrap.return_value = ProbeBootstrap(key(), "vector_probe_" + "c" * 32)
    bridge.forward.return_value = 40404
    client, device = socket.socketpair()
    peer = DevicePeer(device, expected, java, responder)
    peer.start()
    with (
        deterministic(name),
        patch.object(socket, "create_connection", lambda address, timeout: client),
    ):
        connection = ProbeConnection(manager, owner, bridge, ARTIFACT)
        try:
            yield Replay(connection, manager, peer, bridge)
        finally:
            connection.stop()
            client.close()
            if peer.thread is not None:
                peer.thread.join(timeout=5)


def payload_digest(frame: Frame) -> str:
    return hashlib.sha256(frame.payload).hexdigest()


def write_requests() -> None:
    document = {
        "generator": "local-agent tests/cross_language_contract.py --write-requests",
        "scenarios": {
            name: [frame.as_fixture() for frame in sent]
            for name, sent in generate_requests().items()
        },
    }
    # Explicit LF so the generated bytes are identical on every platform.
    REQUESTS_PATH.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-requests", action="store_true", required=True)
    parser.parse_args()
    write_requests()
    print(f"Wrote {REQUESTS_PATH}. Regenerate java_responses.json next (see module docstring).")


if __name__ == "__main__":
    main()
