"""Integration tests for discovery provider isolation and never-auto-pair guarantee.

Verifies:
- Discovery never triggers 'idevicepair pair' under any circumstances (Section 38).
- Complete provider isolation between Android and iOS during discovery (Section 39):
  * Android failure + iOS success
  * iOS failure + Android success
  * Both success
  * iOS zero devices
  * iOS provider toolchain unavailable
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vector_agent.api.devices import _trigger_discovery
from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.devices.session import device_session_manager
from vector_agent.models.device import (
    DeviceAuthorizationState,
    Platform,
)
from vector_agent.security.subprocess_policy import CommandResult

_PAIRED_UDID = "00008120-001E4C123456802E"
_UNPAIRED_UDID = "00008030-001A2B3C4D5E002E"


@pytest.fixture(autouse=True)
def clean_sessions() -> None:
    device_session_manager.clear()


class TestNeverAutoPairGuarantee:
    """Verify Section 38: Discovery must never mutate trust or run 'pair'."""

    def test_discovery_never_runs_pair_command(self) -> None:
        executed_commands: list[list[str]] = []

        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            executed_commands.append(cmd)
            cmd_str = " ".join(cmd)

            # Android failure
            if "devices" in cmd and "-l" in cmd:
                raise ADBCommandTimeoutError("adb devices -l", 5.0)

            # iOS discovery returns 2 devices: one paired, one unpaired
            if "idevice_id" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=f"{_PAIRED_UDID}\n{_UNPAIRED_UDID}\n",
                    stderr="",
                    duration_seconds=0.01,
                )

            # idevicepair validate
            if "idevicepair" in cmd_str and "validate" in cmd_str:
                if _PAIRED_UDID in cmd_str:
                    return CommandResult(
                        command=cmd,
                        return_code=0,
                        stdout=f"SUCCESS: Validated pairing with device {_PAIRED_UDID}\n",
                        stderr="",
                        duration_seconds=0.01,
                    )
                else:
                    return CommandResult(
                        command=cmd,
                        return_code=1,
                        stdout="",
                        stderr="ERROR: Device is not paired with this host\n",
                        duration_seconds=0.01,
                    )

            # idevicepair pair - MUST NEVER BE CALLED!
            if "idevicepair" in cmd_str and "pair" in cmd_str:
                pytest.fail("CRITICAL VIOLATION: idevicepair pair was invoked during discovery!")

            # Allowlisted identity queries
            if "ideviceinfo" in cmd_str and "-k" in cmd_str:
                key = cmd[cmd.index("-k") + 1]
                val_map = {
                    "ProductType": "iPhone15,2\n",
                    "ProductVersion": "17.4.1\n",
                    "BuildVersion": "21E236\n",
                    "DeviceClass": "iPhone\n",
                }
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=val_map.get(key, "\n"),
                    stderr="",
                    duration_seconds=0.01,
                )

            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
            patch("shutil.which", return_value="C:\\tools\\tool.exe"),
        ):
            # Run production discovery trigger
            _trigger_discovery()

        # Check sessions
        paired_id = device_session_manager._make_device_id(Platform.IOS, _PAIRED_UDID)
        unpaired_id = device_session_manager._make_device_id(Platform.IOS, _UNPAIRED_UDID)

        paired_sess = device_session_manager.get_session(paired_id)
        assert paired_sess is not None
        assert paired_sess.authorization_state == DeviceAuthorizationState.AUTHORIZED
        assert paired_sess.identity is not None
        assert paired_sess.identity.model == "iPhone15,2"

        unpaired_sess = device_session_manager.get_session(unpaired_id)
        assert unpaired_sess is not None
        assert unpaired_sess.authorization_state == DeviceAuthorizationState.AUTHORIZATION_REQUIRED
        assert unpaired_sess.identity is None

        # Verify command history contains validate and identity, but ZERO pair commands
        assert any("idevice_id" in " ".join(c) for c in executed_commands)
        assert any("validate" in " ".join(c) for c in executed_commands)
        assert not any("pair" in c and "validate" not in c for c in executed_commands)


class TestProviderIsolation:
    """Verify Section 39: Android and iOS provider isolation in _trigger_discovery."""

    def test_android_failure_ios_success(self) -> None:
        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            cmd_str = " ".join(cmd)
            if "devices" in cmd and "-l" in cmd:
                raise ADBCommandTimeoutError("adb devices -l", 5.0)
            if "idevice_id" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=f"{_PAIRED_UDID}\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "validate" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=f"SUCCESS: Validated pairing with device {_PAIRED_UDID}\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "ideviceinfo" in cmd_str and "-k" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="iPhone15,2\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
            patch("shutil.which", return_value="C:\\tools\\tool.exe"),
        ):
            _trigger_discovery()

        sessions = device_session_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].platform == Platform.IOS

    def test_ios_failure_android_success(self) -> None:
        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            cmd_str = " ".join(cmd)
            if "idevice_id" in cmd_str:
                raise ADBCommandTimeoutError("idevice_id -l", 5.0)
            if "devices" in cmd and "-l" in cmd:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="List of devices attached\n12345678\tdevice model:Pixel_8\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "getprop" in cmd:
                return CommandResult(
                    command=cmd, return_code=0, stdout="Pixel 8\n", stderr="", duration_seconds=0.01
                )
            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
            patch("shutil.which", return_value="C:\\tools\\tool.exe"),
        ):
            _trigger_discovery()

        sessions = device_session_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].platform == Platform.ANDROID

    def test_both_success(self) -> None:
        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            cmd_str = " ".join(cmd)
            if "devices" in cmd and "-l" in cmd:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="List of devices attached\n12345678\tdevice model:Pixel_8\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "getprop" in cmd:
                return CommandResult(
                    command=cmd, return_code=0, stdout="Pixel 8\n", stderr="", duration_seconds=0.01
                )
            if "idevice_id" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=f"{_PAIRED_UDID}\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "validate" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout=f"SUCCESS: Validated pairing with device {_PAIRED_UDID}\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "ideviceinfo" in cmd_str and "-k" in cmd_str:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="iPhone15,2\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
            patch("shutil.which", return_value="C:\\tools\\tool.exe"),
        ):
            _trigger_discovery()

        sessions = device_session_manager.list_sessions()
        assert len(sessions) == 2
        platforms = {s.platform for s in sessions}
        assert platforms == {Platform.ANDROID, Platform.IOS}

    def test_ios_zero_devices(self) -> None:
        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            cmd_str = " ".join(cmd)
            if "idevice_id" in cmd_str:
                return CommandResult(
                    command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
                )
            if "devices" in cmd and "-l" in cmd:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="List of devices attached\n\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("vector_agent.devices.ios.bridge.run_command", side_effect=mock_subprocess),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
            patch("shutil.which", return_value="C:\\tools\\tool.exe"),
        ):
            _trigger_discovery()

        assert len(device_session_manager.list_sessions()) == 0

    def test_ios_toolchain_unavailable_android_still_works(self) -> None:
        def mock_which(cmd: str) -> str | None:
            if "adb" in cmd:
                return "C:\\tools\\adb.exe"
            return None

        def mock_subprocess(cmd: list[str], timeout: float = 5.0) -> CommandResult:
            if "devices" in cmd and "-l" in cmd:
                return CommandResult(
                    command=cmd,
                    return_code=0,
                    stdout="List of devices attached\n12345678\tdevice model:Pixel_8\n",
                    stderr="",
                    duration_seconds=0.01,
                )
            if "getprop" in cmd:
                return CommandResult(
                    command=cmd, return_code=0, stdout="Pixel 8\n", stderr="", duration_seconds=0.01
                )
            return CommandResult(
                command=cmd, return_code=0, stdout="", stderr="", duration_seconds=0.01
            )

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("vector_agent.devices.android.bridge.run_command", side_effect=mock_subprocess),
        ):
            _trigger_discovery()

        sessions = device_session_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].platform == Platform.ANDROID
