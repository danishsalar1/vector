"""Targeted correction regression tests for VECTOR Canonical Phase 7.

Validates:
- R1 HIGH: GasGauge capacity units are never inferred from magnitude (0, 1, 50, 99, 100, 101, 3100).
           Single raw capacity response yields INCONCLUSIVE without "mAh" wording.
- R2 HIGH: Strict developer mode parser algorithm: row-level anchored match on target_udid only.
           No global substring matching, no cross-device row acceptance.
- R3 MEDIUM: EvidenceRecord reliability and confidence are None across all 6 iOS PASS diagnostics.
- R4 MEDIUM: Pair endpoint never triggers pair on UNKNOWN, TIMEOUT, TOOL_UNAVAILABLE, or OFFLINE validation.
             Executes pair only on AUTHORIZATION_REQUIRED.
- R5/R8: Real timeout and FileNotFoundError tests through vector_agent.devices.ios.bridge.run_command boundary
         for all six production iOS diagnostics asserting ERROR and UNSUPPORTED respectively.
- R6/R10/R13: Compatibility resolver enforces execution only on SUPPORTED / RUNTIME_PROBE_REQUIRED.
              Future iOS > 27 produces RUNTIME_PROBE_REQUIRED. Storage honors resolver (zero subprocess).
- R7 MEDIUM: Software inventory validation rejects malformed ProductVersion ("foo", "12 monkeys", etc.).
- R8 MEDIUM: Provider failure visibility in DeviceListResponse.
- LOW 17: parse_idevice_id_output filters malformed UDIDs using validate_ios_udid (no 500).
- LOW 19: ASCII numeric parsing rejects underscores, signs, and non-ASCII digits.
- LOW 20: Command display redaction redacts -u / -s tokens regardless of executable name.
- LOW 24: Storage keys keep amount_data_available_bytes and total_data_available_bytes distinct.
"""

from __future__ import annotations

import plistlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from vector_agent.api.devices import DeviceListResponse, _trigger_discovery
from vector_agent.core.config import AgentSettings
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.android.bridge import AdbDeviceState, AndroidDeviceBridge
from vector_agent.devices.ios.bridge import (
    IOSCommandStatus,
    IOSDeviceBridge,
    IOSDiscoveryResult,
    IOSPairValidationResult,
    IOSToolchainStatus,
)
from vector_agent.devices.ios.compatibility import (
    HIGHEST_CODE_REVIEWED_MAJOR,
    IOSCompatibilityResolver,
    StrategyMaturity,
    StrategyStatus,
)
from vector_agent.devices.ios.parsers import (
    _safe_int,
    parse_battery_telemetry,
    parse_developer_mode_output,
    parse_disk_usage_output,
    parse_gasgauge_plist,
    parse_idevice_id_output,
    parse_pairing_pair_output,
)
from vector_agent.devices.ios.version import AppleOSVersion
from vector_agent.devices.session import (
    DeviceSession,
    device_session_manager,
)
from vector_agent.diagnostics.battery.battery_extended_telemetry import (
    IOSBatteryExtendedDiagnostic,
)
from vector_agent.diagnostics.battery.charging_power_diagnostic import (
    IOSChargingPowerDiagnostic,
)
from vector_agent.diagnostics.battery.ios_battery_diagnostic import (
    IOSBatteryChargeDiagnostic,
)
from vector_agent.diagnostics.storage.ios_storage_accounting import (
    IOSStorageAccountingDiagnostic,
)
from vector_agent.diagnostics.system.developer_mode_diagnostic import (
    IOSDeveloperModeDiagnostic,
)
from vector_agent.diagnostics.system.software_inventory import (
    SoftwareInventoryDiagnostic,
)
from vector_agent.main import app
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceIdentity,
    DiagnosticStatus,
    PairingState,
    Platform,
)
from vector_agent.security.subprocess_policy import CommandResult, format_command_for_display
from vector_agent.security.validation import ValidationError, validate_ios_udid

# ============================================================================
# 1. R1 HIGH: GasGauge Capacity Unit Semantics (No Magnitude Inference)
# ============================================================================


class TestR1BatteryCapacityUnitSemantics:
    """Verifies that numerical magnitude never dictates capacity unit assignment."""

    @pytest.mark.parametrize("cap_val", [0, 1, 50, 99, 100, 101, 3100])
    def test_gasgauge_full_charge_capacity_never_becomes_mah(self, cap_val: int) -> None:
        data = {"GasGauge": {"FullChargeCapacity": cap_val}}
        xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(xml, 0)
        assert err is None
        assert facts is not None
        # Must retain neutral raw name, never _mah
        assert facts.get("full_charge_capacity_raw") == cap_val
        assert "full_charge_capacity_mah" not in facts
        assert "full_charge_capacity" not in facts

    @pytest.mark.parametrize("cap_val", [0, 1, 50, 99, 100, 101, 3100])
    def test_gasgauge_design_capacity_never_becomes_mah(self, cap_val: int) -> None:
        data = {"GasGauge": {"DesignCapacity": cap_val}}
        xml = plistlib.dumps(data)
        facts, err = parse_gasgauge_plist(xml, 0)
        assert err is None
        assert facts is not None
        assert facts.get("design_capacity_raw") == cap_val
        assert "design_capacity_mah" not in facts

    def test_gasgauge_response_with_only_raw_capacity_yields_inconclusive(self) -> None:
        """A response with FullChargeCapacity=100 and no cycle count must NOT PASS."""
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_available_tools.return_value = {"idevicediagnostics": True, "ideviceinfo": True}
        bridge.get_metadata_field.return_value = "17.4"
        bridge.get_gasgauge_telemetry.return_value = (
            {"full_charge_capacity_raw": 100},
            None,
        )
        bridge.get_ioreg_entry.return_value = (None, "Unavailable")

        diag = IOSBatteryExtendedDiagnostic(bridge)
        res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")

        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert "mah" not in res.summary.lower()
        assert len(res.evidence) == 0


