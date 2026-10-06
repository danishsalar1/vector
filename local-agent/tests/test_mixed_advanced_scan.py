"""Integration test for mixed multi-device scans with version/capability-aware iOS diagnostics."""

from unittest.mock import MagicMock

from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.devices.session import DeviceSession
from vector_agent.diagnostics.registry import create_default_registry
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    DeviceIdentity,
    Platform,
    ScanMode,
    ScanRequest,
)
from vector_agent.scan.planner import ScanPlanner


class TestMixedAdvancedDeviceScans:
    """Tests scan planning across mixed device types and iOS versions."""

    def test_mixed_fleet_planning(self) -> None:
        mock_android_bridge = MagicMock(spec=AndroidDeviceBridge)
        mock_ios_bridge = MagicMock(spec=IOSDeviceBridge)
        mock_ios_bridge.is_available.return_value = True

        registry = create_default_registry(bridge=mock_android_bridge, ios_bridge=mock_ios_bridge)

        from datetime import UTC, datetime

        now = datetime.now(UTC)

        # 1. Connected & Authorized Android device
        sess_android = DeviceSession(
            device_id="dev-android-01",
            raw_serial="SERIAL123",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZED,
            last_seen=now,
            identity=DeviceIdentity(
                platform=Platform.ANDROID,
                manufacturer="Google",
                model="Pixel 8",
                android_version="14",
            ),
        )

        # 2. Paired older iPhone (iOS 15.8)
        sess_ios_older = DeviceSession(
            device_id="dev-ios-older-02",
            raw_serial="00008110-FAKEOLDER0001",
            platform=Platform.IOS,
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZED,
            last_seen=now,
            identity=DeviceIdentity(
                platform=Platform.IOS,
                manufacturer="Apple Inc.",
                model="iPhone 7",
                product_type="iPhone9,1",
                ios_version="15.8.3",
                build_version="19H384",
                hardware_model="D10AP",
                cpu_architecture="arm64",
            ),
        )

        # 3. Paired modern iPhone (iOS 27.0)
        sess_ios_modern = DeviceSession(
            device_id="dev-ios-modern-03",
            raw_serial="00008120-FAKEMODERN0002",
            platform=Platform.IOS,
            connection_state=ConnectionState.CONNECTED,
            authorization_state=DeviceAuthorizationState.AUTHORIZED,
            last_seen=now,
            identity=DeviceIdentity(
                platform=Platform.IOS,
                manufacturer="Apple Inc.",
                model="iPhone 16 Pro",
                product_type="iPhone17,1",
                ios_version="27.0.0",
                build_version="31A100",
                hardware_model="D93AP",
                cpu_architecture="arm64e",
            ),
        )

        # 4. Unpaired iPhone
        sess_ios_unpaired = DeviceSession(
            device_id="dev-ios-unpaired-04",
            raw_serial="00008130-FAKEUNPAIRED003",
            platform=Platform.IOS,
            connection_state=ConnectionState.UNAUTHORIZED,
            authorization_state=DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            last_seen=now,
            identity=None,
        )

        planner = ScanPlanner()

        # Plan for Android -> 6 Android diagnostics
        req_android = ScanRequest(device_id="dev-android-01", mode=ScanMode.FULL_VERIFICATION)
        plan_android = planner.plan(session=sess_android, registry=registry, request=req_android)
        assert len(plan_android.diagnostics_planned) == 6
        assert "software_inventory" not in plan_android.diagnostics_planned
        assert "battery_extended_telemetry" not in plan_android.diagnostics_planned
        assert "battery_telemetry" in plan_android.diagnostics_planned

        # Plan for Older iOS -> 6 iOS diagnostics
        req_older = ScanRequest(device_id="dev-ios-older-02", mode=ScanMode.FULL_VERIFICATION)
        plan_older = planner.plan(session=sess_ios_older, registry=registry, request=req_older)
        assert len(plan_older.diagnostics_planned) == 6
        assert "software_inventory" in plan_older.diagnostics_planned
        assert "battery_extended_telemetry" in plan_older.diagnostics_planned
        assert "battery_telemetry" not in plan_older.diagnostics_planned

        # Plan for Modern iOS -> 6 iOS diagnostics
        req_modern = ScanRequest(device_id="dev-ios-modern-03", mode=ScanMode.FULL_VERIFICATION)
        plan_modern = planner.plan(session=sess_ios_modern, registry=registry, request=req_modern)
        assert len(plan_modern.diagnostics_planned) == 6
        assert "software_inventory" in plan_modern.diagnostics_planned
        assert "battery_extended_telemetry" in plan_modern.diagnostics_planned
        assert "storage_accounting" in plan_modern.diagnostics_planned
        assert "developer_mode_state" in plan_modern.diagnostics_planned
        assert "charging_power_telemetry" in plan_modern.diagnostics_planned

        # Plan for Unpaired iOS -> 0 planned, 12 skipped (6 Android NOT_APPLICABLE + 6 iOS RESTRICTED)
        req_unpaired = ScanRequest(device_id="dev-ios-unpaired-04", mode=ScanMode.FULL_VERIFICATION)
        plan_unpaired = planner.plan(
            session=sess_ios_unpaired, registry=registry, request=req_unpaired
        )
        assert len(plan_unpaired.diagnostics_planned) == 0
        assert len(plan_unpaired.diagnostics_skipped) == 12
