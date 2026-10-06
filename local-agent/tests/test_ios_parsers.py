"""Pure parser unit tests for iOS discovery, pairing, and diagnostic outputs.

Tests cover all edge cases from Canonical Phase 7 requirements:
- idevice_id output parsing (empty, one, multiple, duplicates, malformed, control chars, hyphenated UDIDs)
- idevicepair validate parsing (paired, trust required, locked, disconnected, usbmux error, unknown)
- idevicepair pair parsing (paired, already paired, trust required, locked, disconnected, error)
- ideviceinfo key-value parsing (valid, multiline, error string, control chars, length cap)
- battery telemetry parsing (0, 100, mid-range, negative, >100, non-integer, empty, malformed booleans,
  missing optional keys, unknown extra keys, truncated output)
"""

from __future__ import annotations

from vector_agent.devices.ios.parsers import (
    parse_battery_telemetry,
    parse_idevice_id_output,
    parse_ideviceinfo_key_value,
    parse_pairing_pair_output,
    parse_pairing_validate_output,
)
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    PairingState,
)


class TestIdeviceIdParser:
    def test_empty_output(self) -> None:
        assert parse_idevice_id_output("") == []
        assert parse_idevice_id_output("   \n\n  ") == []

    def test_single_device(self) -> None:
        raw = "00008120-001E4C123456802E\n"
        assert parse_idevice_id_output(raw) == ["00008120-001E4C123456802E"]

    def test_multiple_devices(self) -> None:
        raw = (
            "00008120-001E4C123456802E\n"
            "00008030-001A2B3C4D5E002E\n"
            "2b6f0cc904d137be2e1730235f5664094b831186\n"
        )
        assert parse_idevice_id_output(raw) == [
            "00008120-001E4C123456802E",
            "00008030-001A2B3C4D5E002E",
            "2b6f0cc904d137be2e1730235f5664094b831186",
        ]

    def test_blank_lines_and_whitespace(self) -> None:
        raw = "\n  00008120-001E4C123456802E  \n\n\n00008030-001A2B3C4D5E002E\n   \n"
        assert parse_idevice_id_output(raw) == [
            "00008120-001E4C123456802E",
            "00008030-001A2B3C4D5E002E",
        ]

    def test_duplicate_lines_deduplicated_preserving_order(self) -> None:
        raw = "00008120-001E4C123456802E\n00008030-001A2B3C4D5E002E\n00008120-001E4C123456802E\n"
        assert parse_idevice_id_output(raw) == [
            "00008120-001E4C123456802E",
            "00008030-001A2B3C4D5E002E",
        ]

    def test_malformed_control_characters_rejected(self) -> None:
        raw = (
            "00008120-001E4C123456802E\n"
            "00008120\x00malicious\n"
            "00008120-001E4C123456802E\x07\n"
            "00008030-001A2B3C4D5E002E\n"
        )
        assert parse_idevice_id_output(raw) == [
            "00008120-001E4C123456802E",
            "00008030-001A2B3C4D5E002E",
        ]

    def test_bounded_length_failure(self) -> None:
        # Too short (< 16 chars)
        short_raw = "123456789\n"
        assert parse_idevice_id_output(short_raw) == []

        # Too long (> 64 chars)
        long_raw = "a" * 65 + "\n"
        assert parse_idevice_id_output(long_raw) == []


