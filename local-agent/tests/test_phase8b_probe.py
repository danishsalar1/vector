"""Fabricated app/device edges exercise real protocol and lifecycle boundaries."""

from __future__ import annotations

import hmac
import json
import socket
import struct
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests.probe_helpers import response, wire
from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState
from vector_agent.devices.android.probe_bridge import (
    AndroidProbeBridge,
    ProbeBootstrap,
    TrustedProbeArtifact,
)
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.main import create_app
from vector_agent.models.device import Platform, TrustEngineStatus
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.models.probe import ProbeRequestEnvelope
from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.models.probe_lifecycle import ProbeState
from vector_agent.probe.adb_transport import AdbProbeTransport
from vector_agent.probe.lifecycle import ProbeConnection, ProbeService
from vector_agent.probe.protocol import ProbeProtocolSession
from vector_agent.probe.transport import ProbeTransport, ProbeTransportReply
from vector_agent.probe.transport import ProbeTransportStatus as T
from vector_agent.security.bounded_process import BoundedOutput, capture
from vector_agent.security.local_api_auth import get_local_api_auth

ARTIFACT = TrustedProbeArtifact(apk_sha256="a" * 64, signer_sha256="b" * 64)
APK_PATH = "/data/app/~~fabricated/org.vector.probe-fabricated/base.apk"
BOOTSTRAP = ProbeBootstrap(b"k" * 32, "vector_probe_" + "c" * 32)
SERIAL = "FABRICATED_8B"


def hello() -> dict[str, Any]:
    return {
        "application_version": "0.1.0",
        "version_code": 1,
        "protocol_versions": [1],
        "supported_operations": ["HELLO", "GET_CAPABILITIES", "HEARTBEAT"],
        "api_level": 26,
    }


def control_response(request: ProbeRequestEnvelope) -> dict[str, Any]:
    data = response(request)
    data["probe_build"] = None
    if request.operation == O.HELLO:
        data["hello"] = hello()
    if request.operation == O.GET_CAPABILITIES:
        data["capabilities"] = [
            {
                "capability_id": "CONTROL_CHANNEL",
                "available": True,
                "operations": ["HELLO", "GET_CAPABILITIES", "HEARTBEAT"],
            }
        ]
    return data


def discovered() -> ProbeState:
    return ProbeState(
        availability=A.INSTALLED_COMPATIBLE,
        installed=True,
        identity_trusted=True,
        protocol_compatible=True,
        protocol_version=1,
        application_version="0.1.0",
    )


