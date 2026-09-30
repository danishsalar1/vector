"""Tests for security utilities (redaction, validation)."""

from __future__ import annotations

import pytest

from vector_agent.security.redaction import hash_identifier, mask_identifier, redact_imei
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
        with pytest.raises(ValidationError):
            validate_device_serial("abc; rm -rf /")

    def test_valid_udid(self) -> None:
        udid = "00008120-001E4C123456802E"
        assert validate_ios_udid(udid) == udid

    def test_valid_scan_id(self) -> None:
        scan_id = "550e8400-e29b-41d4-a716-446655440000"
        assert validate_scan_id(scan_id) == scan_id

    def test_invalid_scan_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_scan_id("not-a-uuid")
