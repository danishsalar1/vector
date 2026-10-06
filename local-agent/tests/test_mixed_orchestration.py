"""Tests for multi-platform mixed device discovery, planning, and scan orchestration.

Validates:
- Simultaneous coexistence of Android, paired iOS, and unpaired iOS devices.
- Unique opaque device IDs with platform separation and zero raw identifier leakage.
- ScanPlanner platform-targeting (Android gets Android diagnostics, paired iOS gets iOS diagnostics, unpaired iOS cannot plan).
- ScanOrchestrator end-to-end execution on paired iOS devices.
- Truthful diagnostic events (Phase 5 standard event types only).
- Truthful evidence records on PASS (VerificationLevel.RUNTIME_DETECTION).
- TrustEngine remains NOT_READY with trust_score None.
- Cross-device targeting isolation and disconnect/stale-epoch safety.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from vector_agent.devices.android.bridge import (
    AdbDeviceEntry,
    AdbDeviceState,
    AndroidDeviceBridge,
    AndroidIdentity,
)
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.devices.session import DeviceSessionManager, device_session_manager
from vector_agent.diagnostics.registry import create_default_registry
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceCapabilityProfile,
    DeviceIdentity,
    DiagnosticStatus,
    Platform,
    ScanLifecycleState,
    ScanMode,
    ScanRequest,
    TrustEngineStatus,
    VerificationLevel,
)
from vector_agent.scan import (
    DiagnosticEvent,
    DiagnosticEventType,
    ScanOrchestrator,
    ScanPlanner,
    ScanSession,
)


@pytest.fixture(autouse=True)
def clean_sessions() -> None:
    device_session_manager.clear()


_FAKE_ANDROID_SERIAL = "ANDRO_SERIAL_001"
_FAKE_PAIRED_UDID = "00008110-FAKEPAIRED01"
_FAKE_UNPAIRED_UDID = "00008110-FAKEUNPAIRED02"
_NOW = datetime.now(UTC)


def _populate_mixed_devices(mgr: DeviceSessionManager) -> tuple[str, str, str]:
    """Populate manager with 1 Android, 1 paired iOS, and 1 unpaired iOS device."""
    # 1. Android device
    android_entries = [
        AdbDeviceEntry(
            serial=_FAKE_ANDROID_SERIAL,
            state=AdbDeviceState.DEVICE,
            qualifiers={},
        )
    ]

    def android_ident(s: str) -> AndroidIdentity:
        return AndroidIdentity(
            serial=s,
            manufacturer="Google",
            model="Pixel 8",
            device_codename="shiba",
            android_version="14",
            sdk_level=34,
            brand="google",
            retrieved_at=_NOW,
        )

    def android_caps(s: str, dev_id: str) -> DeviceCapabilityProfile:
        return DeviceCapabilityProfile(
            device_id=dev_id,
            platform=Platform.ANDROID,
            profile_complete=True,
        )

    mgr.reconcile_android_discovery(
        android_entries,
        adb_identity_fetcher=android_ident,
        adb_capability_fetcher=android_caps,
    )

    # 2. iOS devices (1 paired, 1 unpaired)
    def ios_pair_fetcher(
        udid: str,
    ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
        if udid == _FAKE_PAIRED_UDID:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )
        return (
            ConnectionState.UNAUTHORIZED,
            DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            "Trust required",
        )

    def ios_ident_fetcher(udid: str) -> DeviceIdentity | None:
        if udid == _FAKE_PAIRED_UDID:
            return DeviceIdentity(
                platform=Platform.IOS,
                model="iPhone15,2",
                ios_version="18.1",
                product_type="iPhone15,2",
                device_codename="iPhone",
            )
        return None

    mgr.reconcile_ios_discovery(
        [_FAKE_PAIRED_UDID, _FAKE_UNPAIRED_UDID],
        pair_state_fetcher=ios_pair_fetcher,
        identity_fetcher=ios_ident_fetcher,
    )

    sessions = mgr.list_sessions()
    android_id = next(s.device_id for s in sessions if s.platform == Platform.ANDROID)
    paired_ios_id = next(
        s.device_id
        for s in sessions
        if s.platform == Platform.IOS
        and s.authorization_state == DeviceAuthorizationState.AUTHORIZED
    )
    unpaired_ios_id = next(
        s.device_id
        for s in sessions
        if s.platform == Platform.IOS
        and s.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
    )

    return android_id, paired_ios_id, unpaired_ios_id


class TestMixedDeviceDiscoveryAndCoexistence:
    """Verify simultaneous coexistence of Android and iOS devices."""

    def test_three_unique_opaque_devices(self) -> None:
        mgr = device_session_manager
        android_id, paired_id, unpaired_id = _populate_mixed_devices(mgr)

        # 3 unique IDs
        assert len({android_id, paired_id, unpaired_id}) == 3

        # Prefixes & privacy
        assert android_id.startswith("android-")
        assert paired_id.startswith("ios-")
        assert unpaired_id.startswith("ios-")

        # Zero leakage of raw identifiers
        for dev_id in (android_id, paired_id, unpaired_id):
            assert _FAKE_ANDROID_SERIAL not in dev_id
            assert _FAKE_PAIRED_UDID not in dev_id
            assert _FAKE_UNPAIRED_UDID not in dev_id

        # Check sessions
        android_session = mgr.get_session(android_id)
        paired_session = mgr.get_session(paired_id)
        unpaired_session = mgr.get_session(unpaired_id)

        assert android_session is not None
        assert paired_session is not None
        assert unpaired_session is not None

        assert android_session.platform == Platform.ANDROID
        assert android_session.connection_state == ConnectionState.CONNECTED
        assert android_session.authorization_state == DeviceAuthorizationState.AUTHORIZED

        assert paired_session.platform == Platform.IOS
        assert paired_session.connection_state == ConnectionState.CONNECTED
        assert paired_session.authorization_state == DeviceAuthorizationState.AUTHORIZED
        assert paired_session.identity is not None
        assert paired_session.identity.model == "iPhone15,2"

        assert unpaired_session.platform == Platform.IOS
        assert unpaired_session.connection_state == ConnectionState.UNAUTHORIZED
        assert (
            unpaired_session.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        )
        assert unpaired_session.identity is None


class TestMixedScanPlanning:
    """Verify ScanPlanner accurately targets platforms and authorization states."""

    def test_planner_derives_correct_diagnostics_per_platform(self) -> None:
        mgr = device_session_manager
        android_id, paired_id, unpaired_id = _populate_mixed_devices(mgr)

        mock_android_bridge = MagicMock(spec=AndroidDeviceBridge)
        mock_ios_bridge = MagicMock(spec=IOSDeviceBridge)
        registry = create_default_registry(
            bridge=mock_android_bridge,
            ios_bridge=mock_ios_bridge,
        )

        planner = ScanPlanner()

        # 1. Android device full scan -> 6 Android diagnostics, 0 iOS diagnostics
        android_session = mgr.get_session(android_id)
        assert android_session is not None
        android_req = ScanRequest(device_id=android_id, mode=ScanMode.FULL_VERIFICATION)
        android_plan = planner.plan(
            session=android_session,
            registry=registry,
            request=android_req,
        )

        assert len(android_plan.diagnostics_planned) == 6
        assert "software_inventory" not in android_plan.diagnostics_planned
        assert "battery_charge_telemetry" not in android_plan.diagnostics_planned
        assert "battery_telemetry" in android_plan.diagnostics_planned

        # 2. Paired iOS device full scan -> 2 iOS diagnostics, 0 Android diagnostics
        paired_session = mgr.get_session(paired_id)
        assert paired_session is not None
        paired_req = ScanRequest(device_id=paired_id, mode=ScanMode.FULL_VERIFICATION)
        paired_plan = planner.plan(
            session=paired_session,
            registry=registry,
            request=paired_req,
        )

        assert len(paired_plan.diagnostics_planned) == 6
        assert "software_inventory" in paired_plan.diagnostics_planned
        assert "battery_charge_telemetry" in paired_plan.diagnostics_planned
        assert "battery_extended_telemetry" in paired_plan.diagnostics_planned
        assert "charging_power_telemetry" in paired_plan.diagnostics_planned
        assert "storage_accounting" in paired_plan.diagnostics_planned
        assert "developer_mode_state" in paired_plan.diagnostics_planned
        assert "battery_telemetry" not in paired_plan.diagnostics_planned
        assert len(paired_plan.diagnostics_skipped) == 6

        # 3. Unpaired iOS device full scan -> ineligibility due to UNAUTHORIZED state
        unpaired_session = mgr.get_session(unpaired_id)
        assert unpaired_session is not None
        unpaired_req = ScanRequest(device_id=unpaired_id, mode=ScanMode.FULL_VERIFICATION)
        unpaired_plan = planner.plan(
            session=unpaired_session,
            registry=registry,
            request=unpaired_req,
        )

        # Plan items must all be skipped with truthful authorization message
        assert len(unpaired_plan.diagnostics_planned) == 0
        assert len(unpaired_plan.diagnostics_skipped) == 12
        skip_reason = unpaired_plan.skip_reasons["software_inventory"]
        assert "unauthorized" in skip_reason.lower() or "pairing" in skip_reason.lower()

    def test_paired_ios_selected_and_single_component_modes(self) -> None:
        mgr = device_session_manager
        _, paired_id, _ = _populate_mixed_devices(mgr)

        mock_ios_bridge = MagicMock(spec=IOSDeviceBridge)
        registry = create_default_registry(ios_bridge=mock_ios_bridge)
        planner = ScanPlanner()
        session = mgr.get_session(paired_id)
        assert session is not None

        # SELECTED mode
        req_sel = ScanRequest(
            device_id=paired_id,
            mode=ScanMode.SELECTED_DIAGNOSTICS,
            diagnostic_ids=["software_inventory"],
        )
        plan_sel = planner.plan(session=session, registry=registry, request=req_sel)
        assert plan_sel.diagnostics_planned == ("software_inventory",)
        assert len(plan_sel.diagnostics_skipped) == 0

        # SINGLE_COMPONENT mode
        req_single = ScanRequest(
            device_id=paired_id,
            mode=ScanMode.SINGLE_COMPONENT,
            diagnostic_ids=["battery_charge_telemetry"],
        )
        plan_single = planner.plan(session=session, registry=registry, request=req_single)
        assert plan_single.diagnostics_planned == ("battery_charge_telemetry",)
        assert len(plan_single.diagnostics_skipped) == 0


class TestScanOrchestrationOnPairedIOS:
    """End-to-end execution of Phase 7 diagnostics via ScanOrchestrator."""

    def test_execute_paired_ios_full_scan(self) -> None:
        mgr = device_session_manager
        _, paired_id, _ = _populate_mixed_devices(mgr)
        session = mgr.get_session(paired_id)
        assert session is not None

        # Setup mock IOS bridge
        mock_ios_bridge = MagicMock(spec=IOSDeviceBridge)
        mock_ios_bridge.get_identity.return_value = DeviceIdentity(
            platform=Platform.IOS,
            model="iPhone15,2",
            ios_version="18.1",
            product_type="iPhone15,2",
            build_version="22B83",
            device_class="iPhone",
        )

        mock_ios_bridge.get_metadata_field.side_effect = lambda u, k, **kw: {
            "ProductType": "iPhone15,2",
            "ProductVersion": "18.1",
            "BuildVersion": "22B83",
            "DeviceClass": "iPhone",
        }.get(k)
        mock_ios_bridge.get_available_tools.return_value = {
            "ideviceinfo",
            "idevicediagnostics",
            "idevicedevmodectl",
            "idevicepair",
        }
        mock_ios_bridge.get_battery_telemetry.return_value = (
            {
                "battery_current_capacity": 88,
                "battery_is_charging": True,
                "external_connected": True,
                "fully_charged": False,
                "has_battery": True,
            },
            None,
        )
        mock_ios_bridge.get_gasgauge_telemetry.return_value = (
            {
                "cycle_count": 50,
                "nominal_charge_capacity": 3200,
                "raw_max_capacity": 3150,
            },
            None,
        )
        mock_ios_bridge.get_ioreg_entry.return_value = (
            {
                "external_connected": True,
                "is_charging": True,
            },
            None,
        )
        mock_ios_bridge.get_disk_usage_telemetry.return_value = (
            {
                "total_disk_capacity_bytes": 128000000000,
                "total_data_capacity_bytes": 120000000000,
                "total_data_available_bytes": 80000000000,
                "amount_data_available_bytes": 80000000000,
            },
            None,
        )
        mock_ios_bridge.is_tool_available.return_value = True
        mock_ios_bridge.get_developer_mode_state.return_value = (
            "ENABLED",
            "Developer Mode is enabled",
        )

        registry = create_default_registry(ios_bridge=mock_ios_bridge)
        planner = ScanPlanner()
        req = ScanRequest(device_id=paired_id, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session=session, registry=registry, request=req)

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)

        emitted_events: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(
            session_manager=mgr,
            registry=registry,
        )

        terminal_session = orchestrator.run_scan(
            scan_session=scan_sess,
            event_callback=emitted_events.append,
        )

        # Assert lifecycle
        assert terminal_session.state == ScanLifecycleState.COMPLETED
        assert len(terminal_session.diagnostic_results) == 6

        # Assert results
        results_by_id = {r.diagnostic_id: r for r in terminal_session.diagnostic_results}

        # 1. software_inventory
        sw_res = results_by_id["software_inventory"]
        assert sw_res.status == DiagnosticStatus.PASS
        assert (
            registry.get_definition(sw_res.diagnostic_id).verification_level
            == VerificationLevel.RUNTIME_DETECTION
        )
        assert len(sw_res.evidence) >= 1
        ev_sw = sw_res.evidence[0]
        assert ev_sw.metadata["product_type"] == "iPhone15,2"
        assert ev_sw.metadata["os_version"] == "18.1"
        assert ev_sw.metadata["build_version"] == "22B83"
        assert ev_sw.metadata["device_class"] == "iPhone"
        # Zero raw UDID or serial in evidence
        assert _FAKE_PAIRED_UDID not in str(ev_sw.metadata)

        # 2. battery_charge_telemetry
        bat_res = results_by_id["battery_charge_telemetry"]
        assert bat_res.status == DiagnosticStatus.PASS
        assert (
            registry.get_definition(bat_res.diagnostic_id).verification_level
            == VerificationLevel.RUNTIME_DETECTION
        )
        assert len(bat_res.evidence) >= 1
        ev_bat = bat_res.evidence[0]
        assert ev_bat.metadata["battery_current_capacity"] == 88
        assert ev_bat.metadata["battery_is_charging"] is True
        assert "health" not in ev_bat.metadata  # No fake health claim in Phase 7!

        # 3. battery_extended_telemetry
        ext_bat_res = results_by_id["battery_extended_telemetry"]
        assert ext_bat_res.status == DiagnosticStatus.PASS
        assert len(ext_bat_res.evidence) >= 1
        assert ext_bat_res.evidence[0].metadata["cycle_count"] == 50

        # 4. charging_power_telemetry
        chg_res = results_by_id["charging_power_telemetry"]
        assert chg_res.status == DiagnosticStatus.PASS

        # 5. storage_accounting
        stor_res = results_by_id["storage_accounting"]
        assert stor_res.status == DiagnosticStatus.PASS

        # 6. developer_mode_state
        dev_res = results_by_id["developer_mode_state"]
        assert dev_res.status == DiagnosticStatus.PASS
        assert dev_res.evidence[0].metadata["developer_mode_status"] == "ENABLED"

        # Trust Engine safety
        summary = terminal_session.to_summary()
        assert summary.trust_engine_status == TrustEngineStatus.NOT_READY
        assert summary.trust_score is None

        # Diagnostic events emitted (standard Phase 5 event types only)
        event_types = [e.event_type for e in emitted_events]
        assert DiagnosticEventType.SCAN_STARTED in event_types
        assert DiagnosticEventType.DIAGNOSTIC_STARTED in event_types
        assert DiagnosticEventType.DIAGNOSTIC_COMPLETED in event_types
        assert DiagnosticEventType.SCAN_COMPLETED in event_types
        # Ensure no fake iOS-specific event types
        for ev in emitted_events:
            assert ev.event_type in DiagnosticEventType

    def test_stale_epoch_on_disconnect_during_scan_fails_safely(self) -> None:
        mgr = device_session_manager
        _, paired_id, _ = _populate_mixed_devices(mgr)
        session = mgr.get_session(paired_id)
        assert session is not None

        mock_ios_bridge = MagicMock(spec=IOSDeviceBridge)

        # Disconnect during execution
        def disconnect_side_effect(udid: str, **kw: Any) -> Any:
            session.session_epoch += 1
            session.connection_state = ConnectionState.OFFLINE
            return None

        mock_ios_bridge.get_identity.side_effect = disconnect_side_effect
        mock_ios_bridge.get_battery_telemetry.return_value = (None, "Device offline")

        registry = create_default_registry(ios_bridge=mock_ios_bridge)
        planner = ScanPlanner()
        req = ScanRequest(device_id=paired_id, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session=session, registry=registry, request=req)

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)

        orchestrator = ScanOrchestrator(session_manager=mgr, registry=registry)
        terminal_session = orchestrator.run_scan(scan_session=scan_sess)

        # Scan must terminate in FAILED state
        assert terminal_session.state == ScanLifecycleState.FAILED
        assert all(r.status != DiagnosticStatus.PASS for r in terminal_session.diagnostic_results)
