"""Regression evidence for the emergency safety repair (fabricated telemetry)."""

import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from vector_agent.devices.android.bridge import (
    AdbDeviceEntry,
    AdbDeviceState,
    AndroidDeviceBridge,
    _evaluate_battery_telemetry,
    _parse_battery_output,
)
from vector_agent.devices.session import device_session_manager
from vector_agent.diagnostics.battery.battery_diagnostic import BatteryTelemetryDiagnostic
from vector_agent.main import create_app
from vector_agent.models.device import VerificationLevel
from vector_agent.scan.service import scan_service
from vector_agent.security.subprocess_policy import CommandResult


@pytest.mark.parametrize(
    "field,value",
    [
        ("level", "-5"),
        ("level", "250"),
        ("voltage", "-1"),
        ("voltage", "0"),
        ("voltage", "4127 mV"),
        ("voltage", "4127000"),
        ("temperature", "-9999"),
        ("temperature", "9999"),
        ("temperature", "31.4 C"),
        ("level", "NaN"),
        ("scale", "0"),
        ("scale", "200"),
        ("present", "garbage"),
    ],
)
def test_invalid_reading_never_passes(field: str, value: str) -> None:
    values = {
        "level": "83",
        "scale": "100",
        "voltage": "4127",
        "temperature": "314",
        "status": "2",
        "present": "true",
    }
    values[field] = value
    tel = _parse_battery_output(
        "\n".join(f"{k}: {v}" for k, v in values.items()), datetime.now(UTC)
    )
    assert _evaluate_battery_telemetry(tel)[0] == "INCONCLUSIVE"


@pytest.mark.parametrize("level,temp", [(0, -400), (100, 850), (83, 314)])
def test_valid_unusual_measurements_remain_telemetry(level: int, temp: int) -> None:
    tel = _parse_battery_output(
        f"level: {level}\nscale: 100\nvoltage: 4127\ntemperature: {temp}\nstatus: 2",
        datetime.now(UTC),
    )
    assert _evaluate_battery_telemetry(tel)[0] == "PASS"


@pytest.mark.parametrize("raw", ["", "level: 80", "voltage: 4100"])
def test_missing_readings_are_inconclusive(raw: str) -> None:
    assert (
        _evaluate_battery_telemetry(_parse_battery_output(raw, datetime.now(UTC)))[0]
        == "INCONCLUSIVE"
    )


@pytest.mark.parametrize("status_val", ["1", "99", "garbage"])
def test_unconfirmed_or_invalid_status_without_temp_is_inconclusive(status_val: str) -> None:
    values = {
        "level": "83",
        "scale": "100",
        "voltage": "4127",
        "status": status_val,
        "present": "true",
    }
    tel = _parse_battery_output(
        "\n".join(f"{k}: {v}" for k, v in values.items()), datetime.now(UTC)
    )
    assert _evaluate_battery_telemetry(tel)[0] == "INCONCLUSIVE"


