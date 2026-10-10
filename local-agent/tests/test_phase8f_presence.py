"""Phase 8F Stage 2B-3: reliable mid-scan device presence detection.

The scan backend must notice, by itself and without any client polling ``GET /devices``,
that the physical device bound to an active scan is gone, while never promoting uncertainty
(ADB errors, timeouts, flapping answers) to a "confirmed disconnect".

Everything here is fabricated: serials, listings and diagnostics. No ADB or iOS tool runs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vector_agent.core.config import AgentSettings
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.android import bridge as bridge_module
from vector_agent.devices.android.bridge import (
    AdbDeviceEntry,
    AdbDeviceState,
    AndroidDeviceBridge,
)
from vector_agent.devices.ios.bridge import IOSDiscoveryResult, IOSToolchainStatus
from vector_agent.devices.presence import (
    AdbPresenceProvider,
    DevicePresenceMonitor,
    IosPresenceProvider,
    PresenceObservation,
    PresenceStatus,
    PresenceVerdict,
)
from vector_agent.devices.session import DeviceSession, DeviceSessionManager
from vector_agent.diagnostics.definition import DiagnosticDefinition
from vector_agent.diagnostics.registry import DiagnosticRegistry
from vector_agent.main import create_app
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    ScanMode,
    VerificationLevel,
)
from vector_agent.scan import (
    DiagnosticEventType,
    ScanLifecycleState,
    ScanOrchestrator,
    ScanPlan,
    ScanSession,
    scan_service,
)

SERIAL = "FABRICATED_PRESENCE_A"
OTHER = "FABRICATED_PRESENCE_B"
NOW = datetime.now(UTC)


# ------------------------------------------------------------------------- fabricated world


class Hardware:
    """What 'adb devices' would currently say. ``mode`` models the tool, not the phone."""

    def __init__(self) -> None:
        self.attached: dict[str, AdbDeviceState] = {SERIAL: AdbDeviceState.DEVICE}
        self.mode = "ok"  # ok | error | timeout | junk
        self.calls = 0
        self.timeouts: list[float] = []
        self.script: list[Any] | None = None  # optional per-call override: list[dict | None]

    def listing(self, timeout: float) -> list[AdbDeviceEntry] | None:
        self.calls += 1
        self.timeouts.append(timeout)
        if self.script:
            step = self.script.pop(0)
            if step is None:
                return None
            return [AdbDeviceEntry(s, st, {}) for s, st in step.items()]
        if self.mode != "ok":
            return None
        return [AdbDeviceEntry(s, st, {}) for s, st in self.attached.items()]

    def unplug(self) -> None:
        self.attached.pop(SERIAL, None)


class FakeAdbBridge:
    def __init__(self, hardware: Hardware) -> None:
        self._hardware = hardware

    def list_attached_devices(self, timeout: float = 3.0) -> list[AdbDeviceEntry] | None:
        return self._hardware.listing(timeout)

    def discover_devices(self) -> Any:  # pragma: no cover - must never be used by presence
        raise AssertionError("presence checks must not run full discovery")


class World:
    def __init__(self, manager: DeviceSessionManager | None = None, **monitor_options: Any) -> None:
        self.manager = manager if manager is not None else DeviceSessionManager()
        self.manager.reconcile_android_discovery(
            [AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})]
        )
        self.session: DeviceSession = self.manager.list_sessions()[0]
        self.device_id = self.session.device_id
        self.hardware = Hardware()
        options: dict[str, Any] = {
            "present_cache_seconds": 0.0,
            "uncertain_cooldown_seconds": 0.0,
            "confirm_interval_seconds": 0.0,
            "sleep": lambda seconds: None,
        }
        options.update(monitor_options)
        self.monitor = DevicePresenceMonitor(
            self.manager,
            {Platform.ANDROID: AdbPresenceProvider(lambda: FakeAdbBridge(self.hardware))},  # type: ignore[arg-type,return-value]
            **options,
        )
        self.executed: list[tuple[str, str]] = []

    def diagnostic(
        self,
        diagnostic_id: str,
        status: DiagnosticStatus = DiagnosticStatus.PASS,
        action: Callable[[], None] | None = None,
    ) -> Any:
        world = self

        class Diag:
            definition = DiagnosticDefinition(
                diagnostic_id=diagnostic_id,
                name=diagnostic_id,
                category="system",
                verification_level=VerificationLevel.RUNTIME_DETECTION,
                supported_platforms=frozenset({Platform.ANDROID}),
            )

            def is_supported(self, platform: Platform) -> bool:
                return True

            def execute(self, *, device_id: str, serial: str) -> DiagnosticResult:
                world.executed.append((diagnostic_id, serial))
                if action is not None:
                    action()
                evidence = (
                    [
                        EvidenceRecord(
                            diagnostic_id=diagnostic_id,
                            device_id=device_id,
                            source_type=EvidenceSourceType.ADB_SHELL,
                            source_name="fabricated",
                            collection_method="fabricated",
                            raw_value="v",
                        )
                    ]
                    if status in (DiagnosticStatus.PASS, DiagnosticStatus.DEGRADED)
                    else []
                )
                return DiagnosticResult(
                    diagnostic_id=diagnostic_id,
                    diagnostic_name=diagnostic_id,
                    category="system",
                    status=status,
                    automation_level=self.definition.automation_level,
                    evidence=evidence,
                    summary=f"result {diagnostic_id}",
                    started_at=NOW,
                    completed_at=NOW,
                    duration_seconds=0.01,
                )

        return Diag()

    def run(self, *diagnostics: Any, presence: bool = True) -> ScanSession:
        registry = DiagnosticRegistry()
        for d in diagnostics:
            registry.register(d)
        plan = ScanPlan(
            device_id=self.device_id,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=tuple(d.definition.diagnostic_id for d in diagnostics),
            planning_session_epoch=self.session.session_epoch,
        )
        scan = ScanSession(device_id=self.device_id, plan=plan)
        scan.transition_to(ScanLifecycleState.PLANNED)
        ScanOrchestrator(
            self.manager, registry, presence=self.monitor if presence else None
        ).run_scan(scan)
        return scan


@pytest.fixture
def world() -> World:
    return World()


def _failed(scan: ScanSession) -> bool:
    return scan.state == ScanLifecycleState.FAILED and (
        scan.events[-1].event_type == DiagnosticEventType.SCAN_FAILED
    )


# ------------------------------------------------------------------------- scan scenarios


def test_phone_connected_throughout_completes_with_bounded_probes(
    world: World,
) -> None:
    diags = [world.diagnostic(f"d{i}") for i in range(5)]
    epoch = world.session.session_epoch
    scan = world.run(*diags)
    assert scan.state == ScanLifecycleState.COMPLETED
    assert [r.diagnostic_id for r in scan.diagnostic_results] == [f"d{i}" for i in range(5)]
    assert world.session.connection_state == ConnectionState.CONNECTED
    assert world.session.session_epoch == epoch
    # No excessive ADB load: one probe before each diagnostic, none after clean ones, plus
    # a single terminal verification for the whole scan.
    assert world.hardware.calls == 5 + 1
    assert all(t == 3.0 for t in world.hardware.timeouts)


def test_phone_disconnected_before_the_first_diagnostic(world: World) -> None:
    world.hardware.unplug()
    scan = world.run(world.diagnostic("d0"), world.diagnostic("d1"))
    assert _failed(scan)
    assert scan.diagnostic_results == []
    assert world.executed == []  # nothing ran against a phone that is gone
    assert world.session.connection_state == ConnectionState.OFFLINE
    assert "disconnected" in (scan.error or "").lower()


def test_phone_disconnected_between_diagnostics_preserves_completed_evidence(
    world: World,
) -> None:
    first = world.diagnostic("d0", action=lambda: None)
    unplug_after = world.diagnostic("d1", action=world.hardware.unplug)  # returns a clean PASS
    never = world.diagnostic("d2")
    scan = world.run(first, unplug_after, never)
    assert _failed(scan)
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0", "d1"]
    assert all(r.status == DiagnosticStatus.PASS and r.evidence for r in scan.diagnostic_results)
    assert ("d2", SERIAL) not in world.executed
    evidence_events = [
        e for e in scan.events if e.event_type == DiagnosticEventType.DIAGNOSTIC_EVIDENCE
    ]
    assert len(evidence_events) == 2
    assert scan.events[-1].diagnostic_id == "d2"


def test_phone_disconnected_while_a_diagnostic_is_running(world: World) -> None:
    ok = world.diagnostic("d0")
    broken = world.diagnostic("d1", status=DiagnosticStatus.ERROR, action=world.hardware.unplug)
    never = world.diagnostic("d2")
    scan = world.run(ok, broken, never)
    assert _failed(scan)
    # d0's evidence survives; the in-flight diagnostic is NOT recorded as a hardware result.
    assert [r.diagnostic_id for r in scan.diagnostic_results] == ["d0"]
    assert all(r.status != DiagnosticStatus.FAIL for r in scan.diagnostic_results)
    assert scan.events[-1].event_type == DiagnosticEventType.SCAN_FAILED
    assert scan.events[-1].diagnostic_id == "d1"
    assert ("d2", SERIAL) not in world.executed
    assert world.session.connection_state == ConnectionState.OFFLINE


def test_no_pass_is_ever_fabricated_for_a_lost_device(world: World) -> None:
    world.hardware.unplug()
    scan = world.run(world.diagnostic("d0"))
    assert not any(r.status == DiagnosticStatus.PASS for r in scan.diagnostic_results)
    assert scan.state != ScanLifecycleState.COMPLETED


def test_another_phone_connected_never_takes_over_the_scan(world: World) -> None:
    other_executions: list[str] = []
    world.hardware.attached = {OTHER: AdbDeviceState.DEVICE}  # original gone, another arrives
    scan = world.run(world.diagnostic("d0"), world.diagnostic("d1"))
    assert _failed(scan)
    assert world.executed == []
    assert [s.raw_serial for s in world.manager.list_sessions()] == [SERIAL]
    assert scan.device_id == world.device_id
    assert other_executions == []


def test_another_phone_alongside_the_original_does_not_disturb_the_scan(world: World) -> None:
    world.hardware.attached[OTHER] = AdbDeviceState.DEVICE
    scan = world.run(world.diagnostic("d0"), world.diagnostic("d1"))
    assert scan.state == ScanLifecycleState.COMPLETED
    assert {serial for _, serial in world.executed} == {SERIAL}


def test_original_phone_reconnecting_under_a_new_epoch_fails_the_scan(world: World) -> None:
    def replug() -> None:
        # What discovery would record if the same phone dropped and came back.
        world.manager.reconcile_android_discovery([])
        world.manager.reconcile_android_discovery(
            [AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})]
        )

    start_epoch = world.session.session_epoch
    scan = world.run(world.diagnostic("d0", action=replug), world.diagnostic("d1"))
    assert _failed(scan)
    assert world.session.session_epoch > start_epoch
    assert scan.session_epoch == start_epoch  # the scan stayed bound to its own epoch
    assert ("d1", SERIAL) not in world.executed
    assert scan.diagnostic_results == []  # the in-flight result of a changed session is discarded


def test_replaced_session_object_is_not_adopted(world: World) -> None:
    def replace() -> None:
        world.manager.clear()
        world.manager.reconcile_android_discovery(
            [AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})]
        )

    scan = world.run(world.diagnostic("d0", action=replace), world.diagnostic("d1"))
    assert _failed(scan)
    assert ("d1", SERIAL) not in world.executed


def test_replaced_session_object_is_not_adopted_even_without_active_presence(
    world: World,
) -> None:
    def replace() -> None:
        world.manager.clear()
        world.manager.reconcile_android_discovery(
            [AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})]
        )

    scan = world.run(world.diagnostic("d0", action=replace), world.diagnostic("d1"), presence=False)
    assert _failed(scan)
    assert ("d1", SERIAL) not in world.executed
    assert scan.diagnostic_results == []


# ------------------------------------------------------------------------- uncertainty is not loss


@pytest.mark.parametrize("mode", ["error", "timeout", "junk"])
def test_adb_temporarily_unavailable_never_marks_the_device_lost(world: World, mode: str) -> None:
    world.hardware.mode = mode
    epoch = world.session.session_epoch
    scan = world.run(world.diagnostic("d0"), world.diagnostic("d1"))
    assert scan.state == ScanLifecycleState.COMPLETED
    assert world.session.connection_state == ConnectionState.CONNECTED
    assert world.session.session_epoch == epoch


def test_tool_errors_with_failing_diagnostics_are_errors_not_a_disconnect(world: World) -> None:
    world.hardware.mode = "error"
    scan = world.run(
        world.diagnostic("d0", status=DiagnosticStatus.ERROR),
        world.diagnostic("d1", status=DiagnosticStatus.ERROR),
    )
    assert scan.state == ScanLifecycleState.COMPLETED
    assert [r.status for r in scan.diagnostic_results] == [DiagnosticStatus.ERROR] * 2
    assert world.session.connection_state == ConnectionState.CONNECTED


def test_flapping_listing_is_uncertain_not_a_confirmed_disconnect(world: World) -> None:
    present = {SERIAL: AdbDeviceState.DEVICE}
    world.hardware.script = [{}, present]  # absent once, present on the confirmation
    scan = world.run(world.diagnostic("d0"))
    assert scan.state == ScanLifecycleState.COMPLETED
    assert world.session.connection_state == ConnectionState.CONNECTED


def test_a_failing_confirmation_probe_is_uncertain_not_a_confirmed_disconnect(
    world: World,
) -> None:
    world.hardware.script = [{}, None]  # absent, then the tool fails
    scan = world.run(world.diagnostic("d0"))
    assert scan.state == ScanLifecycleState.COMPLETED
    assert world.session.connection_state == ConnectionState.CONNECTED


def test_a_single_absent_observation_is_never_enough(world: World) -> None:
    world.hardware.script = [{}]
    verdict = DevicePresenceMonitor(
        world.manager,
        {Platform.ANDROID: AdbPresenceProvider(lambda: FakeAdbBridge(world.hardware))},  # type: ignore[arg-type,return-value]
        confirmations=2,
        sleep=lambda s: None,
    ).verify(world.device_id, world.session, world.session.session_epoch)
    assert (
        verdict == PresenceVerdict.UNCERTAIN
    )  # the second probe had nothing scripted: ok->present
    assert world.session.connection_state == ConnectionState.CONNECTED


def test_confirmations_below_two_are_rejected() -> None:
    with pytest.raises(ValueError):
        DevicePresenceMonitor(DeviceSessionManager(), {}, confirmations=1)


def test_unauthorized_and_offline_listings_are_confirmed_by_agreement_only(
    world: World,
) -> None:
    world.hardware.attached[SERIAL] = AdbDeviceState.UNAUTHORIZED
    start = world.session.session_epoch
    assert world.monitor.verify(world.device_id, world.session, start) == PresenceVerdict.LOST
    assert world.session.connection_state == ConnectionState.UNAUTHORIZED
    assert world.session.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
    assert world.session.session_epoch == start + 1

    other = World()
    other.hardware.script = [
        {SERIAL: AdbDeviceState.UNAUTHORIZED},
        {SERIAL: AdbDeviceState.OFFLINE},  # disagreeing states are not sufficient evidence
    ]
    assert (
        other.monitor.verify(other.device_id, other.session, other.session.session_epoch)
        == PresenceVerdict.UNCERTAIN
    )
    assert other.session.connection_state == ConnectionState.CONNECTED


def test_unsupported_platform_has_no_mechanism_and_stays_uncertain() -> None:
    w = World()
    monitor = DevicePresenceMonitor(w.manager, {}, sleep=lambda s: None)
    assert (
        monitor.verify(w.device_id, w.session, w.session.session_epoch) == PresenceVerdict.UNCERTAIN
    )
    assert w.session.connection_state == ConnectionState.CONNECTED


def test_provider_exceptions_are_uncertain_and_never_leak_the_serial(
    caplog: pytest.LogCaptureFixture,
) -> None:
    w = World()

    class Exploding:
        def observe(self, serial: str, timeout: float) -> PresenceObservation:
            raise RuntimeError(f"boom {serial}")

    monitor = DevicePresenceMonitor(w.manager, {Platform.ANDROID: Exploding()})
    with caplog.at_level("DEBUG"):
        verdict = monitor.verify(w.device_id, w.session, w.session.session_epoch)
    assert verdict == PresenceVerdict.UNCERTAIN
    assert SERIAL not in caplog.text
    assert w.session.connection_state == ConnectionState.CONNECTED


# ------------------------------------------------------------------------- manager binding


def test_mark_device_lost_is_bound_to_session_epoch_serial_and_state(world: World) -> None:
    m, s = world.manager, world.session
    args = {"expected_session": s, "expected_epoch": s.session_epoch, "expected_serial": SERIAL}
    assert not m.mark_device_lost(
        world.device_id, **{**args, "expected_epoch": 99}, new_state=ConnectionState.OFFLINE
    )  # type: ignore[arg-type]
    assert not m.mark_device_lost(
        world.device_id, **{**args, "expected_serial": OTHER}, new_state=ConnectionState.OFFLINE
    )  # type: ignore[arg-type]
    stranger = DeviceSession(
        device_id=world.device_id,
        platform=Platform.ANDROID,
        connection_state=ConnectionState.CONNECTED,
        last_seen=NOW,
        raw_serial=SERIAL,
    )
    assert not m.mark_device_lost(
        world.device_id, **{**args, "expected_session": stranger}, new_state=ConnectionState.OFFLINE
    )  # type: ignore[arg-type]
    assert s.connection_state == ConnectionState.CONNECTED
    with pytest.raises(ValueError):
        m.mark_device_lost(world.device_id, **args, new_state=ConnectionState.CONNECTED)  # type: ignore[arg-type]
    assert m.mark_device_lost(world.device_id, **args, new_state=ConnectionState.OFFLINE)  # type: ignore[arg-type]
    assert not m.mark_device_lost(world.device_id, **args, new_state=ConnectionState.OFFLINE)  # type: ignore[arg-type]


def test_lost_device_reconnects_under_a_fresh_epoch_via_discovery(world: World) -> None:
    world.hardware.unplug()
    world.monitor.verify(world.device_id, world.session, world.session.session_epoch)
    lost_epoch = world.session.session_epoch
    world.manager.reconcile_android_discovery([AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})])
    assert world.session.connection_state == ConnectionState.CONNECTED
    assert world.session.session_epoch > lost_epoch


def test_only_the_bound_device_is_changed(world: World) -> None:
    world.manager.reconcile_android_discovery(
        [
            AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {}),
            AdbDeviceEntry(OTHER, AdbDeviceState.DEVICE, {}),
        ]
    )
    other = next(s for s in world.manager.list_sessions() if s.raw_serial == OTHER)
    other_epoch = other.session_epoch
    world.hardware.attached = {OTHER: AdbDeviceState.DEVICE}
    assert (
        world.monitor.verify(world.device_id, world.session, world.session.session_epoch)
        == PresenceVerdict.LOST
    )
    assert other.connection_state == ConnectionState.CONNECTED
    assert other.session_epoch == other_epoch


def test_already_changed_session_is_lost_without_probing(world: World) -> None:
    epoch = world.session.session_epoch
    world.manager.mark_platform_offline(Platform.ANDROID)
    assert world.monitor.verify(world.device_id, world.session, epoch) == PresenceVerdict.LOST
    assert world.hardware.calls == 0


# ------------------------------------------------------------------------- rate limiting


def test_present_answers_are_cached_briefly_and_uncertain_ones_cool_down() -> None:
    clock = SimpleNamespace(now=100.0)
    w = World(present_cache_seconds=1.0, uncertain_cooldown_seconds=5.0)
    w.monitor._monotonic = lambda: clock.now  # type: ignore[method-assign]
    epoch = w.session.session_epoch
    assert w.monitor.verify(w.device_id, w.session, epoch) == PresenceVerdict.PRESENT
    assert w.monitor.verify(w.device_id, w.session, epoch) == PresenceVerdict.PRESENT
    assert w.hardware.calls == 1
    clock.now += 1.5
    assert w.monitor.verify(w.device_id, w.session, epoch) == PresenceVerdict.PRESENT
    assert w.hardware.calls == 2
    w.hardware.mode = "error"
    clock.now += 1.5
    assert w.monitor.verify(w.device_id, w.session, epoch) == PresenceVerdict.UNCERTAIN
    calls = w.hardware.calls
    clock.now += 1.0
    assert w.monitor.verify(w.device_id, w.session, epoch) == PresenceVerdict.UNCERTAIN
    assert w.hardware.calls == calls  # cooling down: no ADB hammering while it is failing
    clock.now += 5.0
    w.monitor.verify(w.device_id, w.session, epoch)
    assert w.hardware.calls == calls + 1


def test_monitor_state_is_bounded() -> None:
    manager = DeviceSessionManager()
    monitor = DevicePresenceMonitor(manager, {}, sleep=lambda s: None)
    for i in range(500):
        monitor._remember(f"android-{i:012x}", 0, PresenceVerdict.PRESENT)
    assert len(monitor._recent) <= 64


# ------------------------------------------------------------------------- independence / concurrency


def test_detection_does_not_depend_on_frontend_polling(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vector_agent.api import devices as devices_api

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a client-facing discovery was triggered")

    monkeypatch.setattr(devices_api, "_trigger_discovery", forbidden)
    monkeypatch.setattr(AndroidDeviceBridge, "discover_devices", forbidden)
    scan = world.run(
        world.diagnostic("d0"),
        world.diagnostic("d1", action=world.hardware.unplug),
        world.diagnostic("d2"),
    )
    assert _failed(scan)
    assert world.session.connection_state == ConnectionState.OFFLINE


def test_provider_runs_outside_every_manager_lock(world: World) -> None:
    observed: list[bool] = []

    class Probe:
        def observe(self, serial: str, timeout: float) -> PresenceObservation:
            done = threading.Event()
            threading.Thread(
                target=lambda: (world.manager.get_session(world.device_id), done.set()),
                daemon=True,
            ).start()
            observed.append(done.wait(1.0))  # a held manager lock would block this read
            return PresenceObservation(PresenceStatus.PRESENT)

    monitor = DevicePresenceMonitor(world.manager, {Platform.ANDROID: Probe()})
    assert monitor.verify(world.device_id, world.session, world.session.session_epoch) == (
        PresenceVerdict.PRESENT
    )
    assert observed == [True]


def test_concurrent_discovery_and_an_active_scan_do_not_deadlock(world: World) -> None:
    stop = threading.Event()
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            while not stop.is_set():
                world.manager.reconcile_android_discovery(
                    [AdbDeviceEntry(SERIAL, AdbDeviceState.DEVICE, {})]
                )
                world.manager.list_sessions()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    slow = Hardware()
    slow.attached = world.hardware.attached
    original = slow.listing

    def slow_listing(timeout: float) -> list[AdbDeviceEntry] | None:
        time.sleep(0.01)
        return original(timeout)

    slow.listing = slow_listing  # type: ignore[method-assign]
    world.hardware = slow
    world.monitor._providers[Platform.ANDROID] = AdbPresenceProvider(lambda: FakeAdbBridge(slow))  # type: ignore[arg-type,return-value]
    threads = [threading.Thread(target=hammer, daemon=True) for _ in range(3)]
    for t in threads:
        t.start()
    box: dict[str, ScanSession] = {}
    runner = threading.Thread(
        target=lambda: box.update(scan=world.run(*[world.diagnostic(f"d{i}") for i in range(8)])),
        daemon=True,
    )
    runner.start()
    runner.join(15)
    stop.set()
    for t in threads:
        t.join(5)
    assert not runner.is_alive(), "scan deadlocked against concurrent discovery"
    assert not errors
    assert box["scan"].state == ScanLifecycleState.COMPLETED


def test_unplug_during_concurrent_discovery_still_resolves_the_scan(world: World) -> None:
    stop = threading.Event()

    def hammer() -> None:
        while not stop.is_set():
            world.manager.list_sessions()
            world.manager.get_session(world.device_id)

    t = threading.Thread(target=hammer, daemon=True)
    t.start()
    scan = world.run(world.diagnostic("d0", action=world.hardware.unplug), world.diagnostic("d1"))
    stop.set()
    t.join(5)
    assert _failed(scan)


# ------------------------------------------------------------------------- bridge snapshot trust


def _run_result(stdout: str, rc: int = 0, stderr: str = "", truncated: bool = False) -> Any:
    return SimpleNamespace(return_code=rc, stdout=stdout, stderr=stderr, truncated=truncated)


GOOD = "List of devices attached\nFABRICATED_PRESENCE_A\tdevice product:x model:y\n"


def _bridge(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> AndroidDeviceBridge:
    monkeypatch.setattr(AndroidDeviceBridge, "_require_adb", lambda self: "adb")

    def run(args: Any, *, timeout: float = 10.0, **kwargs: Any) -> Any:
        assert list(args) == ["adb", "devices", "-l"]  # fixed argv only
        assert 0 < timeout <= 10.0
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(bridge_module, "run_command", run)
    return AndroidDeviceBridge()


def test_trusted_listing_returns_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = _bridge(monkeypatch, _run_result(GOOD)).list_attached_devices()
    assert entries is not None and [(e.serial, e.state) for e in entries] == [
        (SERIAL, AdbDeviceState.DEVICE)
    ]


def test_empty_but_trustworthy_listing_is_an_empty_list_not_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _bridge(monkeypatch, _run_result("List of devices attached\n\n")).list_attached_devices()
        == []
    )


@pytest.mark.parametrize(
    "outcome",
    [
        ADBCommandTimeoutError(command="adb devices", timeout=3.0),
        OSError("fabricated"),
        RuntimeError("fabricated"),
        _run_result(GOOD, rc=1),
        _run_result(GOOD, truncated=True),
        _run_result(""),
        _run_result("garbage output\n"),
        _run_result(
            "* daemon not running; starting now at tcp:5037\n* daemon started successfully\nList of devices attached\n"
        ),
        _run_result(
            "List of devices attached\n", stderr="adb server version doesn't match; killing daemon"
        ),
    ],
    ids=[
        "timeout",
        "oserror",
        "runtime",
        "rc1",
        "truncated",
        "empty",
        "junk",
        "daemon-start",
        "daemon-stderr",
    ],
)
def test_untrustworthy_answers_are_none_never_an_empty_device_list(
    monkeypatch: pytest.MonkeyPatch, outcome: Any
) -> None:
    assert _bridge(monkeypatch, outcome).list_attached_devices() is None


def test_missing_adb_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_module.shutil, "which", lambda name: None)
    assert AndroidDeviceBridge().list_attached_devices() is None


def test_timeout_is_forwarded_to_the_bounded_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []
    monkeypatch.setattr(AndroidDeviceBridge, "_require_adb", lambda self: "adb")
    monkeypatch.setattr(
        bridge_module,
        "run_command",
        lambda args, *, timeout=10.0, **kw: (seen.append(timeout), _run_result(GOOD))[1],
    )
    AndroidDeviceBridge().list_attached_devices(timeout=1.25)
    assert seen == [1.25]


@pytest.mark.parametrize("bad", [0, -1, 10.5, 99])
def test_monitor_rejects_unbounded_probe_timeouts(bad: float) -> None:
    with pytest.raises(ValueError):
        DevicePresenceMonitor(DeviceSessionManager(), {}, probe_timeout_seconds=bad)


def test_ios_provider_maps_discovery_results() -> None:
    def provider(result: IOSDiscoveryResult) -> IosPresenceProvider:
        return IosPresenceProvider(
            lambda: SimpleNamespace(discover_devices_result=lambda timeout: result)
        )  # type: ignore[arg-type,return-value]

    udid = "00008030-001A2B3C4D5E6F78"
    ok = IOSToolchainStatus.AVAILABLE
    assert (
        provider(IOSDiscoveryResult([udid], ok)).observe(udid, 3).status == PresenceStatus.PRESENT
    )
    assert provider(IOSDiscoveryResult([], ok)).observe(udid, 3).status == PresenceStatus.ABSENT
    for status in (IOSToolchainStatus.ERROR, IOSToolchainStatus.UNAVAILABLE):
        assert (
            provider(IOSDiscoveryResult([], status)).observe(udid, 3).status
            == PresenceStatus.UNCERTAIN
        )


# ------------------------------------------------------------------------- wiring and non-regression


@pytest.fixture
def clean_service() -> Iterator[None]:
    scan_service.set_presence_monitor(None)
    yield
    scan_service.set_presence_monitor(None)


def test_agent_enables_presence_only_while_running_and_never_in_demo(clean_service: None) -> None:
    assert scan_service._presence is None
    with TestClient(create_app(AgentSettings(_env_file=None)), base_url="http://127.0.0.1:8742"):  # type: ignore[call-arg]
        assert isinstance(scan_service._presence, DevicePresenceMonitor)
    assert scan_service._presence is None

    with TestClient(
        create_app(AgentSettings(_env_file=None, demo_mode=True)), base_url="http://127.0.0.1:8742"
    ):  # type: ignore[call-arg]
        assert scan_service._presence is None
    with TestClient(
        create_app(AgentSettings(_env_file=None, presence_check_enabled=False)),
        base_url="http://127.0.0.1:8742",
    ):  # type: ignore[call-arg]
        assert scan_service._presence is None


def test_presence_settings_are_validated() -> None:
    for bad in (0, 0.1, 11, -3):
        with pytest.raises(ValueError):
            AgentSettings(_env_file=None, presence_probe_timeout_seconds=bad)  # type: ignore[call-arg]
    assert AgentSettings(_env_file=None).presence_probe_timeout_seconds == 3.0  # type: ignore[call-arg]


def test_security_boundary_and_probe_are_unchanged_while_presence_is_active(
    clean_service: None,
) -> None:
    app = create_app(AgentSettings(_env_file=None))  # type: ignore[call-arg]
    with TestClient(app, base_url="http://127.0.0.1:8742") as client:
        assert isinstance(scan_service._presence, DevicePresenceMonitor)
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 403
        post = client.post(
            "/api/v1/scans/plan", json={}, headers={"Origin": "https://evil.example"}
        )
        assert post.status_code == 403
        assert client.get("/api/v1/devices/android-0123456789ab/probe").status_code == 401


def test_orchestrator_without_a_monitor_behaves_exactly_as_before(world: World) -> None:
    world.hardware.unplug()  # nobody checks: previous behaviour relies on the manager alone
    scan = world.run(world.diagnostic("d0"), presence=False)
    assert scan.state == ScanLifecycleState.COMPLETED
    assert world.hardware.calls == 0


def test_scan_service_applies_the_monitor_to_new_orchestrators(clean_service: None) -> None:
    monitor = DevicePresenceMonitor(DeviceSessionManager(), {})
    scan_service.set_presence_monitor(monitor)
    assert scan_service._orchestrator._presence is monitor
    scan_service.set_registry(scan_service.registry)  # rebuilding must keep it
    assert scan_service._orchestrator._presence is monitor
