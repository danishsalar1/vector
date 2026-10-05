"""Orchestration, Planner, End-to-End Scan, Timeout Budget, and Privacy tests for Phase 6.

Validates:
- Central registry integration (create_default_registry() registers all 6 standard diagnostics)
- ScanPlanner compatibility across FULL, CATEGORY, SELECTED, SINGLE_COMPONENT modes
- Generic Android support (unknown compatible models work without catalog)
- Non-Android platform skips all Android diagnostics truthfully
- End-to-end multi-diagnostic scan execution (sequential order, event mappings, evidence contract)
- Mixed terminal statuses (PASS, INCONCLUSIVE, UNSUPPORTED, ERROR) with truthful scan summary
- Trust engine safety (trust_score remains None, status stays NOT_READY)
- Diagnostic timeout budget enforcement
- Strict privacy boundary (fabricated sensitive package names, SSIDs, and serials do not leak)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from vector_agent.devices.android.bridge import (
    AndroidDeviceBridge,
    BatteryTelemetry,
    BatteryTelemetryResult,
)
from vector_agent.devices.android.camera import (
    CameraDeviceEntry,
    CameraInventory,
    CameraInventoryResult,
)
from vector_agent.devices.android.display import DisplayMetrics, DisplayMetricsResult
from vector_agent.devices.android.memory import MemoryTelemetry, MemoryTelemetryResult
from vector_agent.devices.android.storage import (
    StorageTelemetry,
    StorageTelemetryResult,
)
from vector_agent.devices.android.thermal import (
    ThermalSensorSample,
    ThermalTelemetry,
    ThermalTelemetryResult,
)
from vector_agent.devices.session import DeviceSession, device_session_manager
from vector_agent.diagnostics.camera.camera_diagnostic import CameraInventoryDiagnostic
from vector_agent.diagnostics.memory.memory_diagnostic import MemoryTelemetryDiagnostic
from vector_agent.diagnostics.registry import (
    DiagnosticRegistry,
    DuplicateDiagnosticError,
    create_default_registry,
)
from vector_agent.diagnostics.storage.storage_diagnostic import StorageTelemetryDiagnostic
from vector_agent.diagnostics.thermal.thermal_diagnostic import ThermalTelemetryDiagnostic
from vector_agent.models.device import (
    ConnectionState,
    DeviceCapabilityProfile,
    DiagnosticResult,
    DiagnosticStatus,
    Platform,
    ScanMode,
    ScanRequest,
    TrustEngineStatus,
)
from vector_agent.scan import (
    DiagnosticApplicability,
    DiagnosticEvent,
    DiagnosticEventType,
    ScanLifecycleState,
    ScanOrchestrator,
    ScanPlanner,
    ScanSession,
)

_DEVICE_ID = "test-phase6-device-001"
_SERIAL = "SECRET_SERIAL_PHASE6_999"
_NOW = datetime.now(UTC)


def _setup_mock_bridge() -> MagicMock:
    """Build a mock bridge returning valid PASS responses for all 6 diagnostics."""
    bridge = MagicMock(spec=AndroidDeviceBridge)

    bridge.get_battery_telemetry.return_value = BatteryTelemetryResult(
        telemetry=BatteryTelemetry(
            level=85,
            scale=100,
            status="Discharging",
            health="Good",
            plugged="Unplugged",
            voltage_mv=4100,
            temperature_tenths_c=285,
            technology="Li-ion",
            present=True,
            raw_output="battery raw",
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / dumpsys battery",
        collection_method="adb shell dumpsys battery",
        error=None,
        collected_at=_NOW,
    )

    bridge.get_storage_telemetry.return_value = StorageTelemetryResult(
        telemetry=StorageTelemetry(
            total_bytes=100_000_000_000,
            used_bytes=35_000_000_000,
            available_bytes=65_000_000_000,
            utilization_percent=35.0,
            logical_target="/data",
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / df -k /data",
        collection_method="adb shell df -k /data",
        error=None,
        collected_at=_NOW,
    )

    bridge.get_memory_telemetry.return_value = MemoryTelemetryResult(
        telemetry=MemoryTelemetry(
            mem_total_bytes=8_000_000_000,
            mem_free_bytes=1_500_000_000,
            mem_available_bytes=4_500_000_000,
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / /proc/meminfo",
        collection_method="adb shell cat /proc/meminfo",
        error=None,
        collected_at=_NOW,
    )

    bridge.get_thermal_telemetry.return_value = ThermalTelemetryResult(
        telemetry=ThermalTelemetry(
            thermal_status_code=0,
            thermal_status_label="NONE",
            sensor_count=1,
            sensors=[ThermalSensorSample(name="cpu-0", temperature_celsius=36.5, sensor_type="3")],
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / dumpsys thermalservice",
        collection_method="adb shell dumpsys thermalservice",
        error=None,
        collected_at=_NOW,
    )

    bridge.get_display_metrics.return_value = DisplayMetricsResult(
        metrics=DisplayMetrics(
            physical_width=1080,
            physical_height=2400,
            physical_density=440,
            override_width=None,
            override_height=None,
            override_density=None,
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / wm size + wm density",
        collection_method="adb shell wm size; wm density",
        error=None,
        collected_at=_NOW,
    )

    bridge.get_camera_inventory.return_value = CameraInventoryResult(
        inventory=CameraInventory(
            camera_count=2,
            cameras=[
                CameraDeviceEntry(camera_id="0", facing="BACK"),
                CameraDeviceEntry(camera_id="1", facing="FRONT"),
            ],
            collected_at=_NOW,
        ),
        status="PASS",
        confidence=1.0,
        evidence_source="ADB / dumpsys media.camera",
        collection_method="adb shell dumpsys media.camera",
        error=None,
        collected_at=_NOW,
    )

    return bridge


def _setup_device_session(
    device_id: str = _DEVICE_ID,
    platform: Platform = Platform.ANDROID,
    connection_state: ConnectionState = ConnectionState.CONNECTED,
    raw_serial: str = _SERIAL,
) -> DeviceSession:
    """Helper to register and return a connected DeviceSession."""
    device_session_manager.clear()
    session = DeviceSession(
        device_id=device_id,
        platform=platform,
        connection_state=connection_state,
        last_seen=_NOW,
        raw_serial=raw_serial,
        capability_profile=DeviceCapabilityProfile(
            device_id=device_id,
            platform=platform,
            profile_complete=True,
        ),
    )
    device_session_manager._sessions[session.device_id] = session
    return session


# ============================================================
# Registry & Planner Integration Tests
# ============================================================


class TestRegistryAndPlannerIntegration:
    """Verifies that create_default_registry and ScanPlanner behave correctly."""

    def test_default_registry_contains_all_six_diagnostics(self) -> None:
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)

        expected_ids = {
            "battery_telemetry",
            "storage_telemetry",
            "memory_telemetry",
            "thermal_telemetry",
            "display_metrics",
            "camera_inventory",
        }
        registered_ids = set(registry.list_ids())
        assert expected_ids.issubset(registered_ids)
        assert len(registered_ids) == 6

        # Verify duplicate registration is rejected
        diag = registry.get("storage_telemetry")
        assert diag is not None
        with pytest.raises(DuplicateDiagnosticError):
            registry.register(diag)

    def test_full_verification_plans_all_six_on_android(self) -> None:
        session = _setup_device_session()
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION),
        )

        assert len(plan.diagnostics_planned) == 6
        assert len(plan.diagnostics_skipped) == 0
        assert "storage_telemetry" in plan.diagnostics_planned
        assert "memory_telemetry" in plan.diagnostics_planned
        assert "thermal_telemetry" in plan.diagnostics_planned
        assert "display_metrics" in plan.diagnostics_planned
        assert "camera_inventory" in plan.diagnostics_planned
        assert "battery_telemetry" in plan.diagnostics_planned

    def test_category_verification_plans_matching_diagnostic(self) -> None:
        session = _setup_device_session()
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        for cat, expected_id in [
            ("storage", "storage_telemetry"),
            ("memory", "memory_telemetry"),
            ("thermal", "thermal_telemetry"),
            ("display", "display_metrics"),
            ("camera", "camera_inventory"),
            ("battery", "battery_telemetry"),
        ]:
            plan = planner.plan(
                session=session,
                registry=registry,
                request=ScanRequest(
                    device_id=session.device_id,
                    mode=ScanMode.CATEGORY_VERIFICATION,
                    category=cat,
                ),
            )
            assert plan.diagnostics_planned == (expected_id,)
            assert plan.total_planned == 1

    def test_selected_diagnostics_mode(self) -> None:
        session = _setup_device_session()
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        requested = ["storage_telemetry", "camera_inventory"]
        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(
                device_id=session.device_id,
                mode=ScanMode.SELECTED_DIAGNOSTICS,
                diagnostic_ids=requested,
            ),
        )
        assert plan.diagnostics_planned == tuple(requested)

    def test_single_component_mode(self) -> None:
        session = _setup_device_session()
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(
                device_id=session.device_id,
                mode=ScanMode.SINGLE_COMPONENT,
                diagnostic_ids=["display_metrics"],
            ),
        )
        assert plan.diagnostics_planned == ("display_metrics",)

    def test_non_android_platform_skips_all_standard_diagnostics(self) -> None:
        session = _setup_device_session(platform=Platform.IOS)
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION),
        )

        assert len(plan.diagnostics_planned) == 0
        assert len(plan.diagnostics_skipped) == 6
        for item in plan.planned_items:
            assert item.applicability == DiagnosticApplicability.NOT_APPLICABLE
            assert "Platform IOS is not supported" in (item.reason or "")

    def test_unknown_android_model_works_generically(self) -> None:
        session = _setup_device_session(platform=Platform.ANDROID)
        session.identity = None  # No model catalog, unknown device
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION),
        )
        assert len(plan.diagnostics_planned) == 6


# ============================================================
# End-to-End Multi-Diagnostic Scan Execution Tests
# ============================================================


class TestEndToEndMultiDiagnosticScan:
    """Verifies complete multi-diagnostic execution via ScanOrchestrator."""

    def test_full_scan_executes_sequentially_with_all_events(self) -> None:
        session = _setup_device_session()
        bridge = _setup_mock_bridge()
        registry = create_default_registry(bridge)
        planner = ScanPlanner()

        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION),
        )

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)
        orchestrator = ScanOrchestrator(device_session_manager, registry)

        emitted_events: list[DiagnosticEvent] = []
        terminal_session = orchestrator.run_scan(
            scan_session=scan_sess,
            event_callback=emitted_events.append,
        )

        assert terminal_session.state == ScanLifecycleState.COMPLETED
        assert len(terminal_session.diagnostic_results) == 6

        # Check that all results have PASS and evidence
        for res in terminal_session.diagnostic_results:
            assert res.status == DiagnosticStatus.PASS
            assert len(res.evidence) > 0
            assert res.summary is not None
            assert _SERIAL not in res.summary

        # Verify event ordering
        event_types = [e.event_type for e in emitted_events]
        assert event_types[0] == DiagnosticEventType.SCAN_STARTED
        assert event_types[-1] == DiagnosticEventType.SCAN_COMPLETED

        # Check diagnostic started -> completed pairings
        started_events = [
            e for e in emitted_events if e.event_type == DiagnosticEventType.DIAGNOSTIC_STARTED
        ]
        completed_events = [
            e for e in emitted_events if e.event_type == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        ]
        assert len(started_events) == 6
        assert len(completed_events) == 6

        summary = terminal_session.to_summary()
        assert summary.trust_engine_status == TrustEngineStatus.NOT_READY
        assert summary.trust_score is None

    def test_mixed_diagnostic_results_handled_truthfully(self) -> None:
        """Scan with PASS, INCONCLUSIVE, UNSUPPORTED, and ERROR."""
        session = _setup_device_session()
        bridge = _setup_mock_bridge()

        # Storage returns INCONCLUSIVE
        bridge.get_storage_telemetry.return_value = StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source="ADB / df -k /data",
            collection_method="adb shell df -k /data",
            error="Empty df",
            collected_at=_NOW,
        )
        # Thermal returns UNSUPPORTED
        bridge.get_thermal_telemetry.return_value = ThermalTelemetryResult(
            telemetry=None,
            status="UNSUPPORTED",
            confidence=0.0,
            evidence_source="ADB / dumpsys thermalservice",
            collection_method="adb shell dumpsys thermalservice",
            error="Thermalservice absent",
            collected_at=_NOW,
        )
        # Memory raises unexpected exception -> ERROR
        bridge.get_memory_telemetry.side_effect = RuntimeError("Kernel cat failed")

        registry = create_default_registry(bridge)
        planner = ScanPlanner()
        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION),
        )

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)
        orchestrator = ScanOrchestrator(device_session_manager, registry)

        emitted_events: list[DiagnosticEvent] = []
        terminal_session = orchestrator.run_scan(scan_sess, event_callback=emitted_events.append)

        # Whole scan still finishes cleanly in COMPLETED state (diagnostics ran to completion)
        assert terminal_session.state == ScanLifecycleState.COMPLETED
        assert len(terminal_session.diagnostic_results) == 6

        res_by_id: dict[str, DiagnosticResult] = {
            r.diagnostic_id: r for r in terminal_session.diagnostic_results
        }
        assert res_by_id["storage_telemetry"].status == DiagnosticStatus.INCONCLUSIVE
        assert res_by_id["thermal_telemetry"].status == DiagnosticStatus.UNSUPPORTED
        assert res_by_id["memory_telemetry"].status == DiagnosticStatus.ERROR  # NOT hardware FAIL
        assert res_by_id["display_metrics"].status == DiagnosticStatus.PASS
        assert res_by_id["camera_inventory"].status == DiagnosticStatus.PASS
        assert res_by_id["battery_telemetry"].status == DiagnosticStatus.PASS

        # Verify event types for each terminal result
        event_types_by_diag: dict[str, list[DiagnosticEventType]] = {}
        for ev in emitted_events:
            if ev.diagnostic_id:
                event_types_by_diag.setdefault(ev.diagnostic_id, []).append(ev.event_type)

        assert (
            DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE in event_types_by_diag["storage_telemetry"]
        )
        assert (
            DiagnosticEventType.DIAGNOSTIC_COMPLETED in event_types_by_diag["thermal_telemetry"]
        )  # UNSUPPORTED -> completed
        assert (
            DiagnosticEventType.DIAGNOSTIC_FAILED in event_types_by_diag["memory_telemetry"]
        )  # ERROR -> failed
        assert (
            DiagnosticEventType.DIAGNOSTIC_COMPLETED in event_types_by_diag["display_metrics"]
        )  # PASS -> completed

        summary = terminal_session.to_summary()
        assert summary.trust_score is None


# ============================================================
# Timeout Budget Enforcement Tests
# ============================================================


class TestTimeoutBudgetEnforcement:
    """Verifies that execution budget is enforced deterministically across bridge and diagnostics."""

    @pytest.mark.parametrize(
        ("diag_id", "bridge_method_name", "diag_class", "expected_timeout_substr"),
        [
            (
                "storage_telemetry",
                "get_storage_telemetry",
                StorageTelemetryDiagnostic,
                "df command timed out",
            ),
            (
                "memory_telemetry",
                "get_memory_telemetry",
                MemoryTelemetryDiagnostic,
                "cat /proc/meminfo command timed out",
            ),
            (
                "thermal_telemetry",
                "get_thermal_telemetry",
                ThermalTelemetryDiagnostic,
                "dumpsys thermalservice command timed out",
            ),
            (
                "camera_inventory",
                "get_camera_inventory",
                CameraInventoryDiagnostic,
                "dumpsys media.camera command timed out",
            ),
        ],
    )
    def test_single_command_timeout_branch_exercised(
        self,
        diag_id: str,
        bridge_method_name: str,
        diag_class: Any,
        expected_timeout_substr: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verifies real ADBCommandTimeoutError routes to dedicated timeout branch across all single-command diagnostics."""
        from vector_agent.core.errors import ADBCommandTimeoutError

        def fake_run_command(cmd: list[str], timeout: float | None = None) -> Any:
            # Note: ADBCommandTimeoutError requires (command: str, timeout: float)
            raise ADBCommandTimeoutError(
                command=" ".join(cmd),
                timeout=timeout or 15.0,
            )

        monkeypatch.setattr("vector_agent.devices.android.bridge.run_command", fake_run_command)
        bridge = AndroidDeviceBridge(adb_path="adb")
        monkeypatch.setattr(bridge, "_require_adb", lambda: "adb")

        # 1. Direct bridge method test: confirm dedicated timeout branch was taken, not generic fallback
        bridge_method = getattr(bridge, bridge_method_name)
        bridge_res = bridge_method(serial=_SERIAL, timeout=15.0)
        assert bridge_res.status == "ERROR"
        assert bridge_res.error == f"{expected_timeout_substr}."
        assert "TypeError" not in (bridge_res.error or "")
        assert "Exception" not in (bridge_res.error or "")

        # 2. Diagnostic + ScanOrchestrator execution test: confirm safe terminal status and summary
        session = _setup_device_session()
        registry = DiagnosticRegistry()
        registry.register(diag_class(bridge))

        planner = ScanPlanner()
        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(
                device_id=session.device_id,
                mode=ScanMode.SINGLE_COMPONENT,
                diagnostic_ids=[diag_id],
            ),
        )
        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)
        orchestrator = ScanOrchestrator(device_session_manager, registry)
        terminal_session = orchestrator.run_scan(scan_sess)

        assert len(terminal_session.diagnostic_results) == 1
        res = terminal_session.diagnostic_results[0]
        assert res.status == DiagnosticStatus.ERROR
        assert res.status != DiagnosticStatus.FAIL
        assert "hardware" not in (res.summary or "").lower()
        assert "execution error" in (res.summary or "").lower()
        assert "TypeError" not in (res.summary or "")
        assert "Exception" not in (res.summary or "")
        assert _SERIAL not in (res.summary or "")

    @pytest.mark.parametrize("failing_cmd", ["wm_size", "wm_density"])
    def test_display_metrics_timeout_returns_error(
        self,
        failing_cmd: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verifies display metrics fails cleanly with ERROR if either wm size or wm density times out."""
        from vector_agent.core.errors import ADBCommandTimeoutError
        from vector_agent.security.subprocess_policy import CommandResult

        def fake_run_command(cmd: list[str], timeout: float | None = None) -> CommandResult:
            if "size" in cmd:
                if failing_cmd == "wm_size":
                    raise ADBCommandTimeoutError(command=" ".join(cmd), timeout=timeout or 15.0)
                return CommandResult(
                    command=cmd,
                    stdout="Physical size: 1080x2400\n",
                    stderr="",
                    return_code=0,
                    duration_seconds=0.1,
                    truncated=False,
                )
            if "density" in cmd:
                if failing_cmd == "wm_density":
                    raise ADBCommandTimeoutError(command=" ".join(cmd), timeout=timeout or 15.0)
                return CommandResult(
                    command=cmd,
                    stdout="Physical density: 440\n",
                    stderr="",
                    return_code=0,
                    duration_seconds=0.1,
                    truncated=False,
                )
            raise AssertionError(f"Unexpected command {cmd}")

        monkeypatch.setattr("vector_agent.devices.android.bridge.run_command", fake_run_command)
        bridge = AndroidDeviceBridge(adb_path="adb")
        monkeypatch.setattr(bridge, "_require_adb", lambda: "adb")

        res = bridge.get_display_metrics(serial=_SERIAL, timeout=15.0)
        assert res.status == "ERROR"
        assert res.metrics is None
        expected_substr = (
            "wm size command timed out"
            if failing_cmd == "wm_size"
            else "wm density command timed out"
        )
        assert expected_substr in (res.error or "")
        assert "TypeError" not in (res.error or "")
        assert "Exception" not in (res.error or "")

    def test_multi_command_display_metrics_budget_sharing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies that wm size and wm density share a single execution budget."""
        calls: list[tuple[list[str], float]] = []
        simulated_now = 1000.0

        def fake_monotonic() -> float:
            nonlocal simulated_now
            val = simulated_now
            simulated_now += 4.0  # simulate 4.0s elapsed between timing checks
            return val

        from vector_agent.security.subprocess_policy import CommandResult

        def fake_run_command(cmd: list[str], timeout: float | None = None) -> CommandResult:
            calls.append((cmd, timeout or 0.0))
            if "size" in cmd:
                return CommandResult(
                    command=cmd,
                    stdout="Physical size: 1080x2400\n",
                    stderr="",
                    return_code=0,
                    duration_seconds=0.1,
                    truncated=False,
                )
            return CommandResult(
                command=cmd,
                stdout="Physical density: 440\n",
                stderr="",
                return_code=0,
                duration_seconds=0.1,
                truncated=False,
            )

        monkeypatch.setattr("time.monotonic", fake_monotonic)
        monkeypatch.setattr("vector_agent.devices.android.bridge.run_command", fake_run_command)
        bridge = AndroidDeviceBridge(adb_path="adb")
        monkeypatch.setattr(bridge, "_require_adb", lambda: "adb")

        total_budget = 12.0
        res = bridge.get_display_metrics(serial=_SERIAL, timeout=total_budget)
        assert res.status == "PASS"
        assert len(calls) == 2

        cmd1, timeout1 = calls[0]
        assert "size" in cmd1
        assert timeout1 <= total_budget

        cmd2, timeout2 = calls[1]
        assert "density" in cmd2
        # Command 2 received strictly bounded remaining time (budget - elapsed), not a fresh budget!
        assert timeout2 < total_budget
        assert timeout2 <= (total_budget - 4.0) + 0.1

    def test_zero_exhausted_budget_no_command_executed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies no blocking command executes if remaining budget <= 0."""
        calls: list[list[str]] = []

        def fake_run_command(cmd: list[str], timeout: float | None = None) -> Any:
            calls.append(cmd)
            raise AssertionError("run_command must not be called when budget is <= 0")

        monkeypatch.setattr("vector_agent.devices.android.bridge.run_command", fake_run_command)
        bridge = AndroidDeviceBridge(adb_path="adb")
        monkeypatch.setattr(bridge, "_require_adb", lambda: "adb")

        res = bridge.get_display_metrics(serial=_SERIAL, timeout=0.0)
        assert res.status == "ERROR"
        assert "expired" in (res.error or "").lower()
        assert len(calls) == 0


# ============================================================
# Privacy & Redaction Review Tests
# ============================================================


class TestPrivacyAndRedactionReview:
    """Verifies that sensitive data never leaks through the real diagnostic execution pipeline."""

    def test_real_pipeline_privacy_marker_flow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exercises raw dumpsys -> bridge -> parser -> diagnostic -> orchestrator -> events -> summary.

        Proves that fabricated secrets in serial, client sections, and raw stdout/stderr
        are completely discarded and never enter DiagnosticResult, EvidenceRecord,
        DiagnosticEvent, or ScanSummary.
        """
        secret_serial = "SERIAL-SECRET-TEST"
        secret_package = "fake.sensitive.package"
        secret_wifi = "FakeHomeWifi"

        fake_camera_dump = (
            f"# Internal service header containing {secret_serial}\n"
            "== Camera HAL device info: ==\n"
            "Number of camera devices: 1\n"
            "Device 0 (v3.4):\n"
            "    Facing: BACK\n"
            "Active Camera Clients:\n"
            f'    Client[0] (PID 8888, package "{secret_package}")\n'
            f"    Wifi SSID: {secret_wifi}\n"
        )

        from vector_agent.security.subprocess_policy import CommandResult

        def fake_run_command(cmd: list[str], timeout: float | None = None) -> CommandResult:
            return CommandResult(
                command=cmd,
                stdout=fake_camera_dump,
                stderr=f"Harmless note with {secret_package}",
                return_code=0,
                duration_seconds=0.1,
                truncated=False,
            )

        monkeypatch.setattr("vector_agent.devices.android.bridge.run_command", fake_run_command)
        bridge = AndroidDeviceBridge(adb_path="adb")
        monkeypatch.setattr(bridge, "_require_adb", lambda: "adb")

        session = _setup_device_session(
            device_id="test-privacy-device-1",
            raw_serial=secret_serial,
        )
        registry = DiagnosticRegistry()
        from vector_agent.diagnostics.camera.camera_diagnostic import CameraInventoryDiagnostic

        registry.register(CameraInventoryDiagnostic(bridge))

        planner = ScanPlanner()
        plan = planner.plan(
            session=session,
            registry=registry,
            request=ScanRequest(
                device_id=session.device_id,
                mode=ScanMode.SINGLE_COMPONENT,
                diagnostic_ids=["camera_inventory"],
            ),
        )

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)
        orchestrator = ScanOrchestrator(device_session_manager, registry)

        events: list[DiagnosticEvent] = []
        terminal_session = orchestrator.run_scan(scan_sess, event_callback=events.append)
        summary = terminal_session.to_summary()

        # 1. Result must be PASS with genuine normalized EvidenceRecord
        assert len(terminal_session.diagnostic_results) == 1
        result = terminal_session.diagnostic_results[0]
        assert result.status == DiagnosticStatus.PASS
        assert len(result.evidence) >= 1
        assert result.evidence[0].normalized_value == 1.0
        assert result.evidence[0].metadata.get("field") == "camera_device_count"

        # 2. Serialize outputs
        serialized_summary = summary.model_dump_json()
        serialized_plan = plan.model_dump_json()
        serialized_events = json.dumps([e.model_dump(mode="json") for e in events])
        serialized_evidence = json.dumps([ev.model_dump(mode="json") for ev in result.evidence])
        result_summary_text = result.summary or ""

        # 3. Assert secrets are completely absent from summary, evidence, events, and plan
        for secret in (secret_serial, secret_package, secret_wifi):
            assert secret not in result_summary_text
            assert secret not in serialized_evidence
            assert secret not in serialized_summary
            assert secret not in serialized_plan
            assert secret not in serialized_events
