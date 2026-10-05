"""Structured error model for the VECTOR agent.

Each error class maps to a specific failure scenario.
Errors are caught by API middleware and returned as structured JSON.
Stack traces are never exposed to the user.
"""

from __future__ import annotations

import re
from enum import StrEnum


class VectorErrorCode(StrEnum):
    # ---- Device connection ----
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    MULTIPLE_DEVICES_FOUND = "MULTIPLE_DEVICES_FOUND"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"

    # ---- ADB ----
    ADB_NOT_INSTALLED = "ADB_NOT_INSTALLED"
    ADB_UNAUTHORIZED = "ADB_UNAUTHORIZED"
    ADB_OFFLINE = "ADB_OFFLINE"
    ADB_COMMAND_TIMEOUT = "ADB_COMMAND_TIMEOUT"
    ADB_COMMAND_FAILED = "ADB_COMMAND_FAILED"
    ADB_PARSE_ERROR = "ADB_PARSE_ERROR"

    # ---- iOS ----
    IOS_PAIRING_REQUIRED = "IOS_PAIRING_REQUIRED"
    IOS_NOT_TRUSTED = "IOS_NOT_TRUSTED"
    IOS_DEPENDENCY_MISSING = "IOS_DEPENDENCY_MISSING"
    IOS_RESTRICTED = "IOS_RESTRICTED"

    # ---- Diagnostic ----
    UNSUPPORTED_DIAGNOSTIC = "UNSUPPORTED_DIAGNOSTIC"
    RESTRICTED_DIAGNOSTIC = "RESTRICTED_DIAGNOSTIC"
    DIAGNOSTIC_TIMEOUT = "DIAGNOSTIC_TIMEOUT"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"

    # ---- Scan ----
    SCAN_NOT_FOUND = "SCAN_NOT_FOUND"
    SCAN_ALREADY_RUNNING = "SCAN_ALREADY_RUNNING"
    SCAN_CANCELLED = "SCAN_CANCELLED"

    # ---- Internal ----
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SUBPROCESS_POLICY_VIOLATION = "SUBPROCESS_POLICY_VIOLATION"
    COMMAND_OUTPUT_TOO_LARGE = "COMMAND_OUTPUT_TOO_LARGE"


class VectorError(Exception):
    """Base class for all VECTOR errors."""

    def __init__(
        self,
        code: VectorErrorCode,
        message: str,
        detail: str | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, object]:
        return {
            "error": self.code.value,
            "message": self.message,
            "detail": self.detail,
            "recoverable": self.recoverable,
        }


# ---- Device errors ----


