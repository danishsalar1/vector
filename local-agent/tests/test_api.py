"""Integration tests for the FastAPI agent."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from vector_agent.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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
            assert item["status"] in ("READY", "NOT_FOUND", "DEGRADED", "NOT_RUN")


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


class TestScansEndpoint:
    async def test_scan_not_found_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/scans/00000000-0000-0000-0000-000000000001")
        assert response.status_code == 404

    async def test_start_scan_returns_scan_id(self, client: AsyncClient) -> None:
        """Phase 0: scan creation returns a scan_id but does not run real diagnostics."""
        response = await client.post(
            "/api/v1/scans",
            json={"device_id": "dev-001"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "scan_id" in data
        assert "state" in data
