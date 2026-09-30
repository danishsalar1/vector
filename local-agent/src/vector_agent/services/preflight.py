"""System preflight environment verification service."""

from __future__ import annotations

import platform
import shutil
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from vector_agent import __version__
from vector_agent.core.config import AgentSettings, get_settings
from vector_agent.core.logging import get_logger
from vector_agent.models.preflight import (
    PreflightCheck,
    PreflightOverall,
    PreflightResponse,
    PreflightStatus,
)
from vector_agent.security.subprocess_policy import run_command

logger = get_logger(__name__)


class SystemPreflightService:
    """Evaluates local host operating system, runtime, and external tooling readiness.

    CRITICAL INVARIANT:
    This service verifies host-side tool availability only. It MUST NEVER
    execute device enumeration commands (e.g. 'adb devices', 'idevice_id -l')
    or attempt phone communication. Device discovery is strictly deferred to Phase 2.
    """

    def __init__(self, settings: AgentSettings | None = None) -> None:
        self._settings = settings or get_settings()

    def run_preflight(self) -> PreflightResponse:
        """Runs all local host checks and compiles an aggregate readiness report."""
        checks: list[PreflightCheck] = []

        check_registry: list[tuple[str, str, str, bool, Callable[[], PreflightCheck]]] = [
            ("platform_os", "Operating System", "platform", False, self._check_platform),
            ("python_runtime", "Python Runtime", "runtime", True, self._check_python_runtime),
            ("vector_agent", "VECTOR Local Agent", "agent", True, self._check_agent_readiness),
            ("android_adb", "Android Tooling (ADB)", "android", False, self._check_android_tooling),
            (
                "ios_libimobiledevice",
                "iOS Tooling (libimobiledevice)",
                "ios",
                False,
                self._check_ios_tooling,
            ),
        ]

        for check_id, check_name, check_cat, check_req, check_fn in check_registry:
            try:
                checks.append(check_fn())
            except Exception as exc:
                logger.exception(
                    "Unexpected error executing preflight check '%s': %s", check_id, exc
                )
                checks.append(
                    PreflightCheck(
                        id=check_id,
                        name=check_name,
                        category=check_cat,
                        status=PreflightStatus.FAIL,
                        message=f"An unexpected error occurred while executing {check_name}.",
                        required=check_req,
                        details="Error suppressed for privacy. Check local agent logs for details.",
                        detail="Check error occurred.",
                    )
                )

        # Derive overall readiness
        overall = self._compute_overall(checks)

        return PreflightResponse(
            overall=overall,
            overall_status=overall,
            checks=checks,
            items=checks,
            timestamp=datetime.now(UTC),
        )

    def _check_platform(self) -> PreflightCheck:
        """Verifies host operating system against supported hardware bridge targets."""
        os_name = platform.system()
        is_windows = os_name == "Windows"

        if is_windows:
            return PreflightCheck(
                id="platform_os",
                name="Operating System",
                category="platform",
                status=PreflightStatus.PASS,
                message="Windows operating system verified for hardware bridge operations.",
                required=True,
                details=f"{platform.system()} {platform.release()} ({platform.version()})",
                detail=f"{platform.system()} {platform.release()}",
            )

        return PreflightCheck(
            id="platform_os",
            name="Operating System",
            category="platform",
            status=PreflightStatus.WARN,
            message=f"{os_name} detected. Primary hardware bridge operations target Windows.",
            required=False,
            details=f"{os_name} {platform.release()}",
            detail=f"{os_name} {platform.release()}",
        )

    def _check_python_runtime(self) -> PreflightCheck:
        """Verifies Python runtime environment meets project version requirements."""
        py_version_str = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
        meets_requirement = sys.version_info[:2] >= (3, 11)

        if meets_requirement:
            return PreflightCheck(
                id="python_runtime",
                name="Python Runtime",
                category="runtime",
                status=PreflightStatus.PASS,
                message=f"Python {py_version_str} operational (>=3.11 supported).",
                required=True,
                details=sys.version,
                detail=py_version_str,
            )

        return PreflightCheck(
            id="python_runtime",
            name="Python Runtime",
            category="runtime",
            status=PreflightStatus.FAIL,
            message=f"Python {py_version_str} detected. Python 3.11 or newer is required.",
            required=True,
            details=sys.version,
            detail=py_version_str,
        )

    def _check_agent_readiness(self) -> PreflightCheck:
        """Verifies local FastAPI agent internal state."""
        return PreflightCheck(
            id="vector_agent",
            name="VECTOR Local Agent",
            category="agent",
            status=PreflightStatus.PASS,
            message="VECTOR local hardware agent service is running.",
            required=True,
            details=f"Agent version: {__version__} | Mode: {'DEMO' if self._settings.demo_mode else 'LIVE'}",
            detail=f"Version {__version__}",
        )

    def _check_android_tooling(self) -> PreflightCheck:
        """Checks for ADB executable availability.

        DOES NOT execute 'adb devices' or query connected USB hardware.
        """
        executable_target = self._settings.adb_path
        resolved_path = shutil.which(executable_target)

        if not resolved_path:
            return PreflightCheck(
                id="android_adb",
                name="Android Tooling (ADB)",
                category="android",
                status=PreflightStatus.NOT_INSTALLED,
                message=(
                    "Android Platform Tools are not installed or are not available on PATH. "
                    "They will be required before Android device discovery."
                ),
                required=False,
                details=f"Executable '{executable_target}' not found.",
                detail=f"'{executable_target}' not found on PATH.",
            )

        # Run a safe, harmless version query using the subprocess policy
        try:
            result = run_command([resolved_path, "version"], timeout=2.0)
            if result.return_code == 0:
                first_line = (
                    result.stdout.strip().splitlines()[0]
                    if result.stdout
                    else "ADB executable available"
                )
                return PreflightCheck(
                    id="android_adb",
                    name="Android Tooling (ADB)",
                    category="android",
                    status=PreflightStatus.PASS,
                    message="Android Platform Tools available.",
                    required=False,
                    details=first_line,
                    detail=str(resolved_path),
                )
            return PreflightCheck(
                id="android_adb",
                name="Android Tooling (ADB)",
                category="android",
                status=PreflightStatus.WARN,
                message="ADB executable found on PATH but returned a non-zero exit code on version check.",
                required=False,
                details=result.stderr.strip() or f"Exit code: {result.return_code}",
                detail=str(resolved_path),
            )
        except Exception as exc:
            logger.warning("Error inspecting ADB version: %s", exc)
            return PreflightCheck(
                id="android_adb",
                name="Android Tooling (ADB)",
                category="android",
                status=PreflightStatus.WARN,
                message="ADB executable located but encountered an error during version query.",
                required=False,
                details=str(exc),
                detail=str(resolved_path),
            )

    def _check_ios_tooling(self) -> PreflightCheck:
        """Checks for libimobiledevice executables.

        DOES NOT execute 'idevice_id -l' or query connected iPhones.
        """
        ideviceinfo_target = self._settings.ideviceinfo_path
        idevice_id_target = self._settings.idevice_id_path

        resolved_info = shutil.which(ideviceinfo_target)
        resolved_id = shutil.which(idevice_id_target)

        if resolved_info and resolved_id:
            try:
                result = run_command([resolved_info, "--version"], timeout=2.0)
                details = (
                    result.stdout.strip().splitlines()[0]
                    if (result.return_code == 0 and result.stdout)
                    else str(resolved_info)
                )
                return PreflightCheck(
                    id="ios_libimobiledevice",
                    name="iOS Tooling (libimobiledevice)",
                    category="ios",
                    status=PreflightStatus.PASS,
                    message="iOS device communication tooling available.",
                    required=False,
                    details=details,
                    detail=str(resolved_info),
                )
            except Exception as exc:
                logger.warning("Error inspecting iOS tooling: %s", exc)
                return PreflightCheck(
                    id="ios_libimobiledevice",
                    name="iOS Tooling (libimobiledevice)",
                    category="ios",
                    status=PreflightStatus.PASS,
                    message="iOS device communication tooling executables located.",
                    required=False,
                    details=f"ideviceinfo: {resolved_info}, idevice_id: {resolved_id}",
                    detail=str(resolved_info),
                )

        missing: list[str] = []
        if not resolved_id:
            missing.append(idevice_id_target)
        if not resolved_info:
            missing.append(ideviceinfo_target)

        return PreflightCheck(
            id="ios_libimobiledevice",
            name="iOS Tooling (libimobiledevice)",
            category="ios",
            status=PreflightStatus.NOT_INSTALLED,
            message="iOS device tooling is not available on PATH. It will be required before iPhone discovery.",
            required=False,
            details=f"Missing executables: {', '.join(missing)}",
            detail=f"'{', '.join(missing)}' not found on PATH.",
        )

    @staticmethod
    def _compute_overall(checks: list[PreflightCheck]) -> PreflightOverall:
        """Computes aggregate environment readiness: READY | PARTIAL | BLOCKED."""
        for c in checks:
            if c.required and c.status in (PreflightStatus.FAIL, PreflightStatus.NOT_INSTALLED):
                return PreflightOverall.BLOCKED

        all_pass = all(c.status == PreflightStatus.PASS for c in checks)
        if all_pass:
            return PreflightOverall.READY

        return PreflightOverall.PARTIAL