# ============================================================================
# 2. R2 HIGH: Developer Mode Parser Strictness
# ============================================================================


class TestR2DeveloperModeParserStrictness:
    """Verifies strict row-level anchored parsing for Developer Mode."""

    def test_target_a_enabled_target_b_na(self) -> None:
        raw_output = "00008030-AAAA111122223333: enabled\n00008030-BBBB111122223333: N/A\n"
        # Query target A
        st_a, msg_a = parse_developer_mode_output(
            0, raw_output, "", target_udid="00008030-AAAA111122223333"
        )
        assert st_a == "ENABLED"
        assert "enabled" in msg_a.lower()

        # Query target B
        st_b, msg_b = parse_developer_mode_output(
            0, raw_output, "", target_udid="00008030-BBBB111122223333"
        )
        assert st_b == "NOT_APPLICABLE"
        assert "not supported" in msg_b.lower()

    @pytest.mark.parametrize(
        "adversarial_text",
        [
            "Developer Mode is not enabled.",
            "00008030-OTHER-PHONE-1234: enabled",
            "Usage: idevicedevmodectl list\nChecks if developer mode is enabled on devices.",
            "this command checks whether developer mode is enabled",
        ],
    )
    def test_adversarial_enabled_substrings_do_not_become_enabled(
        self, adversarial_text: str
    ) -> None:
        target = "00008030-AAAA111122223333"
        status, _ = parse_developer_mode_output(0, adversarial_text, "", target_udid=target)
        assert status != "ENABLED"

    @pytest.mark.parametrize(
        "adversarial_text",
        [
            "Usage: idevicedevmodectl list\nChecks if developer mode is disabled on devices.",
            "arbitrary text containing disabled keyword",
            "00008030-OTHER-PHONE-1234: disabled",
        ],
    )
    def test_adversarial_disabled_substrings_do_not_become_disabled(
        self, adversarial_text: str
    ) -> None:
        target = "00008030-AAAA111122223333"
        status, _ = parse_developer_mode_output(0, adversarial_text, "", target_udid=target)
        assert status != "DISABLED"


# ============================================================================
# 3. R3 MEDIUM: Evidence Confidence/Reliability is None across all iOS diagnostics
# ============================================================================


class TestR3EvidenceConfidenceNone:
    """Verifies all six Phase 7 iOS PASS EvidenceRecords emit confidence=None and reliability=None."""

    def test_all_six_diagnostics_pass_evidence_records_have_none_confidence(self) -> None:
        target_udid = "00008030-001E4C123456802E"
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_available_tools.return_value = {
            "ideviceinfo": True,
            "idevicediagnostics": True,
            "idevicedevmodectl": True,
            "idevicepair": True,
        }
        bridge.get_metadata_field.side_effect = lambda u, k, **kw: {
            "ProductType": "iPhone15,2",
            "ProductVersion": "17.4.1",
            "BuildVersion": "21E236",
            "DeviceClass": "iPhone",
        }.get(k)
        bridge.get_identity.return_value = DeviceIdentity(
            platform=Platform.IOS,
            serial=target_udid,
            ios_version="17.4.1",
            build_version="21E236",
            product_type="iPhone15,2",
            device_class="iPhone",
        )
        bridge.get_battery_telemetry.return_value = (
            {
                "battery_current_capacity": 90,
                "battery_is_charging": True,
                "external_connected": True,
                "fully_charged": False,
                "has_battery": True,
            },
            None,
        )
        bridge.get_gasgauge_telemetry.return_value = (
            {"cycle_count": 88, "nominal_charge_capacity_raw": 3200},
            None,
        )
        bridge.get_ioreg_entry.return_value = (
            {"external_connected": True, "is_charging": True},
            None,
        )
        bridge.get_disk_usage_telemetry.return_value = (
            {
                "total_disk_capacity_bytes": 128000000000,
                "total_data_capacity_bytes": 120000000000,
                "amount_data_available_bytes": 50000000000,
                "total_data_available_bytes": 50000000000,
            },
            None,
        )
        bridge.get_developer_mode_state.return_value = ("ENABLED", "Enabled")

        diagnostics = [
            SoftwareInventoryDiagnostic(bridge),
            IOSBatteryChargeDiagnostic(bridge),
            IOSChargingPowerDiagnostic(bridge),
            IOSBatteryExtendedDiagnostic(bridge),
            IOSStorageAccountingDiagnostic(bridge),
            IOSDeveloperModeDiagnostic(bridge),
        ]

        for d in diagnostics:
            res = d.execute(device_id="test-dev", serial=target_udid)
            assert res.status == DiagnosticStatus.PASS, (
                f"{d.definition.diagnostic_id} failed: {res.summary}"
            )
            assert len(res.evidence) >= 1
            for ev in res.evidence:
                assert ev.confidence is None, (
                    f"{d.definition.diagnostic_id} emitted non-None confidence: {ev.confidence}"
                )
                assert ev.reliability is None, (
                    f"{d.definition.diagnostic_id} emitted non-None reliability: {ev.reliability}"
                )


