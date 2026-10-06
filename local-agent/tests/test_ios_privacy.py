"""Tests for privacy boundaries, redaction, and data minimization in iOS subsystem.

Validates:
- Fabricated sensitive markers (UDID, Serial, DeviceName, IMEI, AppleID, HostID, SystemBUID, EscrowBag)
  are completely absent from all public interfaces, DTOs, EvidenceRecords, DiagnosticEvents,
  ScanSummaries, and logs.
- Bounded allowlist queries (ideviceinfo -k) strictly reject forbidden keys like DeviceName and SerialNumber.
- Command display redacts '-u <udid>' to '-u <UDID_REDACTED>'.
- No pairing secrets or raw plists are persisted or logged.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.devices.session import DeviceSessionManager, device_session_manager
from vector_agent.diagnostics.registry import create_default_registry
from vector_agent.main import create_app
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceIdentity,
    Platform,
    ScanLifecycleState,
    ScanMode,
    ScanRequest,
)
from vector_agent.scan import (
    DiagnosticEvent,
    ScanOrchestrator,
    ScanPlanner,
    ScanSession,
)
from vector_agent.security.subprocess_policy import format_command_for_display, run_command

_SENSITIVE_MARKERS = [
    "IOS-UDID-SECRET-TEST",
    "FAKE-SERIAL-SECRET",
    "Johns-iPhone-PRIVATE",
    "FAKE-IMEI-123456",
    "fake.account@example.invalid",
    "HostID",
    "SystemBUID",
    "EscrowBag",
    "PAIRING-BLOB-CERTIFICATE-SECRET",
]


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state() -> None:
    device_session_manager.clear()


class TestIOSCommandRedactionAndLogging:
    """Verify raw UDID is redacted in command formatting and logging."""

    def test_format_command_for_display_redacts_udid(self) -> None:
        cmd = ["ideviceinfo", "-u", "IOS-UDID-SECRET-TEST", "-k", "ProductType"]
        display = format_command_for_display(cmd)
        assert "IOS-UDID-SECRET-TEST" not in display
        assert "<UDID_REDACTED>" in display
        assert display == "ideviceinfo -u <UDID_REDACTED> -k ProductType"

    def test_subprocess_timeout_redacts_udid_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        secret_udid = "IOS-UDID-SECRET-TEST"
        cmd = ["idevicepair", "-u", secret_udid, "validate"]

        with (
            patch(
                "vector_agent.security.subprocess_policy.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=cmd, timeout=5.0),
            ),
            pytest.raises(ADBCommandTimeoutError),
        ):
            run_command(cmd, timeout=5.0)

        assert secret_udid not in caplog.text
        assert "<UDID_REDACTED>" in caplog.text


class TestIOSDTOAndAPIPrivacy:
    """Verify sensitive markers never reach ConnectedDevice DTO or HTTP API."""

    def test_markers_absent_from_connected_device_dto(self) -> None:
        mgr = DeviceSessionManager()

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )

        def identity_fetcher(udid: str) -> DeviceIdentity | None:
            return DeviceIdentity(
                platform=Platform.IOS,
                model="iPhone15,2",
                ios_version="18.1",
                product_type="iPhone15,2",
                device_codename="iPhone",
            )

        mgr.reconcile_ios_discovery(
            ["IOS-UDID-SECRET-TEST"],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=identity_fetcher,
        )

        session = mgr.list_sessions()[0]
        dto = session.to_connected_device()

        dto_dump = dto.model_dump_json()
        dto_repr = repr(dto)

        for marker in _SENSITIVE_MARKERS:
            assert marker not in dto_dump
            assert marker not in dto_repr

    def test_markers_absent_from_api_endpoints(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )

        def identity_fetcher(udid: str) -> DeviceIdentity | None:
            return DeviceIdentity(
                platform=Platform.IOS,
                model="iPhone15,2",
                ios_version="18.1",
                product_type="iPhone15,2",
                device_codename="iPhone",
            )

        device_session_manager.reconcile_ios_discovery(
            ["IOS-UDID-SECRET-TEST"],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=identity_fetcher,
        )
        dev = device_session_manager.list_sessions()[0]

        # 1. GET /devices (mock discovery trigger to avoid actual host adb/idevice calls)
        with patch("vector_agent.api.devices._trigger_discovery"):
            resp_list = client.get("/api/v1/devices")
            assert resp_list.status_code == 200
            for marker in _SENSITIVE_MARKERS:
                assert marker not in resp_list.text

            # 2. GET /devices/{device_id}
            resp_detail = client.get(f"/api/v1/devices/{dev.device_id}")
            assert resp_detail.status_code == 200
            for marker in _SENSITIVE_MARKERS:
                assert marker not in resp_detail.text

            # 3. POST /devices/{device_id}/pair
            resp_pair = client.post(f"/api/v1/devices/{dev.device_id}/pair")
            assert resp_pair.status_code == 200
            for marker in _SENSITIVE_MARKERS:
                assert marker not in resp_pair.text


class TestIOSEvidenceAndEventPrivacy:
    """Verify sensitive markers never leak into EvidenceRecord, DiagnosticEvent, or ScanSummary."""

    def test_pipeline_evidence_and_events_privacy(self) -> None:
        mgr = device_session_manager

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )

        def identity_fetcher(udid: str) -> DeviceIdentity | None:
            return DeviceIdentity(
                platform=Platform.IOS,
                model="iPhone15,2",
                ios_version="18.1",
                product_type="iPhone15,2",
                device_codename="iPhone",
                build_fingerprint="22B83",
            )

        mgr.reconcile_ios_discovery(
            ["IOS-UDID-SECRET-TEST"],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=identity_fetcher,
        )
        session = mgr.list_sessions()[0]

        mock_bridge = MagicMock(spec=IOSDeviceBridge)
        mock_bridge.get_identity.return_value = identity_fetcher("IOS-UDID-SECRET-TEST")
        mock_bridge.get_battery_telemetry.return_value = (
            {
                "battery_current_capacity": 92,
                "battery_is_charging": False,
                "external_connected": False,
                "fully_charged": False,
                "has_battery": True,
            },
            None,
        )

        registry = create_default_registry(ios_bridge=mock_bridge)
        planner = ScanPlanner()
        req = ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION)
        plan = planner.plan(session=session, registry=registry, request=req)

        scan_sess = ScanSession(device_id=plan.device_id, plan=plan)
        scan_sess.transition_to(ScanLifecycleState.PLANNED)

        emitted_events: list[DiagnosticEvent] = []
        orchestrator = ScanOrchestrator(session_manager=mgr, registry=registry)
        terminal_session = orchestrator.run_scan(
            scan_session=scan_sess,
            event_callback=emitted_events.append,
        )

        assert terminal_session.state == ScanLifecycleState.COMPLETED
        summary = terminal_session.to_summary()
        summary_dump = summary.model_dump_json()

        # Check Summary
        for marker in _SENSITIVE_MARKERS:
            assert marker not in summary_dump

        # Check all EvidenceRecords
        for res in terminal_session.diagnostic_results:
            res_dump = res.model_dump_json()
            for marker in _SENSITIVE_MARKERS:
                assert marker not in res_dump

            for ev in res.evidence:
                ev_dump = ev.model_dump_json()
                for marker in _SENSITIVE_MARKERS:
                    assert marker not in ev_dump

        # Check all DiagnosticEvents
        for ev in emitted_events:
            ev_dump = ev.model_dump_json()
            for marker in _SENSITIVE_MARKERS:
                assert marker not in ev_dump


class TestIOSMetadataAllowlistEnforcement:
    """Verify strict prohibition of non-allowlisted keys like DeviceName and SerialNumber."""

    @pytest.mark.parametrize(
        "forbidden_key",
        [
            "DeviceName",
            "SerialNumber",
            "UniqueDeviceID",
            "InternationalMobileEquipmentIdentity",
            "MobileEquipmentIdentifier",
            "IntegratedCircuitCardIdentity",
            "PhoneNumber",
            "WiFiAddress",
            "BluetoothAddress",
            "AppleID",
            "HostID",
            "SystemBUID",
            "EscrowBag",
        ],
    )
    def test_forbidden_keys_raise_value_error(self, forbidden_key: str) -> None:
        bridge = IOSDeviceBridge()
        with pytest.raises(ValueError) as exc_info:
            bridge.get_metadata_field("00008110-FAKEVECTOR0001", forbidden_key)
        assert "prohibited by privacy allowlist" in str(exc_info.value).lower()
