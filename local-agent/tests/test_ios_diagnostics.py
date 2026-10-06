"""Unit tests for iOS standard diagnostics:
- SoftwareInventoryDiagnostic (software_inventory)
- IOSBatteryChargeDiagnostic (battery_charge_telemetry)

Verifies:
- Diagnostic metadata (platforms, category, verification level, timeout)
- Evidence generation on PASS (every PASS requires evidence)
- Truthful failure semantics (INCONCLUSIVE, ERROR, not hardware FAIL)
- Timeout budget enforcement (monotonic elapsed accounting)
- Data minimization (no UDID, serial, or DeviceName in evidence)
- Battery health disclaimer guarantees
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.diagnostics.battery.ios_battery_diagnostic import (
    IOSBatteryChargeDiagnostic,
)
from vector_agent.diagnostics.system.software_inventory import (
    SoftwareInventoryDiagnostic,
)
from vector_agent.models.device import (
    DeviceIdentity,
    DiagnosticStatus,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)


@pytest.fixture
def mock_bridge() -> MagicMock:
    return MagicMock(spec=IOSDeviceBridge)


class TestSoftwareInventoryDiagnostic:
    def test_definition_invariants(self, mock_bridge: MagicMock) -> None:
        diag = SoftwareInventoryDiagnostic(mock_bridge)
        defn = diag.definition

        assert defn.diagnostic_id == "software_inventory"
        assert defn.category == "system"
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.IOS})
        assert defn.requires_probe is False
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds == 15.0

    def test_execute_pass(self, mock_bridge: MagicMock) -> None:
        ident = DeviceIdentity(
            platform=Platform.IOS,
            manufacturer="Apple Inc.",
            model="iPhone15,2",
            product_type="iPhone15,2",
            ios_version="17.4.1",
            build_version="21E236",
            device_class="iPhone",
            brand="Apple",
            serial=None,
            udid=None,
        )
        mock_bridge.get_identity.return_value = ident

        diag = SoftwareInventoryDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        ev = res.evidence[0]
        assert ev.diagnostic_id == "software_inventory"
        assert ev.source_type == EvidenceSourceType.IDEVICEINFO
        assert ev.metadata["product_type"] == "iPhone15,2"
        assert ev.metadata["os_version"] == "17.4.1"
        assert ev.metadata["build_version"] == "21E236"
        assert ev.metadata["platform"] == "IOS"
        assert "00008120-001E4C123456802E" not in str(res.summary)
        assert "00008120-001E4C123456802E" not in ev.raw_value

    def test_execute_inconclusive_missing_fields(self, mock_bridge: MagicMock) -> None:
        mock_bridge.get_identity.return_value = None

        diag = SoftwareInventoryDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0
        assert "insufficient" in str(res.summary).lower()

    def test_execute_timeout_error(self, mock_bridge: MagicMock) -> None:
        mock_bridge.get_identity.side_effect = ADBCommandTimeoutError("ideviceinfo", 5.0)

        diag = SoftwareInventoryDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.ERROR
        assert len(res.evidence) == 0
        assert "timed out" in str(res.summary).lower()

    def test_execute_budget_exhausted(self, mock_bridge: MagicMock) -> None:
        diag = SoftwareInventoryDiagnostic(mock_bridge)
        # Pass timeout=0 to simulate exhausted budget
        res = diag.execute(
            device_id="ios-abc123456789", serial="00008120-001E4C123456802E", timeout=0.0
        )

        assert res.status == DiagnosticStatus.ERROR
        assert len(res.evidence) == 0
        assert "allocated budget" in str(res.summary).lower()
        mock_bridge.get_identity.assert_not_called()


class TestIOSBatteryChargeDiagnostic:
    def test_definition_invariants(self, mock_bridge: MagicMock) -> None:
        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        defn = diag.definition

        assert defn.diagnostic_id == "battery_charge_telemetry"
        assert defn.category == "battery"
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.IOS})
        assert defn.requires_probe is False
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds == 15.0

    def test_execute_pass(self, mock_bridge: MagicMock) -> None:
        facts = {
            "battery_current_capacity": 85,
            "battery_is_charging": True,
            "external_connected": True,
            "fully_charged": False,
            "has_battery": True,
        }
        mock_bridge.get_battery_telemetry.return_value = (facts, None)

        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 1
        ev = res.evidence[0]
        assert ev.diagnostic_id == "battery_charge_telemetry"
        assert ev.source_type == EvidenceSourceType.IDEVICEINFO
        assert ev.normalized_value == 0.85
        assert ev.unit == "%"
        assert ev.raw_value == "85%"
        assert ev.metadata["battery_current_capacity"] == 85
        assert ev.metadata["battery_is_charging"] is True
        assert ev.metadata["platform"] == "IOS"
        # Disclaims battery health
        assert "not assess battery health" in str(res.summary).lower()

    def test_execute_boundary_capacity(self, mock_bridge: MagicMock) -> None:
        facts = {"battery_current_capacity": 0}
        mock_bridge.get_battery_telemetry.return_value = (facts, None)

        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.PASS
        assert res.evidence[0].normalized_value == 0.0

        facts_100 = {"battery_current_capacity": 100}
        mock_bridge.get_battery_telemetry.return_value = (facts_100, None)
        res_100 = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")
        assert res_100.status == DiagnosticStatus.PASS
        assert res_100.evidence[0].normalized_value == 1.0

    def test_execute_inconclusive_missing_capacity(self, mock_bridge: MagicMock) -> None:
        mock_bridge.get_battery_telemetry.return_value = (None, "Invalid capacity")

        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0

    def test_execute_timeout_error(self, mock_bridge: MagicMock) -> None:
        mock_bridge.get_battery_telemetry.side_effect = ADBCommandTimeoutError("ideviceinfo", 5.0)

        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        res = diag.execute(device_id="ios-abc123456789", serial="00008120-001E4C123456802E")

        assert res.status == DiagnosticStatus.ERROR
        assert len(res.evidence) == 0
        assert "timed out" in str(res.summary).lower()

    def test_execute_budget_exhausted(self, mock_bridge: MagicMock) -> None:
        diag = IOSBatteryChargeDiagnostic(mock_bridge)
        res = diag.execute(
            device_id="ios-abc123456789", serial="00008120-001E4C123456802E", timeout=0.0
        )

        assert res.status == DiagnosticStatus.ERROR
        assert len(res.evidence) == 0
        assert "allocated budget" in str(res.summary).lower()
        mock_bridge.get_battery_telemetry.assert_not_called()