# ============================================================================
# 4. R4 MEDIUM: Never Pair on UNKNOWN, TIMEOUT, TOOL_UNAVAILABLE, OFFLINE
# ============================================================================


class TestR4PairEndpointGuards:
    """Verifies that POST /pair only executes bridge.pair_device when explicitly AUTHORIZATION_REQUIRED."""

    @pytest.fixture(autouse=True)
    def clean_sessions(self) -> Any:
        device_session_manager._sessions.clear()
        yield
        device_session_manager._sessions.clear()

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    @pytest.mark.parametrize(
        ("conn_state", "auth_state", "msg", "expected_pair_calls", "expected_status"),
        [
            (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.UNKNOWN,
                "Unknown rc",
                0,
                "INCONCLUSIVE",
            ),
            (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.RESTRICTED,
                "Device restricted",
                0,
                "RESTRICTED",
            ),
            (
                ConnectionState.OFFLINE,
                DeviceAuthorizationState.UNKNOWN,
                "Device disconnected",
                0,
                "DEVICE_DISCONNECTED",
            ),
            (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "Already trusted",
                0,
                "ALREADY_PAIRED",
            ),
        ],
    )
    def test_no_pair_on_non_authorization_required(
        self,
        client: TestClient,
        conn_state: ConnectionState,
        auth_state: DeviceAuthorizationState,
        msg: str,
        expected_pair_calls: int,
        expected_status: str,
    ) -> None:
        target_udid = "00008030-TESTPAIR00000001"
        mgr = device_session_manager

        mgr.reconcile_ios_discovery(
            [target_udid],
            pair_state_fetcher=lambda u: (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Need trust",
            ),
            identity_fetcher=lambda u: None,
        )
        session = [s for s in mgr.list_sessions() if s.raw_serial == target_udid][0]

        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Paired"))

        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing",
                return_value=(conn_state, auth_state, msg),
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == expected_status
        assert mock_pair.call_count == expected_pair_calls

    def test_trust_dialog_required_executes_exactly_one_pair(self, client: TestClient) -> None:
        target_udid = "00008030-TESTPAIR00000002"
        mgr = device_session_manager

        mgr.reconcile_ios_discovery(
            [target_udid],
            pair_state_fetcher=lambda u: (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Need trust",
            ),
            identity_fetcher=lambda u: None,
        )
        session = [s for s in mgr.list_sessions() if s.raw_serial == target_udid][0]

        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Paired"))

        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing",
                return_value=(
                    ConnectionState.CONNECTED,
                    DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                    "Trust required",
                ),
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
            patch("vector_agent.api.devices.IOSDeviceBridge.get_identity", return_value=None),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        assert mock_pair.call_count == 1


# ============================================================================
# 5. R5 & R8: Real Timeout & FileNotFoundError Tests Across All 6 Diagnostics
# ============================================================================


class TestR5RealTimeoutAndToolMissingThroughBridge:
    """Mocks ONLY vector_agent.devices.ios.bridge.run_command to test real bridge/parser/diagnostic stack."""

    @pytest.mark.parametrize(
        "diagnostic_cls",
        [
            SoftwareInventoryDiagnostic,
            IOSBatteryChargeDiagnostic,
            IOSChargingPowerDiagnostic,
            IOSBatteryExtendedDiagnostic,
            IOSStorageAccountingDiagnostic,
            IOSDeveloperModeDiagnostic,
        ],
    )
    def test_real_timeout_yields_error(self, diagnostic_cls: Any) -> None:
        settings = AgentSettings(
            idevice_id_path="idevice_id",
            idevicepair_path="idevicepair",
            ideviceinfo_path="ideviceinfo",
            idevicediagnostics_path="idevicediagnostics",
            idevicedevmodectl_path="idevicedevmodectl",
        )
        bridge = IOSDeviceBridge(settings=settings)
        diag = diagnostic_cls(bridge)

        def raise_timeout(*args: Any, **kwargs: Any) -> CommandResult:
            raise ADBCommandTimeoutError(command="test_cmd", timeout=5.0)

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=raise_timeout),
            patch("shutil.which", return_value="C:\\tools\\idevice.exe"),
        ):
            res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
            assert res.status == DiagnosticStatus.ERROR, (
                f"{diag.definition.diagnostic_id} status {res.status} != ERROR"
            )

    @pytest.mark.parametrize(
        "diagnostic_cls",
        [
            SoftwareInventoryDiagnostic,
            IOSBatteryChargeDiagnostic,
            IOSChargingPowerDiagnostic,
            IOSBatteryExtendedDiagnostic,
            IOSStorageAccountingDiagnostic,
            IOSDeveloperModeDiagnostic,
        ],
    )
    def test_file_not_found_yields_unsupported(self, diagnostic_cls: Any) -> None:
        settings = AgentSettings(
            idevice_id_path="idevice_id",
            idevicepair_path="idevicepair",
            ideviceinfo_path="ideviceinfo",
            idevicediagnostics_path="idevicediagnostics",
            idevicedevmodectl_path="idevicedevmodectl",
        )
        bridge = IOSDeviceBridge(settings=settings)
        diag = diagnostic_cls(bridge)

        def raise_fnf(*args: Any, **kwargs: Any) -> CommandResult:
            raise FileNotFoundError("No such file or directory: 'idevice'")

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=raise_fnf),
            patch("shutil.which", return_value="C:\\tools\\idevice.exe"),
        ):
            res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
            assert res.status == DiagnosticStatus.UNSUPPORTED, (
                f"{diag.definition.diagnostic_id} status {res.status} != UNSUPPORTED"
            )


