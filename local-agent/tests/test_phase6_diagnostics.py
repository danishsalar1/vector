"""Definition and diagnostic execution unit tests for Phase 6.

Verifies:
- DiagnosticDefinition contracts (ID, category, verification level, platform, timeout)
- Diagnostic execution results across PASS, INCONCLUSIVE, RESTRICTED, UNSUPPORTED, ERROR
- EvidenceRecord population (every PASS has evidence)
- Summary safety (no leaked raw stderr, no serial numbers, no false health claims)
- Timeout budget exhaustion handling
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.android.camera import (
    CameraDeviceEntry,
    CameraInventory,
    CameraInventoryResult,
)
from vector_agent.devices.android.display import DisplayMetrics, DisplayMetricsResult
from vector_agent.devices.android.memory import MemoryTelemetry, MemoryTelemetryResult
from vector_agent.devices.android.storage import (
    StorageTelemetry,
    StorageTelemetryResult,
)
from vector_agent.devices.android.thermal import (
    ThermalSensorSample,
    ThermalTelemetry,
    ThermalTelemetryResult,
)
from vector_agent.diagnostics.camera.camera_diagnostic import (
    CAMERA_INVENTORY_DEFINITION,
    CameraInventoryDiagnostic,
)
from vector_agent.diagnostics.display.display_diagnostic import (
    DISPLAY_METRICS_DEFINITION,
    DisplayMetricsDiagnostic,
)
from vector_agent.diagnostics.memory.memory_diagnostic import (
    MEMORY_TELEMETRY_DEFINITION,
    MemoryTelemetryDiagnostic,
)
from vector_agent.diagnostics.storage.storage_diagnostic import (
    STORAGE_TELEMETRY_DEFINITION,
    StorageTelemetryDiagnostic,
)
from vector_agent.diagnostics.thermal.thermal_diagnostic import (
    THERMAL_TELEMETRY_DEFINITION,
    ThermalTelemetryDiagnostic,
)
from vector_agent.models.device import (
    DiagnosticStatus,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)

_DEVICE_ID = "android-device-abc123"
_SERIAL = "RAW_SECRET_SERIAL_777"
_NOW = datetime.now(UTC)


# ============================================================
# Definition-Level Tests
# ============================================================


class TestDiagnosticDefinitions:
    """Verifies that all Phase 6 definitions satisfy domain requirements."""

    def test_storage_definition(self) -> None:
        defn = STORAGE_TELEMETRY_DEFINITION
        assert defn.diagnostic_id == "storage_telemetry"
        assert defn.name == "Storage Telemetry Verification"
        assert defn.category == "storage"
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.ANDROID})
        assert not defn.requires_probe
        assert defn.required_capabilities == frozenset()
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds > 0

    def test_memory_definition(self) -> None:
        defn = MEMORY_TELEMETRY_DEFINITION
        assert defn.diagnostic_id == "memory_telemetry"
        assert defn.name == "Memory Telemetry Verification"
        assert defn.category == "memory"
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.ANDROID})
        assert not defn.requires_probe
        assert defn.required_capabilities == frozenset()
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds > 0

    def test_thermal_definition(self) -> None:
        defn = THERMAL_TELEMETRY_DEFINITION
        assert defn.diagnostic_id == "thermal_telemetry"
        assert defn.name == "Thermal Telemetry Verification"
        assert defn.category == "thermal"
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.ANDROID})
        assert not defn.requires_probe
        assert defn.required_capabilities == frozenset()
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds > 0

    def test_display_definition(self) -> None:
        defn = DISPLAY_METRICS_DEFINITION
        assert defn.diagnostic_id == "display_metrics"
        assert defn.name == "Display Metrics Verification"
        assert defn.category == "display"
        # Level 1 Runtime Detection: reports declared display configuration
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.ANDROID})
        assert not defn.requires_probe
        assert defn.required_capabilities == frozenset()
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds > 0

    def test_camera_definition(self) -> None:
        defn = CAMERA_INVENTORY_DEFINITION
        assert defn.diagnostic_id == "camera_inventory"
        assert defn.name == "Camera Inventory Verification"
        assert defn.category == "camera"
        # Level 1 Runtime Detection: inventory from service
        assert defn.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert defn.supported_platforms == frozenset({Platform.ANDROID})
        assert not defn.requires_probe
        assert defn.required_capabilities == frozenset()
        assert defn.prerequisites == frozenset()
        assert defn.timeout_seconds > 0


# ============================================================
# Storage Telemetry Diagnostic Execution Tests
# ============================================================


class TestStorageDiagnosticExecution:
    """Verifies execution behavior of StorageTelemetryDiagnostic."""

    def test_execute_pass(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_storage_telemetry.return_value = StorageTelemetryResult(
            telemetry=StorageTelemetry(
                total_bytes=100_000_000,
                used_bytes=25_000_000,
                available_bytes=75_000_000,
                utilization_percent=25.0,
                logical_target="/data",
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / df -k /data",
            collection_method="adb shell df -k /data",
            error=None,
            collected_at=_NOW,
        )

        diag = StorageTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) >= 4
        assert res.summary is not None
        assert "storage chip hardware health" in res.summary  # disclaimer present
        assert _SERIAL not in (res.summary or "")
        # Check evidence source
        for ev in res.evidence:
            assert ev.source_type == EvidenceSourceType.ADB_SHELL
            assert _SERIAL not in ev.raw_value or ""

    def test_execute_inconclusive(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_storage_telemetry.return_value = StorageTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source="ADB / df -k /data",
            collection_method="adb shell df -k /data",
            error="No storage entry found.",
            collected_at=_NOW,
        )
        diag = StorageTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert res.evidence == []

    def test_execute_restricted(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_storage_telemetry.return_value = StorageTelemetryResult(
            telemetry=None,
            status="RESTRICTED",
            confidence=0.0,
            evidence_source="ADB / df -k /data",
            collection_method="adb shell df -k /data",
            error="Permission denied",
            collected_at=_NOW,
        )
        diag = StorageTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.RESTRICTED
        assert "restricted" in (res.summary or "").lower()

    def test_execute_bridge_exception_maps_to_error(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_storage_telemetry.side_effect = RuntimeError("ADB pipe broken")
        diag = StorageTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.ERROR
        assert "ADB pipe broken" not in (res.summary or "")  # no leaked internal error string
        assert "execution error" in (res.summary or "").lower()

    def test_execute_zero_budget_times_out(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        diag = StorageTelemetryDiagnostic(bridge)
        # Pass timeout=0.0 directly
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL, timeout=0.0)
        assert res.status == DiagnosticStatus.ERROR
        assert "timed out" in (res.summary or "").lower()
        bridge.get_storage_telemetry.assert_not_called()


# ============================================================
# Memory Telemetry Diagnostic Execution Tests
# ============================================================


class TestMemoryDiagnosticExecution:
    """Verifies execution behavior of MemoryTelemetryDiagnostic."""

    def test_execute_pass(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_memory_telemetry.return_value = MemoryTelemetryResult(
            telemetry=MemoryTelemetry(
                mem_total_bytes=6_000_000_000,
                mem_free_bytes=1_000_000_000,
                mem_available_bytes=3_000_000_000,
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / /proc/meminfo",
            collection_method="adb shell cat /proc/meminfo",
            error=None,
            collected_at=_NOW,
        )

        diag = MemoryTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 3
        assert "RAM chip hardware integrity" in (res.summary or "")
        assert _SERIAL not in str(res)

    def test_execute_inconclusive(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_memory_telemetry.return_value = MemoryTelemetryResult(
            telemetry=None,
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source="ADB / /proc/meminfo",
            collection_method="adb shell cat /proc/meminfo",
            error="MemTotal not found",
            collected_at=_NOW,
        )
        diag = MemoryTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.INCONCLUSIVE

    def test_execute_bridge_exception(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_memory_telemetry.side_effect = ConnectionResetError("Device reset")
        diag = MemoryTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.ERROR
        assert "Device reset" not in (res.summary or "")


# ============================================================
# Thermal Telemetry Diagnostic Execution Tests
# ============================================================


class TestThermalDiagnosticExecution:
    """Verifies execution behavior of ThermalTelemetryDiagnostic."""

    def test_execute_pass(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_thermal_telemetry.return_value = ThermalTelemetryResult(
            telemetry=ThermalTelemetry(
                thermal_status_code=0,
                thermal_status_label="NONE",
                sensor_count=1,
                sensors=[
                    ThermalSensorSample(
                        name="cpu-0",
                        temperature_celsius=37.0,
                        sensor_type="3",
                    )
                ],
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / dumpsys thermalservice",
            collection_method="adb shell dumpsys thermalservice",
            error=None,
            collected_at=_NOW,
        )

        diag = ThermalTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 3  # status_code, sensor_count, sensor_cpu-0
        assert "cooling defect absence" in (res.summary or "")

    def test_execute_unsupported(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_thermal_telemetry.return_value = ThermalTelemetryResult(
            telemetry=None,
            status="UNSUPPORTED",
            confidence=0.0,
            evidence_source="ADB / dumpsys thermalservice",
            collection_method="adb shell dumpsys thermalservice",
            error="Thermal service not found",
            collected_at=_NOW,
        )
        diag = ThermalTelemetryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)
        assert res.status == DiagnosticStatus.UNSUPPORTED
        assert "not available" in (res.summary or "").lower()


# ============================================================
# Display Metrics Diagnostic Execution Tests
# ============================================================


class TestDisplayDiagnosticExecution:
    """Verifies execution behavior of DisplayMetricsDiagnostic."""

    def test_execute_pass(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_display_metrics.return_value = DisplayMetricsResult(
            metrics=DisplayMetrics(
                physical_width=1080,
                physical_height=2400,
                physical_density=440,
                override_width=None,
                override_height=None,
                override_density=None,
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / wm size + wm density",
            collection_method="adb shell wm size; wm density",
            error=None,
            collected_at=_NOW,
        )

        diag = DisplayMetricsDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 2  # resolution + density
        assert "burn-in, or screen defects" in (res.summary or "")

    def test_execute_pass_with_override(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_display_metrics.return_value = DisplayMetricsResult(
            metrics=DisplayMetrics(
                physical_width=1440,
                physical_height=3200,
                physical_density=560,
                override_width=1080,
                override_height=2400,
                override_density=420,
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / wm size + wm density",
            collection_method="adb shell wm size; wm density",
            error=None,
            collected_at=_NOW,
        )

        diag = DisplayMetricsDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 4  # physical res/density + override res/density


# ============================================================
# Camera Inventory Diagnostic Execution Tests
# ============================================================


class TestCameraDiagnosticExecution:
    """Verifies execution behavior of CameraInventoryDiagnostic."""

    def test_execute_pass(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_camera_inventory.return_value = CameraInventoryResult(
            inventory=CameraInventory(
                camera_count=2,
                cameras=[
                    CameraDeviceEntry(camera_id="0", facing="BACK"),
                    CameraDeviceEntry(camera_id="1", facing="FRONT"),
                ],
                collected_at=_NOW,
            ),
            status="PASS",
            confidence=1.0,
            evidence_source="ADB / dumpsys media.camera",
            collection_method="adb shell dumpsys media.camera",
            error=None,
            collected_at=_NOW,
        )

        diag = CameraInventoryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.PASS
        assert len(res.evidence) == 3  # count + 2 camera entries
        assert "focus, capture, or image quality" in (res.summary or "")

    def test_execute_zero_cameras_is_inconclusive(self) -> None:
        bridge = MagicMock(spec=AndroidDeviceBridge)
        bridge.get_camera_inventory.return_value = CameraInventoryResult(
            inventory=CameraInventory(
                camera_count=0,
                cameras=[],
                collected_at=_NOW,
            ),
            status="INCONCLUSIVE",
            confidence=0.0,
            evidence_source="ADB / dumpsys media.camera",
            collection_method="adb shell dumpsys media.camera",
            error="Camera service reported 0 camera devices. Inconclusive without reference specification.",
            collected_at=_NOW,
        )

        diag = CameraInventoryDiagnostic(bridge)
        res = diag.execute(device_id=_DEVICE_ID, serial=_SERIAL)

        assert res.status == DiagnosticStatus.INCONCLUSIVE
        assert res.evidence == []
        assert "0 camera" in (res.summary or "")
