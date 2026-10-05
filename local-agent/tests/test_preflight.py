"""Unit and integration tests for SystemPreflightService and /api/v1/system/preflight."""

from __future__ import annotations

import typing
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from vector_agent.main import create_app
from vector_agent.models.preflight import PreflightOverall, PreflightStatus
from vector_agent.security.subprocess_policy import CommandResult
from vector_agent.services.preflight import SystemPreflightService


@pytest.fixture
def app() -> typing.Any:
    return create_app()


@pytest.fixture
async def client(app: typing.Any) -> typing.AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestSystemPreflightService:
    def test_preflight_returns_typed_response(self) -> None:
        service = SystemPreflightService()
        result = service.run_preflight()

        assert result.overall in (
            PreflightOverall.READY,
            PreflightOverall.PARTIAL,
            PreflightOverall.BLOCKED,
        )
        assert result.overall_status == result.overall
        assert len(result.checks) == 5
        assert result.items == result.checks
        assert result.timestamp is not None

        check_ids = [c.id for c in result.checks]
        assert "platform_os" in check_ids
        assert "python_runtime" in check_ids
        assert "vector_agent" in check_ids
        assert "android_adb" in check_ids
        assert "ios_libimobiledevice" in check_ids

    def test_platform_check_windows(self) -> None:
        service = SystemPreflightService()
        with patch("platform.system", return_value="Windows"):
            check = service._check_platform()
            assert check.status == PreflightStatus.PASS
            assert check.required is True
            assert "Windows" in check.message

    def test_platform_check_non_windows(self) -> None:
        service = SystemPreflightService()
        with patch("platform.system", return_value="Linux"):
            check = service._check_platform()
            assert check.status == PreflightStatus.WARN
            assert check.required is False
            assert "Linux detected" in check.message

    def test_python_runtime_check_supported(self) -> None:
        service = SystemPreflightService()
        check = service._check_python_runtime()
        # The test environment is running Python 3.11+
        assert check.status == PreflightStatus.PASS
        assert check.required is True
        assert "operational" in check.message

    def test_python_runtime_check_unsupported(self) -> None:
        service = SystemPreflightService()
        with patch("sys.version_info", (3, 10, 0)):
            check = service._check_python_runtime()
            assert check.status == PreflightStatus.FAIL
            assert check.required is True
            assert "Python 3.11 or newer is required" in check.message

    def test_adb_found_and_version_succeeds(self) -> None:
        service = SystemPreflightService()
        mock_result = CommandResult(
            command=["adb", "version"],
            return_code=0,
            stdout="Android Debug Bridge version 1.0.41\nVersion 35.0.1-11580242",
            stderr="",
            duration_seconds=0.01,
        )

        with (
            patch("shutil.which", return_value="/mock/path/to/adb"),
            patch("vector_agent.services.preflight.run_command", return_value=mock_result),
        ):
            check = service._check_android_tooling()
            assert check.status == PreflightStatus.PASS
            assert "Android Platform Tools available" in check.message
            assert "Android Debug Bridge version 1.0.41" in str(check.details)

    def test_adb_missing(self) -> None:
        service = SystemPreflightService()
        with patch("shutil.which", return_value=None):
            check = service._check_android_tooling()
            assert check.status == PreflightStatus.NOT_INSTALLED
            assert check.required is False
            assert "Android Platform Tools are not installed" in check.message

    def test_adb_version_fails(self) -> None:
        service = SystemPreflightService()
        mock_result = CommandResult(
            command=["adb", "version"],
            return_code=1,
            stdout="",
            stderr="error: cannot execute",
            duration_seconds=0.01,
        )

        with (
            patch("shutil.which", return_value="/mock/path/to/adb"),
            patch("vector_agent.services.preflight.run_command", return_value=mock_result),
        ):
            check = service._check_android_tooling()
            assert check.status == PreflightStatus.WARN
            assert "non-zero exit code" in check.message

    def test_ios_tooling_found(self) -> None:
        service = SystemPreflightService()
        mock_result = CommandResult(
            command=["ideviceinfo", "--version"],
            return_code=0,
            stdout="ideviceinfo 1.3.0",
            stderr="",
            duration_seconds=0.01,
        )

        def mock_which(cmd: str) -> str | None:
            if "idevice" in cmd:
                return f"/mock/path/{cmd}"
            return None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("vector_agent.services.preflight.run_command", return_value=mock_result),
        ):
            check = service._check_ios_tooling()
            assert check.status == PreflightStatus.PASS
            assert "iOS device communication tooling available" in check.message

    def test_ios_tooling_missing(self) -> None:
        service = SystemPreflightService()
        with patch("shutil.which", return_value=None):
            check = service._check_ios_tooling()
            assert check.status == PreflightStatus.NOT_INSTALLED
            assert check.required is False
            assert "iOS device tooling is not available on PATH" in check.message

    def test_missing_optional_tooling_results_in_partial(self) -> None:
        service = SystemPreflightService()
        # Mock ADB and iOS as missing
        with patch("shutil.which", return_value=None):
            result = service.run_preflight()
            # Mandatory checks (Platform, Python, Agent) pass, but optional tools are missing
            assert result.overall == PreflightOverall.PARTIAL

    def test_exception_in_tool_detection_handled_safely(self) -> None:
        service = SystemPreflightService()
        with (
            patch("shutil.which", return_value="/mock/adb"),
            patch(
                "vector_agent.services.preflight.run_command",
                side_effect=RuntimeError("Subprocess failed"),
            ),
        ):
            check = service._check_android_tooling()
            assert check.status == PreflightStatus.WARN
            assert "Subprocess failed" in str(check.details)

    def test_critical_no_device_enumeration_executed(self) -> None:
        """CRITICAL INVARIANT:

        Preflight MUST NOT invoke 'adb devices', 'idevice_id -l', or any
        command that enumerates or communicates with connected phones.
        """
        service = SystemPreflightService()
        executed_commands: list[list[str]] = []

        def spy_run_command(cmd: typing.Any, **kwargs: typing.Any) -> CommandResult:
            executed_commands.append(list(cmd))
            return CommandResult(
                command=list(cmd),
                return_code=0,
                stdout="Mock version 1.0",
                stderr="",
                duration_seconds=0.01,
            )

        with (
            patch("shutil.which", return_value="/mock/tool"),
            patch("vector_agent.services.preflight.run_command", side_effect=spy_run_command),
        ):
            service.run_preflight()

        for cmd in executed_commands:
            joined = " ".join(cmd).lower()
            assert "devices" not in joined, f"Preflight must not execute device enumeration: {cmd}"
            assert "-l" not in joined, f"Preflight must not enumerate iOS devices: {cmd}"
            assert "dumpsys" not in joined, f"Preflight must not query device dumpsys: {cmd}"
            assert "getprop" not in joined, f"Preflight must not query device getprop: {cmd}"

    def test_unhandled_exception_in_single_optional_check_is_isolated(self) -> None:
        service = SystemPreflightService()

        with patch.object(
            service, "_check_platform", side_effect=RuntimeError("Kernel query failure")
        ):
            response = service.run_preflight()

        platform_check = next(c for c in response.checks if c.id == "platform_os")
        assert platform_check.status == PreflightStatus.FAIL
        assert "Kernel query failure" not in (platform_check.details or "")
        assert response.overall == PreflightOverall.PARTIAL

    def test_unhandled_exception_in_required_check_blocks_overall(self) -> None:
        service = SystemPreflightService()

        with patch.object(
            service, "_check_agent_readiness", side_effect=RuntimeError("Agent crash")
        ):
            response = service.run_preflight()

        agent_check = next(c for c in response.checks if c.id == "vector_agent")
        assert agent_check.status == PreflightStatus.FAIL
        assert response.overall == PreflightOverall.BLOCKED


class TestPreflightEndpointIntegration:
    async def test_endpoint_returns_200_and_typed_schema(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/preflight")
        assert response.status_code == 200

        data = response.json()
        assert "overall" in data
        assert "overall_status" in data
        assert data["overall"] in ("READY", "PARTIAL", "BLOCKED")
        assert "checks" in data
        assert len(data["checks"]) == 5
        assert "items" in data

        for check in data["checks"]:
            assert "id" in check
            assert "name" in check
            assert "category" in check
            assert "status" in check
            assert check["status"] in ("PASS", "WARN", "FAIL", "NOT_INSTALLED", "NOT_APPLICABLE")
            assert "message" in check
            assert "required" in check
            assert "details" in check

    async def test_preflight_does_not_leak_environment_secrets(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system/preflight")
        assert response.status_code == 200
        raw_text = response.text

        # Ensure raw PATH or authorization tokens are not dumped in endpoint output
        assert "PATH=" not in raw_text
        assert "TOKEN" not in raw_text
        assert "SECRET" not in raw_text
