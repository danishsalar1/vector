"""Tests for security utilities (redaction, validation)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from vector_agent.core.errors import ADBCommandTimeoutError
from vector_agent.security.redaction import hash_identifier, mask_identifier, redact_imei
from vector_agent.security.subprocess_policy import format_command_for_display, run_command
from vector_agent.security.validation import (
    ValidationError,
    validate_device_serial,
    validate_ios_udid,
    validate_scan_id,
)


class TestRedaction:
    def test_mask_identifier_standard(self) -> None:
        masked = mask_identifier("866123456789012")
        assert masked.endswith("9012")
        assert "*" in masked
        assert "866123456789" not in masked

    def test_mask_identifier_short(self) -> None:
        masked = mask_identifier("ABC")
        assert masked == "***"

    def test_mask_identifier_empty(self) -> None:
        assert mask_identifier("") == ""

    def test_hash_identifier_stable(self) -> None:
        h1 = hash_identifier("866123456789012")
        h2 = hash_identifier("866123456789012")
        assert h1 == h2
        assert len(h1) == 16

    def test_hash_identifier_different(self) -> None:
        assert hash_identifier("AAAA") != hash_identifier("BBBB")

    def test_redact_imei_in_text(self) -> None:
        text = "IMEI: 866123456789012 is the device"
        redacted = redact_imei(text)
        assert "866123456789012" not in redacted
        assert "REDACTED" in redacted

    def test_redact_imei_leaves_short_numbers(self) -> None:
        text = "Battery: 83%"
        assert redact_imei(text) == text


class TestValidation:
    def test_valid_serial(self) -> None:
        assert validate_device_serial("ABC123XYZ") == "ABC123XYZ"

    def test_valid_serial_ip_port(self) -> None:
        assert validate_device_serial("192.168.1.100:5555") == "192.168.1.100:5555"

    def test_empty_serial_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_device_serial("")

    def test_serial_with_injection_chars_raises(self) -> None:
        raw_bad_serial = "abc; rm -rf /"
        with pytest.raises(ValidationError) as exc_info:
            validate_device_serial(raw_bad_serial)
        assert raw_bad_serial not in str(exc_info.value)

    def test_valid_udid(self) -> None:
        udid = "00008120-001E4C123456802E"
        assert validate_ios_udid(udid) == udid

    def test_valid_scan_id(self) -> None:
        scan_id = "550e8400-e29b-41d4-a716-446655440000"
        assert validate_scan_id(scan_id) == scan_id

    def test_invalid_scan_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_scan_id("not-a-uuid")


class TestSubprocessPolicyPrivacy:
    def test_format_command_for_display_redacts_adb_serial(self) -> None:
        raw_cmd = ["adb", "-s", "RAW_SECRET_SERIAL_999", "shell", "pm", "list", "features"]
        display = format_command_for_display(raw_cmd)
        assert "RAW_SECRET_SERIAL_999" not in display
        assert display == "adb -s <SERIAL_REDACTED> shell pm list features"

    def test_format_command_for_display_redacts_adb_exe_path(self) -> None:
        raw_cmd = ["C:\\platform-tools\\adb.exe", "-s", "RAW_SECRET_SERIAL_999", "getprop"]
        display = format_command_for_display(raw_cmd)
        assert "RAW_SECRET_SERIAL_999" not in display
        assert display == "C:\\platform-tools\\adb.exe -s <SERIAL_REDACTED> getprop"

    def test_format_command_does_not_redact_unrelated_commands(self) -> None:
        raw_cmd = ["git", "status", "-s"]
        display = format_command_for_display(raw_cmd)
        assert display == "git status -s"

    def test_subprocess_timeout_redacts_serial_in_error_and_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret_serial = "CONFIDENTIAL_SERIAL_456"
        cmd = ["adb", "-s", secret_serial, "shell", "pm", "list", "features"]

        with (
            patch(
                "vector_agent.security.subprocess_policy.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=cmd, timeout=5.0),
            ),
            pytest.raises(ADBCommandTimeoutError) as exc_info,
        ):
            run_command(cmd, timeout=5.0)

        err_detail = exc_info.value.detail or ""
        assert secret_serial not in err_detail
        assert "<SERIAL_REDACTED>" in err_detail
        assert secret_serial not in caplog.text

    def test_subprocess_truncation_redacts_serial_in_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret_serial = "CONFIDENTIAL_SERIAL_789"
        cmd = ["adb", "-s", secret_serial, "shell", "pm", "list", "features"]

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"A" * 100
        mock_proc.stderr = b""

        with patch(
            "vector_agent.security.subprocess_policy.subprocess.run", return_value=mock_proc
        ):
            res = run_command(cmd, max_output_bytes=50)

        assert res.truncated is True
        assert secret_serial not in caplog.text
        assert "<SERIAL_REDACTED>" in caplog.text

    def test_subprocess_args_preserve_real_serial(self) -> None:
        secret_serial = "CONFIDENTIAL_SERIAL_123"
        cmd = ["adb", "-s", secret_serial, "shell", "pm", "list", "features"]

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok"
        mock_proc.stderr = b""

        with patch(
            "vector_agent.security.subprocess_policy.subprocess.run", return_value=mock_proc
        ) as mock_run:
            run_command(cmd)

        mock_run.assert_called_once()
        invoked_args = mock_run.call_args[0][0]
        # Actual subprocess arguments must preserve real internal serial
        assert invoked_args == cmd
        assert secret_serial in invoked_args