# ============================================================================
# 6. R6 / R10 / R13: Compatibility Resolver & Future Major Policy
# ============================================================================


class TestR6CompatibilityResolverSemantics:
    """Verifies resolver execution enforcement, future iOS policy, and storage zero subprocess."""

    def test_future_ios_99_produces_runtime_probe_required_not_supported(self) -> None:
        resolver = IOSCompatibilityResolver(
            available_tools={"ideviceinfo": True, "idevicedevmodectl": True}
        )
        os_ver = AppleOSVersion.parse("99.0.0")
        assert os_ver is not None
        assert os_ver.major > HIGHEST_CODE_REVIEWED_MAJOR

        strategies = resolver.resolve_strategies("developer_mode_state", os_version=os_ver)
        assert len(strategies) >= 1
        for strat, status in strategies:
            assert status == StrategyStatus.RUNTIME_PROBE_REQUIRED
            assert strat.maturity == StrategyMaturity.CODE_TESTED

    def test_known_unsupported_storage_executes_zero_subprocess(self) -> None:
        """On legacy iOS (e.g. 4.3), storage accounting must return UNSUPPORTED without running subprocess."""
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_available_tools.return_value = {"ideviceinfo": True}
        bridge.get_metadata_field.return_value = "4.3"

        diag = IOSStorageAccountingDiagnostic(bridge)
        res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")

        assert res.status == DiagnosticStatus.UNSUPPORTED
        assert bridge.get_disk_usage_telemetry.call_count == 0

    def test_no_hardware_validated_maturity_anywhere(self) -> None:
        resolver = IOSCompatibilityResolver(available_tools={})
        for diag_id in [
            "battery_charge_telemetry",
            "battery_extended_telemetry",
            "charging_power_telemetry",
            "storage_accounting",
            "developer_mode_state",
            "software_inventory",
        ]:
            candidates = resolver.get_candidate_strategies(diag_id)
            for c in candidates:
                assert c.maturity != StrategyMaturity.HARDWARE_VALIDATED


# ============================================================================
# 7. R7 MEDIUM: Software Inventory Version Validation
# ============================================================================


class TestR7SoftwareInventoryVersionValidation:
    """Verifies malformed ProductVersion and invalid ProductType produce INCONCLUSIVE."""

    @pytest.mark.parametrize(
        "bad_version",
        [
            "foo",
            "12 monkeys",
            "17.4beta",
            "17.",
            "17.4.1.2",
            "",
        ],
    )
    def test_malformed_version_yields_inconclusive(self, bad_version: str) -> None:
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_identity.return_value = DeviceIdentity(
            platform=Platform.IOS,
            serial="00008030-001E4C123456802E",
            ios_version=bad_version,
            build_version="21E236",
            product_type="iPhone15,2",
            device_class="iPhone",
        )

        diag = SoftwareInventoryDiagnostic(bridge)
        res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert len(res.evidence) == 0

    def test_valid_version_and_product_type_passes(self) -> None:
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_identity.return_value = DeviceIdentity(
            platform=Platform.IOS,
            serial="00008030-001E4C123456802E",
            ios_version="17.4.1",
            build_version="21E236",
            product_type="iPhone15,2",
            device_class="iPhone",
        )

        diag = SoftwareInventoryDiagnostic(bridge)
        res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
        assert res.status == DiagnosticStatus.PASS
        assert res.summary.startswith("iOS software inventory retrieved")
        assert "Valid iOS" not in res.summary


# ============================================================================
# 8. R8 MEDIUM: Provider Status Visibility in DeviceListResponse
# ============================================================================


class TestR8ProviderStatusVisibility:
    """Verifies provider_statuses is exposed cleanly in DeviceListResponse."""

    def test_device_list_response_provider_statuses(self) -> None:
        resp = DeviceListResponse(
            devices=[],
            count=0,
            provider_statuses={"android": "AVAILABLE", "ios": "ERROR"},
        )
        assert resp.provider_statuses is not None
        assert resp.provider_statuses["android"] == "AVAILABLE"
        assert resp.provider_statuses["ios"] == "ERROR"


# ============================================================================
# 9. LOW: Unified UDID Parser and Validator (No 500)
# ============================================================================


class TestLowUnifiedUDIDParserAndValidator:
    """Verifies that parse_idevice_id_output filters malformed UDIDs and rejects injection strings."""

    @pytest.mark.parametrize(
        "malformed_id",
        [
            "----------------",
            "---abcdefghij---",
            "short",
            "with spaces in id",
            "invalid@special!chars",
            "00008030-001E4C12;rm -rf /",
        ],
    )
    def test_malformed_udid_rejected_during_discovery(self, malformed_id: str) -> None:
        output = f"{malformed_id}\n00008030-001E4C123456802E\n"
        parsed = parse_idevice_id_output(output)
        assert malformed_id not in parsed
        assert parsed == ["00008030-001E4C123456802E"]


# ============================================================================
# 10. LOW: ASCII Numeric Parsing
# ============================================================================


