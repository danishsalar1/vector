"""Unit tests for expanded iOS production diagnostics."""

from unittest.mock import MagicMock

from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.diagnostics.battery.battery_extended_telemetry import (
    IOSBatteryExtendedDiagnostic,
)
from vector_agent.diagnostics.battery.charging_power_diagnostic import (
    IOSChargingPowerDiagnostic,
)
from vector_agent.diagnostics.storage.ios_storage_accounting import (
    IOSStorageAccountingDiagnostic,
)
from vector_agent.diagnostics.system.developer_mode_diagnostic import (
    IOSDeveloperModeDiagnostic,
)
from vector_agent.models.device import DiagnosticStatus, VerificationLevel


def create_bridge(os_version: str = "17.4.1") -> MagicMock:
    bridge = MagicMock(spec=IOSDeviceBridge)
    bridge.get_metadata_field.return_value = os_version
    bridge.get_available_tools.return_value = {
        "idevice_id": True,
        "idevicepair": True,
        "ideviceinfo": True,
        "idevicediagnostics": True,
        "idevicedevmodectl": True,
    }
    bridge.is_tool_available.return_value = True
    return bridge


class TestExtendedBatteryDiagnostic:
    """Tests for IOSBatteryExtendedDiagnostic."""

    def test_gasgauge_success(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_gasgauge_telemetry.return_value = (
            {
                "cycle_count": 88,
                "design_capacity_mah": 3200,
                "full_charge_capacity_mah": 3100,
            },
            None,
        )

        diag = IOSBatteryExtendedDiagnostic(mock_bridge)
        assert diag.definition.verification_level == VerificationLevel.RUNTIME_DETECTION

        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        ev = res.evidence[0]
        assert ev.metadata["cycle_count"] == 88
        assert ev.metadata["design_capacity_mah"] == 3200
        assert ev.normalized_value is None
        assert "Does not claim battery health percentage" in ev.metadata["disclaimer"]

    def test_gasgauge_fails_apple_smart_battery_fallback_succeeds(self) -> None:
        mock_bridge = create_bridge()
        # GasGauge returns error
        mock_bridge.get_gasgauge_telemetry.return_value = (None, "GasGauge not responding")
        # IORegistry succeeds
        mock_bridge.get_ioreg_entry.return_value = (
            {
                "cycle_count": 210,
                "design_capacity_mah": 2815,
                "full_charge_capacity_mah": 2550,
            },
            None,
        )

        diag = IOSBatteryExtendedDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        ev = res.evidence[0]
        assert ev.metadata["cycle_count"] == 210
        assert ev.normalized_value is None
        assert "AppleSmartBattery" in ev.metadata["strategy"]

    def test_unrelated_fact_only_fails_pass_gate(self) -> None:
        """Section 12/40: non-defining fact alone must NOT pass."""
        mock_bridge = create_bridge()
        mock_bridge.get_gasgauge_telemetry.return_value = (
            {
                "voltage_mv": 3950,
                "external_connected": True,
            },
            None,
        )
        mock_bridge.get_ioreg_entry.return_value = (None, "Unavailable")

        diag = IOSBatteryExtendedDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0

    def test_valid_cycle_count_passes_gate(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_gasgauge_telemetry.return_value = (
            {
                "cycle_count": 150,
            },
            None,
        )

        diag = IOSBatteryExtendedDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert res.evidence[0].metadata["cycle_count"] == 150

    def test_all_strategies_fail_yields_inconclusive(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_gasgauge_telemetry.return_value = (None, "err1")
        mock_bridge.get_ioreg_entry.return_value = (None, "err2")

        diag = IOSBatteryExtendedDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0


class TestStorageAccountingDiagnostic:
    """Tests for IOSStorageAccountingDiagnostic."""

    def test_storage_accounting_pass(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_disk_usage_telemetry.return_value = (
            {
                "total_disk_capacity_bytes": 128000000000,
                "total_data_capacity_bytes": 118000000000,
                "data_available_bytes": 55000000000,
            },
            None,
        )

        diag = IOSStorageAccountingDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        ev = res.evidence[0]
        assert ev.metadata["total_disk_capacity_bytes"] == 128000000000
        assert ev.normalized_value is None
        assert "Does not verify physical NAND health" in ev.metadata["disclaimer"]

    def test_storage_accounting_inconclusive(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_disk_usage_telemetry.return_value = (None, "Empty output")

        diag = IOSStorageAccountingDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE

    def test_contradictory_storage_yields_inconclusive(self) -> None:
        """Section 17/40: contradictory storage numbers yield INCONCLUSIVE."""
        mock_bridge = create_bridge()
        mock_bridge.get_disk_usage_telemetry.return_value = (
            {
                "total_disk_capacity_bytes": 10000000000,
                "total_data_capacity_bytes": 20000000000,  # data > disk
                "data_available_bytes": 5000000000,
            },
            None,
        )

        diag = IOSStorageAccountingDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0


class TestDeveloperModeDiagnostic:
    """Tests for IOSDeveloperModeDiagnostic."""

    def test_tool_missing_yields_unsupported(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_available_tools.return_value = {"idevicedevmodectl": False}
        mock_bridge.is_tool_available.return_value = False

        diag = IOSDeveloperModeDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.UNSUPPORTED

    def test_unsupported_on_legacy_ios(self) -> None:
        mock_bridge = create_bridge(os_version="15.4")

        diag = IOSDeveloperModeDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.UNSUPPORTED
        mock_bridge.get_developer_mode_state.assert_not_called()

    def test_enabled_status_pass(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_developer_mode_state.return_value = ("ENABLED", "Enabled")

        diag = IOSDeveloperModeDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        assert res.evidence[0].metadata["developer_mode_status"] == "ENABLED"
        assert res.evidence[0].normalized_value is None

    def test_disabled_status_pass(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_developer_mode_state.return_value = ("DISABLED", "Disabled")

        diag = IOSDeveloperModeDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        assert res.evidence[0].metadata["developer_mode_status"] == "DISABLED"
        assert res.evidence[0].normalized_value is None


class TestChargingPowerDiagnostic:
    """Tests for IOSChargingPowerDiagnostic."""

    def test_charging_power_pass(self) -> None:
        mock_bridge = create_bridge()
        mock_bridge.get_ioreg_entry.return_value = (
            {
                "external_connected": True,
                "is_charging": True,
                "voltage_mv": 3950,
            },
            None,
        )

        diag = IOSChargingPowerDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        assert res.evidence[0].metadata["external_connected"] is True
        assert res.evidence[0].normalized_value is None

    def test_charging_power_cycle_only_does_not_pass(self) -> None:
        """Section 16/40: battery cycle count alone must not pass charging_power."""
        mock_bridge = create_bridge()
        mock_bridge.get_ioreg_entry.return_value = (
            {
                "cycle_count": 500,
                "voltage_mv": 3800,
            },
            None,
        )

        diag = IOSChargingPowerDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0

    def test_contradiction_is_inconclusive(self) -> None:
        """Section 16/40: is_charging=True and external_connected=False yields INCONCLUSIVE."""
        mock_bridge = create_bridge()
        mock_bridge.get_ioreg_entry.return_value = (
            {
                "is_charging": True,
                "external_connected": False,
            },
            None,
        )

        diag = IOSChargingPowerDiagnostic(mock_bridge)
        res = diag.execute(device_id="dev-123", serial="00008120-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0
        assert "contradiction" in str(res.summary).lower()
