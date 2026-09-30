"""Tests for Android API endpoints (no real hardware required)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vector_agent.devices.android.bridge import (
    AdbDeviceEntry,
    AdbDeviceState,
    AndroidDiscoveryResult,
    AndroidIdentity,
    BatteryTelemetry,
    BatteryTelemetryResult,
)
from vector_agent.main import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


_FAKE_SERIAL = "FABRICATED001"
_NOW = datetime.now(UTC)

_FAKE_IDENTITY = AndroidIdentity(
    serial=_FAKE_SERIAL,
    manufacturer="FakeManufacturer",
    model="FakeModel X",
    device_codename="fakedevice",
    android_version="15",
    sdk_level=35,
    brand="FakeBrand",
    retrieved_at=_NOW,
)

_FAKE_BATTERY = BatteryTelemetry(
    level=83,
    scale=100,
    status="Charging",
    health="Good",
    plugged="USB",
    voltage_mv=4127,
    temperature_tenths_c=314,
    technology="Li-ion",
    present=True,
    raw_output="level: 83\nvoltage: 4127",
    collected_at=_NOW,
)


def _authorized_discovery() -> AndroidDiscoveryResult:
    return AndroidDiscoveryResult(
        state=AdbDeviceState.DEVICE,
        devices=[
            AdbDeviceEntry(
                serial=_FAKE_SERIAL,
                state=AdbDeviceState.DEVICE,
                qualifiers={"model": "FakeModel"},
            )
        ],
        message="Android device connected and authorized.",
        adb_available=True,
    )


def _no_device_discovery() -> AndroidDiscoveryResult:
    return AndroidDiscoveryResult(
        state=AdbDeviceState.NO_DEVICE,
        devices=[],
        message="No Android devices detected.",
        adb_available=True,
    )


def _unauthorized_discovery() -> AndroidDiscoveryResult:
    return AndroidDiscoveryResult(
        state=AdbDeviceState.UNAUTHORIZED,
        devices=[
            AdbDeviceEntry(
                serial=_FAKE_SERIAL,
                state=AdbDeviceState.UNAUTHORIZED,
                qualifiers={},
            )
        ],
        message="Android device detected but not authorized.",
        adb_available=True,
    )


class TestAndroidDiscoveryEndpoint:
    def test_authorized_device_returns_device_state(self, client: TestClient) -> None:
        with (
            patch(
                "vector_agent.api.android.AndroidDeviceBridge.discover_devices",
                return_value=_authorized_discovery(),
            ),
            patch(
                "vector_agent.api.android.AndroidDeviceBridge.get_identity",
                return_value=_fake_identity_for(serial=_FAKE_SERIAL),
            ),
        ):
            resp = client.get("/api/v1/devices/android")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "DEVICE"
        assert data["count"] == 1
        assert data["adb_available"] is True
        device = data["devices"][0]
        assert device["connection_state"] == "DEVICE"
        assert device["manufacturer"] == "FakeManufacturer"
        assert device["model"] == "FakeModel X"
        assert device["android_version"] == "15"

    def test_no_device_state(self, client: TestClient) -> None:
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.discover_devices",
            return_value=_no_device_discovery(),
        ):
            resp = client.get("/api/v1/devices/android")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "NO_DEVICE"
        assert data["count"] == 0

    def test_unauthorized_device_state(self, client: TestClient) -> None:
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.discover_devices",
            return_value=_unauthorized_discovery(),
        ):
            resp = client.get("/api/v1/devices/android")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "UNAUTHORIZED"
        device = data["devices"][0]
        assert device["connection_state"] == "UNAUTHORIZED"
        # No identity fields for unauthorized devices
        assert device["manufacturer"] is None
        assert device["model"] is None

    def test_adb_not_available(self, client: TestClient) -> None:
        discovery = AndroidDiscoveryResult(
            state=AdbDeviceState.ERROR,
            devices=[],
            message="Android Platform Tools are required.",
            adb_available=False,
        )
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.discover_devices",
            return_value=discovery,
        ):
            resp = client.get("/api/v1/devices/android")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adb_available"] is False
        assert data["state"] == "ERROR"


class TestAndroidBatteryEndpoint:
    def _discover_and_get_device_id(self, client: TestClient) -> str:
        """Helper: run discovery and return device_id for the test device."""
        with (
            patch(
                "vector_agent.api.android.AndroidDeviceBridge.discover_devices",
                return_value=_authorized_discovery(),
            ),
            patch(
                "vector_agent.api.android.AndroidDeviceBridge.get_identity",
                return_value=_fake_identity_for(serial=_FAKE_SERIAL),
            ),
        ):
            resp = client.get("/api/v1/devices/android")
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert len(devices) == 1
        return devices[0]["device_id"]

    def test_battery_telemetry_pass(self, client: TestClient) -> None:
        device_id = self._discover_and_get_device_id(client)
        battery_result = BatteryTelemetryResult(
            telemetry=_FAKE_BATTERY,
            status="PASS",
            confidence=0.95,
            evidence_source="ADB / dumpsys battery",
            collection_method="adb shell dumpsys battery",
            error=None,
            collected_at=_NOW,
        )
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.get_battery_telemetry",
            return_value=battery_result,
        ):
            resp = client.get(f"/api/v1/devices/android/{device_id}/battery")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PASS"
        assert data["level_pct"] == 83
        assert data["voltage_v"] == pytest.approx(4.127, abs=0.001)
        assert data["temperature_c"] == pytest.approx(31.4, abs=0.01)
        assert data["evidence_source"] == "ADB / dumpsys battery"
        assert "PASS" in data["status_note"]
        assert (
            "not represent" in data["status_note"].lower()
            or "does not" in data["status_note"].lower()
        )

    def test_battery_status_note_does_not_claim_health(self, client: TestClient) -> None:
        """Regression: PASS note must explicitly disclaim battery health."""
        device_id = self._discover_and_get_device_id(client)
        battery_result = BatteryTelemetryResult(
            telemetry=_FAKE_BATTERY,
            status="PASS",
            confidence=0.95,
            evidence_source="ADB / dumpsys battery",
            collection_method="adb shell dumpsys battery",
            error=None,
            collected_at=_NOW,
        )
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.get_battery_telemetry",
            return_value=battery_result,
        ):
            resp = client.get(f"/api/v1/devices/android/{device_id}/battery")
        data = resp.json()
        note = data["status_note"].lower()
        assert (
            "health-assessment" in note
            or "health assessment" in note
            or "battery-health" in note
            or "battery health" in note
        )

    def test_battery_unknown_device_id_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/devices/android/android-nonexistent/battery")
        assert resp.status_code == 404

    def test_battery_error_state(self, client: TestClient) -> None:
        device_id = self._discover_and_get_device_id(client)
        error_result = BatteryTelemetryResult(
            telemetry=None,
            status="ERROR",
            confidence=0.0,
            evidence_source="ADB / dumpsys battery",
            collection_method="adb shell dumpsys battery",
            error="Device disconnected during test.",
            collected_at=_NOW,
        )
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.get_battery_telemetry",
            return_value=error_result,
        ):
            resp = client.get(f"/api/v1/devices/android/{device_id}/battery")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ERROR"
        assert data["error"] is not None
        assert data["level_pct"] is None

    def test_battery_inconclusive_state(self, client: TestClient) -> None:
        device_id = self._discover_and_get_device_id(client)
        inconclusive_battery = BatteryTelemetry(
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
        inconclusive_result = BatteryTelemetryResult(
            telemetry=inconclusive_battery,
            status="INCONCLUSIVE",
            confidence=0.3,
            evidence_source="ADB / dumpsys battery",
            collection_method="adb shell dumpsys battery",
            error=None,
            collected_at=_NOW,
        )
        with patch(
            "vector_agent.api.android.AndroidDeviceBridge.get_battery_telemetry",
            return_value=inconclusive_result,
        ):
            resp = client.get(f"/api/v1/devices/android/{device_id}/battery")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "INCONCLUSIVE"


def _fake_identity_for(serial: str) -> AndroidIdentity:
    return AndroidIdentity(
        serial=serial,
        manufacturer="FakeManufacturer",
        model="FakeModel X",
        device_codename="fakedevice",
        android_version="15",
        sdk_level=35,
        brand="FakeBrand",
        retrieved_at=datetime.now(UTC),
    )