@pytest.mark.parametrize("level,status", [("250", "INCONCLUSIVE"), ("83", "PASS")])
async def test_real_bridge_legacy_api_and_diagnostic_serialization(level: str, status: str) -> None:
    device_session_manager.clear()
    device_session_manager.reconcile_android_discovery(
        [AdbDeviceEntry("FABRICATED001", AdbDeviceState.DEVICE, {})]
    )
    device_id = device_session_manager.list_sessions()[0].device_id
    raw = f"level: {level}\nscale: 100\nvoltage: 4127\ntemperature: 314\nstatus: 2"
    with (
        patch(
            "vector_agent.devices.android.bridge.run_command",
            return_value=CommandResult([], 0, raw, "", 0),
        ),
        patch.object(AndroidDeviceBridge, "_require_adb", return_value="adb"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
        ) as client:
            response = await client.get(f"/api/v1/devices/android/{device_id}/battery")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == status
        assert data["level_pct"] == (83 if status == "PASS" else None)
        assert data["confidence"] is None
        assert "FABRICATED001" not in response.text
        diag = BatteryTelemetryDiagnostic(AndroidDeviceBridge(adb_path="adb"))
        result = diag.execute(device_id=device_id, serial="FABRICATED001")
        assert result.status.value == status
        assert diag.definition.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert result.evidence
        assert all(e.confidence is None and e.reliability is None for e in result.evidence)
        assert '"250"' not in result.model_dump_json()
    device_session_manager.clear()


async def test_blocking_battery_subprocess_does_not_block_health() -> None:
    device_session_manager.clear()
    device_session_manager.reconcile_android_discovery(
        [AdbDeviceEntry("FABRICATED001", AdbDeviceState.DEVICE, {})]
    )
    device_id = device_session_manager.list_sessions()[0].device_id
    entered, release = threading.Event(), threading.Event()

    def delayed(*args: object, **kwargs: object) -> CommandResult:
        entered.set()
        assert release.wait(5)
        return CommandResult([], 0, "level: 83", "", 0)

    with (
        patch("vector_agent.devices.android.bridge.run_command", side_effect=delayed),
        patch.object(AndroidDeviceBridge, "_require_adb", return_value="adb"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
        ) as client:
            task = asyncio.create_task(client.get(f"/api/v1/devices/android/{device_id}/battery"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                health = await asyncio.wait_for(client.get("/api/v1/health"), 1)
                assert health.status_code == 200
                assert not task.done()
            finally:
                release.set()
                await task
                device_session_manager.clear()


@pytest.mark.parametrize("level,expected", [("250", "INCONCLUSIVE"), ("83", "PASS")])
async def test_discovery_plan_scan_results_events_use_validated_telemetry(
    level: str, expected: str
) -> None:
    device_session_manager.clear()
    scan_service.clear()

    def subprocess_fixture(argv: list[str], **kwargs: object) -> CommandResult:
        if argv[-2:] == ["devices", "-l"]:
            out = "List of devices attached\nFABRICATED001 device model:Fixture\n"
        elif "getprop" in argv:
            out = "35" if argv[-1] == "ro.build.version.sdk" else "Fixture"
        elif argv[-2:] == ["dumpsys", "battery"]:
            out = f"level: {level}\nscale: 100\nvoltage: 4127\ntemperature: 314\nstatus: 2"
        elif "features" in argv:
            out = "feature:android.hardware.sensor.accelerometer\n"
        else:
            out = ""
        return CommandResult(argv, 0, out, "", 0)

    with (
        patch("vector_agent.devices.android.bridge.run_command", side_effect=subprocess_fixture),
        patch.object(AndroidDeviceBridge, "_require_adb", return_value="adb"),
        patch("vector_agent.devices.ios.bridge.IOSDeviceBridge.is_available", return_value=False),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
        ) as client:
            discovery = await client.get("/api/v1/devices")
            assert discovery.status_code == 200
            device_id = discovery.json()["devices"][0]["device_id"]
            assert device_id != "FABRICATED001"
            capabilities = await client.get(f"/api/v1/devices/{device_id}/capabilities")
            assert capabilities.status_code == 200
            request = {
                "device_id": device_id,
                "mode": "SELECTED_DIAGNOSTICS",
                "diagnostic_ids": ["battery_telemetry"],
            }
            plan = await client.post("/api/v1/scans/plan", json=request)
            assert plan.status_code == 200
            assert plan.json()["diagnostics_planned"] == ["battery_telemetry"]
            start = await client.post("/api/v1/scans?sync=true", json=request)
            assert start.status_code == 201
            scan_id = start.json()["scan_id"]
            status = await client.get(f"/api/v1/scans/{scan_id}")
            results = await client.get(f"/api/v1/scans/{scan_id}/results")
            events = await client.get(f"/api/v1/scans/{scan_id}/events")
            assert status.json()["state"] == "COMPLETED"
            data = results.json()
            assert data["trust_score"] is None and data["trust_engine_status"] == "NOT_READY"
            assert data["diagnostic_results"][0]["status"] == expected
            assert data["diagnostic_results"][0]["evidence"]
            assert events.json()["events"][-1]["event_type"] == "scan.completed"
            for response in (discovery, capabilities, plan, start, status, results, events):
                assert "FABRICATED001" not in response.text
    scan_service.clear()
    device_session_manager.clear()


def test_all_android_standard_diagnostics_publish_uncalibrated_scores_as_null() -> None:
    from tests.test_phase6_orchestration import _setup_mock_bridge
    from vector_agent.diagnostics.registry import create_default_registry

    registry = create_default_registry(_setup_mock_bridge())
    assert len(registry.list_ids()) == 6
    for diagnostic_id in registry.list_ids():
        result = registry.get(diagnostic_id).execute(device_id="fixture", serial="FABRICATED001")
        assert result.evidence
        assert all(
            e["reliability"] is None and e["confidence"] is None
            for e in result.model_dump(mode="json")["evidence"]
        )


@pytest.mark.parametrize("platform", ["IOS", "ANDROID"])
@pytest.mark.parametrize("route", ["/api/v1/scans/plan", "/api/v1/scans"])
async def test_unauthorized_scan_guidance_is_platform_neutral(platform: str, route: str) -> None:
    from vector_agent.devices.session import DeviceSession
    from vector_agent.models.device import ConnectionState, Platform

    device_session_manager.clear()
    session = DeviceSession(
        device_id="fixture-unauthorized",
        platform=Platform(platform),
        connection_state=ConnectionState.UNAUTHORIZED,
        last_seen=datetime.now(UTC),
        raw_serial="FABRICATED_PRIVATE",
    )
    device_session_manager._sessions[session.device_id] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver"
    ) as client:
        response = await client.post(route, json={"device_id": session.device_id})
    assert response.status_code == 403
    assert "USB debugging" not in response.json()["detail"]
    assert "unauthorized" in response.json()["detail"]
    assert "FABRICATED_PRIVATE" not in response.text
    device_session_manager.clear()
