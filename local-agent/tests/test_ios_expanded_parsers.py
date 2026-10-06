"""Unit tests for expanded iOS pure parsers (GasGauge, IOReg, disk_usage, devmode, NAND)."""

import plistlib

from vector_agent.devices.ios.parsers import (
    parse_developer_mode_output,
    parse_disk_usage_output,
    parse_gasgauge_plist,
    parse_ioreg_battery_plist,
    parse_nand_plist,
)


class TestGasGaugeParser:
    """Tests for parse_gasgauge_plist."""

    def test_valid_gasgauge_plist(self) -> None:
        data = {
            "GasGauge": {
                "CycleCount": 142,
                "DesignCapacity": 3274,
                "FullChargeCapacity": 3150,
                "CurrentCapacity": 2400,
                "Voltage": 3850,
                "Temperature": 2650,  # 26.5 C
                "IsCharging": True,
            }
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["cycle_count"] == 142
        assert facts["design_capacity_raw"] == 3274
        assert facts["full_charge_capacity_raw"] == 3150
        assert facts["current_capacity_raw"] == 2400
        assert "design_capacity_mah" not in facts
        assert "full_charge_capacity_mah" not in facts
        assert facts["voltage_mv"] == 3850
        assert (
            "temperature_celsius" not in facts
        )  # H2: unvalidated temperature magnitude conversion removed
        assert facts["is_charging"] is True

    def test_zero_cycle_count_is_valid(self) -> None:
        data = {
            "CycleCount": 0,
            "DesignCapacity": 4000,
            "FullChargeCapacity": 4000,
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["cycle_count"] == 0

    def test_alternative_casing_keys(self) -> None:
        data = {
            "Cycle Count": 50,
            "Design Capacity": 3000,
            "AppleRawMaxCapacity": 2900,
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["cycle_count"] == 50
        assert facts["design_capacity_raw"] == 3000
        assert "design_capacity_mah" not in facts
        assert facts["raw_max_capacity_raw"] == 2900  # Raw neutral name without _mah

    def test_negative_capacity_rejected(self) -> None:
        data = {
            "CycleCount": 10,
            "DesignCapacity": -500,
            "FullChargeCapacity": 3000,
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(raw_xml, 0)
        assert facts is None
        assert "out of reasonable bounds" in str(err)

    def test_malformed_xml_rejected(self) -> None:
        facts, err = parse_gasgauge_plist("Not an XML plist", 0)
        assert facts is None
        assert "Failed to parse GasGauge XML plist" in str(err)

    def test_nonzero_return_code(self) -> None:
        facts, err = parse_gasgauge_plist("<plist></plist>", 1)
        assert facts is None
        assert "non-zero return code" in str(err)

    def test_empty_input(self) -> None:
        facts, err = parse_gasgauge_plist("", 0)
        assert facts is None


class TestIORegBatteryParser:
    """Tests for parse_ioreg_battery_plist."""

    def test_valid_apple_smart_battery_plist(self) -> None:
        data = {
            "AppleSmartBattery": {
                "CycleCount": 320,
                "DesignCapacity": 3000,
                "AppleRawMaxCapacity": 2700,
                "ExternalConnected": True,
                "Voltage": 3900,
            }
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_ioreg_battery_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["cycle_count"] == 320
        assert facts["design_capacity_mah"] == 3000
        assert facts["raw_max_capacity_mah"] == 2700
        assert facts["external_connected"] is True
        assert facts["voltage_mv"] == 3900

    def test_valid_apple_armpmu_charger_plist(self) -> None:
        data = {
            "AppleARMPMUCharger": {
                "CycleCount": 105,
                "DesignCapacity": 1960,
                "AppleRawMaxCapacity": 1850,
                "ExternalConnected": False,
            }
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_ioreg_battery_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["cycle_count"] == 105
        assert facts["external_connected"] is False


class TestDiskUsageParser:
    """Tests for parse_disk_usage_output."""

    def test_valid_disk_usage(self) -> None:
        raw = """
TotalDiskCapacity: 128000000000
TotalDataCapacity: 120000000000
AmountDataAvailable: 64000000000
"""
        facts, err = parse_disk_usage_output(raw, 0)
        assert err is None
        assert facts is not None
        assert facts["total_disk_capacity_bytes"] == 128000000000
        assert facts["total_data_capacity_bytes"] == 120000000000
        assert facts["amount_data_available_bytes"] == 64000000000
        assert "data_available_bytes" not in facts

    def test_available_exceeding_total_rejected(self) -> None:
        raw = """
TotalDiskCapacity: 64000000000
AmountDataAvailable: 128000000000
"""
        facts, err = parse_disk_usage_output(raw, 0)
        assert facts is None
        assert "exceeds TotalDiskCapacity" in str(err)

    def test_missing_total_capacity_rejected(self) -> None:
        raw = "AmountDataAvailable: 10000000"
        facts, err = parse_disk_usage_output(raw, 0)
        assert facts is None
        assert "Required TotalDiskCapacity field not found" in str(err)

    def test_nonzero_return_code(self) -> None:
        facts, err = parse_disk_usage_output("TotalDiskCapacity: 100", 1)
        assert facts is None


class TestDeveloperModeParser:
    """Tests for parse_developer_mode_output."""

    def test_enabled(self) -> None:
        status, msg = parse_developer_mode_output(
            0, "00008101-0001: enabled", "", target_udid="00008101-0001"
        )
        assert status == "ENABLED"
        assert "enabled" in msg

        # Unanchored text must NOT become ENABLED (R2)
        status_unanchored, _ = parse_developer_mode_output(
            0, "Developer Mode is enabled.", "", target_udid="00008101-0001"
        )
        assert status_unanchored == "UNKNOWN"

    def test_disabled(self) -> None:
        status, msg = parse_developer_mode_output(
            0, "00008101-0001: disabled", "", target_udid="00008101-0001"
        )
        assert status == "DISABLED"
        assert "disabled" in msg

        # Unanchored text must NOT become DISABLED (R2)
        status_unanchored, _ = parse_developer_mode_output(
            0, "Developer Mode is disabled.", "", target_udid="00008101-0001"
        )
        assert status_unanchored == "UNKNOWN"

    def test_row_targeting_multi_device(self) -> None:
        # H4: row-level parsing targeting specific device UDID
        out = """00008101-0001: enabled
00008101-0002: disabled
"""
        status_b, _ = parse_developer_mode_output(0, out, "", target_udid="00008101-0002")
        assert status_b == "DISABLED"

        status_a, _ = parse_developer_mode_output(0, out, "", target_udid="00008101-0001")
        assert status_a == "ENABLED"

    def test_help_text_containing_enabled_does_not_pass(self) -> None:
        # H4: usage/help text containing "enabled" must NEVER become ENABLED
        help_out = "Usage: idevicedevmodectl list [options]\nShows if developer mode is enabled or disabled."
        status, _ = parse_developer_mode_output(0, help_out, "", target_udid="00008101-0001")
        assert status != "ENABLED"

    def test_not_supported(self) -> None:
        status, msg = parse_developer_mode_output(1, "", "Device does not support developer mode.")
        assert status == "UNKNOWN"
        assert "exited with error" in msg

    def test_device_not_found(self) -> None:
        status, msg = parse_developer_mode_output(1, "", "No device found.")
        assert status == "UNKNOWN"
        assert "unreachable" in msg.lower()


class TestNandParser:
    """Tests for parse_nand_plist."""

    def test_valid_nand_plist(self) -> None:
        data = {
            "NANDInfo": {
                "BytesPerPage": 16384,
                "PagesPerBlock": 256,
                "BlocksPerChunk": 1024,
            }
        }
        raw_xml = plistlib.dumps(data)
        facts, err = parse_nand_plist(raw_xml, 0)
        assert err is None
        assert facts is not None
        assert facts["bytesperpage"] == 16384