class TestPairingValidateParser:
    def test_successful_validation(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=0,
            stdout="SUCCESS: Validated pairing with device 00008120-001E4C123456802E",
            stderr="",
        )
        assert conn == ConnectionState.CONNECTED
        assert auth == DeviceAuthorizationState.AUTHORIZED
        assert "paired and trusted" in msg.lower()

    def test_trust_required_not_paired(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=1,
            stdout="",
            stderr="ERROR: Device 00008120-001E4C123456802E is not paired with this host",
        )
        assert conn == ConnectionState.UNAUTHORIZED
        assert auth == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        assert "pairing" in msg.lower() or "trust" in msg.lower()

    def test_device_locked_password_protected(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=1,
            stdout="",
            stderr="ERROR: Could not validate with device: PasswordProtected",
        )
        assert conn == ConnectionState.UNAUTHORIZED
        assert auth == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        assert "locked" in msg.lower() or "passcode" in msg.lower()

    def test_device_disconnected_no_device(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=1,
            stdout="",
            stderr="ERROR: No device found with udid 00008120-001E4C123456802E",
        )
        assert conn == ConnectionState.OFFLINE
        assert auth == DeviceAuthorizationState.UNKNOWN
        assert "disconnected" in msg.lower()

    def test_usbmuxd_unavailable(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=1,
            stdout="",
            stderr="ERROR: Could not connect to usbmuxd: No such file or directory",
        )
        assert conn == ConnectionState.UNKNOWN
        assert auth == DeviceAuthorizationState.UNKNOWN
        assert "usbmux" in msg.lower()

    def test_raw_udid_not_leaked_in_message(self) -> None:
        raw_secret_udid = "00008120-SECRETUDID123456"
        _, _, msg = parse_pairing_validate_output(
            return_code=1,
            stdout="",
            stderr=f"ERROR: Device {raw_secret_udid} returned code 255",
        )
        assert raw_secret_udid not in msg

    def test_empty_or_unknown_output(self) -> None:
        conn, auth, msg = parse_pairing_validate_output(
            return_code=2,
            stdout="unknown internal condition",
            stderr="",
        )
        assert conn == ConnectionState.UNKNOWN
        assert auth == DeviceAuthorizationState.UNKNOWN

    def test_rc0_empty_output_is_unknown(self) -> None:
        # rc=0 with empty output does NOT positively match validated pairing
        conn, auth, msg = parse_pairing_validate_output(
            return_code=0,
            stdout="",
            stderr="",
        )
        assert conn == ConnectionState.UNKNOWN
        assert auth == DeviceAuthorizationState.UNKNOWN


class TestPairingPairParser:
    def test_successful_pair(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=0,
            stdout="SUCCESS: Paired with device 00008120-001E4C123456802E",
            stderr="",
        )
        assert state == PairingState.PAIRED
        assert "paired successfully" in msg.lower()

    def test_user_denied_trust(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=1,
            stdout="",
            stderr="ERROR: User denied trust dialog",
        )
        assert state == PairingState.USER_ACTION_REQUIRED
        assert "denied" in msg.lower() or "reconnect" in msg.lower()

    def test_trust_dialog_pending(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=1,
            stdout="",
            stderr="Please accept the trust dialog on the screen of the device, then attempt to pair again.",
        )
        assert state == PairingState.USER_ACTION_REQUIRED
        assert "trust" in msg.lower()

    def test_device_locked_password_protected(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=1,
            stdout="",
            stderr="ERROR: Device is locked (PasswordProtected). Unlock the device and try again.",
        )
        assert state == PairingState.USER_ACTION_REQUIRED
        assert "unlock" in msg.lower()

    def test_device_disconnected(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=1,
            stdout="",
            stderr="ERROR: No device found with given udid.",
        )
        assert state == PairingState.DEVICE_DISCONNECTED
        assert "disconnected" in msg.lower()

    def test_generic_cli_error(self) -> None:
        state, msg = parse_pairing_pair_output(
            return_code=1,
            stdout="",
            stderr="ERROR: Handshake failed (Code: -12)",
        )
        assert state == PairingState.ERROR
        assert "failed" in msg.lower()


class TestIdeviceinfoKeyValueParser:
    def test_valid_single_line_value(self) -> None:
        assert parse_ideviceinfo_key_value("iPhone15,2\n") == "iPhone15,2"
        assert parse_ideviceinfo_key_value("17.4.1") == "17.4.1"
        assert parse_ideviceinfo_key_value("21E236") == "21E236"
        assert parse_ideviceinfo_key_value("iPhone") == "iPhone"

    def test_empty_or_whitespace_output(self) -> None:
        assert parse_ideviceinfo_key_value("") is None
        assert parse_ideviceinfo_key_value("   \n\n  ") is None

    def test_multiline_output_rejected(self) -> None:
        raw = "iPhone15,2\nExtraLine: 123\n"
        assert parse_ideviceinfo_key_value(raw) is None

    def test_error_prefixes_rejected(self) -> None:
        assert parse_ideviceinfo_key_value("ERROR: Could not get value for key") is None
        assert parse_ideviceinfo_key_value("Could not connect to lockdownd") is None

    def test_control_characters_rejected(self) -> None:
        assert parse_ideviceinfo_key_value("iPhone15,2\x00") is None
        assert parse_ideviceinfo_key_value("iPhone15,2\x07") is None

    def test_excessive_length_rejected(self) -> None:
        long_val = "x" * 129
        assert parse_ideviceinfo_key_value(long_val) is None