class MemoryTransport(ProbeTransport):
    """Fixture I/O only. Uses the production Phase 8A acceptance pipeline."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("bridge")
        kwargs.pop("bootstrap")
        super().__init__(**kwargs)
        self.mutate: Any = lambda data: data
        self.outcome: T | None = None
        self.cleaned = 0
        self.operations: list[O] = []

    def _exchange(self, request: ProbeRequestEnvelope, **kwargs: Any) -> ProbeTransportReply:
        self.operations.append(request.operation)
        if self.outcome:
            return ProbeTransportReply(self.outcome)
        return ProbeTransportReply(T.RECEIVED, wire(self.mutate(control_response(request))))

    def _cleanup(self) -> None:
        self.cleaned += 1


def lifecycle() -> tuple[ProbeConnection, DeviceSessionManager, MagicMock, list[MemoryTransport]]:
    manager = DeviceSessionManager()
    manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
    owner = manager.list_sessions()[0]
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.discover.return_value = discovered()
    bridge.bootstrap.return_value = BOOTSTRAP
    bridge.launch.return_value = True
    bridge.stop.return_value = True
    transports: list[MemoryTransport] = []

    def factory(**kwargs: Any) -> MemoryTransport:
        transport = MemoryTransport(**kwargs)
        transports.append(transport)
        return transport

    return ProbeConnection(manager, owner, bridge, ARTIFACT, factory), manager, bridge, transports


def bridge_outputs(
    monkeypatch: pytest.MonkeyPatch, values: list[tuple[int, str]]
) -> tuple[AndroidProbeBridge, list[list[str]]]:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> BoundedOutput:
        calls.append(args)
        rc, output = values[len(calls) - 1]
        return BoundedOutput(rc, output.encode())

    monkeypatch.setattr("vector_agent.devices.android.probe_bridge.capture", run)
    return AndroidProbeBridge(serial=SERIAL), calls


@pytest.mark.parametrize(
    "values,artifact,expected",
    [
        ([(0, "")], ARTIFACT, A.NOT_INSTALLED),
        ([(1, "private")], ARTIFACT, A.ERROR),
        ([(0, "package:org.vector.probe.evil")], ARTIFACT, A.ERROR),
        ([(0, "package:org.vector.probe"), (0, "package:org.vector.probe")], ARTIFACT, A.DISABLED),
        ([(0, "package:org.vector.probe"), (1, "")], ARTIFACT, A.ERROR),
        ([(0, "package:org.vector.probe"), (0, "")], None, A.INSTALLED_UNVERIFIED),
        (
            [
                (0, "package:org.vector.probe"),
                (0, ""),
                (0, "package:" + APK_PATH),
                (0, "a" * 64 + "  " + APK_PATH),
            ],
            ARTIFACT,
            A.INSTALLED_COMPATIBLE,
        ),
        (
            [
                (0, "package:org.vector.probe"),
                (0, ""),
                (0, "package:" + APK_PATH),
                (0, "f" * 64 + "  " + APK_PATH),
            ],
            ARTIFACT,
            A.UNTRUSTED,
        ),
        (
            [
                (0, "package:org.vector.probe"),
                (0, ""),
                (0, "package:" + APK_PATH),
                (0, "not-a-digest"),
            ],
            ARTIFACT,
            A.INSTALLED_UNVERIFIED,
        ),
        (
            [
                (0, "package:org.vector.probe"),
                (0, ""),
                (0, "package:" + APK_PATH),
                (1, "a" * 64 + "  " + APK_PATH),
            ],
            ARTIFACT,
            A.INSTALLED_UNVERIFIED,
        ),
        (
            [
                (0, "package:org.vector.probe"),
                (0, ""),
                (0, "package:" + APK_PATH),
                (0, "a" * 64 + "  " + APK_PATH),
            ],
            ARTIFACT.model_copy(update={"protocol_version": 2}),
            A.INSTALLED_INCOMPATIBLE,
        ),
    ],
)
def test_discovery(
    monkeypatch: pytest.MonkeyPatch, values: Any, artifact: Any, expected: A
) -> None:
    bridge, calls = bridge_outputs(monkeypatch, values)
    state = bridge.discover(artifact)
    assert state.availability == expected
    assert SERIAL not in state.model_dump_json()
    assert "private" not in state.model_dump_json()
    assert not state.transport_connected
    assert all(call[:3] == ["adb", "-s", SERIAL] for call in calls)
    if expected == A.INSTALLED_COMPATIBLE:
        assert state.identity_trusted and state.application_version == "0.1.0"


@pytest.mark.parametrize(
    "path",
    [
        "/sdcard/base.apk",
        "/data/app/other/base.apk",
        APK_PATH + "\npackage:" + APK_PATH,
        APK_PATH + ";id",
        APK_PATH + "\n",
        APK_PATH.replace("base.apk", "../base.apk"),
    ],
)
def test_no_arbitrary_apk_path(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    # _call strips terminal whitespace; multi-line or alternate paths fail closed.
    if path.endswith("\n"):
        path += "unexpected"
    bridge, calls = bridge_outputs(
        monkeypatch, [(0, "package:org.vector.probe"), (0, ""), (0, "package:" + path)]
    )
    assert not bridge.discover(ARTIFACT).identity_trusted
    assert len(calls) == 3


@pytest.mark.parametrize("value", ["", "-s", "a\n", "x;id", "a b", "x" * 65, "a\0"])
def test_serial_boundary(value: str) -> None:
    with pytest.raises(ValueError):
        AndroidProbeBridge(serial=value)


@pytest.mark.parametrize("digest", ["", "a" * 63, "G" * 64, "a" * 64 + "\n", None])
def test_signer_configuration(digest: Any) -> None:
    with pytest.raises(ValidationError):
        TrustedProbeArtifact(apk_sha256="a" * 64, signer_sha256=digest)


def test_fixed_launch_stop_and_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge, calls = bridge_outputs(
        monkeypatch,
        [
            (0, "Status: ok"),
            (0, ""),
            (0, "42123"),
            (0, SERIAL + " tcp:42123 localabstract:" + BOOTSTRAP.endpoint),
            (0, ""),
        ],
    )
    assert bridge.launch() and bridge.stop()
    port = bridge.forward(BOOTSTRAP)
    with pytest.raises(ValueError):
        bridge.remove_forward(port + 1)
    bridge.remove_forward(port)
    assert calls == [
        [
            "adb",
            "-s",
            SERIAL,
            "shell",
            "am",
            "start",
            "--user",
            "0",
            "-W",
            "-n",
            "org.vector.probe/.ProbeActivity",
        ],
        ["adb", "-s", SERIAL, "shell", "am", "force-stop", "--user", "0", "org.vector.probe"],
        ["adb", "-s", SERIAL, "forward", "tcp:0", "localabstract:" + BOOTSTRAP.endpoint],
        ["adb", "-s", SERIAL, "forward", "--list"],
        ["adb", "-s", SERIAL, "forward", "--remove", "tcp:42123"],
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("REQUIRED", "REQUIRED"),
        ("DENIED", "DENIED"),
        ("6b" * 32 + "\n" + BOOTSTRAP.endpoint, BOOTSTRAP),
    ],
)
def test_bootstrap(monkeypatch: pytest.MonkeyPatch, value: str, expected: Any) -> None:
    bridge, calls = bridge_outputs(monkeypatch, [(0, value)])
    assert bridge.bootstrap() == expected
    assert calls[0][3:] == [
        "exec-out",
        "run-as",
        "org.vector.probe",
        "cat",
        "files/vector-probe-session",
    ]
    assert "6b" * 32 not in repr(BOOTSTRAP)


@pytest.mark.parametrize(
    "state,expected_avail,expected_reason",
    [
        ("REQUIRED", A.CONSENT_REQUIRED, R.APPROVE_ON_DEVICE),
        ("DENIED", A.CONSENT_DENIED, R.USER_DECLINED),
        ("RESTRICTED", A.RESTRICTED, R.DEVELOPMENT_ACCESS_REQUIRED),
        ("NOT_STARTED", A.CONSENT_REQUIRED, R.PROBE_NOT_STARTED),
        ("EXPIRED", A.DISCONNECTED, R.SESSION_EXPIRED),
    ],
)
def test_consent(state: str, expected_avail: A, expected_reason: R) -> None:
    connection, _, bridge, transports = lifecycle()
    assert connection.launch().availability == A.CONSENT_REQUIRED
    bridge.bootstrap.return_value = state
    res = connection.connect()
    assert res.availability == expected_avail
    assert res.reason == expected_reason
    assert not transports


def test_hello_capabilities_heartbeat_no_diagnostic_claims() -> None:
    connection, _, _, transports = lifecycle()
    state = connection.connect()
    assert state.availability == A.CONNECTED and state.transport_connected
    assert state.identity_trusted and state.protocol_compatible
    assert state.capabilities[0].capability_id == "CONTROL_CHANNEL"
    assert connection.heartbeat().availability == A.CONNECTED
    assert transports[0].operations == [O.HELLO, O.GET_CAPABILITIES, O.HEARTBEAT]
    for forbidden in ("PASS", "trust_score", "confidence", "genuine"):
        assert forbidden not in state.model_dump_json()
    assert TrustEngineStatus.NOT_READY.value == "NOT_READY"
    connection.stop()
    assert transports[0].cleaned == 1
    assert not connection.state().transport_connected


@pytest.mark.parametrize("change", ["disconnect", "reconnect", "epoch", "replacement"])
def test_owner_invalidation(change: str) -> None:
    connection, manager, _, transports = lifecycle()
    connection.connect()
    if change == "epoch":
        manager.list_sessions()[0].session_epoch += 1
    elif change == "replacement":
        manager.clear()
        manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
    else:
        manager.reconcile_android_discovery([])
        if change == "reconnect":
            manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
    assert connection.heartbeat().availability == A.DISCONNECTED
    assert transports[0].cleaned == 1
    assert transports[0].operations == [O.HELLO, O.GET_CAPABILITIES]


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (T.TIMEOUT, A.DISCONNECTED),
        (T.UNAVAILABLE, A.DISCONNECTED),
        (T.AUTHENTICATION_FAILURE, A.UNTRUSTED),
        (T.PROTOCOL_VIOLATION, A.ERROR),
        (T.UNSUPPORTED_PROTOCOL, A.INSTALLED_INCOMPATIBLE),
        (T.CANCELLED, A.DISCONNECTED),
    ],
)
def test_heartbeat_fail_closed(outcome: T, expected: A) -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    transports[0].outcome = outcome
    result = connection.heartbeat()
    assert result.availability == expected
    assert not result.capabilities and not result.transport_connected
    assert transports[0].cleaned == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "x" * 43),
        ("device_epoch", 999),
        ("probe_session_id", "00000000-0000-4000-8000-000000000000"),
        ("sequence_number", 0),
        ("operation", "GET_CAPABILITIES"),
        ("protocol_version", 2),
    ],
)
def test_authenticated_but_misbound_reply(field: str, value: Any) -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    transports[0].mutate = lambda data: {**data, field: value}
    assert not connection.heartbeat().transport_connected
    assert transports[0].cleaned == 1


@pytest.mark.parametrize(
    "error,reason",
    [
        (FileNotFoundError, R.TOOL_UNAVAILABLE),
        (TimeoutError, R.TIMEOUT),
        (ValueError, R.INVALID_RESPONSE),
    ],
)
def test_safe_errors(error: type[Exception], reason: R) -> None:
    connection, _, bridge, _ = lifecycle()
    bridge.discover.side_effect = error("PRIVATE_SERIAL_PRIVATE_PATH")
    result = connection.discover()
    assert result.reason == reason
    assert "PRIVATE" not in result.model_dump_json()


def test_real_transport_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    request = session.create_request(O.HELLO, current_device_epoch=3)
    errors: list[Exception] = []

    def server() -> None:
        try:
            stream = peer.makefile("rb")
            size = struct.unpack("!I", stream.read(4))[0]
            mac, payload = stream.read(32), stream.read(size)
            assert hmac.compare_digest(
                mac, hmac.digest(BOOTSTRAP.key, b"request\0" + payload, "sha256")
            )
            assert json.loads(payload)["nonce"] == request.nonce
            raw = wire(control_response(request))
            frame = (
                struct.pack("!I", len(raw))
                + hmac.digest(BOOTSTRAP.key, b"response\0" + raw, "sha256")
                + raw
            )
            for start in range(0, len(frame), 7):
                peer.sendall(frame[start : start + 7])
            stream.close()
        except Exception as error:
            errors.append(error)
        finally:
            peer.close()

    worker = threading.Thread(target=server)
    worker.start()
    result = transport.request(request, timeout_seconds=2, cancellation=threading.Event())
    worker.join(2)
    assert not errors
    assert result.status == T.RECEIVED and result.response is not None
    assert result.response.hello is not None
    assert transport.close() == T.CLOSED
    bridge.remove_forward.assert_called_once_with(45678)


@pytest.mark.parametrize(
    "reply,status",
    [
        (struct.pack("!I", 65537), T.BOUNDS_VIOLATION),
        (struct.pack("!I", 2) + b"x" * 32 + b"{}", T.AUTHENTICATION_FAILURE),
    ],
)
def test_socket_rejects_before_ingestion(
    monkeypatch: pytest.MonkeyPatch, reply: bytes, status: T
) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    peer.sendall(reply)
    request = session.create_request(O.HELLO, current_device_epoch=3)
    assert (
        transport.request(request, timeout_seconds=1, cancellation=threading.Event()).status
        == status
    )
    transport.close()
    peer.close()


def test_bounded_process_actual_pipes() -> None:
    result = capture(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff'); sys.exit(7)"]
    )
    assert result.returncode == 7 and result.stdout == b"\xff"
    for pipe in ("stdout", "stderr"):
        with pytest.raises(OSError, match="output rejected"):
            capture([sys.executable, "-c", f"import sys; sys.{pipe}.write('x'*100000)"], limit=1024)
    with pytest.raises(TimeoutError, match="timed out"):
        capture([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.1)


def test_api_requires_process_authorization_and_local_host() -> None:
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8742") as client:
        path = "/api/v1/devices/android-0123456789ab/probe"
        assert client.get(path).status_code == 401
        headers = {"X-Vector-Local-Authorization": get_local_api_auth().token_for_local_bootstrap()}
        assert (
            client.get(path, headers={**headers, "Origin": "https://hostile.example"}).status_code
            == 403
        )
        assert client.get(path, headers={**headers, "Host": "hostile.example"}).status_code == 403
        assert client.get(path, headers=headers).status_code == 409


def test_permission_and_scope_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = (root / "android-probe/app/src/main/AndroidManifest.xml").read_text()
    # Phase 8C deliberately adds this exact permission set; no unrelated access.
    import xml.etree.ElementTree as ET

    permissions = {
        node.attrib["{http://schemas.android.com/apk/res/android}name"]
        for node in ET.fromstring(manifest).findall("uses-permission")
    }
    assert permissions == {
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
        "android.permission.ACTIVITY_RECOGNITION",
        "android.permission.VIBRATE",
        "android.permission.ACCESS_WIFI_STATE",
    }
    assert (
        "<service" not in manifest and "<receiver" not in manifest and "<provider" not in manifest
    )
    assert 'android:allowBackup="false"' in manifest
    source = (
        root / "android-probe/app/src/main/java/org/vector/probe/ProbeActivity.java"
    ).read_text()
    assert "onPause" in source and 'revoke("REQUIRED"' in source
    assert "getIntent" not in source


def test_service_reconnect_uses_new_owner_and_protocol() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    device_id = manager.list_sessions()[0].device_id
    first = service.connection(device_id)
    manager.mark_platform_offline(Platform.ANDROID)
    manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
    second = service.connection(device_id)
    assert first is not second and not first._live()
    service.close()


@pytest.mark.parametrize("operation", [O.HELLO, O.GET_CAPABILITIES])
@pytest.mark.parametrize("damage", ["malformed", "missing", "future", "timeout"])
def test_negotiation_failure(operation: O, damage: str) -> None:
    connection, _, _, transports = lifecycle()
    original_factory = connection._factory

    def factory(**kwargs: Any) -> ProbeTransport:
        transport = original_factory(**kwargs)
        original_exchange = transport._exchange

        def exchange(request: ProbeRequestEnvelope, **options: Any) -> ProbeTransportReply:
            if request.operation != operation:
                return original_exchange(request, **options)
            if damage == "timeout":
                return ProbeTransportReply(T.TIMEOUT)
            data = control_response(request)
            if operation == O.HELLO:
                if damage == "missing":
                    del data["hello"]
                elif damage == "future":
                    data["hello"]["application_version"] = "9.0.0"
                else:
                    data["hello"]["api_level"] = True
            elif damage == "missing":
                data["capabilities"] = []
            elif damage == "future":
                data["capabilities"][0]["operations"].append("START_CHALLENGE")
            else:
                data["capabilities"][0]["available"] = "true"
            return ProbeTransportReply(T.RECEIVED, wire(data))

        transport._exchange = exchange  # type: ignore[method-assign]
        return transport

    connection._factory = factory
    result = connection.connect()
    assert result.availability in (A.ERROR, A.INSTALLED_INCOMPATIBLE, A.DISCONNECTED)
    assert not result.transport_connected and not result.capabilities
    assert transports[0].cleaned == 1


def test_late_reply_after_epoch_change() -> None:
    connection, manager, _, transports = lifecycle()
    connection.connect()

    def mutate(data: Any) -> Any:
        manager.mark_platform_offline(Platform.ANDROID)
        manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
        return data

    transports[0].mutate = mutate
    assert connection.heartbeat().availability == A.DISCONNECTED
    assert not connection.state().capabilities


def test_stop_interrupts_pending_exchange_and_rejects_late_response() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    started = threading.Event()

    def exchange(
        request: ProbeRequestEnvelope, *, cancellation: Any, **options: Any
    ) -> ProbeTransportReply:
        started.set()
        assert connection._cancel.wait(2)
        return ProbeTransportReply(T.RECEIVED, wire(control_response(request)))

    transports[0]._exchange = exchange  # type: ignore[method-assign]
    results: list[ProbeState] = []
    worker = threading.Thread(target=lambda: results.append(connection.heartbeat()))
    worker.start()
    assert started.wait(2)
    assert connection.stop().availability == A.DISCONNECTED
    worker.join(2)
    assert not worker.is_alive() and not results[0].transport_connected
    assert transports[0].cleaned == 1


def test_cross_session_request_cannot_use_transport() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    other = ProbeProtocolSession(device_id="android-ffffffffffff", device_epoch=0)
    request = other.create_request(O.HEARTBEAT, current_device_epoch=0)
    assert (
        transports[0].request(request, timeout_seconds=1, cancellation=threading.Event()).status
        == T.PROTOCOL_VIOLATION
    )
    assert transports[0].operations == [O.HELLO, O.GET_CAPABILITIES]
    connection.stop()


@pytest.mark.parametrize(
    "listing",
    ["", "OTHER_DEVICE tcp:42123 localabstract:other", SERIAL + " tcp:42123 localabstract:other"],
)
def test_teardown_never_removes_another_forward(
    monkeypatch: pytest.MonkeyPatch, listing: str
) -> None:
    bridge, calls = bridge_outputs(monkeypatch, [(0, "42123"), (0, listing)])
    port = bridge.forward(BOOTSTRAP)
    with pytest.raises(ConnectionError):
        bridge.remove_forward(port)
    assert len(calls) == 2
    assert not any("--remove" in call for call in calls)


@pytest.mark.parametrize(
    "raw",
    [b"{", b'{"a":1,"a":2}', b'{"protocol_version":2}', b"x" * 65537],
    ids=["malformed", "duplicate", "future", "oversized"],
)
def test_authenticated_hostile_bytes_fail_closed(raw: bytes) -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    transports[0]._exchange = lambda *args, **kwargs: ProbeTransportReply(T.RECEIVED, raw)  # type: ignore[method-assign]
    assert not connection.heartbeat().transport_connected
    assert transports[0].cleaned == 1


@pytest.mark.parametrize("bad_signer", [True, False])
def test_trust_enrollment_verifies_signature_and_fixed_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_signer: bool
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"fabricated-apk")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    calls: list[list[str]] = []

    def tool(args: list[str], **kwargs: Any) -> BoundedOutput:
        calls.append(args)
        if len(calls) == 1:
            digest = "c" * 64 if bad_signer else "b" * 64
            return BoundedOutput(
                0, ("Signer #1 certificate SHA-256 digest: " + digest + "\r\n").encode()
            )
        return BoundedOutput(
            0,
            b"package: name='org.vector.probe' versionCode='1' versionName='0.1.0' platformBuildVersionName='15'\napplication-debuggable\n",
        )

    monkeypatch.setattr(trust_build, "capture", tool)
    if bad_signer:
        with pytest.raises(ValueError, match="signature verification failed"):
            trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)
        assert len(calls) == 1
    else:
        artifact = trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)
        assert artifact.signer_sha256 == "b" * 64
        assert len(calls) == 2
        assert all(call[-1] == str(build / "app-debug.apk") for call in calls)


@pytest.mark.parametrize("value", [b"{", b"x" * 4097, b'{"apk_sha256":"wrong"}'])
def test_invalid_trust_record_never_enables_probe(tmp_path: Path, value: bytes) -> None:
    from vector_agent.probe.trust_build import load_trusted_artifact

    path = tmp_path / "trust.json"
    path.write_bytes(value)
    assert load_trusted_artifact(path) is None


def test_stop_never_force_stops_untrusted_package() -> None:
    connection, _, bridge, _ = lifecycle()
    bridge.discover.return_value = ProbeState(availability=A.UNTRUSTED)
    assert connection.stop(stop_app=True).availability == A.UNTRUSTED
    bridge.stop.assert_not_called()


def test_device_removed_during_discovery_prevents_launch() -> None:
    connection, manager, bridge, _ = lifecycle()

    def discover(artifact: Any) -> ProbeState:
        manager.mark_platform_offline(Platform.ANDROID)
        return discovered()

    bridge.discover.side_effect = discover
    assert connection.launch().availability == A.DISCONNECTED
    bridge.launch.assert_not_called()


def test_demo_service_never_opens_a_real_or_synthetic_probe() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager, enabled=False)
    with pytest.raises(ValueError):
        service.connection(manager.list_sessions()[0].device_id)
    assert not service._connections
    service.close()


def test_cleanup_failure_remains_visible() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()

    def broken_cleanup() -> None:
        raise ConnectionError("private tool output")

    transports[0]._cleanup = broken_cleanup  # type: ignore[method-assign]
    assert connection.stop().availability == A.ERROR
    assert connection.state().reason == R.TOOL_ERROR
    assert not connection.state().transport_connected


def test_bootstrap_not_started_vs_restricted(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge, _ = bridge_outputs(monkeypatch, [(1, ""), (0, "")])
    assert bridge.bootstrap() == "NOT_STARTED"

    bridge, _ = bridge_outputs(monkeypatch, [(1, ""), (1, "")])
    assert bridge.bootstrap() == "RESTRICTED"

    bridge, _ = bridge_outputs(monkeypatch, [(0, "EXPIRED")])
    assert bridge.bootstrap() == "EXPIRED"


def test_unreachable_endpoint_maps_to_device_unavailable() -> None:
    connection, _, _, _ = lifecycle()

    def failing_factory(**kwargs: Any) -> Any:
        raise ConnectionError("Probe endpoint unavailable.")

    connection._factory = failing_factory
    res = connection.connect()
    assert res.availability == A.DISCONNECTED
    assert res.reason == R.DEVICE_UNAVAILABLE


def test_transport_closed_maps_to_session_expired() -> None:
    connection, _, _, transports = lifecycle()
    connection.connect()
    transports[0]._exchange = lambda *args, **kwargs: ProbeTransportReply(T.CLOSED)  # type: ignore[method-assign]
    res = connection.heartbeat()
    assert res.availability == A.DISCONNECTED
    assert res.reason == R.SESSION_EXPIRED


def test_service_evicts_dead_records_and_allows_17th_device() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    for i in range(16):
        s = f"FABRICATED_{i:02d}"
        manager.reconcile_android_discovery([AdbDeviceEntry(s, AdbDeviceState.DEVICE, {})])
        dev_id = [x for x in manager.list_sessions() if x.raw_serial == s][0].device_id
        conn = service.connection(dev_id)
        conn.stop()

    s17 = "FABRICATED_17"
    manager.reconcile_android_discovery([AdbDeviceEntry(s17, AdbDeviceState.DEVICE, {})])
    dev17_id = [x for x in manager.list_sessions() if x.raw_serial == s17][0].device_id
    conn17 = service.connection(dev17_id)
    assert conn17._live()
    service.close()


def test_get_probe_state_does_not_allocate_worker_or_connection() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    dev_id = manager.list_sessions()[0].device_id
    state = service.get_state(dev_id)
    assert state.availability == A.DISCONNECTED
    assert state.reason == R.STOPPED
    assert len(service._connections) == 0
    assert len(service._workers) == 0
    service.close()


def test_service_prunes_exited_workers_and_dead_records() -> None:
    import time

    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    dev_id = manager.list_sessions()[0].device_id
    service.connection(dev_id)
    assert dev_id in service._connections
    manager.mark_platform_offline(Platform.ANDROID)
    for _ in range(25):
        time.sleep(0.05)
        with service._lock:
            service._prune_locked()
            if dev_id not in service._connections:
                break
    assert dev_id not in service._connections
    assert dev_id not in service._workers
    service.close()


def test_service_preserves_live_connections() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    s1, s2 = "FABRICATED_A", "FABRICATED_B"
    manager.reconcile_android_discovery(
        [
            AdbDeviceEntry(s1, AdbDeviceState.DEVICE, {}),
            AdbDeviceEntry(s2, AdbDeviceState.DEVICE, {}),
        ]
    )
    d1 = [x for x in manager.list_sessions() if x.raw_serial == s1][0].device_id
    d2 = [x for x in manager.list_sessions() if x.raw_serial == s2][0].device_id
    c1 = service.connection(d1)
    c2 = service.connection(d2)
    assert c1._live() and c2._live()
    assert len(service._connections) == 2
    service.close()


def test_concurrent_worker_retirement_does_not_remove_replacement_connection() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    dev_id = manager.list_sessions()[0].device_id
    c1 = service.connection(dev_id)
    assert c1._live()
    # Invalidate c1
    c1._cancel.set()
    assert not c1._live()
    # Allocating connection again stops dead c1 and installs c2 without retirement races
    c2 = service.connection(dev_id)
    assert c2 is not c1
    assert c2._live()
    assert service._connections.get(dev_id) is c2
    service.close()


def test_service_rejects_17th_device_when_16_connections_remain_live() -> None:
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    entries = [
        AdbDeviceEntry(f"FABRICATED_DEV_{i:02d}", AdbDeviceState.DEVICE, {}) for i in range(17)
    ]
    manager.reconcile_android_discovery(entries)

    conns = []
    for i in range(16):
        s = f"FABRICATED_DEV_{i:02d}"
        dev_id = [x for x in manager.list_sessions() if x.raw_serial == s][0].device_id
        c = service.connection(dev_id)
        assert c._live()
        conns.append((dev_id, c))

    s17 = "FABRICATED_DEV_16"
    dev17_id = [x for x in manager.list_sessions() if x.raw_serial == s17][0].device_id

    # 17th device must be rejected when 16 live connections genuinely exist
    with pytest.raises(ValueError, match="Probe connection limit reached"):
        service.connection(dev17_id)

    # All 16 original connections remain intact and live
    for _, c in conns:
        assert c._live()

    # When 1 of the 16 is retired:
    _, retired_conn = conns[0]
    retired_conn.stop()
    assert not retired_conn._live()

    # 17th device is now admitted
    c17 = service.connection(dev17_id)
    assert c17._live()
    service.close()


def test_probe_service_lock_not_contended_across_devices() -> None:
    """A blocked operation on device A does not block status/allocation for device B."""
    _, manager, _, _ = lifecycle()
    service = ProbeService(manager)
    s_a, s_b = "FABRICATED_DEV_A", "FABRICATED_DEV_B"
    manager.reconcile_android_discovery(
        [
            AdbDeviceEntry(s_a, AdbDeviceState.DEVICE, {}),
            AdbDeviceEntry(s_b, AdbDeviceState.DEVICE, {}),
        ]
    )
    dev_a = [x for x in manager.list_sessions() if x.raw_serial == s_a][0].device_id
    dev_b = [x for x in manager.list_sessions() if x.raw_serial == s_b][0].device_id

    conn_a = service.connection(dev_a)
    assert conn_a._live()

    import threading
    import time

    a_in_op = threading.Event()
    a_release = threading.Event()

    def blocked_a_op() -> None:
        with conn_a._operation:
            a_in_op.set()
            a_release.wait(timeout=5)

    thread_a = threading.Thread(target=blocked_a_op)
    thread_a.start()
    assert a_in_op.wait(timeout=2)

    # Device A's connection lock is held. Device B must NOT be blocked.
    b_start = time.monotonic()
    state_b = service.get_state(dev_b)
    assert state_b.availability == A.DISCONNECTED
    conn_b = service.connection(dev_b)
    assert conn_b._live()
    b_elapsed = time.monotonic() - b_start

    assert b_elapsed < 1.0

    a_release.set()
    thread_a.join(timeout=2)
    service.close()


def test_connection_error_reports_session_changed_when_ownership_invalidated() -> None:
    """When ownership is invalidated during launch, SESSION_CHANGED wins over ConnectionError."""
    _, manager, _, _ = lifecycle()
    owner = manager.list_sessions()[0]
    bridge = AndroidProbeBridge(serial=owner.raw_serial or "", adb_path="adb")
    conn = ProbeConnection(manager, owner, bridge, None)

    # Invalidate ownership (simulate session change during execution)
    manager.probe_owner_epoch(owner)
    owner.session_epoch += 1

    def mock_action() -> ProbeState:
        raise ConnectionError("ADB transport lost")

    res = conn._guarded(mock_action)
    assert res.availability == A.DISCONNECTED
    assert res.reason == R.SESSION_CHANGED
    assert res.reason != R.DEVICE_UNAVAILABLE


def test_connection_error_reports_device_unavailable_when_ownership_valid() -> None:
    """When ownership remains valid, genuine ConnectionError reports DEVICE_UNAVAILABLE."""
    _, manager, _, _ = lifecycle()
    owner = manager.list_sessions()[0]
    bridge = AndroidProbeBridge(serial=owner.raw_serial or "", adb_path="adb")
    conn = ProbeConnection(manager, owner, bridge, None)

    assert conn._live()

    def mock_action() -> ProbeState:
        raise ConnectionError("device offline")

    res = conn._guarded(mock_action)
    assert res.availability == A.DISCONNECTED
    assert res.reason == R.DEVICE_UNAVAILABLE
    assert res.reason != R.SESSION_CHANGED


@pytest.mark.parametrize(
    "mutate_fn",
    [
        lambda h: h.update(protocol_versions=[2]),
        lambda h: h.update(version_code=2),
        lambda h: h.update(supported_operations=["HELLO", "GET_CAPABILITIES"]),
        lambda h: h.update(protocol_versions=[99]),
    ],
    ids=["protocol_mismatch", "version_code_mismatch", "missing_heartbeat", "future_protocol"],
)
def test_hello_negatives_exact_rejection(mutate_fn: Any) -> None:
    connection, _, _, transports = lifecycle()
    original_factory = connection._factory

    def factory(**kwargs: Any) -> ProbeTransport:
        transport = original_factory(**kwargs)
        original_exchange = transport._exchange

        def exchange(request: ProbeRequestEnvelope, **options: Any) -> ProbeTransportReply:
            if request.operation != O.HELLO:
                return original_exchange(request, **options)
            data = control_response(request)
            mutate_fn(data["hello"])
            return ProbeTransportReply(T.RECEIVED, wire(data))

        transport._exchange = exchange  # type: ignore[method-assign]
        return transport

    connection._factory = factory
    res = connection.connect()
    assert res.availability == A.INSTALLED_INCOMPATIBLE
    assert res.reason == R.VERSION_NOT_SUPPORTED


def test_transport_reflected_request_mac_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    req = session.create_request(O.HELLO, current_device_epoch=3)
    payload = req.model_dump_json().encode("utf-8")
    reflected_mac = hmac.digest(BOOTSTRAP.key, b"request\0" + payload, "sha256")
    frame = struct.pack("!I", len(payload)) + reflected_mac + payload
    peer.sendall(frame)
    res = transport.request(req, timeout_seconds=1, cancellation=threading.Event())
    assert res.status == T.AUTHENTICATION_FAILURE
    transport.close()
    peer.close()


def test_transport_zero_length_frame_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    req = session.create_request(O.HELLO, current_device_epoch=3)
    peer.sendall(b"\x00\x00\x00\x00")
    res = transport.request(req, timeout_seconds=1, cancellation=threading.Event())
    assert res.status == T.BOUNDS_VIOLATION
    transport.close()
    peer.close()


def test_transport_truncated_frame_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    req = session.create_request(O.HELLO, current_device_epoch=3)
    peer.sendall(b"\x00\x00\x00\x10")
    peer.close()
    res = transport.request(req, timeout_seconds=1, cancellation=threading.Event())
    assert res.status == T.UNAVAILABLE
    transport.close()


def test_transport_mid_read_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    client, peer = socket.socketpair()
    bridge = MagicMock(spec=AndroidProbeBridge)
    bridge.forward.return_value = 45678
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: client)
    session = ProbeProtocolSession(device_id="android-0123456789ab", device_epoch=3)
    transport = AdbProbeTransport(
        session=session, current_device_epoch=lambda: 3, bridge=bridge, bootstrap=BOOTSTRAP
    )
    req = session.create_request(O.HELLO, current_device_epoch=3)
    cancel = threading.Event()
    threading.Timer(0.05, cancel.set).start()
    res = transport.request(req, timeout_seconds=1, cancellation=cancel)
    assert res.status == T.CANCELLED
    transport.close()
    peer.close()


def test_trust_enrollment_zero_or_multiple_signers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"apk-content")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)

    monkeypatch.setattr(
        trust_build, "capture", lambda args, **kw: BoundedOutput(0, b"No signers found\n")
    )
    with pytest.raises(ValueError, match="signature verification failed"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)

    multi = (
        b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
        b"Signer #2 certificate SHA-256 digest: " + ("c" * 64).encode() + b"\n"
    )
    monkeypatch.setattr(trust_build, "capture", lambda args, **kw: BoundedOutput(0, multi))
    with pytest.raises(ValueError, match="signature verification failed"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


def test_trust_enrollment_apksigner_nonzero_rc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"apk-content")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    out = b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
    monkeypatch.setattr(trust_build, "capture", lambda args, **kw: BoundedOutput(1, out))
    with pytest.raises(ValueError, match="signature verification failed"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


def test_trust_enrollment_non_debuggable_apk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"apk-content")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    calls = []

    def mock_capture(args: list[str], **kw: Any) -> BoundedOutput:
        calls.append(args)
        if len(calls) == 1:
            return BoundedOutput(
                0, b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
            )
        return BoundedOutput(
            0, b"package: name='org.vector.probe' versionCode='1' versionName='0.1.0'\n"
        )

    monkeypatch.setattr(trust_build, "capture", mock_capture)
    with pytest.raises(ValueError, match="metadata rejected"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


def test_trust_enrollment_bad_version_or_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"apk-content")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    calls = []

    def mock_capture(args: list[str], **kw: Any) -> BoundedOutput:
        calls.append(args)
        if len(calls) == 1:
            return BoundedOutput(
                0, b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
            )
        return BoundedOutput(
            0,
            b"package: name='wrong.package' versionCode='1' versionName='0.1.0'\napplication-debuggable\n",
        )

    monkeypatch.setattr(trust_build, "capture", mock_capture)
    with pytest.raises(ValueError, match="metadata rejected"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


@pytest.mark.parametrize(
    "bad_aapt2",
    [
        b"package: name='org.vector.probe' versionCode='99' versionName='0.1.0'\napplication-debuggable\n",
        b"package: name='org.vector.probe' versionCode='1' versionName='9.9.9'\napplication-debuggable\n",
    ],
    ids=["bad_version_code", "bad_version_name"],
)
def test_trust_enrollment_bad_version_code_and_version_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_aapt2: bytes
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    (build / "app-debug.apk").write_bytes(b"apk-content")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    calls: list[list[str]] = []

    def mock_capture(args: list[str], **kw: Any) -> BoundedOutput:
        calls.append(args)
        if len(calls) == 1:
            return BoundedOutput(
                0, b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
            )
        return BoundedOutput(0, bad_aapt2)

    monkeypatch.setattr(trust_build, "capture", mock_capture)
    with pytest.raises(ValueError, match="metadata rejected"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


def test_trust_enrollment_apk_hash_changed_during_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.probe import trust_build

    build = tmp_path / "android-probe/app/build/outputs/apk/debug"
    build.mkdir(parents=True)
    apk = build / "app-debug.apk"
    apk.write_bytes(b"apk-content-before")
    monkeypatch.setattr(trust_build, "REPOSITORY", tmp_path)
    calls = []

    def mock_capture(args: list[str], **kw: Any) -> BoundedOutput:
        calls.append(args)
        if len(calls) == 1:
            apk.write_bytes(b"apk-content-after-mutation")
            return BoundedOutput(
                0, b"Signer #1 certificate SHA-256 digest: " + ("b" * 64).encode() + b"\n"
            )
        return BoundedOutput(
            0,
            b"package: name='org.vector.probe' versionCode='1' versionName='0.1.0'\napplication-debuggable\n",
        )

    monkeypatch.setattr(trust_build, "capture", mock_capture)
    with pytest.raises(ValueError, match="changed during verification"):
        trust_build.verify_build(tmp_path / "sdk", tmp_path / "java.exe", "b" * 64)


def test_literal_golden_protocol_vector_and_hmac() -> None:
    literal_request_json = b'{"protocol_version":1,"probe_session_id":"01234567-89ab-4def-8123-456789abcdef","device_epoch":3,"binding":null,"nonce":"0123456789012345678901234567890123456789012","sequence_number":0,"issued_at":"2026-10-07T12:00:00Z","expires_at":"2026-10-07T12:00:30Z","operation":"HELLO"}'
    key = bytes(range(1, 33))
    req_mac = hmac.digest(key, b"request\0" + literal_request_json, "sha256")
    assert req_mac.hex() == "c5b088693199230918954638aa46a91283b63f1bcdc9bf55e6e05272847af5c4"

    envelope = ProbeRequestEnvelope.model_validate_json(literal_request_json)
    assert envelope.protocol_version == 1
    assert envelope.operation == O.HELLO
    assert envelope.sequence_number == 0
    assert envelope.nonce == "0123456789012345678901234567890123456789012"
    # Production request serializer produces the literal expected request JSON bytes
    assert envelope.model_dump_json().encode("utf-8") == literal_request_json

    literal_response_json = b'{"protocol_version":1,"probe_session_id":"01234567-89ab-4def-8123-456789abcdef","device_epoch":3,"binding":null,"nonce":"0123456789012345678901234567890123456789012","sequence_number":0,"issued_at":"2026-10-07T12:00:00Z","expires_at":"2026-10-07T12:00:30Z","operation":"HELLO","status":"OK","probe_build":null,"hello":{"application_version":"0.1.0","version_code":1,"protocol_versions":[1],"supported_operations":["HELLO","GET_CAPABILITIES","HEARTBEAT"],"api_level":26},"observations":[],"capabilities":[]}'
    res_mac = hmac.digest(key, b"response\0" + literal_response_json, "sha256")
    assert res_mac.hex() == "0257b677dd2f7cb049206292c0b4688e3e92d55d1b06003a10045a82f20a79a5"

    from vector_agent.probe.protocol import parse_response

    # Production response parser accepts the literal response
    parsed_res = parse_response(literal_response_json)
    assert parsed_res.status == "OK"
    assert parsed_res.hello is not None
    assert parsed_res.hello.application_version == "0.1.0"
    assert parsed_res.hello.version_code == 1
    assert parsed_res.hello.protocol_versions == (1,)
    assert parsed_res.hello.supported_operations == (
        O.HELLO,
        O.GET_CAPABILITIES,
        O.HEARTBEAT,
    )
