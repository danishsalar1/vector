"""Tests for iOS session reconciliation and explicit pairing endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vector_agent.devices.session import DeviceSessionManager, device_session_manager
from vector_agent.main import create_app
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceIdentity,
    PairingState,
    Platform,
)
from vector_agent.scan.service import scan_service


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state() -> None:
    device_session_manager.clear()


_FAKE_UDID_1 = "00008110-FAKEVECTOR0001"
_FAKE_UDID_2 = "00008110-FAKEVECTOR0002"
_NOW = datetime.now(UTC)


class TestIOSSessionReconciliation:
    """Test DeviceSessionManager.reconcile_ios_discovery."""

    def test_reconcile_unauthorized_device(self) -> None:
        mgr = DeviceSessionManager()

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.UNAUTHORIZED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Device is not paired with this host.",
            )

        identity_called = False

        def identity_fetcher(udid: str) -> DeviceIdentity | None:
            nonlocal identity_called
            identity_called = True
            return None

        mgr.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=identity_fetcher,
        )

        # Minimization: identity_fetcher should NOT be called for untrusted device
        assert not identity_called

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        s = sessions[0]

        assert s.platform == Platform.IOS
        assert s.connection_state == ConnectionState.UNAUTHORIZED
        assert s.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        assert s.raw_serial == _FAKE_UDID_1
        assert s.identity is None
        # Diagnostic access must be None for unauthorized device
        assert s.get_serial_for_diagnostic() is None

        # Opaque ID check
        assert _FAKE_UDID_1 not in s.device_id
        assert s.device_id.startswith("ios-")

    def test_reconcile_authorized_device_fetches_safe_identity(self) -> None:
        mgr = DeviceSessionManager()

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "Device is paired and trusted.",
            )

        def identity_fetcher(udid: str) -> DeviceIdentity | None:
            return DeviceIdentity(
                platform=Platform.IOS,
                model="iPhone15,2",
                ios_version="18.1",
                product_type="iPhone15,2",
            )

        mgr.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=identity_fetcher,
        )

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        s = sessions[0]

        assert s.platform == Platform.IOS
        assert s.connection_state == ConnectionState.CONNECTED
        assert s.authorization_state == DeviceAuthorizationState.AUTHORIZED
        assert s.identity is not None
        assert s.identity.model == "iPhone15,2"
        assert s.identity.ios_version == "18.1"
        assert s.get_serial_for_diagnostic() == _FAKE_UDID_1

    def test_reconcile_device_disconnect_and_reconnect(self) -> None:
        mgr = DeviceSessionManager()

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )

        mgr.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        s1 = mgr.list_sessions()[0]
        initial_epoch = s1.session_epoch

        # Disconnect (empty discovery)
        mgr.reconcile_ios_discovery(
            [],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        assert s1.connection_state == ConnectionState.OFFLINE
        assert s1.get_serial_for_diagnostic() is None

        # Reconnect
        mgr.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        assert s1.connection_state == ConnectionState.CONNECTED
        assert s1.session_epoch > initial_epoch

    def test_apply_device_pair_success_increments_epoch(self) -> None:
        mgr = DeviceSessionManager()

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        mgr.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        s = mgr.list_sessions()[0]
        old_epoch = s.session_epoch
        assert s.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED

        new_identity = DeviceIdentity(
            platform=Platform.IOS,
            model="iPhone14,5",
            ios_version="17.5.1",
            product_type="iPhone14,5",
        )

        # Apply success
        updated = mgr.apply_device_pair_success(
            device_id=s.device_id,
            expected_epoch=old_epoch,
            identity=new_identity,
        )
        assert updated is True
        assert s.authorization_state == DeviceAuthorizationState.AUTHORIZED
        assert s.session_epoch > old_epoch
        assert s.identity == new_identity

        # Stale epoch application must be rejected
        rejected = mgr.apply_device_pair_success(
            device_id=s.device_id,
            expected_epoch=old_epoch,  # old epoch
            identity=new_identity,
        )
        assert rejected is False


class TestIOSPairingEndpoint:
    """Test POST /api/v1/devices/{device_id}/pair exercising full production bridge, parser, and session wiring."""

    def test_pair_unknown_device_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/devices/ios-unknown-id/pair")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_pair_offline_device_returns_400(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]
        device_session_manager.mark_platform_offline(Platform.IOS)

        resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")
        assert resp.status_code == 400
        assert "offline" in resp.json()["detail"].lower()

    def test_pair_android_device_returns_400(self, client: TestClient) -> None:
        from vector_agent.devices.android.bridge import AdbDeviceEntry, AdbDeviceState

        entries = [
            AdbDeviceEntry(serial="ANDROSERIAL01", state=AdbDeviceState.DEVICE, qualifiers={})
        ]
        device_session_manager.reconcile_android_discovery(
            entries, adb_identity_fetcher=lambda s: None
        )
        android_dev = device_session_manager.list_sessions()[0]

        resp = client.post(f"/api/v1/devices/{android_dev.device_id}/pair")
        assert resp.status_code == 400
        assert "not supported for android" in resp.json()["detail"].lower()

    def test_pair_already_paired_returns_already_paired_status(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "OK",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ALREADY_PAIRED"
        assert "already paired" in data["message"].lower()

    def test_pair_success_updates_session_and_increments_epoch(self, client: TestClient) -> None:
        """Integration test (B1, M7): mocks only run_command at subprocess boundary.

        Exercises: HTTP pair endpoint -> production API -> production bridge pair_device
        -> production pairing parser -> production session apply logic.
        """

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]
        initial_epoch = dev.session_epoch

        command_history: list[list[str]] = []

        class SubResult:
            def __init__(self, rc: int, out: str, err: str = ""):
                self.return_code = rc
                self.stdout = out
                self.stderr = err

        def mock_subprocess(cmd: list[str], timeout: float = 10.0):
            command_history.append(cmd)
            action = cmd[-1]
            if action == "validate":
                return SubResult(
                    1, "ERROR: Could not validate with device ... Please accept trust dialog"
                )
            elif action == "pair":
                return SubResult(0, "SUCCESS: Paired with device 00008110-FAKEVECTOR0001")
            elif "-k" in cmd:
                key = cmd[-1]
                if key == "ProductType":
                    return SubResult(0, "iPhone15,2\n")
                elif key == "ProductVersion":
                    return SubResult(0, "18.0\n")
                elif key == "BuildVersion":
                    return SubResult(0, "22A3354\n")
                return SubResult(0, "OK\n")
            return SubResult(0, "")

        with patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PAIRED"
        assert data["device_id"] == dev.device_id
        assert _FAKE_UDID_1 not in resp.text  # Raw UDID never exposed

        # Verify exact pair command invoked once
        pair_invocations = [c for c in command_history if c[-1] == "pair"]
        assert len(pair_invocations) == 1

        # Check session is updated to AUTHORIZED with epoch incremented once
        updated_dev = device_session_manager.get_session(dev.device_id)
        assert updated_dev is not None
        assert updated_dev.authorization_state == DeviceAuthorizationState.AUTHORIZED
        assert updated_dev.session_epoch == initial_epoch + 1

        # M7 Idempotency: second request performs validate-before-pair and does NOT call pair
        def mock_subprocess_second(cmd: list[str], timeout: float = 10.0):
            command_history.append(cmd)
            action = cmd[-1]
            if action == "validate":
                return SubResult(
                    0, "SUCCESS: Validated pairing with device 00008110-FAKEVECTOR0001"
                )
            elif action == "pair":
                raise AssertionError(
                    "idevicepair pair should NOT be called for already-paired device!"
                )
            return SubResult(0, "")

        with patch(
            "vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess_second
        ):
            resp2 = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "ALREADY_PAIRED"

    def test_pair_idempotency_stale_unknown_session_does_not_call_pair(
        self, client: TestClient
    ) -> None:
        """M7: Session says UNKNOWN / AUTHORIZATION_REQUIRED, but validate says paired -> no pair command."""

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.UNKNOWN,
                "Unknown state",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        class SubResult:
            def __init__(self, rc: int, out: str):
                self.return_code = rc
                self.stdout = out
                self.stderr = ""

        def mock_subprocess(cmd: list[str], timeout: float = 10.0):
            if cmd[-1] == "validate":
                return SubResult(
                    0, "SUCCESS: Validated pairing with device 00008110-FAKEVECTOR0001"
                )
            elif cmd[-1] == "pair":
                raise AssertionError(
                    "idevicepair pair MUST NOT be called when validation succeeds!"
                )
            return SubResult(0, "iPhone15,2\n")

        with patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ALREADY_PAIRED"

    def test_pair_user_action_required(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]
        initial_epoch = dev.session_epoch

        class SubResult:
            def __init__(self, rc: int, out: str):
                self.return_code = rc
                self.stdout = out
                self.stderr = ""

        def mock_subprocess(cmd: list[str], timeout: float = 10.0):
            return SubResult(1, "ERROR: Could not pair with device. Please accept trust dialog")

        with patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "USER_ACTION_REQUIRED"
        assert "trust" in data["message"].lower()

        # Session should still be unauthorized and epoch unchanged
        same_dev = device_session_manager.get_session(dev.device_id)
        assert same_dev is not None
        assert same_dev.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        assert same_dev.session_epoch == initial_epoch

    def test_pair_device_locked(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Locked",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        class SubResult:
            def __init__(self, rc: int, out: str):
                self.return_code = rc
                self.stdout = out
                self.stderr = ""

        def mock_subprocess(cmd: list[str], timeout: float = 10.0):
            return SubResult(1, "ERROR: Device is PasswordProtected")

        with patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "USER_ACTION_REQUIRED"
        assert "passcode" in data["message"].lower() or "locked" in data["message"].lower()

    def test_pair_timeout(self, client: TestClient) -> None:
        from vector_agent.core.errors import ADBCommandTimeoutError

        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        class SubResult:
            def __init__(self, rc: int, out: str):
                self.return_code = rc
                self.stdout = out
                self.stderr = ""

        def mock_subprocess(cmd: list[str], timeout: float = 10.0):
            if cmd[-1] == "validate":
                return SubResult(1, "Trust required")
            raise ADBCommandTimeoutError(command="idevicepair pair", timeout=15.0)

        with patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ERROR"
        assert "timed out" in data["message"].lower()

    def test_pair_active_scan_guard_returns_409(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        with patch.object(scan_service, "has_active_scan", return_value=True):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 409
        assert "scan is active" in resp.json()["detail"].lower()

    def test_pair_stale_epoch_after_disconnect_discarded(self, client: TestClient) -> None:
        def pair_state_fetcher(
            udid: str,
        ) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
            return (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Trust required",
            )

        device_session_manager.reconcile_ios_discovery(
            [_FAKE_UDID_1],
            pair_state_fetcher=pair_state_fetcher,
            identity_fetcher=lambda u: None,
        )
        dev = device_session_manager.list_sessions()[0]

        # Simulate reconnect changing epoch during pairing
        def mock_pair_with_concurrent_disconnect(udid: str):
            # Advance epoch behind the back and mark offline
            dev.session_epoch += 1
            dev.connection_state = ConnectionState.OFFLINE
            return (PairingState.PAIRED, "Device paired and trusted successfully.")

        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing",
                return_value=(
                    ConnectionState.CONNECTED,
                    DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                    "Trust required",
                ),
            ),
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.pair_device",
                side_effect=mock_pair_with_concurrent_disconnect,
            ),
        ):
            resp = client.post(f"/api/v1/devices/{dev.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DEVICE_DISCONNECTED"
        assert "changed during pairing" in data["message"].lower()
