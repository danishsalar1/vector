"""Production tests for Canonical Phase 5.

Scan Orchestration:
- Diagnostic Registry enhancements
- Scan Planner & Request Modes
- Scan Plan immutability and privacy
- Scan Lifecycle & State Transitions
- Diagnostic Event stream (truthful, no fake progress)
- Execution Orchestration
- Stale device / session epoch protection
- Failure semantics (distinguish execution failure vs hardware fail)
- Trust Engine safety (stays NOT_READY, score is None)
- API integration
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from vector_agent.devices.android.bridge import BatteryTelemetry, BatteryTelemetryResult
from vector_agent.devices.session import (
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceSession,
    DeviceUnauthorizedError,
    device_session_manager,
)
from vector_agent.diagnostics.battery.battery_diagnostic import (
    BatteryTelemetryDiagnostic,
)
from vector_agent.diagnostics.definition import (
    DiagnosticDefinition,
)
from vector_agent.diagnostics.registry import (
    DiagnosticRegistry,
)
from vector_agent.main import create_app
from vector_agent.models.device import (
    CapabilityEntry,
    CapabilityStatus,
    ConnectionState,
    DeviceCapabilityProfile,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    ScanMode,
    ScanRequest,
    TrustEngineStatus,
    VerificationLevel,
)
from vector_agent.scan import (
    DeviceScanActiveError,
    DiagnosticApplicability,
    DiagnosticEvent,
    DiagnosticEventType,
    InvalidLifecycleTransitionError,
    InvalidScanRequestError,
    PlannedDiagnostic,
    ScanLifecycleState,
    ScanOrchestrator,
    ScanPlan,
    ScanPlanner,
    ScanService,
    ScanSession,
    UnknownDiagnosticError,
    scan_service,
)

# ============================================================
# Helpers & Mock Diagnostics
# ============================================================

_NOW = datetime.now(UTC)
_DEVICE_ID = "android-test001"
_SERIAL = "FABRICATED_SERIAL_001"


def _make_dummy_evidence(diagnostic_id: str, device_id: str = _DEVICE_ID) -> EvidenceRecord:
    return EvidenceRecord(
        diagnostic_id=diagnostic_id,
        device_id=device_id,
        source_type=EvidenceSourceType.ADB_SHELL,
        source_name="dummy_source",
        collection_method="dummy_method",
        raw_value="test_value",
    )


def _make_scan_plan(
    device_id: str = _DEVICE_ID,
    diagnostics_planned: list[str] | tuple[str, ...] = (),
) -> ScanPlan:
    return ScanPlan(
        device_id=device_id,
        platform=Platform.ANDROID,
        mode=ScanMode.FULL_VERIFICATION,
        diagnostics_planned=tuple(diagnostics_planned),
    )


class DummyDiagnostic:
    """Mock diagnostic implementing Diagnostic protocol."""

    def __init__(
        self,
        defn: DiagnosticDefinition,
        result_status: DiagnosticStatus = DiagnosticStatus.PASS,
        evidence: list[EvidenceRecord] | None = None,
        should_raise: Exception | None = None,
    ) -> None:
        self._defn = defn
        self._status = result_status
        if evidence is not None:
            self._evidence = evidence
        elif result_status in (DiagnosticStatus.PASS, DiagnosticStatus.DEGRADED):
            self._evidence = [_make_dummy_evidence(defn.diagnostic_id)]
        else:
            self._evidence = []
        self._should_raise = should_raise
        self.executed_with: list[dict[str, Any]] = []

    @property
    def definition(self) -> DiagnosticDefinition:
        return self._defn

    def is_supported(self, platform: Platform) -> bool:
        return platform in self._defn.supported_platforms

    def execute(self, *, device_id: str, serial: str) -> DiagnosticResult:
        self.executed_with.append({"device_id": device_id, "serial": serial})
        if self._should_raise:
            raise self._should_raise

        return DiagnosticResult(
            diagnostic_id=self._defn.diagnostic_id,
            diagnostic_name=self._defn.name,
            category=self._defn.category,
            status=self._status,
            automation_level=self._defn.automation_level,
            evidence=list(self._evidence),
            summary=f"Result for {self._defn.diagnostic_id}",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=0.05,
        )


def _make_connected_session(
    device_id: str = _DEVICE_ID,
    serial: str = _SERIAL,
    capabilities: dict[str, CapabilityEntry] | None = None,
    connection_state: ConnectionState = ConnectionState.CONNECTED,
    epoch: int = 0,
) -> DeviceSession:
    profile = None
    if capabilities is not None:
        profile = DeviceCapabilityProfile(
            device_id=device_id,
            platform=Platform.ANDROID,
            capabilities=capabilities,
            profile_complete=True,
        )

    return DeviceSession(
        device_id=device_id,
        platform=Platform.ANDROID,
        connection_state=connection_state,
        last_seen=_NOW,
        raw_serial=serial,
        session_epoch=epoch,
        capability_profile=profile,
    )


@pytest.fixture(autouse=True)
def clean_state() -> None:
    device_session_manager.clear()


# ============================================================
# PART 1 & 24: Diagnostic Registry (Platform-Neutral)
# ============================================================


class TestDiagnosticRegistryEnhancements:
    def test_registry_platform_neutral_definitions(self) -> None:
        """24. registry remains platform-neutral."""
        registry = DiagnosticRegistry()
        defn_android = DiagnosticDefinition(
            diagnostic_id="android_test",
            name="Android Test",
            category="sensors",
            supported_platforms=frozenset({Platform.ANDROID}),
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
        )
        defn_ios = DiagnosticDefinition(
            diagnostic_id="ios_test",
            name="iOS Test",
            category="sensors",
            supported_platforms=frozenset({Platform.IOS}),
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
        )
        defn_both = DiagnosticDefinition(
            diagnostic_id="neutral_test",
            name="Neutral Test",
            category="system",
            supported_platforms=frozenset({Platform.ANDROID, Platform.IOS}),
            verification_level=VerificationLevel.RUNTIME_DETECTION,
        )

        registry.register(DummyDiagnostic(defn_android))
        registry.register(DummyDiagnostic(defn_ios))
        registry.register(DummyDiagnostic(defn_both))

        android_defs = registry.get_definitions_by_platform(Platform.ANDROID)
        ios_defs = registry.get_definitions_by_platform(Platform.IOS)

        assert {d.diagnostic_id for d in android_defs} == {"android_test", "neutral_test"}
        assert {d.diagnostic_id for d in ios_defs} == {"ios_test", "neutral_test"}
        assert len(registry.get_definitions()) == 3

    def test_registry_fields_and_lookup(self) -> None:
        defn = DiagnosticDefinition(
            diagnostic_id="sensor_gyro",
            name="Gyroscope Verification",
            category="sensors",
            supported_platforms=frozenset({Platform.ANDROID}),
            required_capabilities=frozenset({"android.hardware.sensor.gyroscope"}),
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            requires_probe=False,
            prerequisites=frozenset({"sensor_accel"}),
        )
        registry = DiagnosticRegistry()
        registry.register(DummyDiagnostic(defn))

        found = registry.get_definition("sensor_gyro")
        assert found is not None
        assert found.requires_probe is False
        assert found.verification_level == VerificationLevel.FUNCTIONAL_VERIFICATION
        assert "android.hardware.sensor.gyroscope" in found.required_capabilities
        assert "sensor_accel" in found.prerequisites


# ============================================================
# PART 2, 3, 4: Scan Planner & Request Modes
# ============================================================


class TestScanPlannerModes:
    @pytest.fixture
    def setup_registry(self) -> DiagnosticRegistry:
        registry = DiagnosticRegistry()
        # Battery diagnostic (no capability gate)
        registry.register(
            DummyDiagnostic(
                DiagnosticDefinition(
                    diagnostic_id="battery_telemetry",
                    name="Battery Telemetry",
                    category="battery",
                    verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                    supported_platforms=frozenset({Platform.ANDROID}),
                )
            )
        )
        # Gyroscope diagnostic (requires gyro capability)
        registry.register(
            DummyDiagnostic(
                DiagnosticDefinition(
                    diagnostic_id="sensor_gyro",
                    name="Gyroscope Test",
                    category="sensors",
                    verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                    supported_platforms=frozenset({Platform.ANDROID}),
                    required_capabilities=frozenset({"android.hardware.sensor.gyroscope"}),
                )
            )
        )
        # Camera diagnostic (requires camera capability)
        registry.register(
            DummyDiagnostic(
                DiagnosticDefinition(
                    diagnostic_id="camera_back",
                    name="Back Camera Test",
                    category="camera",
                    verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                    supported_platforms=frozenset({Platform.ANDROID}),
                    required_capabilities=frozenset({"android.hardware.camera"}),
                )
            )
        )
        return registry

    def test_full_verification_produces_plan(self, setup_registry: DiagnosticRegistry) -> None:
        """1. Full Verification produces plan from registry + current capabilities."""
        session = _make_connected_session(
            capabilities={
                "android.hardware.sensor.gyroscope": CapabilityEntry(
                    name="android.hardware.sensor.gyroscope",
                    status=CapabilityStatus.PRESENT,
                    verification_level=VerificationLevel.RUNTIME_DETECTION,
                ),
                "android.hardware.camera": CapabilityEntry(
                    name="android.hardware.camera",
                    status=CapabilityStatus.PRESENT,
                    verification_level=VerificationLevel.RUNTIME_DETECTION,
                ),
            }
        )

        planner = ScanPlanner()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session, setup_registry, req)

        assert plan.mode == ScanMode.FULL_VERIFICATION
        assert plan.device_id == _DEVICE_ID
        assert set(plan.diagnostics_planned) == {"battery_telemetry", "sensor_gyro", "camera_back"}
        assert plan.diagnostics_skipped == ()

    def test_category_verification_selects_category_only(
        self, setup_registry: DiagnosticRegistry
    ) -> None:
        """2. Category Verification selects only appropriate category diagnostics."""
        session = _make_connected_session(
            capabilities={
                "android.hardware.sensor.gyroscope": CapabilityEntry(
                    name="android.hardware.sensor.gyroscope",
                    status=CapabilityStatus.PRESENT,
                ),
            }
        )
        planner = ScanPlanner()
        req = ScanRequest(
            device_id=_DEVICE_ID,
            mode=ScanMode.CATEGORY_VERIFICATION,
            category="sensors",
        )
        plan = planner.plan(session, setup_registry, req)

        assert plan.mode == ScanMode.CATEGORY_VERIFICATION
        assert plan.diagnostics_planned == ("sensor_gyro",)
        assert "battery_telemetry" not in plan.diagnostics_planned
        assert "camera_back" not in plan.diagnostics_planned

    def test_selected_diagnostics_honors_requested_ids(
        self, setup_registry: DiagnosticRegistry
    ) -> None:
        """3. Selected Diagnostics honors requested IDs."""
        session = _make_connected_session(
            capabilities={
                "android.hardware.sensor.gyroscope": CapabilityEntry(
                    name="android.hardware.sensor.gyroscope",
                    status=CapabilityStatus.PRESENT,
                ),
            }
        )
        planner = ScanPlanner()
        req = ScanRequest(
            device_id=_DEVICE_ID,
            mode=ScanMode.SELECTED_DIAGNOSTICS,
            diagnostic_ids=["sensor_gyro"],
        )
        plan = planner.plan(session, setup_registry, req)

        assert plan.diagnostics_planned == ("sensor_gyro",)
        assert plan.diagnostics_requested == ("sensor_gyro",)

    def test_single_diagnostic_request_works(self, setup_registry: DiagnosticRegistry) -> None:
        """4. Single diagnostic request works."""
        session = _make_connected_session()
        planner = ScanPlanner()
        req = ScanRequest(
            device_id=_DEVICE_ID,
            mode=ScanMode.SINGLE_COMPONENT,
            diagnostic_ids=["battery_telemetry"],
        )
        plan = planner.plan(session, setup_registry, req)

        assert plan.diagnostics_planned == ("battery_telemetry",)
        assert len(plan.diagnostics_planned) == 1

    def test_unknown_diagnostic_id_fails_truthfully(
        self, setup_registry: DiagnosticRegistry
    ) -> None:
        """5. Unknown diagnostic ID fails truthfully."""
        session = _make_connected_session()
        planner = ScanPlanner()
        req = ScanRequest(
            device_id=_DEVICE_ID,
            mode=ScanMode.SELECTED_DIAGNOSTICS,
            diagnostic_ids=["nonexistent_hardware_test"],
        )
        with pytest.raises(UnknownDiagnosticError) as exc_info:
            planner.plan(session, setup_registry, req)
        assert "nonexistent_hardware_test" in str(exc_info.value)

    def test_unsupported_and_restricted_diagnostics_skipped_with_reason(
        self, setup_registry: DiagnosticRegistry
    ) -> None:
        """6. Unsupported/restricted diagnostics are skipped with reason, not failed."""
        session = _make_connected_session(
            capabilities={
                "android.hardware.sensor.gyroscope": CapabilityEntry(
                    name="android.hardware.sensor.gyroscope",
                    status=CapabilityStatus.ABSENT,
                ),
                "android.hardware.camera": CapabilityEntry(
                    name="android.hardware.camera",
                    status=CapabilityStatus.RESTRICTED,
                ),
            }
        )
        planner = ScanPlanner()
        plan = planner.plan(session, setup_registry, ScanRequest(device_id=_DEVICE_ID))

        # Gyroscope should be skipped as UNSUPPORTED with reason
        assert "sensor_gyro" in plan.diagnostics_skipped
        assert "ABSENT" in plan.skip_reasons["sensor_gyro"]

        # Camera should be skipped as RESTRICTED with reason
        assert "camera_back" in plan.diagnostics_skipped
        assert "RESTRICTED" in plan.skip_reasons["camera_back"]

        # Battery has no capability gate so it is planned
        assert "battery_telemetry" in plan.diagnostics_planned

    def test_not_reported_and_unknown_capability_does_not_create_fail(
        self, setup_registry: DiagnosticRegistry
    ) -> None:
        """7. NOT_REPORTED/UNKNOWN capability does not create diagnostic FAIL."""
        session = _make_connected_session(
            capabilities={
                "android.hardware.sensor.gyroscope": CapabilityEntry(
                    name="android.hardware.sensor.gyroscope",
                    status=CapabilityStatus.NOT_REPORTED,
                ),
                "android.hardware.camera": CapabilityEntry(
                    name="android.hardware.camera",
                    status=CapabilityStatus.UNKNOWN,
                ),
            }
        )
        planner = ScanPlanner()
        plan = planner.plan(session, setup_registry, ScanRequest(device_id=_DEVICE_ID))

        # Check planned_items
        gyro_item = next(p for p in plan.planned_items if p.diagnostic_id == "sensor_gyro")
        camera_item = next(p for p in plan.planned_items if p.diagnostic_id == "camera_back")

        assert gyro_item.applicability == DiagnosticApplicability.UNAVAILABLE
        assert camera_item.applicability == DiagnosticApplicability.UNKNOWN

        # Skipped, but never FAIL
        assert "sensor_gyro" in plan.diagnostics_skipped
        assert "camera_back" in plan.diagnostics_skipped


# ============================================================
# PART 4: Scan Plan Privacy & Immutability
# ============================================================


class TestScanPlanPrivacyAndImmutability:
    def test_plan_contains_opaque_device_id_only(self) -> None:
        """11. plan contains opaque device ID only."""
        session = _make_connected_session(device_id="android-aabbccdd1122", serial="SECRET_SERIAL")
        planner = ScanPlanner()
        registry = DiagnosticRegistry()
        plan = planner.plan(session, registry, ScanRequest(device_id="android-aabbccdd1122"))

        assert plan.device_id == "android-aabbccdd1122"
        # 12. raw serial absent from plan
        dump = plan.model_dump_json()
        assert "SECRET_SERIAL" not in dump
        assert not hasattr(plan, "raw_serial")
        assert not hasattr(plan, "serial")

    def test_plan_is_immutable(self) -> None:
        session = _make_connected_session()
        planner = ScanPlanner()
        registry = DiagnosticRegistry()
        plan = planner.plan(session, registry, ScanRequest(device_id=_DEVICE_ID))

        with pytest.raises(ValidationError):
            plan.device_id = "new_id"  # type: ignore[misc]


# ============================================================
# PART 5: Scan Lifecycle & State Transitions
# ============================================================


class TestScanLifecycle:
    def test_scan_lifecycle_moves_through_valid_states(self) -> None:
        """13. scan lifecycle moves through valid states."""
        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        assert session.state == ScanLifecycleState.CREATED

        session.transition_to(ScanLifecycleState.PLANNED)
        assert session.state == ScanLifecycleState.PLANNED

        session.transition_to(ScanLifecycleState.RUNNING)
        assert session.state == ScanLifecycleState.RUNNING
        assert session.started_at is not None

        session.transition_to(ScanLifecycleState.COMPLETED)
        assert session.state == ScanLifecycleState.COMPLETED
        assert session.completed_at is not None
        assert session.is_terminal is True

    def test_invalid_lifecycle_transition_is_rejected(self) -> None:
        """14. invalid lifecycle transition is rejected."""
        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)

        # Cannot jump from CREATED directly to COMPLETED
        with pytest.raises(InvalidLifecycleTransitionError):
            session.transition_to(ScanLifecycleState.COMPLETED)

        session.transition_to(ScanLifecycleState.PLANNED)
        session.transition_to(ScanLifecycleState.RUNNING)
        session.transition_to(ScanLifecycleState.COMPLETED)

        # Cannot move out of terminal state
        with pytest.raises(InvalidLifecycleTransitionError):
            session.transition_to(ScanLifecycleState.RUNNING)


# ============================================================
# PART 6, 7: Diagnostic Events & Orchestration
# ============================================================


class TestScanOrchestrationAndEvents:
    def test_orchestration_event_sequence_and_evidence(self) -> None:
        """
        15. diagnostic.started emitted before execution.
        16. evidence event is backed by actual EvidenceRecord.
        17. terminal diagnostic event matches actual DiagnosticResult.
        18. scan.completed occurs only after all executable diagnostics finish.
        23. no fake progress events/percentages appear.
        """
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        evidence1 = _make_dummy_evidence("test_diag1")
        evidence2 = _make_dummy_evidence("test_diag1")

        diag1 = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="test_diag1",
                name="Test Diagnostic 1",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.PASS,
            evidence=[evidence1, evidence2],
        )

        diag2 = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="test_diag2",
                name="Test Diagnostic 2",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.INCONCLUSIVE,
        )

        registry = DiagnosticRegistry()
        registry.register(diag1)
        registry.register(diag2)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=["test_diag1", "test_diag2"],
        )
        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        scan_session.transition_to(ScanLifecycleState.PLANNED)

        emitted_events: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(scan_session, event_callback=emitted_events.append)

        assert scan_session.state == ScanLifecycleState.COMPLETED

        # Check event types sequence
        event_types = [ev.event_type for ev in emitted_events]
        assert event_types[0] == DiagnosticEventType.SCAN_STARTED
        assert event_types[1] == DiagnosticEventType.DIAGNOSTIC_STARTED
        assert emitted_events[1].diagnostic_id == "test_diag1"

        # Evidence events
        ev_evidence = [
            ev for ev in emitted_events if ev.event_type == DiagnosticEventType.DIAGNOSTIC_EVIDENCE
        ]
        assert len(ev_evidence) == 2
        # 16. evidence event is backed by actual EvidenceRecord
        assert ev_evidence[0].evidence == evidence1
        assert ev_evidence[1].evidence == evidence2

        # 17. terminal diagnostic event matches actual DiagnosticResult
        completed_1 = next(
            ev
            for ev in emitted_events
            if ev.event_type == DiagnosticEventType.DIAGNOSTIC_COMPLETED
            and ev.diagnostic_id == "test_diag1"
        )
        assert completed_1.result is not None
        assert completed_1.result.status == DiagnosticStatus.PASS

        inconclusive_2 = next(
            ev
            for ev in emitted_events
            if ev.event_type == DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE
            and ev.diagnostic_id == "test_diag2"
        )
        assert inconclusive_2.result is not None
        assert inconclusive_2.result.status == DiagnosticStatus.INCONCLUSIVE

        # 18. scan.completed occurs at the end
        assert event_types[-1] == DiagnosticEventType.SCAN_COMPLETED

        # 23. no fake progress events/percentages appear
        for ev in emitted_events:
            assert ev.progress is None

    def test_execution_exception_becomes_error_not_hardware_fail(self) -> None:
        """19. execution exception becomes execution failure/inconclusive, not fabricated hardware FAIL."""
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag_crash = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="crash_diag",
                name="Crash Diagnostic",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            should_raise=RuntimeError("Subprocess communication pipe broken"),
        )
        registry = DiagnosticRegistry()
        registry.register(diag_crash)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=["crash_diag"],
        )
        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        scan_session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(scan_session)

        # Scan should complete its planned sequence, recording an ERROR result, NOT a FAIL
        assert len(scan_session.diagnostic_results) == 1
        res = scan_session.diagnostic_results[0]
        assert res.status == DiagnosticStatus.ERROR
        assert res.status != DiagnosticStatus.FAIL
        assert "RuntimeError" in (res.summary or "")

    def test_battery_diagnostic_semantics_remain_intact(self) -> None:
        """21. existing battery diagnostic semantics remain unchanged."""
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        bridge = MagicMock()
        bridge.get_battery_telemetry.return_value = BatteryTelemetryResult(
            telemetry=BatteryTelemetry(
                level=88,
                scale=100,
                status="Charging",
                health="Good",
                plugged="USB",
                voltage_mv=4100,
                temperature_tenths_c=300,
                technology="Li-ion",
                present=True,
                raw_output="level: 88\nvoltage: 4100",
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=0.95,
            evidence_source="dumpsys battery",
            collection_method="dumpsys battery",
            error=None,
            collected_at=_NOW,
        )

        battery_diag = BatteryTelemetryDiagnostic(bridge)
        registry = DiagnosticRegistry()
        registry.register(battery_diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=["battery_telemetry"],
        )
        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        scan_session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(scan_session)

        assert len(scan_session.diagnostic_results) == 1
        res = scan_session.diagnostic_results[0]
        assert res.status == DiagnosticStatus.PASS
        # Status note confirms PASS means telemetry collected, not health
        assert "telemetry" in (res.summary or "").lower()

    def test_no_numeric_trust_score_becomes_available(self) -> None:
        """22. no numeric Trust Score becomes available."""
        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
        )
        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        summary = scan_session.to_summary()

        assert summary.trust_score is None
        assert summary.trust_confidence is None
        assert summary.trust_engine_status == TrustEngineStatus.NOT_READY


# ============================================================
# PART 8: Stale Device & Session Epoch Safety
# ============================================================


class TestStaleDeviceSafety:
    def test_stale_device_id_cannot_retarget(self) -> None:
        """8. stale device_id cannot retarget another device."""
        # Device 1 is known, but request targets device 2
        session1 = _make_connected_session(device_id="android-device-1")
        device_session_manager._sessions["android-device-1"] = session1

        service = ScanService()
        req = ScanRequest(device_id="android-device-2")

        with pytest.raises(DeviceNotFoundError):
            service.create_plan(req)

    def test_offline_device_cannot_start_scan_as_connected(self) -> None:
        """9. offline device cannot start a scan as connected."""
        session = _make_connected_session(connection_state=ConnectionState.OFFLINE)
        device_session_manager._sessions[_DEVICE_ID] = session

        service = ScanService()
        req = ScanRequest(device_id=_DEVICE_ID)

        with pytest.raises(DeviceNotConnectedError):
            service.start_scan(req)

    def test_unauthorized_device_cannot_run_diagnostics(self) -> None:
        """10. unauthorized device cannot run privileged diagnostics."""
        session = _make_connected_session(connection_state=ConnectionState.UNAUTHORIZED)
        device_session_manager._sessions[_DEVICE_ID] = session

        service = ScanService()
        req = ScanRequest(device_id=_DEVICE_ID)

        with pytest.raises(DeviceUnauthorizedError):
            service.start_scan(req)

    def test_session_epoch_change_during_execution_stops_stale_result_application(
        self,
    ) -> None:
        """20. disconnect/session epoch change during execution stops stale result application."""
        dev_session = _make_connected_session(epoch=1)
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        class DisconnectingDiagnostic(DummyDiagnostic):
            def execute(self, *, device_id: str, serial: str) -> DiagnosticResult:
                # Simulate device reconnecting with new epoch during execution
                current = device_session_manager.get_session(device_id)
                assert current is not None
                current.session_epoch = 2  # Epoch incremented by reconnect
                return super().execute(device_id=device_id, serial=serial)

        diag = DisconnectingDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="epoch_test",
                name="Epoch Test",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            )
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=["epoch_test"],
        )
        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        scan_session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(scan_session)

        # Scan should fail due to epoch mismatch and NOT apply the result
        assert scan_session.state == ScanLifecycleState.FAILED
        assert len(scan_session.diagnostic_results) == 0
        assert (
            "epoch" in (scan_session.error or "").lower()
            or "session" in (scan_session.error or "").lower()
        )


# ============================================================
# PART 10: Scan API Integration Tests
# ============================================================


class TestScanAPIEndpoints:
    @pytest.fixture
    def app(self) -> Any:
        return create_app()

    @pytest.fixture
    async def client(self, app: Any) -> Any:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_api_create_plan_endpoint(self, client: AsyncClient) -> None:
        session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = session

        response = await client.post(
            "/api/v1/scans/plan",
            json={"device_id": _DEVICE_ID, "mode": "FULL_VERIFICATION"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == _DEVICE_ID
        assert data["mode"] == "FULL_VERIFICATION"
        assert "battery_telemetry" in data["diagnostics_planned"]
        # Raw serial must never be in plan response
        assert "raw_serial" not in response.text
        assert _SERIAL not in response.text

    async def test_api_start_and_get_scan_results(self, client: AsyncClient) -> None:
        session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = session

        # Start synchronous scan
        response = await client.post(
            "/api/v1/scans?sync=true",
            json={"device_id": _DEVICE_ID},
        )
        assert response.status_code == 201
        data = response.json()
        scan_id = data["scan_id"]
        assert data["state"] == "COMPLETED"

        # Query summary
        summary_resp = await client.get(f"/api/v1/scans/{scan_id}")
        assert summary_resp.status_code == 200
        summary_data = summary_resp.json()
        assert summary_data["scan_id"] == scan_id
        assert summary_data["state"] == "COMPLETED"
        assert summary_data["trust_engine_status"] == "NOT_READY"
        assert summary_data["trust_score"] is None

        # Query results
        results_resp = await client.get(f"/api/v1/scans/{scan_id}/results")
        assert results_resp.status_code == 200

        # Query events JSON
        events_resp = await client.get(f"/api/v1/scans/{scan_id}/events")
        assert events_resp.status_code == 200
        events_data = events_resp.json()
        assert "events" in events_data
        assert len(events_data["events"]) >= 3  # scan.started, diagnostic.started, ...
        # No raw serial in events response
        assert _SERIAL not in events_resp.text


# ============================================================
# PART 11: Corrections from Claude Adversarial Review
# ============================================================


class TestEvidenceEnforcement:
    """1. Every PASS or DEGRADED requires evidence."""

    def test_pass_without_evidence_converts_to_error(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="pass_no_ev",
                name="Pass No Evidence",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.PASS,
            evidence=[],  # Intentionally zero evidence!
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("pass_no_ev",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session)

        assert len(session.diagnostic_results) == 1
        res = session.diagnostic_results[0]
        # PASS with no evidence MUST be converted to ERROR
        assert res.status == DiagnosticStatus.ERROR
        assert "zero evidence" in (res.summary or "").lower()

    def test_degraded_without_evidence_converts_to_error(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="degraded_no_ev",
                name="Degraded No Evidence",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.DEGRADED,
            evidence=[],  # Zero evidence
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("degraded_no_ev",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session)

        assert len(session.diagnostic_results) == 1
        res = session.diagnostic_results[0]
        assert res.status == DiagnosticStatus.ERROR
        assert "zero evidence" in (res.summary or "").lower()

    def test_pending_or_running_status_converts_to_error(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="running_res",
                name="Running Diagnostic",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.RUNNING,
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("running_res",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session)

        assert len(session.diagnostic_results) == 1
        res = session.diagnostic_results[0]
        assert res.status == DiagnosticStatus.ERROR
        assert "non-terminal" in (res.summary or "").lower()

    def test_fail_without_evidence_remains_fail(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="fail_diag",
                name="Fail Diagnostic",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.FAIL,
            evidence=[],
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("fail_diag",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session)

        assert len(session.diagnostic_results) == 1
        res = session.diagnostic_results[0]
        # FAIL represents measured diagnostic result; remains FAIL
        assert res.status == DiagnosticStatus.FAIL


class TestDiagnosticEventSemantics:
    """2. Fix diagnostic event semantics: completed, inconclusive, failed."""

    def test_hardware_fail_emits_diagnostic_completed(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="measured_fail",
                name="Measured Fail",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.FAIL,
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("measured_fail",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        emitted: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session, event_callback=emitted.append)

        # Hardware FAIL must emit diagnostic.completed with result.status == FAIL
        completed_events = [
            ev for ev in emitted if ev.event_type == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        ]
        assert len(completed_events) == 1
        assert completed_events[0].result is not None
        assert completed_events[0].result.status == DiagnosticStatus.FAIL

        # Must NOT emit diagnostic.failed for hardware FAIL
        failed_diag_events = [
            ev for ev in emitted if ev.event_type == DiagnosticEventType.DIAGNOSTIC_FAILED
        ]
        assert len(failed_diag_events) == 0

    def test_execution_error_emits_diagnostic_failed(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="exec_error",
                name="Exec Error",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.ERROR,
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("exec_error",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        emitted: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session, event_callback=emitted.append)

        failed_diag_events = [
            ev for ev in emitted if ev.event_type == DiagnosticEventType.DIAGNOSTIC_FAILED
        ]
        assert len(failed_diag_events) == 1
        assert failed_diag_events[0].result is not None
        assert failed_diag_events[0].result.status == DiagnosticStatus.ERROR

    def test_inconclusive_emits_diagnostic_inconclusive(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="inconclusive_diag",
                name="Inconclusive Diag",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            ),
            result_status=DiagnosticStatus.INCONCLUSIVE,
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("inconclusive_diag",),
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        emitted: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session, event_callback=emitted.append)

        inconclusive_events = [
            ev for ev in emitted if ev.event_type == DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE
        ]
        assert len(inconclusive_events) == 1
        assert inconclusive_events[0].result is not None
        assert inconclusive_events[0].result.status == DiagnosticStatus.INCONCLUSIVE


class TestWorkerCrashHandling:
    """3. Worker crash must not leave scan running."""

    def test_orchestrator_unexpected_exception_sync_handled(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        service = ScanService()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)

        # Force orchestrator to raise an unexpected runtime exception
        service._orchestrator.run_scan = MagicMock(
            side_effect=RuntimeError("Subprocess fatal abort")
        )

        session = service.start_scan(req, run_async=False)
        assert session.state == ScanLifecycleState.FAILED
        assert session.error == "An unexpected internal error occurred during scan execution."
        assert "Subprocess fatal abort" not in (session.error or "")

        scan_failed_events = [
            ev for ev in session.events if ev.event_type == DiagnosticEventType.SCAN_FAILED
        ]
        assert len(scan_failed_events) == 1
        assert "unexpected internal error" in (scan_failed_events[0].message or "")

    def test_orchestrator_unexpected_exception_async_handled(self) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        service = ScanService()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)

        crash_event = threading.Event()

        def crashing_run_scan(s: ScanSession, **kwargs: Any) -> ScanSession:
            crash_event.set()
            raise RuntimeError("Async worker segfault simulation")

        service._orchestrator.run_scan = crashing_run_scan

        session = service.start_scan(req, run_async=True)
        assert crash_event.wait(timeout=2.0)

        import time

        for _ in range(50):
            if session.is_terminal:
                break
            time.sleep(0.02)

        assert session.state == ScanLifecycleState.FAILED
        assert session.error == "An unexpected internal error occurred during scan execution."
        assert "Async worker segfault" not in (session.error or "")


class TestScanPlanImmutability:
    """4. Make ScanPlan actually immutable."""

    def test_plan_contents_cannot_be_mutated(self) -> None:
        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_requested=("diag1", "diag2"),
            diagnostics_planned=("diag1",),
            diagnostics_skipped=("diag2",),
            planned_items=(
                PlannedDiagnostic(
                    diagnostic_id="diag1",
                    applicability=DiagnosticApplicability.APPLICABLE,
                ),
                PlannedDiagnostic(
                    diagnostic_id="diag2",
                    applicability=DiagnosticApplicability.UNSUPPORTED,
                    reason="Not supported on hardware",
                ),
            ),
            registry_diagnostic_ids=("diag1", "diag2"),
        )

        assert isinstance(plan.diagnostics_planned, tuple)
        assert isinstance(plan.diagnostics_skipped, tuple)
        assert isinstance(plan.planned_items, tuple)

        # Attempting tuple mutation operations must fail
        with pytest.raises(AttributeError):
            plan.diagnostics_planned.append("diag3")  # type: ignore[attr-defined]

        # Attempting item assignment must fail
        with pytest.raises(TypeError):
            plan.diagnostics_planned[0] = "mutated"  # type: ignore[index]

        # Attempting field reassignment must fail (frozen model)
        with pytest.raises(ValidationError):
            plan.mode = ScanMode.SINGLE_COMPONENT

        # Mutating the computed skip_reasons dict must not alter plan state
        reasons = plan.skip_reasons
        reasons["hacked"] = "injected"
        assert "hacked" not in plan.skip_reasons


class TestPlanTimeSessionEpochProtection:
    """6 & 15. Plan-time session epoch protection."""

    def test_reconnect_epoch_change_between_plan_and_execution_refuses_run(self) -> None:
        dev_session = _make_connected_session(epoch=1)
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        service = ScanService()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)
        scan_session = service.create_scan(req)

        assert scan_session.plan.planning_session_epoch == 1

        # Simulate device disconnect and reconnect (bumping session_epoch to 2)
        dev_session.session_epoch = 2

        # Execute scan
        orchestrator = ScanOrchestrator(device_session_manager, service.registry)
        orchestrator.run_scan(scan_session)

        assert scan_session.state == ScanLifecycleState.FAILED
        assert "Device session changed between planning and execution" in (scan_session.error or "")
        assert len(scan_session.diagnostic_results) == 0

    def test_pre_diagnostic_disconnect_stops_execution_without_results(self) -> None:
        """15. Pre-diagnostic disconnect invokes no diagnostic implementations."""
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag = DummyDiagnostic(
            DiagnosticDefinition(
                diagnostic_id="dummy_diag",
                name="Dummy",
                category="system",
                verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
                supported_platforms=frozenset({Platform.ANDROID}),
            )
        )
        registry = DiagnosticRegistry()
        registry.register(diag)

        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
            diagnostics_planned=("dummy_diag",),
            planning_session_epoch=dev_session.session_epoch,
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        # Disconnect device before run
        dev_session.connection_state = ConnectionState.OFFLINE

        orchestrator = ScanOrchestrator(device_session_manager, registry)
        orchestrator.run_scan(session)

        assert session.state == ScanLifecycleState.FAILED
        assert len(diag.executed_with) == 0
        assert len(session.diagnostic_results) == 0


class TestPrerequisiteSemanticsAndCircularity:
    """7. Prerequisite semantics and circularity rejection."""

    def test_circular_prerequisite_self_dependency_blocked(self) -> None:
        session = _make_connected_session()
        defn = DiagnosticDefinition(
            diagnostic_id="diag_self",
            name="Self Depending",
            category="system",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
            prerequisites=frozenset({"diag_self"}),
        )
        registry = DiagnosticRegistry()
        registry.register(DummyDiagnostic(defn))

        planner = ScanPlanner()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session, registry, req)

        assert "diag_self" in plan.diagnostics_skipped
        assert "Circular prerequisite" in plan.skip_reasons["diag_self"]

    def test_circular_prerequisite_mutual_dependency_blocked(self) -> None:
        session = _make_connected_session()
        defn_a = DiagnosticDefinition(
            diagnostic_id="diag_a",
            name="Diag A",
            category="system",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
            prerequisites=frozenset({"diag_b"}),
        )
        defn_b = DiagnosticDefinition(
            diagnostic_id="diag_b",
            name="Diag B",
            category="system",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
            prerequisites=frozenset({"diag_a"}),
        )
        registry = DiagnosticRegistry()
        registry.register(DummyDiagnostic(defn_a))
        registry.register(DummyDiagnostic(defn_b))

        planner = ScanPlanner()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session, registry, req)

        assert "diag_a" in plan.diagnostics_skipped
        assert "Circular prerequisite detected" in plan.skip_reasons["diag_a"]


class TestLifecycleTornReadPrevention:
    """8. Lifecycle torn reads fix."""

    def test_timestamps_and_error_set_before_state_assignment(self) -> None:
        plan = ScanPlan(
            device_id=_DEVICE_ID,
            platform=Platform.ANDROID,
            mode=ScanMode.FULL_VERIFICATION,
        )
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)

        # Transition to PLANNED then RUNNING
        session.transition_to(ScanLifecycleState.PLANNED)
        session.transition_to(ScanLifecycleState.RUNNING)
        assert session.state == ScanLifecycleState.RUNNING
        assert session.started_at is not None

        # Transition to FAILED with error
        session.transition_to(ScanLifecycleState.FAILED, error="Critical hardware malfunction")
        assert session.state == ScanLifecycleState.FAILED
        assert session.error == "Critical hardware malfunction"
        assert session.completed_at is not None


class TestScanRequestValidationHardening:
    """9. Harden scan request validation."""

    def test_full_verification_rejects_category_or_ids(self) -> None:
        session = _make_connected_session()
        planner = ScanPlanner()
        registry = DiagnosticRegistry()

        with pytest.raises(InvalidScanRequestError) as exc1:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION, category="sensors"
                ),
            )
        assert "category must not be specified" in str(exc1.value)

        with pytest.raises(InvalidScanRequestError) as exc2:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION, diagnostic_ids=["d1"]
                ),
            )
        assert "diagnostic_ids must not be specified" in str(exc2.value)

    def test_category_verification_validation(self) -> None:
        session = _make_connected_session()
        planner = ScanPlanner()
        registry = DiagnosticRegistry()

        with pytest.raises(InvalidScanRequestError) as exc1:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID, mode=ScanMode.CATEGORY_VERIFICATION, category=None
                ),
            )
        assert "category must be specified" in str(exc1.value)

        with pytest.raises(InvalidScanRequestError) as exc2:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID,
                    mode=ScanMode.CATEGORY_VERIFICATION,
                    category="nonexistent_cat",
                ),
            )
        assert "No matching diagnostics" in str(exc2.value)

        with pytest.raises(InvalidScanRequestError) as exc3:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID,
                    mode=ScanMode.CATEGORY_VERIFICATION,
                    category="battery",
                    diagnostic_ids=["d1"],
                ),
            )
        assert "diagnostic_ids must not be specified" in str(exc3.value)

    def test_selected_diagnostics_validation(self) -> None:
        session = _make_connected_session()
        planner = ScanPlanner()
        registry = DiagnosticRegistry()

        with pytest.raises(InvalidScanRequestError) as exc1:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID, mode=ScanMode.SELECTED_DIAGNOSTICS, diagnostic_ids=[]
                ),
            )
        assert "diagnostic_ids must not be empty" in str(exc1.value)

        # Reject duplicates
        with pytest.raises(InvalidScanRequestError) as exc2:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID,
                    mode=ScanMode.SELECTED_DIAGNOSTICS,
                    diagnostic_ids=["d1", "d1"],
                ),
            )
        assert "Duplicate diagnostic IDs" in str(exc2.value)

        with pytest.raises(InvalidScanRequestError) as exc3:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID,
                    mode=ScanMode.SELECTED_DIAGNOSTICS,
                    category="sensors",
                    diagnostic_ids=["d1"],
                ),
            )
        assert "category must not be specified" in str(exc3.value)

    def test_single_component_validation(self) -> None:
        session = _make_connected_session()
        planner = ScanPlanner()
        registry = DiagnosticRegistry()

        with pytest.raises(InvalidScanRequestError) as exc1:
            planner.plan(
                session,
                registry,
                ScanRequest(
                    device_id=_DEVICE_ID,
                    mode=ScanMode.SINGLE_COMPONENT,
                    diagnostic_ids=["d1", "d2"],
                ),
            )
        assert "Exactly one diagnostic ID" in str(exc1.value)

    def test_scan_request_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ScanRequest(device_id=_DEVICE_ID, extra_unrecognized_field="forbidden_payload")  # type: ignore[call-arg]


class TestScanSummaryPlanOutcome:
    """10. Scan summary explains all-skipped / plan outcome."""

    def test_summary_exposes_plan_with_skip_reasons(self) -> None:
        dev_session = _make_connected_session(connection_state=ConnectionState.UNAUTHORIZED)
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        defn = DiagnosticDefinition(
            diagnostic_id="unauth_test",
            name="Unauth Test",
            category="system",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
        )
        registry = DiagnosticRegistry()
        registry.register(DummyDiagnostic(defn))

        planner = ScanPlanner()
        req = ScanRequest(device_id=_DEVICE_ID, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(dev_session, registry, req)

        scan_session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        summary = scan_session.to_summary()

        assert summary.plan is not None
        assert "unauth_test" in summary.plan.diagnostics_skipped
        assert "unauthorized" in summary.plan.skip_reasons["unauth_test"].lower()
        # Verify no raw serial in summary
        summary_dump = summary.model_dump(mode="json")
        assert "raw_serial" not in summary_dump
        assert _SERIAL not in str(summary_dump)


class TestBatteryResultErrorBoundary:
    """12. Remove public raw exception text from battery result path."""

    def test_battery_diagnostic_does_not_leak_exception_string(self) -> None:
        bridge = MagicMock()
        sensitive_string = "/usr/local/bin/adb -s SENSITIVE_SERIAL_TOKEN_99999 exec failed with rc=1: permission denied"
        bridge.get_battery_telemetry.side_effect = RuntimeError(sensitive_string)

        battery_diag = BatteryTelemetryDiagnostic(bridge)
        result = battery_diag.execute(device_id=_DEVICE_ID, serial="SECRET_INTERNAL_SERIAL")

        assert result.status == DiagnosticStatus.ERROR
        # Fixed safe summary only
        assert result.summary == "Battery telemetry collection failed due to an execution error."
        assert sensitive_string not in (result.summary or "")
        assert "SENSITIVE_SERIAL_TOKEN_99999" not in str(result.model_dump())
        assert "/usr/local/bin/adb" not in str(result.model_dump())


class TestAsyncScanExecutionAPI:
    """14. Hermetic async path test with mock registry and clean isolation."""

    @pytest.fixture
    def app(self) -> Any:
        return create_app()

    @pytest.fixture
    async def client(self, app: Any) -> Any:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    @pytest.fixture(autouse=True)
    def hermetic_environment(self) -> Generator[None, None, None]:
        scan_service.clear()
        device_session_manager.clear()
        orig_reg = scan_service.registry

        fake_reg = DiagnosticRegistry()
        fake_defn = DiagnosticDefinition(
            diagnostic_id="battery_telemetry",
            name="Hermetic Battery Diagnostic",
            category="battery",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
            required_capabilities=["battery"],
        )
        fake_diag = DummyDiagnostic(defn=fake_defn, result_status=DiagnosticStatus.PASS)
        fake_reg.register(fake_diag)
        scan_service.set_registry(fake_reg)

        yield

        scan_service.clear()
        device_session_manager.clear()
        scan_service.set_registry(orig_reg)

    async def test_api_async_scan_lifecycle_deterministic_completion(
        self, client: AsyncClient
    ) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        # Start asynchronous scan (sync=False)
        response = await client.post(
            "/api/v1/scans",
            json={"device_id": _DEVICE_ID},
        )
        assert response.status_code == 201
        data = response.json()
        scan_id = data["scan_id"]
        assert data["state"] in ("PLANNED", "RUNNING", "COMPLETED")

        # Poll summary until terminal
        import asyncio

        for _ in range(50):
            res = await client.get(f"/api/v1/scans/{scan_id}")
            assert res.status_code == 200
            s_data = res.json()
            if s_data["state"] in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.02)

        summary_resp = await client.get(f"/api/v1/scans/{scan_id}")
        assert summary_resp.status_code == 200
        assert summary_resp.json()["state"] == "COMPLETED"


class TestEventSemanticsAndStatusMapping:
    """Focused tests for UNSUPPORTED / RESTRICTED / SKIPPED / ERROR event semantics."""

    def test_status_mapping_semantics(self) -> None:
        """UNSUPPORTED, RESTRICTED, SKIPPED -> diagnostic.completed.
        ERROR -> diagnostic.failed.
        INCONCLUSIVE -> diagnostic.inconclusive.
        """
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.PASS)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.FAIL)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.DEGRADED)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.UNSUPPORTED)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.RESTRICTED)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.SKIPPED)
            == DiagnosticEventType.DIAGNOSTIC_COMPLETED
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.INCONCLUSIVE)
            == DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE
        )
        assert (
            ScanOrchestrator._map_status_to_event_type(DiagnosticStatus.ERROR)
            == DiagnosticEventType.DIAGNOSTIC_FAILED
        )

        with pytest.raises(ValueError, match="Unhandled diagnostic status"):
            ScanOrchestrator._map_status_to_event_type(
                cast(DiagnosticStatus, "UNKNOWN_NON_EXISTENT")
            )

    @pytest.mark.parametrize(
        ("status", "expected_event_type"),
        [
            (DiagnosticStatus.UNSUPPORTED, DiagnosticEventType.DIAGNOSTIC_COMPLETED),
            (DiagnosticStatus.RESTRICTED, DiagnosticEventType.DIAGNOSTIC_COMPLETED),
            (DiagnosticStatus.SKIPPED, DiagnosticEventType.DIAGNOSTIC_COMPLETED),
            (DiagnosticStatus.ERROR, DiagnosticEventType.DIAGNOSTIC_FAILED),
        ],
    )
    def test_orchestrator_emits_expected_event_per_status(
        self,
        status: DiagnosticStatus,
        expected_event_type: DiagnosticEventType,
    ) -> None:
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        diag_defn = DiagnosticDefinition(
            diagnostic_id=f"test_{status.value.lower()}",
            name=f"Test {status.value}",
            category="hardware",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
        )
        diag = DummyDiagnostic(defn=diag_defn, result_status=status)
        registry = DiagnosticRegistry()
        registry.register(diag)

        orchestrator = ScanOrchestrator(session_manager=device_session_manager, registry=registry)
        plan = _make_scan_plan(diagnostics_planned=[diag_defn.diagnostic_id])
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)

        emitted: list[DiagnosticEvent] = []
        orchestrator.run_scan(session, event_callback=emitted.append)

        terminal_events = [
            ev
            for ev in emitted
            if ev.diagnostic_id == diag_defn.diagnostic_id
            and ev.event_type
            in (
                DiagnosticEventType.DIAGNOSTIC_COMPLETED,
                DiagnosticEventType.DIAGNOSTIC_FAILED,
                DiagnosticEventType.DIAGNOSTIC_INCONCLUSIVE,
            )
        ]
        assert len(terminal_events) == 1
        assert terminal_events[0].event_type == expected_event_type


class TestPerDeviceScanExclusivity:
    """Enforce one active scan per device."""

    @pytest.fixture(autouse=True)
    def clean_env(self) -> Generator[None, None, None]:
        scan_service.clear()
        device_session_manager.clear()
        orig_reg = scan_service.registry

        fake_reg = DiagnosticRegistry()
        fake_defn = DiagnosticDefinition(
            diagnostic_id="dummy_diag",
            name="Dummy Diagnostic",
            category="general",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
        )
        fake_diag = DummyDiagnostic(defn=fake_defn, result_status=DiagnosticStatus.PASS)
        fake_reg.register(fake_diag)
        scan_service.set_registry(fake_reg)

        yield

        scan_service.clear()
        device_session_manager.clear()
        scan_service.set_registry(orig_reg)

    def test_same_device_active_scan_rejected(self) -> None:
        """Starting a scan on a device with an active non-terminal scan must be rejected."""
        dev1 = _make_connected_session(device_id="dev-001")
        device_session_manager._sessions["dev-001"] = dev1

        scan1 = scan_service.create_scan(ScanRequest(device_id="dev-001"))
        assert not scan1.is_terminal

        with pytest.raises(DeviceScanActiveError, match="already in progress"):
            scan_service.start_scan(ScanRequest(device_id="dev-001"))

    def test_different_devices_concurrent_allowed(self) -> None:
        """Different devices must not be globally serialized; both can be active."""
        dev1 = _make_connected_session(device_id="dev-001")
        dev2 = _make_connected_session(device_id="dev-002")
        device_session_manager._sessions["dev-001"] = dev1
        device_session_manager._sessions["dev-002"] = dev2

        scan1 = scan_service.create_scan(ScanRequest(device_id="dev-001"))
        scan2 = scan_service.create_scan(ScanRequest(device_id="dev-002"))

        assert scan1.device_id == "dev-001"
        assert scan2.device_id == "dev-002"
        assert not scan1.is_terminal
        assert not scan2.is_terminal

    def test_same_device_sequential_after_terminal_allowed(self) -> None:
        """Terminal scans must not block future scans on the same device."""
        dev1 = _make_connected_session(device_id="dev-001")
        device_session_manager._sessions["dev-001"] = dev1

        scan1 = scan_service.start_scan(ScanRequest(device_id="dev-001"), run_async=False)
        assert scan1.is_terminal
        assert scan1.state == ScanLifecycleState.COMPLETED

        scan2 = scan_service.start_scan(ScanRequest(device_id="dev-001"), run_async=False)
        assert scan2.is_terminal
        assert scan2.state == ScanLifecycleState.COMPLETED
        assert scan1.scan_id != scan2.scan_id

    @pytest.mark.asyncio
    async def test_api_returns_409_conflict_on_active_scan(self) -> None:
        """FastAPI POST /api/v1/scans returns HTTP 409 Conflict when device has an active scan."""
        dev1 = _make_connected_session(device_id="dev-001")
        device_session_manager._sessions["dev-001"] = dev1

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            scan_service.create_scan(ScanRequest(device_id="dev-001"))

            resp = await client.post("/api/v1/scans", json={"device_id": "dev-001"})
            assert resp.status_code == 409
            assert "already in progress" in resp.json()["detail"]


class TestRunScanRepeatedStartGuard:
    """Guard run_scan against repeated start and non-PLANNED execution."""

    def test_run_scan_rejects_already_running_scan_without_mutation(self) -> None:
        """Calling run_scan on a RUNNING scan must reject clearly and NOT convert RUNNING -> FAILED."""
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        plan = _make_scan_plan()
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)
        session.transition_to(ScanLifecycleState.RUNNING)
        assert session.state == ScanLifecycleState.RUNNING

        orchestrator = ScanOrchestrator(
            session_manager=device_session_manager,
            registry=DiagnosticRegistry(),
        )

        with pytest.raises(InvalidLifecycleTransitionError, match="must be PLANNED"):
            orchestrator.run_scan(session)

        # Must NOT be mutated to FAILED
        assert session.state == ScanLifecycleState.RUNNING
        assert session.error is None

    def test_scan_service_run_scan_rejects_non_planned_scan_without_mutation(self) -> None:
        """Calling ScanService.run_scan on non-PLANNED scan rejects and preserves state."""
        dev_session = _make_connected_session()
        device_session_manager._sessions[_DEVICE_ID] = dev_session

        plan = _make_scan_plan()
        session = ScanSession(device_id=_DEVICE_ID, plan=plan)
        session.transition_to(ScanLifecycleState.PLANNED)
        session.transition_to(ScanLifecycleState.RUNNING)

        scan_service.clear()
        scan_service._scans[session.scan_id] = session

        with pytest.raises(InvalidLifecycleTransitionError, match="must be in PLANNED state"):
            scan_service.run_scan(session.scan_id)

        assert session.state == ScanLifecycleState.RUNNING
        assert session.error is None
