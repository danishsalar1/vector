"""Unit tests for IOSCompatibilityResolver and StrategyStatus."""

from vector_agent.devices.ios.compatibility import (
    IOSCompatibilityResolver,
    StrategyMaturity,
    StrategyStatus,
)
from vector_agent.devices.ios.version import AppleOSVersion
from vector_agent.models.device import DeviceAuthorizationState


class TestIOSCompatibilityResolver:
    """Tests for dynamic strategy resolution across iOS version families."""

    def test_developer_mode_strategy_version_boundary(self) -> None:
        tools = {"idevicedevmodectl": True}
        resolver = IOSCompatibilityResolver(available_tools=tools)

        # iOS 15.x -> KNOWN_UNSUPPORTED
        strategies_15 = resolver.resolve_strategies(
            "developer_mode_state",
            os_version=AppleOSVersion.parse("15.8.3"),
        )
        assert len(strategies_15) == 1
        assert strategies_15[0][1] == StrategyStatus.KNOWN_UNSUPPORTED

        # iOS 16.0 -> SUPPORTED
        strategies_16 = resolver.resolve_strategies(
            "developer_mode_state",
            os_version=AppleOSVersion.parse("16.0.0"),
        )
        assert strategies_16[0][1] == StrategyStatus.SUPPORTED

        # iOS 27.0 -> SUPPORTED
        strategies_27 = resolver.resolve_strategies(
            "developer_mode_state",
            os_version=AppleOSVersion.parse("27.0.0"),
        )
        assert strategies_27[0][1] == StrategyStatus.SUPPORTED

    def test_tool_missing_causes_runtime_unavailable(self) -> None:
        # Tool not available on host
        tools = {"idevicedevmodectl": False}
        resolver = IOSCompatibilityResolver(available_tools=tools)
        strategies = resolver.resolve_strategies(
            "developer_mode_state",
            os_version=AppleOSVersion.parse("17.4.0"),
        )
        assert strategies[0][1] == StrategyStatus.RUNTIME_UNAVAILABLE

    def test_unauthorized_state_causes_restricted(self) -> None:
        tools = {"idevicedevmodectl": True}
        resolver = IOSCompatibilityResolver(available_tools=tools)
        strategies = resolver.resolve_strategies(
            "developer_mode_state",
            os_version=AppleOSVersion.parse("17.4.0"),
            auth_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
        )
        assert strategies[0][1] == StrategyStatus.RESTRICTED

    def test_future_unknown_ios_major_requires_runtime_probe(self) -> None:
        tools = {"idevicediagnostics": True}
        resolver = IOSCompatibilityResolver(available_tools=tools)

        # Unknown future major release (e.g. iOS 28, 30, 99)
        # Fragile relay/IORegistry strategies should return RUNTIME_PROBE_REQUIRED
        strategies_30 = resolver.resolve_strategies(
            "battery_extended_telemetry",
            os_version=AppleOSVersion.parse("30.0.0"),
        )
        assert len(strategies_30) == 3
        assert strategies_30[0][1] == StrategyStatus.RUNTIME_PROBE_REQUIRED
        assert strategies_30[1][1] == StrategyStatus.RUNTIME_PROBE_REQUIRED

    def test_battery_extended_strategies_resolution_and_maturity(self) -> None:
        tools = {"idevicediagnostics": True}
        resolver = IOSCompatibilityResolver(available_tools=tools)

        # On iOS 17.0, GasGauge and AppleSmartBattery are supported, legacy charger is not
        strategies = resolver.resolve_strategies(
            "battery_extended_telemetry",
            os_version=AppleOSVersion.parse("17.0.0"),
        )
        assert len(strategies) == 3
        # Strategy 0: GasGauge
        assert strategies[0][0].strategy_id == "gasgauge"
        assert strategies[0][0].maturity == StrategyMaturity.CODE_TESTED
        assert strategies[0][1] == StrategyStatus.SUPPORTED
        # Strategy 1: AppleSmartBattery
        assert strategies[1][0].strategy_id == "ioreg_smart_battery"
        assert strategies[1][0].maturity == StrategyMaturity.CODE_TESTED
        assert strategies[1][1] == StrategyStatus.SUPPORTED
        # Strategy 2: AppleARMPMUCharger (max 12.5.7) -> KNOWN_UNSUPPORTED on iOS 17
        assert strategies[2][0].strategy_id == "ioreg_armpmu_charger"
        assert strategies[2][1] == StrategyStatus.KNOWN_UNSUPPORTED