class TestLowASCIINumericParsing:
    """Verifies _safe_int accepts ASCII decimal digits and rejects non-standard formats."""

    @pytest.mark.parametrize(
        "bad_int_str",
        [
            "1_0",
            "+3",
            "١٢٣",  # Arabic-Indic digits
            " 42 ",
            "0x10",
            "12.3",
            "nan",
        ],
    )
    def test_safe_int_rejects_non_ascii_decimals(self, bad_int_str: str) -> None:
        assert _safe_int(bad_int_str) is None

    @pytest.mark.parametrize(
        ("good_str", "expected"),
        [
            ("0", 0),
            ("42", 42),
            ("1234567890", 1234567890),
            (100, 100),
        ],
    )
    def test_safe_int_accepts_valid_ascii(self, good_str: Any, expected: int) -> None:
        assert _safe_int(good_str) == expected


# ============================================================================
# 11. LOW: Command Display Redaction
# ============================================================================


class TestLowCommandDisplayRedaction:
    """Verifies format_command_for_display redacts -u and -s regardless of binary filename."""

    def test_custom_pairer_binary_redacts_udid(self) -> None:
        cmd = ["C:\\custom\\tools\\my_pairer.exe", "-u", "00008030-001E4C123456802E", "--verbose"]
        formatted = format_command_for_display(cmd)
        assert "00008030-001E4C123456802E" not in formatted
        assert formatted == "C:\\custom\\tools\\my_pairer.exe -u <UDID_REDACTED> --verbose"

    def test_custom_android_binary_redacts_serial(self) -> None:
        cmd = ["/opt/bin/custom_tool", "-s", "SECRET_DEVICE_SERIAL", "shell"]
        formatted = format_command_for_display(cmd)
        assert "SECRET_DEVICE_SERIAL" not in formatted
        assert formatted == "/opt/bin/custom_tool -s <SERIAL_REDACTED> shell"


# ============================================================================
# 12. LOW: Storage Keys Distinction
# ============================================================================


class TestLowStorageKeysDistinction:
    """Verifies amount_data_available_bytes and total_data_available_bytes are kept distinct."""

    def test_storage_distinct_keys(self) -> None:
        raw = """TotalDiskCapacity: 128000000000
TotalDataCapacity: 120000000000
AmountDataAvailable: 50000000000
TotalDataAvailable: 55000000000
"""
        facts, err = parse_disk_usage_output(raw, 0)
        assert err is None
        assert facts is not None
        assert facts["amount_data_available_bytes"] == 50000000000
        assert facts["total_data_available_bytes"] == 55000000000
        assert "data_available_bytes" not in facts


# ============================================================================
# F1: Android Provider Status Truthfulness
# ============================================================================


