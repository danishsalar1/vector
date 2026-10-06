"""Unit tests for IOSDeviceBridge.

Verifies:
- Fixed command invocation with argument arrays and shell=False
- Toolchain availability detection
- Discovery via idevice_id
- Pairing validation and explicit pairing
- Safe metadata allowlist enforcement (DeviceName / serial / UDID forbidden)
- Identity creation with redaction guarantees
- Battery telemetry domain querying
- Subprocess timeout and error handling
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vector_agent.core.config import AgentSettings
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.ios.bridge import (
    IOSDeviceBridge,
    IOSDiscoveryError,
    IOSToolchainStatus,
)
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    PairingState,
    Platform,
)
from vector_agent.security.subprocess_policy import CommandResult


@pytest.fixture
def mock_settings() -> AgentSettings:
    return AgentSettings(
        idevice_id_path="idevice_id",
        idevicepair_path="idevicepair",
        ideviceinfo_path="ideviceinfo",
        ios_timeout_seconds=5.0,
    )


@pytest.fixture
def bridge(mock_settings: AgentSettings) -> IOSDeviceBridge:
    return IOSDeviceBridge(settings=mock_settings)


class TestIOSToolchainAvailability:
    def test_all_tools_available(self, bridge: IOSDeviceBridge) -> None:
        with patch("shutil.which", return_value="C:\\tools\\idevice.exe"):
            assert bridge.get_toolchain_status() == IOSToolchainStatus.AVAILABLE
            assert bridge.is_available() is True

    def test_one_tool_missing(self, bridge: IOSDeviceBridge) -> None:
        def mock_which(cmd: str) -> str | None:
            if cmd == "idevice_id":
                return "C:\\tools\\idevice_id.exe"
            return None

        with patch("shutil.which", side_effect=mock_which):
            assert bridge.get_toolchain_status() == IOSToolchainStatus.UNAVAILABLE
            assert bridge.is_available() is False

    def test_all_tools_missing(self, bridge: IOSDeviceBridge) -> None:
        with patch("shutil.which", return_value=None):
            assert bridge.get_toolchain_status() == IOSToolchainStatus.UNAVAILABLE
            assert bridge.is_available() is False


class TestIOSDiscovery:
    def test_discover_devices_success(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevice_id", "-l"],
            return_code=0,
            stdout="00008120-001E4C123456802E\n00008030-001A2B3C4D5E002E\n",
            stderr="",
            duration_seconds=0.05,
        )

        with (
            patch.object(bridge, "is_tool_available", return_value=True),
            patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res) as mock_run,
        ):
            udids = bridge.discover_devices()
            assert udids == [
                "00008120-001E4C123456802E",
                "00008030-001A2B3C4D5E002E",
            ]
            mock_run.assert_called_once_with(["idevice_id", "-l"], timeout=5.0)

    def test_discover_devices_zero_devices(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevice_id", "-l"],
            return_code=0,
            stdout="",
            stderr="",
            duration_seconds=0.01,
        )
        with (
            patch.object(bridge, "is_tool_available", return_value=True),
            patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res),
        ):
            res = bridge.discover_devices_result()
            assert res.status == IOSToolchainStatus.AVAILABLE
            assert res.udids == []
            assert bridge.discover_devices() == []

    def test_discover_devices_toolchain_unavailable(self, bridge: IOSDeviceBridge) -> None:
        with patch.object(bridge, "is_tool_available", return_value=False):
            res = bridge.discover_devices_result()
            assert res.status == IOSToolchainStatus.UNAVAILABLE
            assert res.udids == []
            with pytest.raises(IOSDiscoveryError):
                bridge.discover_devices()

    def test_discover_devices_nonzero_exit(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevice_id", "-l"],
            return_code=1,
            stdout="",
            stderr="No devices attached",
            duration_seconds=0.01,
        )
        with (
            patch.object(bridge, "is_tool_available", return_value=True),
            patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res),
        ):
            res = bridge.discover_devices_result()
            assert res.status == IOSToolchainStatus.ERROR
            with pytest.raises(IOSDiscoveryError):
                bridge.discover_devices()

    def test_discover_devices_timeout(self, bridge: IOSDeviceBridge) -> None:
        with (
            patch.object(bridge, "is_tool_available", return_value=True),
            patch(
                "vector_agent.devices.ios.bridge.run_command",
                side_effect=ADBCommandTimeoutError("idevice_id -l", 5.0),
            ),
        ):
            res = bridge.discover_devices_result()
            assert res.status == IOSToolchainStatus.ERROR
            assert "timed out" in (res.error or "").lower()
            with pytest.raises(IOSDiscoveryError):
                bridge.discover_devices()


class TestIOSPairingValidation:
    def test_validate_pairing_success(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicepair", "-u", "00008120-001E4C123456802E", "validate"],
            return_code=0,
            stdout="SUCCESS: Validated pairing with device 00008120-001E4C123456802E",
            stderr="",
            duration_seconds=0.02,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            conn, auth, _ = bridge.validate_pairing("00008120-001E4C123456802E")
            assert conn == ConnectionState.CONNECTED
            assert auth == DeviceAuthorizationState.AUTHORIZED

    def test_validate_pairing_untrusted(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicepair", "-u", "00008120-001E4C123456802E", "validate"],
            return_code=1,
            stdout="",
            stderr="ERROR: Device 00008120-001E4C123456802E is not paired with this host",
            duration_seconds=0.02,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            conn, auth, _ = bridge.validate_pairing("00008120-001E4C123456802E")
            assert conn == ConnectionState.UNAUTHORIZED
            assert auth == DeviceAuthorizationState.AUTHORIZATION_REQUIRED

    def test_validate_pairing_timeout(self, bridge: IOSDeviceBridge) -> None:
        with patch(
            "vector_agent.devices.ios.bridge.run_command",
            side_effect=ADBCommandTimeoutError("idevicepair validate", 10.0),
        ):
            conn, auth, msg = bridge.validate_pairing("00008120-001E4C123456802E")
            assert conn == ConnectionState.UNKNOWN
            assert auth == DeviceAuthorizationState.UNKNOWN
            assert "timed out" in msg.lower()

    def test_validate_pairing_tool_missing(self, bridge: IOSDeviceBridge) -> None:
        with patch(
            "vector_agent.devices.ios.bridge.run_command",
            side_effect=FileNotFoundError("idevicepair not found"),
        ):
            conn, auth, msg = bridge.validate_pairing("00008120-001E4C123456802E")
            assert conn == ConnectionState.UNKNOWN
            assert auth == DeviceAuthorizationState.UNKNOWN
            assert "unavailable" in msg.lower()


class TestIOSExplicitPairing:
    def test_pair_device_success(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicepair", "-u", "00008120-001E4C123456802E", "pair"],
            return_code=0,
            stdout="SUCCESS: Paired with device 00008120-001E4C123456802E",
            stderr="",
            duration_seconds=0.05,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            status, msg = bridge.pair_device("00008120-001E4C123456802E")
            assert status == PairingState.PAIRED
            assert "paired successfully" in msg.lower()

    def test_pair_device_user_action_required(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicepair", "-u", "00008120-001E4C123456802E", "pair"],
            return_code=1,
            stdout="",
            stderr="Please accept the trust dialog on the screen of the device, then attempt to pair again.",
            duration_seconds=0.05,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            status, msg = bridge.pair_device("00008120-001E4C123456802E")
            assert status == PairingState.USER_ACTION_REQUIRED
            assert "trust" in msg.lower()

    def test_pair_device_timeout(self, bridge: IOSDeviceBridge) -> None:
        with patch(
            "vector_agent.devices.ios.bridge.run_command",
            side_effect=ADBCommandTimeoutError("idevicepair pair", 15.0),
        ):
            status, msg = bridge.pair_device("00008120-001E4C123456802E")
            assert status == PairingState.ERROR
            assert "timed out" in msg.lower()


class TestIOSMetadataAllowlist:
    def test_allowlisted_keys_allowed(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["ideviceinfo", "-u", "00008120-001E4C123456802E", "-k", "ProductType"],
            return_code=0,
            stdout="iPhone15,2\n",
            stderr="",
            duration_seconds=0.01,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            assert (
                bridge.get_metadata_field("00008120-001E4C123456802E", "ProductType")
                == "iPhone15,2"
            )

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
        ],
    )
    def test_forbidden_keys_raise_value_error(
        self, bridge: IOSDeviceBridge, forbidden_key: str
    ) -> None:
        with pytest.raises(ValueError, match="prohibited by privacy allowlist"):
            bridge.get_metadata_field("00008120-001E4C123456802E", forbidden_key)


class TestIOSIdentity:
    def test_get_identity_success(self, bridge: IOSDeviceBridge) -> None:
        def mock_metadata(udid: str, key: str, timeout: float = 5.0) -> str | None:
            return {
                "ProductType": "iPhone15,2",
                "ProductVersion": "17.4.1",
                "BuildVersion": "21E236",
                "DeviceClass": "iPhone",
            }.get(key)

        with patch.object(bridge, "get_metadata_field", side_effect=mock_metadata):
            ident = bridge.get_identity("00008120-001E4C123456802E")
            assert ident is not None
            assert ident.platform == Platform.IOS
            assert ident.model == "iPhone15,2"
            assert ident.ios_version == "17.4.1"
            assert ident.build_version == "21E236"
            assert ident.device_class == "iPhone"
            assert ident.build_fingerprint is None
            assert ident.device_codename is None
            # Critical privacy invariants
            assert ident.serial is None
            assert ident.udid is None
            assert ident.marketing_name is None

    def test_get_identity_fails_if_no_essential_fields(self, bridge: IOSDeviceBridge) -> None:
        with patch.object(bridge, "get_metadata_field", return_value=None):
            assert bridge.get_identity("00008120-001E4C123456802E") is None

    def test_get_identity_budget_exhausted(self, bridge: IOSDeviceBridge) -> None:
        calls = []

        def mock_metadata(udid: str, key: str, timeout: float = 5.0) -> str | None:
            calls.append(key)
            return "iPhone15,2"

        # Simulate monotonic clock advancing beyond deadline after first call
        clock_ticks = [100.0, 100.1, 100.6, 100.7, 100.8]
        with (
            patch("time.monotonic", side_effect=clock_ticks),
            patch.object(bridge, "get_metadata_field", side_effect=mock_metadata),
            pytest.raises(ADBCommandTimeoutError),
        ):
            bridge.get_identity("00008120-001E4C123456802E", timeout=0.5)
        # Only the first key query should have been attempted before budget expired
        assert len(calls) == 1


class TestIOSBatteryTelemetry:
    def test_get_battery_telemetry_success(self, bridge: IOSDeviceBridge) -> None:
        raw = (
            "BatteryCurrentCapacity: 88\n"
            "BatteryIsCharging: false\n"
            "ExternalConnected: false\n"
            "FullyCharged: false\n"
            "HasBattery: true\n"
        )
        mock_res = CommandResult(
            command=[
                "ideviceinfo",
                "-u",
                "00008120-001E4C123456802E",
                "-q",
                "com.apple.mobile.battery",
            ],
            return_code=0,
            stdout=raw,
            stderr="",
            duration_seconds=0.03,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            facts, err = bridge.get_battery_telemetry("00008120-001E4C123456802E")
            assert err is None
            assert facts is not None
            assert facts["battery_current_capacity"] == 88
            assert facts["battery_is_charging"] is False

    def test_get_battery_telemetry_timeout(self, bridge: IOSDeviceBridge) -> None:
        with patch(
            "vector_agent.devices.ios.bridge.run_command",
            side_effect=ADBCommandTimeoutError("ideviceinfo", 5.0),
        ):
            facts, err = bridge.get_battery_telemetry("00008120-001E4C123456802E")
            assert facts is None
            assert "timed out" in str(err).lower()
