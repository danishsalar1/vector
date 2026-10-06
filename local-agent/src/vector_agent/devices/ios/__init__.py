"""iOS device bridge module."""

from vector_agent.devices.ios.bridge import (
    IOSDeviceBridge,
    IOSDiscoveryError,
    IOSDiscoveryResult,
    IOSToolchainStatus,
)
from vector_agent.devices.ios.compatibility import (
    EvidenceStrategy,
    IOSCompatibilityResolver,
    StrategyMaturity,
    StrategyStatus,
)
from vector_agent.devices.ios.parsers import (
    parse_battery_telemetry,
    parse_developer_mode_output,
    parse_disk_usage_output,
    parse_gasgauge_plist,
    parse_idevice_id_output,
    parse_ideviceinfo_key_value,
    parse_ioreg_battery_plist,
    parse_nand_plist,
    parse_pairing_pair_output,
    parse_pairing_validate_output,
)
from vector_agent.devices.ios.version import AppleOSVersion

__all__ = [
    "AppleOSVersion",
    "EvidenceStrategy",
    "IOSCompatibilityResolver",
    "IOSDeviceBridge",
    "IOSDiscoveryError",
    "IOSDiscoveryResult",
    "IOSToolchainStatus",
    "StrategyMaturity",
    "StrategyStatus",
    "parse_battery_telemetry",
    "parse_developer_mode_output",
    "parse_disk_usage_output",
    "parse_gasgauge_plist",
    "parse_idevice_id_output",
    "parse_ideviceinfo_key_value",
    "parse_ioreg_battery_plist",
    "parse_nand_plist",
    "parse_pairing_pair_output",
    "parse_pairing_validate_output",
]
