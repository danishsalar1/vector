"""Phase 8F Stage 2B-3 integration correction: discovery and presence must agree.

Before: ``GET /devices`` marked a platform OFFLINE (epoch advanced) whenever a provider
returned ERROR/UNAVAILABLE or an unrecognised answer, which could fail a running scan that
the independent presence monitor correctly treated as UNCERTAIN.

Rule now: only a TRUSTWORTHY listing may change a session. A timeout, missing tool, tool
error or malformed/incomplete answer leaves sessions (state, epoch, serial) exactly as last
committed and is reported through ``provider_statuses``; the public listing then shows such a
device as UNKNOWN instead of presenting stale data as verified connectivity.

Everything is fabricated; no ADB or iOS tool runs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.test_phase8f_presence import OTHER, SERIAL, Hardware, World, _failed
from vector_agent.api.devices import DiscoveryUncertainError, _trigger_discovery
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.android.bridge import (
    AdbDeviceState,
    AndroidDeviceBridge,
)
from vector_agent.devices.ios.bridge import IOSDiscoveryResult, IOSToolchainStatus
from vector_agent.devices.session import DeviceSession, device_session_manager
from vector_agent.main import create_app
from vector_agent.models.device import (
    ConnectedDevice,
    ConnectionState,
    DeviceAuthorizationState,
    DiagnosticStatus,
    Platform,
)
from vector_agent.scan import ScanLifecycleState
from vector_agent.security.subprocess_policy import CommandResult

HEADER = "List of devices attached\n"
ONE_DEVICE = f"{HEADER}{SERIAL}\tdevice product:x model:y\n"
NO_DEVICE = f"{HEADER}\n"
OTHER_ONLY = f"{HEADER}{OTHER}\tdevice product:x model:y\n"
UNAUTHORIZED = f"{HEADER}{SERIAL}\tunauthorized\n"

UNCERTAIN_ANSWERS: dict[str, Any] = {
    "tool-error": CommandResult(
        ["adb"], return_code=1, stdout="", stderr="failed", duration_seconds=0.1
    ),
    "tool-error-with-header": CommandResult(
        ["adb"], return_code=1, stdout=HEADER, stderr="protocol fault", duration_seconds=0.1
    ),
    "timeout": ADBCommandTimeoutError(command="adb devices -l", timeout=10.0),
    "os-error": OSError("fabricated"),
    "empty-output": CommandResult(
        ["adb"], return_code=0, stdout="", stderr="", duration_seconds=0.1
    ),
    "garbage": CommandResult(
        ["adb"], return_code=0, stdout="garbage\n", stderr="", duration_seconds=0.1
    ),
    "no-header-with-device": CommandResult(
        ["adb"], return_code=0, stdout=f"{SERIAL}\tdevice\n", stderr="", duration_seconds=0.1
    ),
    "daemon-restart": CommandResult(
        ["adb"],
        return_code=0,
        stdout=f"* daemon not running; starting now at tcp:5037\n* daemon started successfully\n{HEADER}\n",
        stderr="",
        duration_seconds=0.1,
    ),
    "truncated": CommandResult(
        ["adb"], return_code=0, stdout=ONE_DEVICE, stderr="", duration_seconds=0.1, truncated=True
    ),
}


class FakeAdb:
    """Swappable answer for 'adb devices -l'; every other adb call returns empty success."""

    def __init__(self) -> None:
        self.answer: Any = CommandResult(
            ["adb"], return_code=0, stdout=ONE_DEVICE, stderr="", duration_seconds=0.1
        )
        self.on_present: Callable[[], None] | None = None

    def set_listing(self, stdout: str) -> None:
        self.answer = CommandResult(
            ["adb"], return_code=0, stdout=stdout, stderr="", duration_seconds=0.1
        )

    def run(self, cmd: list[str], timeout: float = 5.0, **kwargs: Any) -> CommandResult:
        if "devices" in cmd and "-l" in cmd:
            if isinstance(self.answer, BaseException):
                raise self.answer
            return self.answer  # type: ignore[no-any-return]
        return CommandResult(cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01)


@pytest.fixture
def adb() -> Iterator[FakeAdb]:
    device_session_manager._sessions.clear()
    fake = FakeAdb()
    ios = MagicMock()
    ios.is_available.return_value = False
    with (
        patch("vector_agent.devices.android.bridge.run_command", side_effect=fake.run),
        patch("shutil.which", return_value="C:\\tools\\adb.exe"),
        patch("vector_agent.api.devices._get_ios_bridge", return_value=ios),
    ):
        yield fake
    device_session_manager._sessions.clear()


def _seeded(adb: FakeAdb) -> DeviceSession:
    """One CONNECTED phone, established through real, trustworthy discovery."""
    adb.set_listing(ONE_DEVICE)
    assert _trigger_discovery()["android"] == "AVAILABLE"
    session = device_session_manager.list_sessions()[0]
    assert session.connection_state == ConnectionState.CONNECTED
    return session


IOS_UDID = "00008030-001E4C123456802E"


def _seed_ios() -> DeviceSession:
    """One CONNECTED, authorized iPhone session established through reconcile."""
    device_session_manager.reconcile_ios_discovery(
        [IOS_UDID],
        pair_state_fetcher=lambda u: (
            ConnectionState.CONNECTED,
            DeviceAuthorizationState.AUTHORIZED,
            "ok",
        ),
    )
    return next(s for s in device_session_manager.list_sessions() if s.platform == Platform.IOS)


def _snapshot(s: DeviceSession) -> tuple[Any, ...]:
    return (s.connection_state, s.authorization_state, s.session_epoch, s.raw_serial, id(s))


# ------------------------------------------------------------------------- uncertain failures


@pytest.mark.parametrize("name", list(UNCERTAIN_ANSWERS))
def test_uncertain_discovery_never_changes_a_session(adb: FakeAdb, name: str) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    adb.answer = UNCERTAIN_ANSWERS[name]
    for _ in range(5):  # repeated failures must not accumulate epoch advances
        assert _trigger_discovery()["android"] == "ERROR"
    assert _snapshot(session) == before
    assert device_session_manager.get_session(session.device_id) is session


def test_provider_unavailable_is_reported_and_changes_nothing(adb: FakeAdb) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    with patch("shutil.which", return_value=None):
        assert _trigger_discovery()["android"] == "UNAVAILABLE"
    assert _snapshot(session) == before


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (RuntimeError("fabricated"), "ERROR"),
        (ValueError("fabricated"), "ERROR"),
        (OSError("fabricated"), "UNAVAILABLE"),
        (FileNotFoundError("fabricated"), "UNAVAILABLE"),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, Exception) else v,
)
def test_provider_exceptions_never_change_a_session(
    adb: FakeAdb, error: Exception, status: str
) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    with patch("vector_agent.api.devices._get_android_bridge", side_effect=error):
        assert _trigger_discovery()["android"] == status
    assert _snapshot(session) == before


def test_an_already_offline_session_stays_offline_when_a_provider_is_uncertain(
    adb: FakeAdb,
) -> None:
    session = _seeded(adb)
    adb.set_listing(NO_DEVICE)
    _trigger_discovery()
    assert session.connection_state == ConnectionState.OFFLINE
    before = _snapshot(session)
    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
    listed = client.get("/api/v1/devices").json()["devices"][0]
    assert listed["connection_state"] == "OFFLINE"  # known absent: never softened to UNKNOWN
    assert _snapshot(session) == before


def test_ios_uncertain_outcomes_preserve_ios_sessions() -> None:
    device_session_manager._sessions.clear()
    udid = "00008030-001E4C123456802E"
    try:
        for outcome in (
            IOSDiscoveryResult([], IOSToolchainStatus.ERROR, "usbmuxd died"),
            IOSDiscoveryResult([], IOSToolchainStatus.UNAVAILABLE),
        ):
            device_session_manager.reconcile_ios_discovery(
                [udid],
                pair_state_fetcher=lambda u: (
                    ConnectionState.CONNECTED,
                    DeviceAuthorizationState.AUTHORIZED,
                    "ok",
                ),
            )
            session = device_session_manager.list_sessions()[0]
            before = _snapshot(session)
            ios = MagicMock()
            ios.is_available.return_value = True
            ios.discover_devices_result.return_value = outcome
            android = MagicMock()
            android.discover_devices.return_value = MagicMock(
                adb_available=True, state=AdbDeviceState.NO_DEVICE, trusted=True, devices=[]
            )
            with (
                patch("vector_agent.api.devices._get_ios_bridge", return_value=ios),
                patch("vector_agent.api.devices._get_android_bridge", return_value=android),
            ):
                _trigger_discovery()
            assert _snapshot(session) == before
        with (
            patch("vector_agent.api.devices._get_ios_bridge", side_effect=OSError("x")),
            patch("vector_agent.api.devices._get_android_bridge", side_effect=OSError("x")),
        ):
            _trigger_discovery()
        assert session.connection_state == ConnectionState.CONNECTED
    finally:
        device_session_manager._sessions.clear()


def test_both_providers_uncertain_is_503_and_changes_nothing(adb: FakeAdb) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    ios = MagicMock()
    ios.is_available.return_value = True
    ios.discover_devices_result.return_value = IOSDiscoveryResult(
        [], IOSToolchainStatus.ERROR, "usbmuxd died"
    )
    with patch("vector_agent.api.devices._get_ios_bridge", return_value=ios):
        with pytest.raises(DiscoveryUncertainError):
            _trigger_discovery()
        client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
        assert client.get("/api/v1/devices").status_code == 503
        assert client.get(f"/api/v1/devices/{session.device_id}/capabilities").status_code == 503
    assert _snapshot(session) == before


UNEXPECTED_FAULTS = [
    RuntimeError("PRIVATE_FAULT_MARKER"),
    ValueError("PRIVATE_FAULT_MARKER"),
    KeyError("PRIVATE_FAULT_MARKER"),
    AttributeError("PRIVATE_FAULT_MARKER"),
    OSError("PRIVATE_FAULT_MARKER"),
    AssertionError("PRIVATE_FAULT_MARKER"),
]


@pytest.mark.parametrize("fault", UNEXPECTED_FAULTS, ids=lambda e: type(e).__name__)
def test_unexpected_discovery_exception_preserves_identity_state_and_epoch(
    adb: FakeAdb, fault: Exception
) -> None:
    session = _seeded(adb)
    ios_session = _seed_ios()
    before = _snapshot(session)
    ios_before = _snapshot(ios_session)
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
    with (
        patch("vector_agent.api.devices.logger") as log,
        patch("vector_agent.api.devices._trigger_discovery", side_effect=fault),
    ):
        listing = client.get("/api/v1/devices")
        caps = client.get(f"/api/v1/devices/{session.device_id}/capabilities")
    # The error stays visible (503 + type-only log) ...
    for response in (listing, caps):
        assert response.status_code == 503
        assert response.json() == {"detail": "Device discovery failed."}
        assert "PRIVATE_FAULT_MARKER" not in response.text
    logged = [call.args for call in log.error.call_args_list]
    assert len(logged) == 2 and all(args[-1] == type(fault).__name__ for args in logged)
    assert "PRIVATE_FAULT_MARKER" not in repr(log.mock_calls)
    # ... but nothing about the phone was concluded.
    assert _snapshot(session) == before
    assert _snapshot(ios_session) == ios_before  # both platforms are left exactly as committed
    assert device_session_manager.get_session(session.device_id) is session


@pytest.mark.parametrize("fault", UNEXPECTED_FAULTS, ids=lambda e: type(e).__name__)
def test_unexpected_ios_provider_exception_changes_no_session(
    adb: FakeAdb, fault: Exception
) -> None:
    android = _seeded(adb)
    ios = _seed_ios()
    before = (_snapshot(android), _snapshot(ios))
    unavailable = isinstance(fault, OSError)
    with patch("vector_agent.api.devices._get_ios_bridge", side_effect=fault):
        statuses = _trigger_discovery()
    assert statuses["ios"] == ("UNAVAILABLE" if unavailable else "ERROR")
    assert (_snapshot(android), _snapshot(ios)) == before


def test_unexpected_exception_inside_the_provider_path_is_reported_and_changes_nothing(
    adb: FakeAdb,
) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    for fault in UNEXPECTED_FAULTS:
        with patch.object(device_session_manager, "reconcile_android_discovery", side_effect=fault):
            assert _trigger_discovery()["android"] in ("ERROR", "UNAVAILABLE")
    assert _snapshot(session) == before


def test_failed_discovery_response_never_claims_fresh_connectivity(adb: FakeAdb) -> None:
    _seeded(adb)
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
    assert client.get("/api/v1/devices").json()["devices"][0]["connection_state"] == "CONNECTED"
    with patch("vector_agent.api.devices._trigger_discovery", side_effect=RuntimeError("x")):
        failed = client.get("/api/v1/devices")
    assert failed.status_code == 503
    assert set(failed.json()) == {"detail"}  # no device list, no connection_state at all


def test_discovery_exception_during_a_scan_does_not_fail_the_scan(adb: FakeAdb) -> None:
    world = _shared_world(adb)
    epoch = world.session.session_epoch
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")

    def frontend_poll_hits_unexpected_exception() -> None:
        with patch("vector_agent.api.devices._trigger_discovery", side_effect=RuntimeError("x")):
            assert client.get("/api/v1/devices").status_code == 503
            assert client.get(f"/api/v1/devices/{world.device_id}/capabilities").status_code == 503

    scan = world.run(
        world.diagnostic("d0"),
        world.diagnostic("d1", action=frontend_poll_hits_unexpected_exception),
        world.diagnostic("d2"),
    )
    assert scan.state == ScanLifecycleState.COMPLETED
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0", "d1", "d2"]
    assert world.session.connection_state == ConnectionState.CONNECTED
    assert world.session.session_epoch == epoch


def test_genuine_unplugging_is_still_detected_after_a_discovery_exception(adb: FakeAdb) -> None:
    world = _shared_world(adb)
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")

    def exception_then_real_unplug() -> None:
        with patch("vector_agent.api.devices._trigger_discovery", side_effect=RuntimeError("x")):
            assert client.get("/api/v1/devices").status_code == 503
        world.hardware.unplug()
        adb.set_listing(NO_DEVICE)
        assert client.get("/api/v1/devices").status_code == 200  # authoritative evidence

    scan = world.run(
        world.diagnostic("d0", action=exception_then_real_unplug), world.diagnostic("d1")
    )
    assert _failed(scan)
    assert world.session.connection_state == ConnectionState.OFFLINE
    assert ("d1", SERIAL) not in world.executed


# ------------------------------------------------------------------------- honest public view


def test_listing_never_presents_preserved_data_as_verified_connectivity(adb: FakeAdb) -> None:
    session = _seeded(adb)
    before = _snapshot(session)
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")

    ok = client.get("/api/v1/devices").json()
    assert ok["provider_statuses"]["android"] == "AVAILABLE"
    assert ok["devices"][0]["connection_state"] == "CONNECTED"

    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    body = client.get("/api/v1/devices").json()
    assert body["provider_statuses"]["android"] == "ERROR"
    listed = body["devices"][0]
    assert listed["connection_state"] == "UNKNOWN"
    assert listed["authorization_state"] == "UNKNOWN"
    assert listed["capability_profile"] is None
    assert listed["device_id"] == session.device_id
    # The stored session is untouched, so a running scan is unaffected.
    assert _snapshot(session) == before

    adb.set_listing(ONE_DEVICE)  # discovery recovers: verified again, same epoch
    again = client.get("/api/v1/devices").json()
    assert again["devices"][0]["connection_state"] == "CONNECTED"
    assert _snapshot(session) == before


def test_public_schema_is_unchanged(adb: FakeAdb) -> None:
    _seeded(adb)
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
    for answer in (ONE_DEVICE, None):
        if answer is None:
            adb.answer = UNCERTAIN_ANSWERS["timeout"]
        else:
            adb.set_listing(answer)
        body = client.get("/api/v1/devices").json()
        assert set(body) == {"devices", "count", "provider_statuses"}
        assert set(body["devices"][0]) == set(ConnectedDevice.model_fields)


def test_other_platforms_and_absent_sessions_are_not_relabelled(adb: FakeAdb) -> None:
    android = _seeded(adb)
    ios_udid = "00008030-001E4C123456802E"
    device_session_manager.reconcile_ios_discovery(
        [ios_udid],
        pair_state_fetcher=lambda u: (
            ConnectionState.CONNECTED,
            DeviceAuthorizationState.AUTHORIZED,
            "ok",
        ),
    )
    ios = next(s for s in device_session_manager.list_sessions() if s.platform == Platform.IOS)
    ios_bridge = MagicMock()
    ios_bridge.is_available.return_value = True
    ios_bridge.discover_devices_result.return_value = IOSDiscoveryResult(
        [ios_udid], IOSToolchainStatus.AVAILABLE
    )
    ios_bridge.validate_pairing.return_value = (
        ConnectionState.CONNECTED,
        DeviceAuthorizationState.AUTHORIZED,
        "ok",
    )
    ios_bridge.get_identity.return_value = None
    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    client = TestClient(create_app(), base_url="http://127.0.0.1:8742")
    with patch("vector_agent.api.devices._get_ios_bridge", return_value=ios_bridge):
        devices = {d["device_id"]: d for d in client.get("/api/v1/devices").json()["devices"]}
    assert devices[android.device_id]["connection_state"] == "UNKNOWN"
    assert devices[ios.device_id]["connection_state"] == "CONNECTED"  # isolated provider, verified

    adb.set_listing(NO_DEVICE)  # a trustworthy "gone" is an honest OFFLINE, not UNKNOWN
    with patch("vector_agent.api.devices._get_ios_bridge", return_value=ios_bridge):
        devices = {d["device_id"]: d for d in client.get("/api/v1/devices").json()["devices"]}
    assert devices[android.device_id]["connection_state"] == "OFFLINE"


# ------------------------------------------------------------------------- genuine changes still apply


def test_genuine_disconnection_updates_the_session(adb: FakeAdb) -> None:
    session = _seeded(adb)
    epoch = session.session_epoch
    adb.set_listing(NO_DEVICE)
    assert _trigger_discovery()["android"] == "AVAILABLE"
    assert session.connection_state == ConnectionState.OFFLINE
    assert session.session_epoch == epoch + 1


def test_genuine_unauthorized_updates_the_session(adb: FakeAdb) -> None:
    session = _seeded(adb)
    adb.set_listing(UNAUTHORIZED)
    _trigger_discovery()
    assert session.connection_state == ConnectionState.UNAUTHORIZED
    assert session.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED


def test_reconnection_after_a_real_disconnect_starts_a_new_epoch(adb: FakeAdb) -> None:
    session = _seeded(adb)
    adb.set_listing(NO_DEVICE)
    _trigger_discovery()
    lost_epoch = session.session_epoch
    adb.set_listing(ONE_DEVICE)
    _trigger_discovery()
    assert session.connection_state == ConnectionState.CONNECTED
    assert session.session_epoch > lost_epoch


# ------------------------------------------------------------------------- bridge trust flag


def _bridge(adb: FakeAdb) -> AndroidDeviceBridge:
    return AndroidDeviceBridge()


def test_bridge_flags_untrustworthy_answers_without_changing_their_state(adb: FakeAdb) -> None:
    for name in ("empty-output", "garbage", "no-header-with-device", "daemon-restart", "truncated"):
        adb.answer = UNCERTAIN_ANSWERS[name]
        result = _bridge(adb).discover_devices()
        assert result.trusted is False, name
    for stdout, state in (
        (ONE_DEVICE, AdbDeviceState.DEVICE),
        (NO_DEVICE, AdbDeviceState.NO_DEVICE),
    ):
        adb.set_listing(stdout)
        result = _bridge(adb).discover_devices()
        assert result.trusted is True and result.state == state


# ------------------------------------------------------------------------- scan interaction


def _shared_world(adb: FakeAdb) -> World:
    """A World whose manager is the global one that ``GET /devices`` discovery mutates."""
    device_session_manager._sessions.clear()
    world = World(manager=device_session_manager)
    world.session.raw_serial = SERIAL
    return world


def test_transient_adb_error_during_a_scan_no_longer_fails_it(adb: FakeAdb) -> None:
    world = _shared_world(adb)
    epoch = world.session.session_epoch

    def frontend_poll_hits_adb_error() -> None:
        adb.answer = UNCERTAIN_ANSWERS["timeout"]
        _trigger_discovery()

    scan = world.run(
        world.diagnostic("d0"),
        world.diagnostic("d1", action=frontend_poll_hits_adb_error),
        world.diagnostic("d2"),
    )
    assert scan.state == ScanLifecycleState.COMPLETED
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0", "d1", "d2"]
    assert world.session.connection_state == ConnectionState.CONNECTED
    assert world.session.session_epoch == epoch
    assert all(r.status == DiagnosticStatus.PASS for r in scan.diagnostic_results)


@pytest.mark.parametrize("name", ["timeout", "garbage", "daemon-restart", "tool-error"])
def test_every_uncertain_provider_outcome_keeps_the_scan_running(adb: FakeAdb, name: str) -> None:
    world = _shared_world(adb)

    def poll() -> None:
        adb.answer = UNCERTAIN_ANSWERS[name]
        _trigger_discovery()

    scan = world.run(world.diagnostic("d0", action=poll), world.diagnostic("d1", action=poll))
    assert scan.state == ScanLifecycleState.COMPLETED


def test_genuine_disconnection_via_polling_still_fails_the_scan_and_keeps_evidence(
    adb: FakeAdb,
) -> None:
    world = _shared_world(adb)

    def unplug_and_poll() -> None:
        world.hardware.unplug()
        adb.set_listing(NO_DEVICE)
        _trigger_discovery()

    scan = world.run(
        world.diagnostic("d0"),
        world.diagnostic("d1", action=unplug_and_poll),
        world.diagnostic("d2"),
    )
    assert _failed(scan)
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0"]
    assert ("d2", SERIAL) not in world.executed


def test_device_swap_never_retargets_the_scan(adb: FakeAdb) -> None:
    world = _shared_world(adb)
    original_id = world.device_id

    def swap() -> None:
        world.hardware.attached = {OTHER: AdbDeviceState.DEVICE}
        adb.set_listing(OTHER_ONLY)
        _trigger_discovery()  # frontend discovery sees only the new phone

    scan = world.run(
        world.diagnostic("d0", action=swap), world.diagnostic("d1"), world.diagnostic("d2")
    )
    assert _failed(scan)
    assert scan.device_id == original_id
    assert {serial for _, serial in world.executed} == {SERIAL}  # never executed on the other phone
    other = next(s for s in device_session_manager.list_sessions() if s.raw_serial == OTHER)
    assert other.device_id != original_id and other.connection_state == ConnectionState.CONNECTED
    assert world.session.connection_state == ConnectionState.OFFLINE


def test_concurrent_frontend_polling_and_scan_do_not_deadlock_or_fail_it(adb: FakeAdb) -> None:
    world = _shared_world(adb)
    stop = threading.Event()
    errors: list[BaseException] = []
    answers = ["timeout", "garbage", "tool-error", "daemon-restart"]

    def poll() -> None:
        i = 0
        try:
            while not stop.is_set():
                adb.answer = UNCERTAIN_ANSWERS[answers[i % len(answers)]]
                _trigger_discovery()
                i += 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    pollers = [threading.Thread(target=poll, daemon=True) for _ in range(2)]
    for t in pollers:
        t.start()
    box: dict[str, Any] = {}
    runner = threading.Thread(
        target=lambda: box.update(scan=world.run(*[world.diagnostic(f"d{i}") for i in range(8)])),
        daemon=True,
    )
    runner.start()
    runner.join(20)
    stop.set()
    for t in pollers:
        t.join(5)
    assert not runner.is_alive(), "scan deadlocked against frontend polling"
    assert not errors
    assert box["scan"].state == ScanLifecycleState.COMPLETED
    assert world.session.session_epoch == 0
    assert world.session.connection_state == ConnectionState.CONNECTED


# ------------------------------------------------------------------------- last-diagnostic boundary


def test_unplug_during_the_last_diagnostic_no_longer_reads_as_a_completed_scan() -> None:
    world = World()
    scan = world.run(world.diagnostic("d0"), world.diagnostic("d1", action=world.hardware.unplug))
    assert _failed(scan)
    # Evidence collected while the phone was attached is kept, as for any mid-scan loss.
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0", "d1"]
    assert all(r.status == DiagnosticStatus.PASS and r.evidence for r in scan.diagnostic_results)
    assert world.session.connection_state == ConnectionState.OFFLINE


def test_final_verification_is_one_bounded_probe_and_uncertainty_does_not_fail_the_scan() -> None:
    world = World()
    world.hardware.mode = "error"
    scan = world.run(*[world.diagnostic(f"d{i}") for i in range(6)])
    assert scan.state == ScanLifecycleState.COMPLETED
    assert (
        world.hardware.calls == 6 + 1
    )  # one pre-check each + ONE terminal check, none after clean results
    assert world.session.session_epoch == 0


def test_final_verification_adds_no_probe_when_presence_checking_is_off() -> None:
    world = World()
    world.run(world.diagnostic("d0"), presence=False)
    assert world.hardware.calls == 0
    assert isinstance(world.hardware, Hardware)