class TestF1AndroidProviderStatusTruthfulness:
    """Verifies that Android provider_statuses truthfully reflects real discovery outcome."""

    @pytest.fixture(autouse=True)
    def clean_sessions(self) -> Any:
        device_session_manager._sessions.clear()
        yield
        device_session_manager._sessions.clear()

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_adb_return_code_1_stderr_failed(self) -> None:
        """1. return_code=1, stdout='', stderr='failed' -> state=ERROR, adb_available=True, provider_statuses['android']='ERROR'."""
        mock_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=1,
            stdout="",
            stderr="failed",
            duration_seconds=0.1,
        )
        bridge = AndroidDeviceBridge()
        with (
            patch("shutil.which", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_res),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios,
        ):
            mock_ios.return_value.is_available.return_value = False
            res = bridge.discover_devices()
            assert res.state == AdbDeviceState.ERROR
            assert res.adb_available is True
            statuses = _trigger_discovery()
            assert statuses["android"] == "ERROR"

    def test_adb_return_code_127(self) -> None:
        """2. return_code=127, stdout='' -> ERROR."""
        mock_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=127,
            stdout="",
            stderr="",
            duration_seconds=0.1,
        )
        bridge = AndroidDeviceBridge()
        with (
            patch("shutil.which", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_res),
        ):
            res = bridge.discover_devices()
            assert res.state == AdbDeviceState.ERROR
            assert res.adb_available is True

    def test_adb_return_code_1_with_header_stdout(self) -> None:
        """3. return_code=1, stdout='List of devices attached\\n' -> ERROR (must NOT be NO_DEVICE)."""
        mock_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=1,
            stdout="List of devices attached\n",
            stderr="error: protocol fault",
            duration_seconds=0.1,
        )
        bridge = AndroidDeviceBridge()
        with (
            patch("shutil.which", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_res),
        ):
            res = bridge.discover_devices()
            assert res.state == AdbDeviceState.ERROR
            assert res.adb_available is True

    def test_adb_return_code_0_zero_devices(self) -> None:
        """4. return_code=0, stdout='List of devices attached\\n' -> NO_DEVICE / provider AVAILABLE."""
        mock_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=0,
            stdout="List of devices attached\n\n",
            stderr="",
            duration_seconds=0.1,
        )
        bridge = AndroidDeviceBridge()
        with (
            patch("shutil.which", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_res),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios,
        ):
            mock_ios.return_value.is_available.return_value = False
            res = bridge.discover_devices()
            assert res.state == AdbDeviceState.NO_DEVICE
            assert res.adb_available is True
            statuses = _trigger_discovery()
            assert statuses["android"] == "AVAILABLE"

    def test_adb_not_found_on_path(self) -> None:
        """5. adb not found -> UNAVAILABLE."""
        bridge = AndroidDeviceBridge()
        with (
            patch("shutil.which", return_value=None),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios,
        ):
            mock_ios.return_value.is_available.return_value = False
            res = bridge.discover_devices()
            assert res.state == AdbDeviceState.ERROR
            assert res.adb_available is False
            statuses = _trigger_discovery()
            assert statuses["android"] == "UNAVAILABLE"

    def test_android_error_ios_available_http_200_real_discovery(self, client: TestClient) -> None:
        """Android ERROR + iOS AVAILABLE -> HTTP 200, truthful statuses, iOS devices preserved."""
        mock_adb_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=1,
            stdout="",
            stderr="failed",
            duration_seconds=0.1,
        )
        mock_ios_disc = IOSDiscoveryResult(
            udids=["00008030-001E4C123456802E"],
            status=IOSToolchainStatus.AVAILABLE,
        )
        with (
            patch("shutil.which", side_effect=lambda x: "C:\\tools\\" + x if x else None),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_adb_res),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios_getter,
        ):
            mock_ios = mock_ios_getter.return_value
            mock_ios.is_available.return_value = True
            mock_ios.discover_devices_result.return_value = mock_ios_disc
            mock_ios.validate_pairing.return_value = (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "ok",
            )
            mock_ios.get_identity.return_value = None

            resp = client.get("/api/v1/devices")
            assert resp.status_code == 200
            data = resp.json()
            assert data["provider_statuses"] == {"android": "ERROR", "ios": "AVAILABLE"}
            assert len(data["devices"]) == 1
            assert data["devices"][0]["platform"] == Platform.IOS.value
            ios_sess = device_session_manager.get_session(data["devices"][0]["device_id"])
            assert ios_sess is not None
            assert ios_sess.raw_serial == "00008030-001E4C123456802E"

    def test_android_available_ios_error_http_200_real_discovery(self, client: TestClient) -> None:
        """Android AVAILABLE + iOS ERROR -> HTTP 200, truthful statuses."""
        mock_adb_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=0,
            stdout="List of devices attached\n\n",
            stderr="",
            duration_seconds=0.1,
        )
        mock_ios_disc = IOSDiscoveryResult(
            udids=[],
            status=IOSToolchainStatus.ERROR,
            error="usbmuxd died",
        )
        with (
            patch("shutil.which", side_effect=lambda x: "C:\\tools\\" + x if x else None),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_adb_res),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios_getter,
        ):
            mock_ios = mock_ios_getter.return_value
            mock_ios.is_available.return_value = True
            mock_ios.discover_devices_result.return_value = mock_ios_disc

            resp = client.get("/api/v1/devices")
            assert resp.status_code == 200
            data = resp.json()
            assert data["provider_statuses"] == {"android": "AVAILABLE", "ios": "ERROR"}

    def test_both_providers_error_returns_503_real_discovery(self, client: TestClient) -> None:
        """Both ERROR -> preserve current intended HTTP 503 behavior."""
        mock_adb_res = CommandResult(
            command=["adb", "devices", "-l"],
            return_code=1,
            stdout="",
            stderr="failed",
            duration_seconds=0.1,
        )
        mock_ios_disc = IOSDiscoveryResult(
            udids=[],
            status=IOSToolchainStatus.ERROR,
            error="usbmuxd died",
        )
        with (
            patch("shutil.which", side_effect=lambda x: "C:\\tools\\" + x if x else None),
            patch("vector_agent.devices.android.bridge.run_command", return_value=mock_adb_res),
            patch("vector_agent.api.devices._get_ios_bridge") as mock_ios_getter,
        ):
            mock_ios = mock_ios_getter.return_value
            mock_ios.is_available.return_value = True
            mock_ios.discover_devices_result.return_value = mock_ios_disc

            resp = client.get("/api/v1/devices")
            assert resp.status_code == 503


# ============================================================================
# F2: Developer Mode Resolver Enforcement
# ============================================================================


class TestF2DeveloperModeResolverEnforcement:
    """Verifies that developer_mode diagnostic never executes devmodectl on prohibited statuses."""

    @pytest.mark.parametrize(
        ("compat_status", "expected_diag_status", "can_execute"),
        [
            (StrategyStatus.KNOWN_UNSUPPORTED, DiagnosticStatus.UNSUPPORTED, False),
            (StrategyStatus.KNOWN_BROKEN, DiagnosticStatus.UNSUPPORTED, False),
            (StrategyStatus.RESTRICTED, DiagnosticStatus.RESTRICTED, False),
            (StrategyStatus.RUNTIME_UNAVAILABLE, DiagnosticStatus.UNSUPPORTED, False),
            (StrategyStatus.UNKNOWN, DiagnosticStatus.INCONCLUSIVE, False),
            (StrategyStatus.SUPPORTED, DiagnosticStatus.PASS, True),
            (StrategyStatus.RUNTIME_PROBE_REQUIRED, DiagnosticStatus.PASS, True),
        ],
    )
    def test_resolver_status_execution_matrix(
        self,
        compat_status: StrategyStatus,
        expected_diag_status: DiagnosticStatus,
        can_execute: bool,
    ) -> None:
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_available_tools.return_value = {"ideviceinfo": True, "idevicedevmodectl": True}
        bridge.get_metadata_field.return_value = "17.4"
        bridge.get_developer_mode_state.return_value = ("ENABLED", "Enabled")

        diag = IOSDeveloperModeDiagnostic(bridge)

        with patch.object(
            IOSCompatibilityResolver,
            "resolve_strategies",
            return_value=[("developer_mode", compat_status)],
        ):
            res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
            assert res.status == expected_diag_status
            if can_execute:
                assert bridge.get_developer_mode_state.call_count == 1
                assert res.status == DiagnosticStatus.PASS
            else:
                assert bridge.get_developer_mode_state.call_count == 0
                assert res.status != DiagnosticStatus.PASS