class TestBatteryTelemetryParser:
    def test_valid_battery_output(self) -> None:
        raw = (
            "BatteryCurrentCapacity: 85\n"
            "BatteryIsCharging: true\n"
            "ExternalConnected: true\n"
            "FullyCharged: false\n"
            "HasBattery: true\n"
        )
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert err is None
        assert facts is not None
        assert facts["battery_current_capacity"] == 85
        assert facts["battery_is_charging"] is True
        assert facts["external_connected"] is True
        assert facts["fully_charged"] is False
        assert facts["has_battery"] is True

    def test_capacity_boundary_values(self) -> None:
        raw_0 = "BatteryCurrentCapacity: 0\n"
        facts, err = parse_battery_telemetry(raw_0, return_code=0)
        assert err is None and facts is not None
        assert facts["battery_current_capacity"] == 0

        raw_100 = "BatteryCurrentCapacity: 100\n"
        facts, err = parse_battery_telemetry(raw_100, return_code=0)
        assert err is None and facts is not None
        assert facts["battery_current_capacity"] == 100

    def test_capacity_out_of_bounds(self) -> None:
        raw_neg = "BatteryCurrentCapacity: -1\n"
        facts, err = parse_battery_telemetry(raw_neg, return_code=0)
        assert facts is None
        assert "out of range" in str(err)

        raw_101 = "BatteryCurrentCapacity: 101\n"
        facts, err = parse_battery_telemetry(raw_101, return_code=0)
        assert facts is None
        assert "out of range" in str(err)

    def test_non_integer_capacity(self) -> None:
        raw = "BatteryCurrentCapacity: eighty-five\n"
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert facts is None
        assert "not an integer" in str(err)

    def test_empty_output(self) -> None:
        facts, err = parse_battery_telemetry("", return_code=0)
        assert facts is None
        assert "Empty" in str(err)

    def test_non_zero_return_code(self) -> None:
        facts, err = parse_battery_telemetry("BatteryCurrentCapacity: 80\n", return_code=1)
        assert facts is None
        assert "non-zero" in str(err)

    def test_malformed_boolean_values(self) -> None:
        raw = "BatteryCurrentCapacity: 80\nBatteryIsCharging: maybe\n"
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert facts is None
        assert "Malformed boolean" in str(err)

    def test_missing_optional_keys_allowed(self) -> None:
        raw = "BatteryCurrentCapacity: 72\n"
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert err is None and facts is not None
        assert facts["battery_current_capacity"] == 72
        assert "battery_is_charging" not in facts

    def test_missing_required_capacity_rejected(self) -> None:
        raw = "BatteryIsCharging: true\nExternalConnected: true\n"
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert facts is None
        assert "Required BatteryCurrentCapacity" in str(err)

    def test_unknown_extra_keys_ignored_safely(self) -> None:
        raw = (
            "BatteryCurrentCapacity: 60\n"
            "GasGaugeFirmwareVersion: 1.0.4\n"
            "UnknownVendorMetadata: private_data\n"
            "BatteryIsCharging: false\n"
        )
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert err is None and facts is not None
        assert facts["battery_current_capacity"] == 60
        assert facts["battery_is_charging"] is False
        assert "GasGaugeFirmwareVersion" not in facts
        assert "UnknownVendorMetadata" not in facts

    def test_truncated_output_rejected(self) -> None:
        raw = "BatteryCurrentCapacity: 80\nBatteryIsChar"
        facts, err = parse_battery_telemetry(raw, return_code=0)
        assert facts is None
        assert "missing separator" in str(err)
