"""Integration tests for the FastAPI agent."""

from __future__ import annotations

import typing
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from vector_agent.devices.session import DeviceSession, device_session_manager
from vector_agent.main import create_app
from vector_agent.models.device import ConnectionState, DeviceCapabilityProfile, Platform


@pytest.fixture
def app() -> typing.Any:
    return create_app()


@pytest.fixture
async def client(app: typing.Any) -> typing.AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clear_sessions() -> None:
    from vector_agent.devices.session import device_session_manager

    device_session_manager.clear()


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_health_has_required_fields(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "mode" in data
        assert data["status"] == "OK"

    async def test_health_mode_live(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["mode"] in ("LIVE", "DEMO")


class TestPreflightEndpoint:
    async def test_preflight_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/preflight")
        assert response.status_code == 200

    async def test_preflight_has_items(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/preflight")
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0
        assert "overall" in data

    async def test_preflight_items_have_status(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/preflight")
        items = response.json()["items"]
        for item in items:
            assert "name" in item
            assert "status" in item
            assert item["status"] in (
                "PASS",
                "WARN",
                "FAIL",
                "NOT_INSTALLED",
                "NOT_APPLICABLE",
                "READY",
                "NOT_FOUND",
                "DEGRADED",
                "NOT_RUN",
            )


class TestDevicesEndpoint:
    async def test_devices_returns_empty_list(self, client: AsyncClient) -> None:
        """Phase 0: no device discovery implemented yet."""
        response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["devices"] == []

    async def test_unknown_device_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/devices/nonexistent-device-id")
        assert response.status_code == 404

    async def test_get_capabilities_unknown_device_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/devices/nonexistent-id/capabilities")
        assert response.status_code == 404

    async def test_get_capabilities_ios_device_returns_501(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="ios-dev-01",
            platform=Platform.IOS,
            connection_state=ConnectionState.CONNECTED,
            last_seen=datetime.now(UTC),
            raw_serial="IOS_DUMMY_SERIAL",
        )
        device_session_manager._sessions["ios-dev-01"] = session

        response = await client.get("/api/v1/devices/ios-dev-01/capabilities")
        assert response.status_code == 501
        assert "not yet implemented" in response.json()["detail"].lower()

    async def test_get_capabilities_connected_android_device(self, client: AsyncClient) -> None:
        profile = DeviceCapabilityProfile(
            device_id="dev-existing",
            platform=Platform.ANDROID,
            profile_complete=True,
        )
        session = DeviceSession(
            device_id="dev-existing",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=datetime.now(UTC),
            capability_profile=profile,
            raw_serial="DUMMY_SERIAL",
        )
        device_session_manager._sessions["dev-existing"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            response = await client.get("/api/v1/devices/dev-existing/capabilities")
        assert response.status_code == 200
        assert response.json()["device_id"] == "dev-existing"
        assert response.json()["platform"] == "ANDROID"
        assert "raw_serial" not in response.json()

    async def test_get_capabilities_unauthorized_device_returns_403(
        self, client: AsyncClient
    ) -> None:
        session = DeviceSession(
            device_id="dev-unauth",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.UNAUTHORIZED,
            last_seen=datetime.now(UTC),
            raw_serial="DUMMY_SERIAL",
        )
        device_session_manager._sessions["dev-unauth"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            response = await client.get("/api/v1/devices/dev-unauth/capabilities")
        assert response.status_code == 403
        assert "unauthorized" in response.json()["detail"].lower()

    async def test_get_capabilities_offline_device_returns_400(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="dev-offline",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.OFFLINE,
            last_seen=datetime.now(UTC),
            raw_serial="DUMMY_SERIAL",
        )
        device_session_manager._sessions["dev-offline"] = session

        response = await client.get("/api/v1/devices/dev-offline/capabilities")
        assert response.status_code == 400
        assert "not connected" in response.json()["detail"].lower()

    async def test_discovery_failure_returns_503_and_preserves_session(
        self, client: AsyncClient
    ) -> None:
        session = DeviceSession(
            device_id="dev-active",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=datetime.now(UTC),
            raw_serial="ACTIVE_SERIAL",
        )
        device_session_manager._sessions["dev-active"] = session

        with patch(
            "vector_agent.api.devices._trigger_discovery", side_effect=RuntimeError("ADB crash")
        ):
            response = await client.get("/api/v1/devices")
        assert response.status_code == 503
        assert response.json()["detail"] == "Device discovery failed."
        assert "ADB crash" not in response.text
        # An unexpected discovery exception is a failure to OBSERVE, not proof of
        # disconnection: the committed session (identity, state, epoch) is unchanged.
        assert session.connection_state == ConnectionState.CONNECTED
        assert session.session_epoch == 0
        assert session.raw_serial == "ACTIVE_SERIAL"
        assert device_session_manager.get_session("dev-active") is session
        # The error stays visible and no device list implying fresh connectivity is returned.
        assert "devices" not in response.json()

    async def test_devices_includes_explicit_platform(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="dev-p1",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=datetime.now(UTC),
            raw_serial="SERIAL_P1",
        )
        device_session_manager._sessions["dev-p1"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["devices"][0]["platform"] == "ANDROID"
        assert "raw_serial" not in data["devices"][0]


class TestScansEndpoint:
    async def test_scan_not_found_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/scans/00000000-0000-0000-0000-000000000001")
        assert response.status_code == 404

    async def test_start_scan_returns_scan_id(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="dev-001",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=datetime.now(UTC),
            raw_serial="SN001",
        )
        device_session_manager._sessions["dev-001"] = session

        response = await client.post(
            "/api/v1/scans",
            json={"device_id": "dev-001"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "scan_id" in data
        assert "state" in data

    async def test_start_scan_unknown_device_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/scans",
            json={"device_id": "nonexistent-device"},
        )
        assert response.status_code == 404

    async def test_start_scan_offline_device_returns_400(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="dev-offline",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.OFFLINE,
            last_seen=datetime.now(UTC),
            raw_serial="SN_OFFLINE",
        )
        device_session_manager._sessions["dev-offline"] = session

        response = await client.post(
            "/api/v1/scans",
            json={"device_id": "dev-offline"},
        )
        assert response.status_code == 400
