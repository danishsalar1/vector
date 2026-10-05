"""Focused tests for Phase 1: Diagnostic Protocol + Battery Migration.

Covers:
- DiagnosticDefinition validation
- Diagnostic registry registration and lookup
- Duplicate diagnostic rejection
- BatteryTelemetryDiagnostic success path
- EvidenceRecord production and provenance
- Incomplete telemetry → INCONCLUSIVE
- Battery PASS does not claim battery health
- No fabricated normalized battery-health value
- TrustEngineStatus defaults to NOT_READY
- trust_score remains None while engine is NOT_READY
- Existing Android battery API compatibility (via existing tests)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from vector_agent.devices.android.bridge import BatteryTelemetry, BatteryTelemetryResult
from vector_agent.diagnostics import (
    DiagnosticDefinition,
    DiagnosticRegistry,
    DuplicateDiagnosticError,
)
from vector_agent.diagnostics.battery import (
    BATTERY_TELEMETRY_DEFINITION,
    BatteryTelemetryDiagnostic,
)
from vector_agent.models.device import (
    AutomationLevel,
    DiagnosticStatus,
    EvidenceSourceType,
    Platform,
    ScanSummary,
    TrustEngineStatus,
)

# ============================================================
# Fixtures
# ============================================================

_NOW = datetime.now(UTC)
_DEVICE_ID = "android-test001"
_SERIAL = "FABRICATED001"

_FULL_TELEMETRY = BatteryTelemetry(
    level=83,
    scale=100,
    status="Charging",
    health="Good",
    plugged="USB",
    voltage_mv=4127,
    temperature_tenths_c=314,
    technology="Li-ion",
    present=True,
    raw_output="level: 83\nvoltage: 4127\ntemperature: 314",
    collected_at=_NOW,
)

_PARTIAL_TELEMETRY = BatteryTelemetry(
    level=None,
    scale=None,
    status=None,
    health=None,
    plugged=None,
    voltage_mv=None,
    temperature_tenths_c=None,
    technology=None,
    present=None,
    raw_output="",
    collected_at=_NOW,
)


def _make_bridge_result(
    telemetry: BatteryTelemetry | None,
    status: str,
    confidence: float = 0.95,
    error: str | None = None,
) -> BatteryTelemetryResult:
    return BatteryTelemetryResult(
        telemetry=telemetry,
        status=status,
        confidence=confidence,
        evidence_source="ADB / dumpsys battery",
        collection_method="adb shell dumpsys battery",
        error=error,
        collected_at=_NOW,
    )


def _make_diagnostic(bridge_result: BatteryTelemetryResult) -> BatteryTelemetryDiagnostic:
    bridge = MagicMock()
    bridge.get_battery_telemetry.return_value = bridge_result
    return BatteryTelemetryDiagnostic(bridge)


# ============================================================
# DiagnosticDefinition
# ============================================================


class TestDiagnosticDefinition:
    def test_battery_definition_id(self) -> None:
        assert BATTERY_TELEMETRY_DEFINITION.diagnostic_id == "battery_telemetry"

    def test_battery_definition_name(self) -> None:
        assert BATTERY_TELEMETRY_DEFINITION.name == "Battery Telemetry Verification"

    def test_battery_definition_category(self) -> None:
        assert BATTERY_TELEMETRY_DEFINITION.category == "battery"

    def test_battery_definition_android_only(self) -> None:
        assert Platform.ANDROID in BATTERY_TELEMETRY_DEFINITION.supported_platforms
        assert Platform.IOS not in BATTERY_TELEMETRY_DEFINITION.supported_platforms

    def test_battery_definition_automatic(self) -> None:
        assert BATTERY_TELEMETRY_DEFINITION.automation_level == AutomationLevel.AUTOMATIC

    def test_battery_definition_timeout_reasonable(self) -> None:
        assert 0 < BATTERY_TELEMETRY_DEFINITION.timeout_seconds <= 60

    def test_definition_is_immutable(self) -> None:
        """DiagnosticDefinition is a frozen dataclass."""
        with pytest.raises((AttributeError, TypeError)):
            BATTERY_TELEMETRY_DEFINITION.diagnostic_id = "tampered"

    def test_custom_definition_fields(self) -> None:
        from vector_agent.models.device import VerificationLevel

        defn = DiagnosticDefinition(
            diagnostic_id="camera_functional",
            name="Camera Functional Test",
            category="cameras",
            verification_level=VerificationLevel.FUNCTIONAL_VERIFICATION,
            supported_platforms=frozenset({Platform.ANDROID}),
            required_capabilities=frozenset({"rear_camera"}),
            automation_level=AutomationLevel.AUTOMATIC,
            timeout_seconds=15.0,
        )
        assert defn.diagnostic_id == "camera_functional"
        assert defn.verification_level == VerificationLevel.FUNCTIONAL_VERIFICATION
        assert Platform.ANDROID in defn.supported_platforms
        assert "rear_camera" in defn.required_capabilities


# ============================================================
# Diagnostic protocol
# ============================================================


class TestDiagnosticProtocol:
    def test_is_supported_android(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        assert diag.is_supported(Platform.ANDROID) is True

    def test_is_not_supported_ios(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        assert diag.is_supported(Platform.IOS) is False

    def test_definition_property(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        assert diag.definition is BATTERY_TELEMETRY_DEFINITION


# ============================================================
# DiagnosticRegistry
# ============================================================


class TestDiagnosticRegistry:
    def test_empty_registry(self) -> None:
        registry = DiagnosticRegistry()
        assert registry.count == 0
        assert registry.get_all() == []

    def test_register_and_retrieve(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        assert registry.count == 1
        assert registry.get("battery_telemetry") is diag

    def test_duplicate_registration_rejected(self) -> None:
        registry = DiagnosticRegistry()
        diag1 = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        diag2 = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag1)
        with pytest.raises(DuplicateDiagnosticError, match="battery_telemetry"):
            registry.register(diag2)

    def test_get_nonexistent_returns_none(self) -> None:
        registry = DiagnosticRegistry()
        assert registry.get("nonexistent_id") is None

    def test_get_definition(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        defn = registry.get_definition("battery_telemetry")
        assert defn is not None
        assert defn.diagnostic_id == "battery_telemetry"

    def test_get_definition_nonexistent(self) -> None:
        registry = DiagnosticRegistry()
        assert registry.get_definition("does_not_exist") is None

    def test_get_by_platform_android(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        android_diags = registry.get_by_platform(Platform.ANDROID)
        assert len(android_diags) == 1
        assert android_diags[0].definition.diagnostic_id == "battery_telemetry"

    def test_get_by_platform_ios_empty(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        ios_diags = registry.get_by_platform(Platform.IOS)
        assert ios_diags == []

    def test_get_by_category(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        battery_diags = registry.get_by_category("battery")
        assert len(battery_diags) == 1

    def test_get_by_category_no_match(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        sensor_diags = registry.get_by_category("sensors")
        assert sensor_diags == []

    def test_list_ids_sorted(self) -> None:
        registry = DiagnosticRegistry()
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        registry.register(diag)
        assert registry.list_ids() == ["battery_telemetry"]


# ============================================================
# BatteryTelemetryDiagnostic — success path
# ============================================================


class TestBatteryDiagnosticSuccess:
    def test_pass_with_full_telemetry(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.status == DiagnosticStatus.PASS

    def test_result_has_correct_ids(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.diagnostic_id == "battery_telemetry"
        assert result.diagnostic_name == "Battery Telemetry Verification"
        assert result.category == "battery"

    def test_result_has_timing(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_pass_summary_does_not_claim_health(self) -> None:
        """PASS summary must not imply battery health assessment."""
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.summary is not None
        summary_lower = result.summary.lower()
        # Must not claim battery is healthy
        assert "battery is healthy" not in summary_lower
        assert "battery health is" not in summary_lower
        # Must explicitly note it's only telemetry collection
        assert "telemetry" in summary_lower or "collection" in summary_lower


# ============================================================
# EvidenceRecord production and provenance
# ============================================================


class TestBatteryEvidenceRecords:
    def test_evidence_records_produced(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert len(result.evidence) > 0

    def test_evidence_source_is_adb_dumpsys(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            assert ev.source_type == EvidenceSourceType.ADB_DUMPSYS

    def test_evidence_device_id_propagated(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            assert ev.device_id == _DEVICE_ID

    def test_evidence_diagnostic_id_propagated(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            assert ev.diagnostic_id == "battery_telemetry"

    def test_battery_level_evidence_raw_value(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        level_records = [
            ev for ev in result.evidence if ev.metadata.get("field") == "battery_level"
        ]
        assert len(level_records) == 1
        assert level_records[0].raw_value == "83"
        assert level_records[0].unit == "percent"

    def test_battery_level_not_normalized_to_health(self) -> None:
        """Battery charge percentage must NOT be mapped to a normalized health value.

        This is a critical design invariant: battery level != battery health.
        """
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        level_records = [
            ev for ev in result.evidence if ev.metadata.get("field") == "battery_level"
        ]
        assert len(level_records) == 1
        # normalized_value must be None for battery level — it is NOT a health score
        assert level_records[0].normalized_value is None, (
            "battery level must not be normalized as a health value"
        )

    def test_no_raw_output_in_evidence(self) -> None:
        """raw_output from the bridge must not appear in evidence records.

        Raw OEM command output must not leak through the evidence pipeline.
        """
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            # raw_value of individual parsed fields is fine; entire raw_output is not
            assert ev.raw_value != _FULL_TELEMETRY.raw_output, (
                "raw_output from bridge must not appear as an evidence raw_value"
            )

    def test_evidence_confidence_propagated(self) -> None:
        bridge_result = _make_bridge_result(_FULL_TELEMETRY, "PASS", confidence=0.87)
        diag = _make_diagnostic(bridge_result)
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            assert ev.confidence == pytest.approx(0.87)

    def test_evidence_reliability_range(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        for ev in result.evidence:
            assert 0.0 <= ev.reliability <= 1.0

    def test_voltage_evidence_unit(self) -> None:
        diag = _make_diagnostic(_make_bridge_result(_FULL_TELEMETRY, "PASS"))
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        voltage_records = [
            ev for ev in result.evidence if ev.metadata.get("field") == "battery_voltage"
        ]
        assert len(voltage_records) == 1
        assert voltage_records[0].unit == "mV"


# ============================================================
# Incomplete telemetry → INCONCLUSIVE
# ============================================================


class TestBatteryDiagnosticInconclusive:
    def test_inconclusive_when_bridge_returns_inconclusive(self) -> None:
        diag = _make_diagnostic(
            _make_bridge_result(_PARTIAL_TELEMETRY, "INCONCLUSIVE", confidence=0.3)
        )
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.status == DiagnosticStatus.INCONCLUSIVE

    def test_inconclusive_no_fabricated_evidence(self) -> None:
        """With completely empty telemetry, no evidence records should be fabricated."""
        diag = _make_diagnostic(
            _make_bridge_result(_PARTIAL_TELEMETRY, "INCONCLUSIVE", confidence=0.3)
        )
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        # All telemetry fields are None, so no records should be emitted
        assert result.evidence == []

    def test_inconclusive_is_not_fail(self) -> None:
        """INCONCLUSIVE must never be treated as FAIL."""
        diag = _make_diagnostic(
            _make_bridge_result(_PARTIAL_TELEMETRY, "INCONCLUSIVE", confidence=0.3)
        )
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.status != DiagnosticStatus.FAIL

    def test_partial_telemetry_some_fields(self) -> None:
        """Partial telemetry with only level+voltage should still produce those records."""
        partial = BatteryTelemetry(
            level=55,
            scale=None,
            status=None,
            health=None,
            plugged=None,
            voltage_mv=3800,
            temperature_tenths_c=None,
            technology=None,
            present=None,
            raw_output="level: 55\nvoltage: 3800",
            collected_at=_NOW,
        )
        bridge_result = _make_bridge_result(partial, "INCONCLUSIVE", confidence=0.6)
        diag = _make_diagnostic(bridge_result)
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        # Should have records for level and voltage only
        fields = {ev.metadata.get("field") for ev in result.evidence}
        assert "battery_level" in fields
        assert "battery_voltage" in fields


# ============================================================
# Error path
# ============================================================


class TestBatteryDiagnosticError:
    def test_bridge_error_propagated(self) -> None:
        diag = _make_diagnostic(
            _make_bridge_result(None, "ERROR", confidence=0.0, error="ADB disconnected")
        )
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.status == DiagnosticStatus.ERROR

    def test_bridge_exception_becomes_error(self) -> None:
        bridge = MagicMock()
        bridge.get_battery_telemetry.side_effect = RuntimeError("ADB crashed")
        diag = BatteryTelemetryDiagnostic(bridge)
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.status == DiagnosticStatus.ERROR
        assert result.summary is not None
        assert "crashed" in result.summary.lower() or "failed" in result.summary.lower()

    def test_error_result_has_timing(self) -> None:
        bridge = MagicMock()
        bridge.get_battery_telemetry.side_effect = RuntimeError("timeout")
        diag = BatteryTelemetryDiagnostic(bridge)
        result = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert result.started_at is not None
        assert result.completed_at is not None


# ============================================================
# Trust Engine safety
# ============================================================


class TestTrustEngineSafety:
    def test_scan_summary_trust_engine_default_not_ready(self) -> None:
        """TrustEngineStatus must default to NOT_READY."""
        scan = ScanSummary(device_id="dev-001")
        assert scan.trust_engine_status == TrustEngineStatus.NOT_READY

    def test_scan_summary_trust_score_none_by_default(self) -> None:
        """trust_score must be None when TrustEngineStatus is NOT_READY."""
        scan = ScanSummary(device_id="dev-001")
        assert scan.trust_score is None

    def test_trust_engine_status_values(self) -> None:
        """Verify all three required states exist."""
        assert TrustEngineStatus.NOT_READY == "NOT_READY"
        assert TrustEngineStatus.ACTIVE == "ACTIVE"
        assert TrustEngineStatus.ERROR == "ERROR"

    def test_new_scan_never_has_trust_score(self) -> None:
        """A freshly created scan must never carry a fabricated trust score."""
        scan = ScanSummary(device_id="test-device")
        # Trust engine is not ready → score must be None
        assert scan.trust_engine_status == TrustEngineStatus.NOT_READY
        assert scan.trust_score is None, (
            "trust_score must not be fabricated while trust engine is NOT_READY"
        )

    def test_trust_confidence_also_none_by_default(self) -> None:
        scan = ScanSummary(device_id="dev-002")
        assert scan.trust_confidence is None
