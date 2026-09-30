"""Tests for ADB device discovery parsing (no real hardware required)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vector_agent.devices.android.bridge import (
    AdbDeviceState,
    _parse_battery_output,
    _parse_devices_output,
)

# ============================================================
# 'adb devices -l' output fixtures
# ============================================================

FIXTURE_NO_DEVICES = """\
List of devices attached
"""

FIXTURE_ONE_AUTHORIZED = """\
List of devices attached
FABRICATED001\t device product:spes model:M2101K6G device:spes transport_id:1
"""

FIXTURE_ONE_UNAUTHORIZED = """\
List of devices attached
FABRICATED002\t unauthorized
"""

FIXTURE_ONE_OFFLINE = """\
List of devices attached
FABRICATED003\t offline
"""

FIXTURE_MULTIPLE_DEVICES = """\
List of devices attached
FABRICATED001\t device product:spes model:M2101K6G device:spes transport_id:1
FABRICATED004\t device product:other model:OtherModel device:other transport_id:2
"""

FIXTURE_DAEMON_STARTUP = """\
* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
FABRICATED001\t device product:spes model:M2101K6G device:spes transport_id:1
"""

FIXTURE_MALFORMED_LINES = """\
List of devices attached

some-garbage-without-state
"""

FIXTURE_EMPTY = ""


# ============================================================
# ADB devices -l parser tests
# ============================================================


class TestParseDevicesOutput:
    def test_no_devices(self) -> None:
        result = _parse_devices_output(FIXTURE_NO_DEVICES)
        assert result.state == AdbDeviceState.NO_DEVICE
        assert result.devices == []
        assert result.adb_available is True
        assert "No Android" in result.message or "no" in result.message.lower()

    def test_one_authorized_device(self) -> None:
        result = _parse_devices_output(FIXTURE_ONE_AUTHORIZED)
        assert result.state == AdbDeviceState.DEVICE
        assert len(result.devices) == 1
        assert result.devices[0].serial == "FABRICATED001"
        assert result.devices[0].state == AdbDeviceState.DEVICE
        assert result.adb_available is True

    def test_unauthorized_device(self) -> None:
        result = _parse_devices_output(FIXTURE_ONE_UNAUTHORIZED)
        assert result.state == AdbDeviceState.UNAUTHORIZED
        assert len(result.devices) == 1
        assert result.devices[0].state == AdbDeviceState.UNAUTHORIZED
        assert (
            "not authorized" in result.message.lower() or "unauthorized" in result.message.lower()
        )

    def test_offline_device(self) -> None:
        result = _parse_devices_output(FIXTURE_ONE_OFFLINE)
        assert result.state == AdbDeviceState.OFFLINE
        assert len(result.devices) == 1
        assert result.devices[0].state == AdbDeviceState.OFFLINE
        assert "offline" in result.message.lower()

    def test_multiple_devices(self) -> None:
        result = _parse_devices_output(FIXTURE_MULTIPLE_DEVICES)
        assert result.state == AdbDeviceState.MULTIPLE_DEVICES
        assert len(result.devices) == 2
        assert "2" in result.message

    def test_daemon_startup_lines_handled(self) -> None:
        """Lines starting with '*' or 'daemon' should be skipped."""
        result = _parse_devices_output(FIXTURE_DAEMON_STARTUP)
        assert result.state == AdbDeviceState.DEVICE
        assert len(result.devices) == 1

    def test_malformed_lines_handled_safely(self) -> None:
        """Lines without proper format should be ignored without raising."""
        result = _parse_devices_output(FIXTURE_MALFORMED_LINES)
        # some-garbage-without-state has no second field, should be skipped
        assert result.state == AdbDeviceState.NO_DEVICE
        assert result.devices == []

    def test_empty_output(self) -> None:
        result = _parse_devices_output(FIXTURE_EMPTY)
        assert result.state == AdbDeviceState.NO_DEVICE
        assert result.devices == []


# ============================================================
# Battery output parser tests
# ============================================================

_NOW = datetime.now(UTC)

FIXTURE_BATTERY_COMPLETE = """\
Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  Max charging current: 2000000
  Max charging voltage: 5000000
  Charge counter: 3500000
  status: 2
  health: 2
  present: true
  level: 83
  scale: 100
  voltage: 4127
  temperature: 314
  technology: Li-ion
"""

FIXTURE_BATTERY_MISSING_FIELDS = """\
Current Battery Service state:
  AC powered: false
  USB powered: false
  level: 72
  scale: 100
"""

FIXTURE_BATTERY_MALFORMED_NUMERIC = """\
Current Battery Service state:
  level: not-a-number
  voltage: GARBAGE
  temperature: ???
  present: true
"""

FIXTURE_BATTERY_NOT_PRESENT = """\
Current Battery Service state:
  present: false
  level: 0
  scale: 100
"""

FIXTURE_BATTERY_EMPTY = ""


class TestParseBatteryOutput:
    def test_complete_valid_output(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        assert tel.level == 83
        assert tel.scale == 100
        assert tel.voltage_mv == 4127
        assert tel.temperature_tenths_c == 314
        assert tel.technology == "Li-ion"
        assert tel.present is True
        # Derived properties
        assert tel.temperature_celsius == pytest.approx(31.4, abs=0.01)
        assert tel.voltage_volts == pytest.approx(4.127, abs=0.001)

    def test_status_mapped_correctly(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        # status: 2 → "Charging"
        assert tel.status == "Charging"

    def test_health_mapped_correctly(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        # health: 2 → "Good"
        assert tel.health == "Good"

    def test_plugged_inferred_from_usb_powered(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        # USB powered: true → plugged = "USB"
        assert tel.plugged == "USB"

    def test_missing_optional_fields(self) -> None:
        """Partial output should not raise; missing fields are None."""
        tel = _parse_battery_output(FIXTURE_BATTERY_MISSING_FIELDS, _NOW)
        assert tel.level == 72
        assert tel.voltage_mv is None
        assert tel.temperature_tenths_c is None
        assert tel.technology is None

    def test_malformed_numeric_field(self) -> None:
        """Non-numeric values should produce None without exception."""
        tel = _parse_battery_output(FIXTURE_BATTERY_MALFORMED_NUMERIC, _NOW)
        assert tel.level is None
        assert tel.voltage_mv is None
        assert tel.temperature_tenths_c is None
        assert tel.present is True  # boolean field should still parse

    def test_battery_not_present(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_NOT_PRESENT, _NOW)
        assert tel.present is False
        assert tel.level == 0

    def test_temperature_conversion(self) -> None:
        """Android stores temperature in tenths of Celsius."""
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        # 314 tenths → 31.4°C
        assert tel.temperature_celsius == pytest.approx(31.4, abs=0.01)

    def test_voltage_conversion(self) -> None:
        """Android stores voltage in millivolts."""
        tel = _parse_battery_output(FIXTURE_BATTERY_COMPLETE, _NOW)
        # 4127 mV → 4.127 V
        assert tel.voltage_volts == pytest.approx(4.127, abs=0.001)

    def test_empty_output_safe(self) -> None:
        tel = _parse_battery_output(FIXTURE_BATTERY_EMPTY, _NOW)
        assert tel.level is None
        assert tel.voltage_mv is None
        assert tel.present is None
