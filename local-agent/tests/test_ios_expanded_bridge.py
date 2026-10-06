"""Unit tests for expanded IOSDeviceBridge capabilities."""

from unittest.mock import MagicMock, patch

import pytest

from vector_agent.core.config import AgentSettings
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.security.subprocess_policy import CommandResult


class TestIOSBridgeExpansion:
    """Tests for expanded IOSDeviceBridge methods and security guards."""

    @pytest.fixture
    def bridge(self) -> IOSDeviceBridge:
        settings = AgentSettings()
        return IOSDeviceBridge(settings)

    def test_tool_availability_checks(self, bridge: IOSDeviceBridge) -> None:
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda path: "/usr/bin/" + path if "diag" not in path else None
            tools = bridge.get_available_tools()
            assert tools["idevice_id"] is True
            assert tools["idevicepair"] is True
            assert tools["ideviceinfo"] is True
            assert tools["idevicediagnostics"] is False

    def test_ioreg_entry_rejects_non_allowlisted_entry(self, bridge: IOSDeviceBridge) -> None:
        with pytest.raises(ValueError, match="not allowlisted"):
            bridge.get_ioreg_entry("00008120-001E4C123456802E", "IOPlatformExpertDevice")

    def test_ioreg_entry_allows_apple_smart_battery(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicediagnostics"],
            return_code=0,
            stdout="""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AppleSmartBattery</key>
    <dict>
        <key>CycleCount</key>
        <integer>150</integer>
        <key>DesignCapacity</key>
        <integer>3200</integer>
    </dict>
</dict>
</plist>""",
            stderr="",
            duration_seconds=0.1,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            facts, err = bridge.get_ioreg_entry("00008120-001E4C123456802E", "AppleSmartBattery")
            assert err is None
            assert facts is not None
            assert facts["cycle_count"] == 150
            assert facts["design_capacity_mah"] == 3200

    def test_disk_usage_telemetry(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["ideviceinfo"],
            return_code=0,
            stdout="TotalDiskCapacity: 64000000000\nAmountDataAvailable: 32000000000\n",
            stderr="",
            duration_seconds=0.1,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            facts, err = bridge.get_disk_usage_telemetry("00008120-001E4C123456802E")
            assert err is None
            assert facts is not None
            assert facts["total_disk_capacity_bytes"] == 64000000000
            assert facts["amount_data_available_bytes"] == 32000000000

    def test_developer_mode_state(self, bridge: IOSDeviceBridge) -> None:
        mock_res = CommandResult(
            command=["idevicedevmodectl"],
            return_code=0,
            stdout="00008120-001E4C123456802E: enabled\n",
            stderr="",
            duration_seconds=0.1,
        )
        with patch("vector_agent.devices.ios.bridge.run_command", return_value=mock_res):
            status, msg = bridge.get_developer_mode_state("00008120-001E4C123456802E")
            assert status == "ENABLED"

    def test_get_identity_includes_hardware_model_and_cpu_arch(
        self, bridge: IOSDeviceBridge
    ) -> None:
        def fake_metadata(udid: str, key: str, timeout: float = 5.0) -> str | None:
            mapping = {
                "ProductType": "iPhone15,2",
                "ProductVersion": "17.4.1",
                "BuildVersion": "21E236",
                "DeviceClass": "iPhone",
                "HardwareModel": "D73AP",
                "CPUArchitecture": "arm64e",
            }
            return mapping.get(key)

        bridge.get_metadata_field = MagicMock(side_effect=fake_metadata)  # type: ignore[method-assign]
        ident = bridge.get_identity("00008120-001E4C123456802E")
        assert ident is not None
        assert ident.product_type == "iPhone15,2"
        assert ident.ios_version == "17.4.1"
        assert ident.hardware_model == "D73AP"
        assert ident.cpu_architecture == "arm64e"