# ============================================================================
# F3: Developer Mode Parser Strictness (No Global Substring Scanning)
# ============================================================================


class TestF3DeveloperModeParserStrictness:
    """Verifies rc!=0 never globally scans text and exact target row is respected."""

    def test_rc_1_with_other_device_not_supported_returns_unknown(self) -> None:
        target = "00008030-AAAA111122223333"
        other = "00008030-BBBB111122223333"
        raw_output = f"{other}: not supported\n{target}: enabled\n"
        st, msg = parse_developer_mode_output(1, raw_output, "", target_udid=target)
        assert st == "UNKNOWN"
        assert "requires ios 16" not in msg.lower()

    def test_rc_1_with_generic_usbmuxd_not_supported_returns_unknown(self) -> None:
        target = "00008030-AAAA111122223333"
        st, msg = parse_developer_mode_output(
            1, "", "operation not supported by usbmuxd build", target_udid=target
        )
        assert st == "UNKNOWN"
        assert "requires ios 16" not in msg.lower()

    def test_ios_17_rc_1_does_not_claim_requires_ios_16(self) -> None:
        bridge = MagicMock(spec=IOSDeviceBridge)
        bridge.get_available_tools.return_value = {"ideviceinfo": True, "idevicedevmodectl": True}
        bridge.get_metadata_field.return_value = "17.4"
        bridge.get_developer_mode_state.return_value = (
            "UNKNOWN",
            "Developer Mode query exited with error (return code 1).",
        )

        diag = IOSDeveloperModeDiagnostic(bridge)
        res = diag.execute(device_id="test-dev", serial="00008030-001E4C123456802E")
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert "requires ios 16" not in res.summary.lower()

    @pytest.mark.parametrize(
        ("token", "expected_state"),
        [
            ("enabled", "ENABLED"),
            ("disabled", "DISABLED"),
            ("N/A", "NOT_APPLICABLE"),
            ("unsupported", "NOT_APPLICABLE"),
        ],
    )
    def test_rc_0_exact_target_row_states(self, token: str, expected_state: str) -> None:
        target = "00008030-AAAA111122223333"
        raw_output = f"00008030-OTHER00000000000: N/A\n{target}: {token}\n"
        st, _ = parse_developer_mode_output(0, raw_output, "", target_udid=target)
        assert st == expected_state


# ============================================================================
# F4: Strict ASCII decimal integer for Battery Percent
# ============================================================================


class TestF4BatteryPercentStrictASCIIParsing:
    """Verifies that BatteryCurrentCapacity rejects non-ASCII decimal numbers."""

    @pytest.mark.parametrize("bad_val", ["١٧", "1_0", "+3", "0x10", "12.3", ""])
    def test_rejects_non_ascii_battery_percent(self, bad_val: str) -> None:
        raw = f"BatteryCurrentCapacity: {bad_val}\nBatteryIsCharging: true\nExternalConnected: true\nFullyCharged: false\nHasBattery: true\n"
        facts, err = parse_battery_telemetry(raw, 0)
        assert facts is None
        assert err is not None

    def test_accepts_valid_ascii_battery_percent(self) -> None:
        raw = "BatteryCurrentCapacity: 88\nBatteryIsCharging: true\nExternalConnected: true\nFullyCharged: false\nHasBattery: true\n"
        facts, err = parse_battery_telemetry(raw, 0)
        assert err is None
        assert facts is not None
        assert facts["battery_current_capacity"] == 88


# ============================================================================
# F5: Pair Output Strict Positive Grammar
# ============================================================================


class TestF5PairOutputStrictPositiveGrammar:
    """Verifies that parse_pairing_pair_output rejects negative phrases and only matches strict positive grammar."""

    @pytest.mark.parametrize(
        "bad_phrase",
        [
            "never paired",
            "paired: false",
            "not successfully paired",
            "unsuccessfully paired",
            "not paired",
            "pairing failed",
            "device was not paired",
            "wasn't successfully paired",
            "couldn't be successfully paired",
            "isn't paired successfully",
            "unable to be successfully paired",
            "paired successfully: no",
            "paired successfully? false",
            "success: paired = false",
            "success: paired false",
            "successfully paired: 0",
            "dis-paired successfully",
            "SUCCESS: Paired with device X but record rejected",
        ],
    )
    def test_negative_phrases_never_yield_paired(self, bad_phrase: str) -> None:
        st, _ = parse_pairing_pair_output(0, bad_phrase, "")
        assert st != PairingState.PAIRED
        assert st == PairingState.INCONCLUSIVE

    @pytest.mark.parametrize("rc", [1, 2, 255])
    @pytest.mark.parametrize(
        "phrase",
        [
            "Device paired successfully",
            "SUCCESS: Paired with device 00008030-001E4C123456802E",
            "paired",
            "successfully paired",
        ],
    )
    def test_nonzero_return_code_never_yields_paired(self, rc: int, phrase: str) -> None:
        st, _ = parse_pairing_pair_output(rc, phrase, "")
        assert st != PairingState.PAIRED
        assert st == PairingState.ERROR

    @pytest.mark.parametrize(
        "good_phrase",
        [
            "SUCCESS: Paired with device 00008030-001E4C123456802E",
            "Successfully paired",
            "successfully paired with device 00008030-001E4C123456802E",
            "Device paired successfully",
            "SUCCESS",
        ],
    )
    def test_positive_phrases_yield_paired(self, good_phrase: str) -> None:
        st, _ = parse_pairing_pair_output(0, good_phrase, "")
        assert st == PairingState.PAIRED


