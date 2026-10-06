"""iOS version, model, and capability compatibility resolver.

Invariants:
- Does NOT hardcode per-version test arrays.
- Evaluates ordered candidate evidence strategies dynamically.
- Distinguishes SUPPORTED, KNOWN_UNSUPPORTED, KNOWN_BROKEN, RESTRICTED, RUNTIME_UNAVAILABLE.
- Distinguishes current-state verification from maximum verification.
- Older iOS software is NEVER classified as hardware failure.
- Handles skipped major versions (e.g. iOS 18 to 26/27) and unknown future releases safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from vector_agent.devices.ios.version import AppleOSVersion
from vector_agent.models.device import DeviceAuthorizationState


class StrategyStatus(StrEnum):
    """Status of an evidence extraction strategy for a specific device state."""

    SUPPORTED = "SUPPORTED"
    KNOWN_UNSUPPORTED = "KNOWN_UNSUPPORTED"
    KNOWN_BROKEN = "KNOWN_BROKEN"
    RESTRICTED = "RESTRICTED"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    RUNTIME_PROBE_REQUIRED = "RUNTIME_PROBE_REQUIRED"
    UNKNOWN = "UNKNOWN"


class StrategyMaturity(StrEnum):
    """Maturity level of an evidence extraction strategy.

    Distinguishes implementation readiness from physical device qualification:
    - CODE_TESTED: Strategy implemented and covered by unit/mock tests.
    - UPSTREAM_DOCUMENTED: Behavior documented in Apple/libimobiledevice research.
    - RUNTIME_PROBED: Observed dynamically on live transport.
    - HARDWARE_VALIDATED: Qualified on physical reference hardware (hardware smoke test run).
    """

    CODE_TESTED = "CODE_TESTED"
    UPSTREAM_DOCUMENTED = "UPSTREAM_DOCUMENTED"
    RUNTIME_PROBED = "RUNTIME_PROBED"
    HARDWARE_VALIDATED = "HARDWARE_VALIDATED"


@dataclass(frozen=True)
class EvidenceStrategy:
    """A concrete evidence source strategy for a diagnostic."""

    strategy_id: str
    description: str
    required_tool: str
    min_version: tuple[int, ...] | None = None
    max_version: tuple[int, ...] | None = None
    known_broken_from: tuple[int, ...] | None = None
    known_broken_to: tuple[int, ...] | None = None
    maturity: StrategyMaturity = StrategyMaturity.CODE_TESTED


HIGHEST_CODE_REVIEWED_MAJOR = 27


class IOSCompatibilityResolver:
    """Evaluates candidate evidence strategies and compatibility boundaries."""

    def __init__(self, available_tools: Any = None) -> None:
        if isinstance(available_tools, dict):
            self.available_tools = available_tools
        elif isinstance(available_tools, (set, list, tuple, frozenset)):
            self.available_tools = dict.fromkeys(available_tools, True)
        else:
            self.available_tools = {}

    def resolve_strategy_status(
        self,
        strategy: EvidenceStrategy,
        os_version: AppleOSVersion | None,
        auth_state: DeviceAuthorizationState = DeviceAuthorizationState.AUTHORIZED,
    ) -> StrategyStatus:
        """Evaluate if a strategy is supported on the target device."""
        # 1. Authorization guard
        if auth_state != DeviceAuthorizationState.AUTHORIZED:
            return StrategyStatus.RESTRICTED

        # 2. Tool availability guard
        if not self.available_tools.get(strategy.required_tool, False):
            return StrategyStatus.RUNTIME_UNAVAILABLE

        # 3. If version is unknown, report UNKNOWN (conservative)
        if os_version is None:
            return StrategyStatus.UNKNOWN

        # 4. Known-broken version check
        if strategy.known_broken_from is not None:
            broken_start = strategy.known_broken_from
            broken_end = strategy.known_broken_to
            if os_version.is_within(broken_start, broken_end):
                return StrategyStatus.KNOWN_BROKEN

        # 5. Version boundaries
        if strategy.min_version is not None and os_version.is_below(*strategy.min_version):
            return StrategyStatus.KNOWN_UNSUPPORTED

        if strategy.max_version is not None and not os_version.is_within(
            max_ver=strategy.max_version
        ):
            return StrategyStatus.KNOWN_UNSUPPORTED

        # 6. Global future major iOS policy (> HIGHEST_CODE_REVIEWED_MAJOR) (R10):
        # Never return fully SUPPORTED solely because version >= minimum.
        # Apply RUNTIME_PROBE_REQUIRED consistently to all version-aware strategies.
        if os_version.major > HIGHEST_CODE_REVIEWED_MAJOR:
            return StrategyStatus.RUNTIME_PROBE_REQUIRED

        return StrategyStatus.SUPPORTED

    def get_candidate_strategies(self, diagnostic_id: str) -> list[EvidenceStrategy]:
        """Return ordered list of defined strategies for a diagnostic ID."""
        if diagnostic_id == "battery_extended_telemetry":
            return [
                EvidenceStrategy(
                    strategy_id="gasgauge",
                    description="Diagnostics Relay GasGauge XML plist",
                    required_tool="idevicediagnostics",
                    min_version=(4, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
                EvidenceStrategy(
                    strategy_id="ioreg_smart_battery",
                    description="IORegistry AppleSmartBattery entry",
                    required_tool="idevicediagnostics",
                    min_version=(5, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
                EvidenceStrategy(
                    strategy_id="ioreg_armpmu_charger",
                    description="IORegistry AppleARMPMUCharger entry (legacy hardware)",
                    required_tool="idevicediagnostics",
                    min_version=(5, 0, 0),
                    max_version=(12, 5, 7),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
            ]

        if diagnostic_id == "storage_accounting":
            return [
                EvidenceStrategy(
                    strategy_id="disk_usage_domain",
                    description="Lockdown com.apple.disk_usage domain query",
                    required_tool="ideviceinfo",
                    min_version=(5, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
            ]

        if diagnostic_id == "developer_mode_state":
            return [
                EvidenceStrategy(
                    strategy_id="devmodectl_list",
                    description="Read-only Developer Mode query via idevicedevmodectl list",
                    required_tool="idevicedevmodectl",
                    min_version=(16, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
            ]

        if diagnostic_id == "charging_power_telemetry":
            return [
                EvidenceStrategy(
                    strategy_id="ioreg_charger",
                    description="IORegistry AppleARMPMUCharger / AppleSmartBattery power telemetry",
                    required_tool="idevicediagnostics",
                    min_version=(5, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
                EvidenceStrategy(
                    strategy_id="battery_domain_charger",
                    description="Lockdown com.apple.mobile.battery power state",
                    required_tool="ideviceinfo",
                    min_version=(4, 0, 0),
                    maturity=StrategyMaturity.CODE_TESTED,
                ),
            ]

        return []

    def resolve_strategies(
        self,
        diagnostic_id: str,
        os_version: AppleOSVersion | None,
        auth_state: DeviceAuthorizationState = DeviceAuthorizationState.AUTHORIZED,
    ) -> list[tuple[EvidenceStrategy, StrategyStatus]]:
        """Return all strategies for a diagnostic with their evaluated statuses."""
        candidates = self.get_candidate_strategies(diagnostic_id)
        results: list[tuple[EvidenceStrategy, StrategyStatus]] = []
        for strategy in candidates:
            status = self.resolve_strategy_status(strategy, os_version, auth_state)
            results.append((strategy, status))
        return results
