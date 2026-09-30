"""Tests for core error model."""

from __future__ import annotations

from vector_agent.core.errors import (
    ADBCommandTimeoutError,
    ADBNotInstalledError,
    ADBUnauthorizedError,
    DeviceNotFoundError,
    IOSNotTrustedError,
    MultipleDevicesFoundError,
    ScanNotFoundError,
    UnsupportedDiagnosticError,
    VectorErrorCode,
)


class TestVectorErrors:
    def test_device_not_found_code(self) -> None:
        err = DeviceNotFoundError()
        assert err.code == VectorErrorCode.DEVICE_NOT_FOUND
        assert not err.recoverable

    def test_adb_unauthorized_recoverable(self) -> None:
        err = ADBUnauthorizedError(serial="ABC123")
        assert err.code == VectorErrorCode.ADB_UNAUTHORIZED
        assert err.recoverable

    def test_adb_timeout_code(self) -> None:
        err = ADBCommandTimeoutError(command="adb shell getprop", timeout=10.0)
        assert err.code == VectorErrorCode.ADB_COMMAND_TIMEOUT

    def test_multiple_devices_found(self) -> None:
        err = MultipleDevicesFoundError(detail="serial1, serial2")
        assert err.code == VectorErrorCode.MULTIPLE_DEVICES_FOUND
        assert "serial1" in (err.detail or "")

    def test_scan_not_found(self) -> None:
        err = ScanNotFoundError("00000000-0000-0000-0000-000000000001")
        assert err.code == VectorErrorCode.SCAN_NOT_FOUND

    def test_ios_not_trusted_recoverable(self) -> None:
        err = IOSNotTrustedError()
        assert err.recoverable

    def test_error_to_dict_fields(self) -> None:
        err = DeviceNotFoundError(detail="No USB device")
        d = err.to_dict()
        assert d["error"] == "DEVICE_NOT_FOUND"
        assert d["detail"] == "No USB device"
        assert d["recoverable"] is False

    def test_adb_not_installed_has_detail(self) -> None:
        err = ADBNotInstalledError()
        assert err.detail is not None
        assert len(err.detail) > 20

    def test_unsupported_diagnostic(self) -> None:
        err = UnsupportedDiagnosticError("barometer", "Device has no barometer sensor.")
        assert err.code == VectorErrorCode.UNSUPPORTED_DIAGNOSTIC
        assert "barometer" in err.message