# ============================================================================
# F6: UDID Validator & Defensive Revalidation
# ============================================================================


class TestF6UDIDValidatorAndDefensiveRevalidation:
    """Verifies that option-like or hyphen-wrapped junk is rejected by validator, session manager, and API."""

    @pytest.mark.parametrize(
        "junk_id",
        [
            "-AAAAAAAAAAAAAAAA-",
            "--version-AAAAAAAAAA",
            "-00008030-001E4C12-",
            "--help",
            "-u",
        ],
    )
    def test_validator_rejects_junk_ids(self, junk_id: str) -> None:
        with pytest.raises(ValidationError):
            validate_ios_udid(junk_id)

    def test_reconcile_defensively_drops_junk_ids(self) -> None:
        mgr = device_session_manager
        mgr._sessions.clear()
        mgr.reconcile_ios_discovery(
            ["-AAAAAAAAAAAAAAAA-", "--version-AAAAAAAAAA", "00008030-001E4C123456802E"],
            pair_state_fetcher=lambda u: (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZED,
                "ok",
            ),
            identity_fetcher=lambda u: None,
        )
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].raw_serial == "00008030-001E4C123456802E"

    def test_post_pair_rejects_malformed_identifier_with_400_not_500(self) -> None:
        mgr = device_session_manager
        mgr._sessions.clear()
        # Manually create a session with a malformed identifier
        sess = DeviceSession(
            device_id="malformed-dev-test",
            platform=Platform.IOS,
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            raw_serial="-INVALID-JUNK-UDID-",
            last_seen=datetime.now(UTC),
        )
        mgr._sessions["malformed-dev-test"] = sess

        client = TestClient(app)
        resp = client.post("/api/v1/devices/malformed-dev-test/pair")
        assert resp.status_code == 400
        assert "invalid identifier" in resp.json()["detail"].lower()


# ============================================================================
# F7: Pair Validation Timeout Typed Result & Zero Pair Calls
# ============================================================================


class TestF7PairValidationTimeout:
    """Verifies that pairing validation timeout relies ONLY on typed status."""

    def _setup_session(self, target_udid: str = "00008030-001E4C123456802E") -> DeviceSession:
        mgr = device_session_manager
        mgr._sessions.clear()
        mgr.reconcile_ios_discovery(
            [target_udid],
            pair_state_fetcher=lambda u: (
                ConnectionState.CONNECTED,
                DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
                "Need trust",
            ),
            identity_fetcher=lambda u: None,
        )
        return mgr.list_sessions()[0]

    def test_case_a_typed_timeout_message_x(self) -> None:
        """CASE A: typed status = TIMEOUT, message = 'x' -> PairingState.ERROR, zero pair commands."""
        session = self._setup_session()
        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Paired"))
        mock_val = IOSPairValidationResult(
            connection_state=ConnectionState.UNKNOWN,
            authorization_state=DeviceAuthorizationState.UNKNOWN,
            message="x",
            status=IOSCommandStatus.TIMEOUT,
        )
        client = TestClient(app)
        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing", return_value=mock_val
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ERROR"
        assert mock_pair.call_count == 0

    def test_case_b_typed_success_message_with_timeout_words(self) -> None:
        """CASE B: typed status = SUCCESS, message = 'Tap Trust; prompt will timeout in 60 seconds' -> NOT timeout, normal pairing proceeds."""
        session = self._setup_session()
        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Device paired successfully."))
        mock_val = IOSPairValidationResult(
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            message="Tap Trust; prompt will timeout in 60 seconds",
            status=IOSCommandStatus.SUCCESS,
        )
        client = TestClient(app)
        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing", return_value=mock_val
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PAIRED"
        assert mock_pair.call_count == 1

    def test_case_c_typed_success_message_timed_out(self) -> None:
        """CASE C: typed status = SUCCESS, message = 'timed out' -> MUST NOT convert to TIMEOUT, normal pairing proceeds."""
        session = self._setup_session()
        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Device paired successfully."))
        mock_val = IOSPairValidationResult(
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            message="timed out",
            status=IOSCommandStatus.SUCCESS,
        )
        client = TestClient(app)
        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing", return_value=mock_val
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PAIRED"
        assert mock_pair.call_count == 1

    def test_case_d_typed_timeout_without_timeout_wording(self) -> None:
        """CASE D: typed TIMEOUT, message contains no timeout wording -> ERROR, zero pair commands."""
        session = self._setup_session()
        mock_pair = MagicMock(return_value=(PairingState.PAIRED, "Paired"))
        mock_val = IOSPairValidationResult(
            connection_state=ConnectionState.UNKNOWN,
            authorization_state=DeviceAuthorizationState.UNKNOWN,
            message="Connection aborted by daemon",
            status=IOSCommandStatus.TIMEOUT,
        )
        client = TestClient(app)
        with (
            patch(
                "vector_agent.api.devices.IOSDeviceBridge.validate_pairing", return_value=mock_val
            ),
            patch("vector_agent.api.devices.IOSDeviceBridge.pair_device", mock_pair),
        ):
            resp = client.post(f"/api/v1/devices/{session.device_id}/pair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ERROR"
        assert mock_pair.call_count == 0
