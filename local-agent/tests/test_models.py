"""Tests for Pydantic device models."""

from __future__ import annotations

from vector_agent.models.device import (
    AutomationLevel,
    CapabilityStatus,
    ConnectedDevice,
    ConnectionState,
    DeviceCapabilityProfile,
    DeviceIdentity,
    DiagnosticResult,
    DiagnosticStatus,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    ScanLifecycleState,
    ScanSummary,
)


class TestDeviceModels:
    def test_device_identity_defaults(self) -> None:
        identity = DeviceIdentity(platform=Platform.ANDROID)
        assert identity.platform == Platform.ANDROID
        assert identity.manufacturer is None
        assert identity.discovered_at is not None

    def test_capability_profile_get_unknown(self) -> None:
        profile = DeviceCapabilityProfile(
            device_id="dev-001",
            platform=Platform.ANDROID,
        )
        assert profile.get("barometer") == CapabilityStatus.UNKNOWN

    def test_capability_profile_get_present(self) -> None:
        from vector_agent.models.device import CapabilityEntry

        profile = DeviceCapabilityProfile(
            device_id="dev-001",
            platform=Platform.ANDROID,
            capabilities={
                "accelerometer": CapabilityEntry(
                    name="accelerometer",
                    status=CapabilityStatus.PRESENT,
                    source="ADB_DUMPSYS",
                )
            },
        )
        assert profile.get("accelerometer") == CapabilityStatus.PRESENT
        assert profile.get("gyroscope") == CapabilityStatus.UNKNOWN

    def test_connected_device_has_id(self) -> None:
        device = ConnectedDevice(connection_state=ConnectionState.CONNECTED)
        assert device.device_id
        assert len(device.device_id) > 0

    def test_scan_summary_state_default(self) -> None:
        scan = ScanSummary(device_id="dev-001")
        assert scan.state == ScanLifecycleState.CREATED
        assert isinstance(scan.scan_id, str)
        assert scan.trust_score is None  # Never fabricate trust scores.

    def test_evidence_record_synthetic_labeled(self) -> None:
        """Synthetic evidence must be clearly labeled via source_type."""
        ev = EvidenceRecord(
            diagnostic_id="battery",
            device_id="dev-001",
            source_type=EvidenceSourceType.SYNTHETIC_TEST_ONLY,
            source_name="synthetic_battery_generator",
            collection_method="synthetic",
        )
        assert ev.source_type == EvidenceSourceType.SYNTHETIC_TEST_ONLY

    def test_evidence_confidence_range(self) -> None:
        """Confidence and reliability must be clamped to [0, 1]."""
        ev = EvidenceRecord(
            diagnostic_id="storage",
            device_id="dev-001",
            source_type=EvidenceSourceType.ADB_GETPROP,
            source_name="getprop ro.product.model",
            collection_method="adb",
            confidence=0.85,
            reliability=0.95,
        )
        assert 0.0 <= ev.confidence <= 1.0
        assert 0.0 <= ev.reliability <= 1.0

    def test_diagnostic_result_unsupported(self) -> None:
        """UNSUPPORTED is a valid status and must not be treated as FAIL."""
        result = DiagnosticResult(
            diagnostic_id="barometer",
            diagnostic_name="Barometer",
            category="sensors",
            status=DiagnosticStatus.UNSUPPORTED,
            automation_level=AutomationLevel.AUTOMATIC,
            summary="Device does not have a barometer sensor.",
        )
        assert result.status == DiagnosticStatus.UNSUPPORTED
        # UNSUPPORTED != FAIL: this is a critical design invariant.
        assert result.status != DiagnosticStatus.FAIL
