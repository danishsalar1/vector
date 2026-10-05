"""Android device bridge and standard diagnostics support."""

from vector_agent.devices.android.bridge import (
    AdbDeviceState,
    AndroidDeviceBridge,
    AndroidDiscoveryResult,
    AndroidIdentity,
    BatteryTelemetry,
    BatteryTelemetryResult,
)
from vector_agent.devices.android.camera import (
    CameraDeviceEntry,
    CameraInventory,
    CameraInventoryResult,
    parse_camera_inventory,
)
from vector_agent.devices.android.display import (
    DisplayMetrics,
    DisplayMetricsResult,
    parse_display_metrics,
)
from vector_agent.devices.android.memory import (
    MemoryTelemetry,
    MemoryTelemetryResult,
    parse_proc_meminfo,
)
from vector_agent.devices.android.storage import (
    StorageTelemetry,
    StorageTelemetryResult,
    parse_storage_df,
)
from vector_agent.devices.android.thermal import (
    ThermalSensorSample,
    ThermalTelemetry,
    ThermalTelemetryResult,
    parse_dumpsys_thermal,
)

__all__ = [
    "AdbDeviceState",
    "AndroidDeviceBridge",
    "AndroidDiscoveryResult",
    "AndroidIdentity",
    "BatteryTelemetry",
    "BatteryTelemetryResult",
    "CameraDeviceEntry",
    "CameraInventory",
    "CameraInventoryResult",
    "DisplayMetrics",
    "DisplayMetricsResult",
    "MemoryTelemetry",
    "MemoryTelemetryResult",
    "StorageTelemetry",
    "StorageTelemetryResult",
    "ThermalSensorSample",
    "ThermalTelemetry",
    "ThermalTelemetryResult",
    "parse_camera_inventory",
    "parse_display_metrics",
    "parse_dumpsys_thermal",
    "parse_proc_meminfo",
    "parse_storage_df",
]