class DeviceNotFoundError(VectorError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(VectorErrorCode.DEVICE_NOT_FOUND, "No device found.", detail=detail)


class MultipleDevicesFoundError(VectorError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            VectorErrorCode.MULTIPLE_DEVICES_FOUND,
            "Multiple devices detected. Connect only one device.",
            detail=detail,
        )


class DeviceDisconnectedError(VectorError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            VectorErrorCode.DEVICE_DISCONNECTED,
            "Device disconnected during operation.",
            detail=detail,
            recoverable=True,
        )


# ---- ADB errors ----


class ADBNotInstalledError(VectorError):
    def __init__(self) -> None:
        super().__init__(
            VectorErrorCode.ADB_NOT_INSTALLED,
            "ADB (Android Debug Bridge) is not installed or not on PATH.",
            detail=(
                "Install Android Platform Tools and ensure 'adb' is available on PATH. "
                "See: https://developer.android.com/studio/releases/platform-tools"
            ),
        )


class ADBUnauthorizedError(VectorError):
    def __init__(self, serial: str | None = None) -> None:
        device_hint = f" (device: {serial})" if serial else ""
        super().__init__(
            VectorErrorCode.ADB_UNAUTHORIZED,
            f"Android device{device_hint} has not authorized USB debugging.",
            detail=(
                "Unlock the device and accept the 'Allow USB Debugging' prompt. "
                "If no prompt appears, revoke USB debugging authorizations in Developer Options and reconnect."
            ),
            recoverable=True,
        )


class ADBOfflineError(VectorError):
    def __init__(self, serial: str | None = None) -> None:
        device_hint = f" (device: {serial})" if serial else ""
        super().__init__(
            VectorErrorCode.ADB_OFFLINE,
            f"Android device{device_hint} is listed as offline by ADB.",
            detail="Disconnect and reconnect the USB cable. Ensure the cable supports data transfer.",
            recoverable=True,
        )


class ADBCommandTimeoutError(VectorError):
    def __init__(self, command: str, timeout: float) -> None:
        safe_cmd = re.sub(r"(-s\s+)[^\s]+", r"\1<SERIAL_REDACTED>", command)
        super().__init__(
            VectorErrorCode.ADB_COMMAND_TIMEOUT,
            f"ADB command timed out after {timeout}s.",
            detail=f"Command: {safe_cmd}",
        )


class ADBCommandFailedError(VectorError):
    def __init__(self, command: str, return_code: int, stderr: str) -> None:
        safe_cmd = re.sub(r"(-s\s+)[^\s]+", r"\1<SERIAL_REDACTED>", command)
        super().__init__(
            VectorErrorCode.ADB_COMMAND_FAILED,
            f"ADB command failed with exit code {return_code}.",
            detail=f"Command: {safe_cmd} | stderr: {stderr[:200]}",
        )


class ADBParseError(VectorError):
    def __init__(self, source: str, detail: str | None = None) -> None:
        super().__init__(
            VectorErrorCode.ADB_PARSE_ERROR,
            f"Failed to parse ADB output from '{source}'.",
            detail=detail,
        )


# ---- iOS errors ----


class IOSPairingRequiredError(VectorError):
    def __init__(self) -> None:
        super().__init__(
            VectorErrorCode.IOS_PAIRING_REQUIRED,
            "iPhone pairing is required.",
            detail="Connect the iPhone and unlock it, then trust this computer when prompted.",
            recoverable=True,
        )


class IOSNotTrustedError(VectorError):
    def __init__(self) -> None:
        super().__init__(
            VectorErrorCode.IOS_NOT_TRUSTED,
            "iPhone has not trusted this computer.",
            detail="Unlock the iPhone and select 'Trust This Computer' when prompted.",
            recoverable=True,
        )


class IOSDependencyMissingError(VectorError):
    def __init__(self, tool: str) -> None:
        super().__init__(
            VectorErrorCode.IOS_DEPENDENCY_MISSING,
            f"iOS diagnostic tool '{tool}' is not installed or not on PATH.",
            detail=(
                "Install libimobiledevice. See: https://libimobiledevice.org/ "
                "On Windows, binaries may be available via the libimobiledevice-win32 project."
            ),
        )


# ---- Diagnostic errors ----


class UnsupportedDiagnosticError(VectorError):
    def __init__(self, diagnostic_id: str, reason: str) -> None:
        super().__init__(
            VectorErrorCode.UNSUPPORTED_DIAGNOSTIC,
            f"Diagnostic '{diagnostic_id}' is not supported on this device.",
            detail=reason,
        )


class RestrictedDiagnosticError(VectorError):
    def __init__(self, diagnostic_id: str, reason: str) -> None:
        super().__init__(
            VectorErrorCode.RESTRICTED_DIAGNOSTIC,
            f"Diagnostic '{diagnostic_id}' is restricted by the OS.",
            detail=reason,
        )


# ---- Scan errors ----


class ScanNotFoundError(VectorError):
    def __init__(self, scan_id: str) -> None:
        super().__init__(
            VectorErrorCode.SCAN_NOT_FOUND,
            f"Scan '{scan_id}' not found.",
        )


class ScanCancelledError(VectorError):
    def __init__(self, scan_id: str) -> None:
        super().__init__(
            VectorErrorCode.SCAN_CANCELLED,
            f"Scan '{scan_id}' was cancelled.",
            recoverable=True,
        )
