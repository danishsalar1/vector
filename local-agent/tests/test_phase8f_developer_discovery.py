"""Stage 2B-3 closure: the developer-only LIVE Probe console obeys the agent's evidence rule.

``probe/developer.discover`` used to mark every Android session OFFLINE on any adb error and
to treat unrecognised output as "no devices". It now reconciles ONLY a trustworthy listing
(the agent's own ``list_attached_devices`` predicate) and leaves sessions, states and epochs
untouched otherwise, while saying so once per transition without exposing device data.

All data is fabricated; no adb runs.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.test_phase8f_discovery_consistency import (
    NO_DEVICE,
    ONE_DEVICE,
    OTHER_ONLY,
    UNAUTHORIZED,
    UNCERTAIN_ANSWERS,
    FakeAdb,
)
from tests.test_phase8f_presence import OTHER, SERIAL
from vector_agent.devices.android import bridge as bridge_module
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.models.device import ConnectionState, DeviceAuthorizationState
from vector_agent.probe.developer import discover, refresh_discovery, run_command


class RecordingAdb(FakeAdb):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[list[str]] = []

    def run(self, cmd: list[str], timeout: float = 5.0, **kwargs: Any) -> Any:
        self.commands.append(list(cmd))
        assert 0 < timeout <= 5.0  # bounded
        return super().run(cmd, timeout=timeout, **kwargs)


@pytest.fixture
def adb() -> Iterator[RecordingAdb]:
    fake = RecordingAdb()
    with (
        patch.object(AndroidDeviceBridge, "_require_adb", lambda self: "adb"),
        patch.object(bridge_module, "run_command", side_effect=fake.run),
    ):
        yield fake


@pytest.fixture
def manager(adb: RecordingAdb) -> DeviceSessionManager:
    m = DeviceSessionManager()
    adb.set_listing(ONE_DEVICE)
    assert discover(m, "adb") is True
    assert m.list_sessions()[0].connection_state == ConnectionState.CONNECTED
    return m


def _snapshot(m: DeviceSessionManager) -> list[tuple[Any, ...]]:
    return [
        (id(s), s.connection_state, s.authorization_state, s.session_epoch, s.raw_serial)
        for s in m.list_sessions()
    ]


# ------------------------------------------------------------------------- uncertain evidence


@pytest.mark.parametrize("name", list(UNCERTAIN_ANSWERS))
def test_uncertain_discovery_preserves_sessions_and_epochs(
    adb: RecordingAdb, manager: DeviceSessionManager, name: str
) -> None:
    before = _snapshot(manager)
    adb.answer = UNCERTAIN_ANSWERS[name]
    for _ in range(5):  # repeated failures must not accumulate epoch advances either
        assert discover(manager, "adb") is False
    assert _snapshot(manager) == before


def test_missing_adb_executable_is_uncertain(manager: DeviceSessionManager) -> None:
    before = _snapshot(manager)
    with (
        patch.object(AndroidDeviceBridge, "_require_adb", side_effect=FileNotFoundError("x")),
    ):
        assert discover(manager, "adb") is False
    assert _snapshot(manager) == before


@pytest.mark.parametrize("error", [OSError("x"), ValueError("x"), TimeoutError("x")])
def test_a_failure_while_reconciling_is_uncertain_not_offline(
    manager: DeviceSessionManager, error: Exception
) -> None:
    before = _snapshot(manager)
    with patch.object(manager, "reconcile_android_discovery", side_effect=error):
        assert discover(manager, "adb") is False
    assert _snapshot(manager) == before


def test_no_uncertain_path_can_ever_call_the_platform_wide_offline_marker(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    boom = MagicMock(side_effect=AssertionError("platform marked offline on uncertainty"))
    with patch.object(manager, "mark_platform_offline", boom):
        for answer in UNCERTAIN_ANSWERS.values():
            adb.answer = answer
            discover(manager, "adb")
        with patch.object(manager, "reconcile_android_discovery", side_effect=OSError("x")):
            discover(manager, "adb")
    assert boom.call_count == 0


# ------------------------------------------------------------------------- trustworthy evidence


def test_valid_empty_listing_is_genuine_absence(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    session = manager.list_sessions()[0]
    epoch = session.session_epoch
    adb.set_listing(NO_DEVICE)
    assert discover(manager, "adb") is True
    assert session.connection_state == ConnectionState.OFFLINE
    assert session.session_epoch == epoch + 1


def test_valid_empty_listing_with_no_known_devices_is_simply_empty(adb: RecordingAdb) -> None:
    m = DeviceSessionManager()
    adb.set_listing(NO_DEVICE)
    assert discover(m, "adb") is True
    assert m.list_sessions() == []


def test_unauthorized_listing_is_genuine(adb: RecordingAdb, manager: DeviceSessionManager) -> None:
    session = manager.list_sessions()[0]
    adb.set_listing(UNAUTHORIZED)
    assert discover(manager, "adb") is True
    assert session.connection_state == ConnectionState.UNAUTHORIZED
    assert session.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED


def test_present_listing_keeps_the_same_epoch(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    before = _snapshot(manager)
    assert discover(manager, "adb") is True
    assert _snapshot(manager) == before


def test_reconnect_after_genuine_absence_starts_a_new_epoch(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    session = manager.list_sessions()[0]
    adb.set_listing(NO_DEVICE)
    discover(manager, "adb")
    lost = session.session_epoch
    adb.set_listing(ONE_DEVICE)
    discover(manager, "adb")
    assert session.connection_state == ConnectionState.CONNECTED
    assert session.session_epoch > lost


def test_another_phone_never_replaces_the_known_session(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    original = manager.list_sessions()[0]
    adb.set_listing(OTHER_ONLY)
    assert discover(manager, "adb") is True
    assert original.connection_state == ConnectionState.OFFLINE
    assert original.raw_serial == SERIAL
    other = next(s for s in manager.list_sessions() if s.raw_serial == OTHER)
    assert other is not original and other.device_id != original.device_id


# ------------------------------------------------------------------------- visibility, privacy, security


def test_uncertainty_is_visible_once_per_transition_and_leaks_nothing(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    out = io.StringIO()
    flag = threading.Event()
    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    for _ in range(4):
        assert refresh_discovery(manager, "adb", flag, out) is False
    assert out.getvalue().count("uncertain") == 1  # not repeated every 2 s
    adb.set_listing(ONE_DEVICE)
    assert refresh_discovery(manager, "adb", flag, out) is True
    assert refresh_discovery(manager, "adb", flag, out) is True
    assert out.getvalue().count("recovered") == 1
    # Fixed texts only: no serial, listing, command or exception detail can appear.
    assert out.getvalue() == (
        "Device discovery is uncertain; device state left unchanged.\nDevice discovery recovered.\n"
    )
    adb.answer = UNCERTAIN_ANSWERS["garbage"]
    refresh_discovery(manager, "adb", flag, out)
    assert out.getvalue().count("uncertain") == 2  # a new transition is reported again


def test_only_the_fixed_bounded_adb_command_is_ever_run(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    for answer in (NO_DEVICE, UNCERTAIN_ANSWERS["garbage"], ONE_DEVICE):
        if isinstance(answer, str):
            adb.set_listing(answer)
        else:
            adb.answer = answer
        discover(manager, "adb")
    assert {tuple(c) for c in adb.commands} == {("adb", "devices", "-l")}


def test_console_commands_still_see_the_preserved_device(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    adb.answer = UNCERTAIN_ANSWERS["timeout"]
    discover(manager, "adb")
    selected, text = run_command(["devices"], manager=manager, service=MagicMock(), selected=None)
    session = manager.list_sessions()[0]
    assert selected is None
    assert session.device_id in text and "CONNECTED" in text
    assert SERIAL not in text  # opaque ids only


def test_session_object_is_the_same_after_uncertainty(
    adb: RecordingAdb, manager: DeviceSessionManager
) -> None:
    session: DeviceSession = manager.list_sessions()[0]
    adb.answer = UNCERTAIN_ANSWERS["daemon-restart"]
    discover(manager, "adb")
    assert manager.get_session(session.device_id) is session
