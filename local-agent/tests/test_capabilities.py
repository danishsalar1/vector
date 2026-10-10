"""Focused tests for Canonical Phase 4: Capability Foundation + Runtime Discovery.

Covers:
1. Generic Android capability discovery from fabricated fixture output (flagship & budget).
2. Unknown Android model works without catalog/reference data.
3. Capability output maps into platform-neutral domain contract.
4. Raw serial never appears in capability API output, models, or evidence records.
5. Stale/unknown device ID fails safely (404).
6. Offline device does not masquerade as connected capability knowledge (ConnectedDevice is None, API is 400).
7. Unauthorized/restricted state is handled truthfully (403).
8. Reconnect/rediscovery can refresh capability snapshot.
9. Missing/ambiguous runtime information stays unknown/not reported rather than fake PASS/FAIL.
10. No factory/reference claims are made without a reference profile.
11. Current Phase 2/3 behavior remains intact.
12. Existing battery diagnostic semantics remain intact.
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from vector_agent.devices.android.bridge import (
    AdbDeviceEntry,
    AdbDeviceState,
    AndroidDeviceBridge,
    AndroidDiscoveryResult,
)
from vector_agent.devices.android.capabilities import parse_pm_features
from vector_agent.devices.session import (
    DeviceNotConnectedError,
    DeviceSession,
    DeviceSessionManager,
    device_session_manager,
)
from vector_agent.main import create_app
from vector_agent.models.device import (
    CapabilityStatus,
    ConnectionState,
    DeviceCapabilityProfile,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)
from vector_agent.security.subprocess_policy import CommandResult

# ============================================================
# Fabricated Fixtures
# ============================================================

_NOW = datetime.now(UTC)
_FAKE_DEVICE_ID = "android-testcaps01"
_FAKE_SERIAL = "FABRICATED_SERIAL_CAPS_123"

_FLAGSHIP_FEATURES_OUTPUT = """\
feature:reqGlEsVersion=0x30002
feature:android.hardware.audio.output
feature:android.hardware.audio.pro
feature:android.hardware.bluetooth
feature:android.hardware.bluetooth_le
feature:android.hardware.camera
feature:android.hardware.camera.any
feature:android.hardware.camera.autofocus
feature:android.hardware.camera.flash
feature:android.hardware.camera.front
feature:android.hardware.camera.level.full
feature:android.hardware.fingerprint
feature:android.hardware.biometrics.face
feature:android.hardware.location
feature:android.hardware.location.gps
feature:android.hardware.microphone
feature:android.hardware.nfc
feature:android.hardware.nfc.hce
feature:android.hardware.sensor.accelerometer
feature:android.hardware.sensor.barometer
feature:android.hardware.sensor.compass
feature:android.hardware.sensor.gyroscope
feature:android.hardware.sensor.light
feature:android.hardware.sensor.proximity
feature:android.hardware.sensor.stepcounter
feature:android.hardware.sensor.stepdetector
feature:android.hardware.sensor.hinge_angle
feature:android.hardware.telephony
feature:android.hardware.telephony.gsm
feature:android.hardware.touchscreen
feature:android.hardware.touchscreen.multitouch
feature:android.hardware.usb.accessory
feature:android.hardware.usb.host
feature:android.hardware.uwb
feature:android.hardware.vulkan.version=4198400
feature:android.hardware.vulkan.level=1
feature:android.hardware.wifi
feature:android.hardware.wifi.direct
feature:android.hardware.wifi.aware
"""

_BUDGET_FEATURES_OUTPUT = """\
feature:reqGlEsVersion=0x20000
feature:android.hardware.audio.output
feature:android.hardware.bluetooth
feature:android.hardware.camera
feature:android.hardware.camera.any
feature:android.hardware.camera.front
feature:android.hardware.location
feature:android.hardware.location.network
feature:android.hardware.microphone
feature:android.hardware.sensor.accelerometer
feature:android.hardware.sensor.light
feature:android.hardware.sensor.proximity
feature:android.hardware.telephony
feature:android.hardware.telephony.gsm
feature:android.hardware.touchscreen
feature:android.hardware.wifi
"""

_EMPTY_FEATURES_OUTPUT = """\
List of features:
"""


# ============================================================
# Test Cases: Runtime Feature Parsing & Domain Mapping
# ============================================================


class TestRuntimeCapabilityParsing:
    def test_flagship_features_parsing(self) -> None:
        """Parse flagship phone features into platform-neutral profile."""
        profile = parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=_FAKE_DEVICE_ID)

        assert profile.device_id == _FAKE_DEVICE_ID
        assert profile.platform == Platform.ANDROID
        assert profile.profile_complete is True

        # Sensors
        assert profile.get("accelerometer") == CapabilityStatus.PRESENT
        assert profile.get("gyroscope") == CapabilityStatus.PRESENT
        assert profile.get("barometer") == CapabilityStatus.PRESENT
        assert profile.get("magnetometer") == CapabilityStatus.PRESENT
        assert profile.get("ambient_light") == CapabilityStatus.PRESENT
        assert profile.get("proximity") == CapabilityStatus.PRESENT
        assert profile.get("step_counter") == CapabilityStatus.PRESENT
        assert profile.get("hinge_angle") == CapabilityStatus.PRESENT

        # Camera
        assert profile.get("camera") == CapabilityStatus.PRESENT
        assert profile.get("camera.front") == CapabilityStatus.PRESENT
        assert profile.get("camera.flash") == CapabilityStatus.PRESENT
        assert profile.get("camera.autofocus") == CapabilityStatus.PRESENT

        # Biometrics
        assert profile.get("biometrics.fingerprint") == CapabilityStatus.PRESENT
        assert profile.get("biometrics.face") == CapabilityStatus.PRESENT

        # Connectivity
        assert profile.get("nfc") == CapabilityStatus.PRESENT
        assert profile.get("uwb") == CapabilityStatus.PRESENT
        assert profile.get("wifi") == CapabilityStatus.PRESENT
        assert profile.get("bluetooth") == CapabilityStatus.PRESENT
        assert profile.get("bluetooth_le") == CapabilityStatus.PRESENT

        # Battery subsystem remains UNKNOWN in pm list features (tested via dumpsys battery)
        assert profile.get("battery") == CapabilityStatus.UNKNOWN

        # Level 1 verification check
        gyro_entry = profile.get_entry("gyroscope")
        assert gyro_entry is not None
        assert gyro_entry.verification_level == VerificationLevel.RUNTIME_DETECTION
        assert len(gyro_entry.evidence) > 0
        ev = gyro_entry.evidence[0]
        assert ev.source_type == EvidenceSourceType.ADB_SHELL
        assert ev.device_id == _FAKE_DEVICE_ID
        assert ev.confidence == 1.0

    def test_budget_features_distinguishes_not_reported_from_absent_or_fail(self) -> None:
        """Omitted capabilities must be NOT_REPORTED, never assumed absent or failed."""
        profile = parse_pm_features(_BUDGET_FEATURES_OUTPUT, device_id=_FAKE_DEVICE_ID)

        assert profile.device_id == _FAKE_DEVICE_ID
        assert profile.profile_complete is True

        # Present
        assert profile.get("accelerometer") == CapabilityStatus.PRESENT
        assert profile.get("wifi") == CapabilityStatus.PRESENT
        assert profile.get("camera") == CapabilityStatus.PRESENT

        # Tracked but not declared by device -> NOT_REPORTED
        assert profile.get("gyroscope") == CapabilityStatus.NOT_REPORTED
        assert profile.get("barometer") == CapabilityStatus.NOT_REPORTED
        assert profile.get("nfc") == CapabilityStatus.NOT_REPORTED
        assert profile.get("uwb") == CapabilityStatus.NOT_REPORTED
        assert profile.get("biometrics.face") == CapabilityStatus.NOT_REPORTED

        # Semantics: NOT_REPORTED does not claim Runtime Detection or fabricate evidence
        baro_entry = profile.get_entry("barometer")
        assert baro_entry is not None
        assert baro_entry.verification_level is None
        assert baro_entry.status == CapabilityStatus.NOT_REPORTED
        assert baro_entry.evidence == []
        assert "Not reported in runtime system features" in (baro_entry.note or "")

        # Unprobed capability is UNKNOWN
        assert profile.get("untracked_alien_sensor") == CapabilityStatus.UNKNOWN

    def test_empty_output_handled_safely_as_unknown(self) -> None:
        """Empty or unparseable output produces incomplete profile with UNKNOWN status."""
        profile = parse_pm_features(_EMPTY_FEATURES_OUTPUT, device_id=_FAKE_DEVICE_ID)

        assert profile.profile_complete is False
        assert profile.get("accelerometer") == CapabilityStatus.UNKNOWN
        assert profile.get("camera") == CapabilityStatus.UNKNOWN
        entry = profile.get_entry("accelerometer")
        assert entry is not None
        assert entry.status == CapabilityStatus.UNKNOWN
        assert entry.verification_level is None
        assert "empty or unparseable" in (entry.note or "").lower()

    def test_unknown_phone_model_works_without_catalog(self) -> None:
        """Capability discovery works purely from runtime output, no catalog required."""
        profile = parse_pm_features(
            _FLAGSHIP_FEATURES_OUTPUT,
            device_id="android-unknown-brand-999",
        )
        assert profile.is_present("accelerometer")
        assert profile.is_present("gyroscope")
        assert profile.get("barometer") == CapabilityStatus.PRESENT

    def test_platform_features_metadata_and_namespace(self) -> None:
        """Raw Android features are preserved in metadata without polluting canonical lookup."""
        profile = parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=_FAKE_DEVICE_ID)
        # Platform-neutral lookup does not resolve raw unmapped android strings directly
        assert profile.get("android.hardware.sensor.gyroscope") == CapabilityStatus.UNKNOWN
        # But canonical platform-neutral name resolves
        assert profile.get("gyroscope") == CapabilityStatus.PRESENT
        # And raw features are preserved in metadata
        assert "android.hardware.sensor.gyroscope" in profile.metadata["raw_platform_features"]

    def test_malformed_output_mixed_with_valid_lines(self) -> None:
        """Malformed lines are skipped gracefully while valid lines are extracted."""
        raw = """
        garbage header line
        feature:android.hardware.wifi
        another malformed line without prefix
        feature:android.hardware.camera
        corrupted:::line
        """
        profile = parse_pm_features(raw, device_id=_FAKE_DEVICE_ID)
        assert profile.get("wifi") == CapabilityStatus.PRESENT
        assert profile.get("camera") == CapabilityStatus.PRESENT
        assert profile.metadata.get("malformed_lines_count", 0) >= 3

    def test_duplicate_feature_lines(self) -> None:
        """Duplicate feature declarations are handled idempotently without error."""
        raw = """
        feature:android.hardware.wifi
        feature:android.hardware.wifi
        feature:android.hardware.wifi
        """
        profile = parse_pm_features(raw, device_id=_FAKE_DEVICE_ID)
        assert profile.get("wifi") == CapabilityStatus.PRESENT
        entry = profile.get_entry("wifi")
        assert entry is not None
        assert len(entry.evidence) == 1

    def test_truncated_command_output(self) -> None:
        """Truncated output marks profile_complete as False and records metadata."""
        profile = parse_pm_features(
            _FLAGSHIP_FEATURES_OUTPUT,
            device_id=_FAKE_DEVICE_ID,
            truncated=True,
        )
        assert profile.profile_complete is False
        assert profile.metadata.get("truncated") is True

    def test_truncated_partial_output_marks_missing_capabilities_unknown(self) -> None:
        """When output is truncated, omitted capabilities must be UNKNOWN, not NOT_REPORTED."""
        partial = """
        feature:android.hardware.wifi
        feature:android.hardware.camera
        feature:android.hardware.bluetooth
        """
        profile = parse_pm_features(partial, device_id=_FAKE_DEVICE_ID, truncated=True)
        assert profile.profile_complete is False
        assert profile.metadata.get("truncated") is True
        assert profile.get("wifi") == CapabilityStatus.PRESENT
        assert profile.get("camera") == CapabilityStatus.PRESENT

        # Crucial check: missing tracked capabilities must be UNKNOWN, NOT NOT_REPORTED
        assert profile.get("accelerometer") == CapabilityStatus.UNKNOWN
        assert profile.get("gyroscope") == CapabilityStatus.UNKNOWN
        assert profile.get("nfc") == CapabilityStatus.UNKNOWN
        entry = profile.get_entry("accelerometer")
        assert entry is not None
        assert entry.status == CapabilityStatus.UNKNOWN
        assert entry.verification_level is None
        assert entry.evidence == []

    def test_truncated_final_line_discarded_cannot_produce_present(self) -> None:
        """When output is truncated mid-line, final partial line is discarded and cannot produce PRESENT."""
        partial_cut = (
            "feature:android.hardware.sensor.accelerometer\nfeature:android.hardware.sensor.gyr"
        )
        profile = parse_pm_features(partial_cut, device_id=_FAKE_DEVICE_ID, truncated=True)
        assert profile.profile_complete is False
        assert profile.get("accelerometer") == CapabilityStatus.PRESENT

        # The cut-off line (gyroscope fragment) must NOT produce PRESENT
        assert profile.get("gyroscope") == CapabilityStatus.UNKNOWN
        # No evidence should exist for the discarded partial fragment
        assert not any("gyr" in str(ev.raw_value) for ev in profile.evidence)


# ============================================================
# Test Cases: Bridge & Security Invariants
# ============================================================


class TestBridgeCapabilityDiscovery:
    def test_bridge_discover_capabilities_success(self) -> None:
        """Bridge invokes 'pm list features' safely and returns profile."""
        bridge = AndroidDeviceBridge(adb_path="adb")
        mock_cmd = MagicMock(
            return_value=CommandResult(
                command=["adb", "shell", "pm", "list", "features"],
                return_code=0,
                stdout=_FLAGSHIP_FEATURES_OUTPUT,
                stderr="",
                duration_seconds=0.1,
            )
        )

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", mock_cmd),
        ):
            profile = bridge.discover_capabilities(_FAKE_SERIAL, device_id=_FAKE_DEVICE_ID)

        assert profile.device_id == _FAKE_DEVICE_ID
        assert profile.get("accelerometer") == CapabilityStatus.PRESENT

        # Verify command policy
        mock_cmd.assert_called_once()
        cmd_args = mock_cmd.call_args[0][0]
        assert cmd_args == [
            "C:\\tools\\adb.exe",
            "-s",
            _FAKE_SERIAL,
            "shell",
            "pm",
            "list",
            "features",
        ]
        assert mock_cmd.call_args[1]["timeout"] == 10.0

    def test_bridge_discover_capabilities_error_exit_code(self) -> None:
        """Bridge raises RuntimeError on non-zero exit code."""
        bridge = AndroidDeviceBridge(adb_path="adb")
        mock_cmd = MagicMock(
            return_value=CommandResult(
                command=["adb", "shell", "pm", "list", "features"],
                return_code=1,
                stdout="",
                stderr="device offline",
                duration_seconds=0.1,
            )
        )

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", mock_cmd),
            pytest.raises(RuntimeError, match="failed with exit code 1"),
        ):
            bridge.discover_capabilities(_FAKE_SERIAL, device_id=_FAKE_DEVICE_ID)

    def test_stderr_containing_raw_serial_does_not_leak(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Raw serial in ADB stderr must not leak to exception message or logs."""
        bridge = AndroidDeviceBridge(adb_path="adb")
        mock_cmd = MagicMock(
            return_value=CommandResult(
                command=["adb", "shell", "pm", "list", "features"],
                return_code=1,
                stdout="",
                stderr=f"adb: device '{_FAKE_SERIAL}' offline",
                duration_seconds=0.1,
            )
        )

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", mock_cmd),
            pytest.raises(RuntimeError) as exc_info,
        ):
            bridge.discover_capabilities(_FAKE_SERIAL, device_id=_FAKE_DEVICE_ID)

        assert _FAKE_SERIAL not in str(exc_info.value)
        assert "failed with exit code 1" in str(exc_info.value)
        assert _FAKE_SERIAL not in caplog.text

    def test_invalid_serial_validation_privacy(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invalid serial validation failure must not leak raw invalid serial in exception or logs."""
        bridge = AndroidDeviceBridge(adb_path="adb")
        invalid_serial = "BAD_SERIAL_$$$###"

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            pytest.raises(ValueError) as exc_info,
        ):
            bridge.discover_capabilities(invalid_serial, device_id=_FAKE_DEVICE_ID)

        err_msg = str(exc_info.value)
        assert invalid_serial not in err_msg
        assert _FAKE_DEVICE_ID in err_msg
        assert invalid_serial not in caplog.text

    def test_discovery_timeout_raises_timeout_error(self) -> None:
        """Subprocess timeout raises TimeoutError without raw serial in error text."""
        bridge = AndroidDeviceBridge(adb_path="adb")

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            patch(
                "vector_agent.devices.android.bridge.run_command",
                side_effect=TimeoutError("Command timed out"),
            ),
            pytest.raises(TimeoutError) as exc_info,
        ):
            bridge.discover_capabilities(_FAKE_SERIAL, device_id=_FAKE_DEVICE_ID)

        assert _FAKE_SERIAL not in str(exc_info.value)
        assert "timed out" in str(exc_info.value).lower()

    def test_raw_serial_never_in_profile_or_evidence(self) -> None:
        """Raw serial must never be present in profile, entries, or evidence records."""
        bridge = AndroidDeviceBridge(adb_path="adb")
        mock_cmd = MagicMock(
            return_value=CommandResult(
                command=["adb", "shell", "pm", "list", "features"],
                return_code=0,
                stdout=_FLAGSHIP_FEATURES_OUTPUT,
                stderr="",
                duration_seconds=0.1,
            )
        )

        with (
            patch.object(bridge, "_require_adb", return_value="C:\\tools\\adb.exe"),
            patch("vector_agent.devices.android.bridge.run_command", mock_cmd),
        ):
            profile = bridge.discover_capabilities(_FAKE_SERIAL, device_id=_FAKE_DEVICE_ID)

        # Dump to json and dict
        profile_json = profile.model_dump_json()
        assert _FAKE_SERIAL not in profile_json

        for entry in profile.capabilities.values():
            assert _FAKE_SERIAL not in repr(entry)
            for ev in entry.evidence:
                assert ev.device_id == _FAKE_DEVICE_ID
                assert _FAKE_SERIAL not in (ev.collection_method or "")
                assert _FAKE_SERIAL not in (ev.source_name or "")
                assert _FAKE_SERIAL not in repr(ev)


# ============================================================
# Test Cases: DeviceSession Integration & Refresh Semantics
# ============================================================


class TestDeviceSessionCapabilityIntegration:
    @pytest.fixture
    def session_mgr(self) -> DeviceSessionManager:
        return DeviceSessionManager()

    def test_reconcile_discovers_capabilities(self, session_mgr: DeviceSessionManager) -> None:
        """Reconciliation passes capability fetcher and stores snapshot in session."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]

        def mock_cap_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            return parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=device_id)

        session_mgr.reconcile_android_discovery(
            entries,
            adb_capability_fetcher=mock_cap_fetcher,
        )

        sessions = session_mgr.list_sessions()
        assert len(sessions) == 1
        session = sessions[0]
        assert session.capability_profile is not None
        assert session.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT

        # ConnectedDevice preserves capability profile when CONNECTED
        connected = session.to_connected_device()
        assert connected.capability_profile is not None
        assert connected.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT

    def test_offline_device_masks_capability_knowledge(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """When device goes OFFLINE, to_connected_device() hides capability profile."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]

        def mock_cap_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            return parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=device_id)

        session_mgr.reconcile_android_discovery(
            entries,
            adb_capability_fetcher=mock_cap_fetcher,
        )

        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is not None

        # Device disconnects
        session_mgr.reconcile_android_discovery([])
        assert session.connection_state == ConnectionState.OFFLINE

        # ConnectedDevice must NOT masquerade offline device as having active connected capabilities
        connected = session.to_connected_device()
        assert connected.connection_state == ConnectionState.OFFLINE
        assert connected.capability_profile is None

    def test_reconnect_refreshes_capability_profile(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Reconnecting a device refreshes capability profile."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]

        call_count = 0

        def mock_cap_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            nonlocal call_count
            call_count += 1
            output = _FLAGSHIP_FEATURES_OUTPUT if call_count > 1 else _BUDGET_FEATURES_OUTPUT
            return parse_pm_features(output, device_id=device_id)

        # Initial connect (budget)
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=mock_cap_fetcher)
        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is not None
        assert session.capability_profile.get("gyroscope") == CapabilityStatus.NOT_REPORTED

        # Disconnect
        session_mgr.reconcile_android_discovery([])
        assert session.connection_state == ConnectionState.OFFLINE

        # Reconnect (now flagship)
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=mock_cap_fetcher)
        assert session.connection_state == ConnectionState.CONNECTED
        assert session.capability_profile is not None
        assert session.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT

    def test_explicit_refresh_device_capabilities(self, session_mgr: DeviceSessionManager) -> None:
        """refresh_device_capabilities explicitly updates the snapshot."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]
        session_mgr.reconcile_android_discovery(entries)
        session = session_mgr.list_sessions()[0]
        device_id = session.device_id
        assert session.capability_profile is None

        refreshed = session_mgr.refresh_device_capabilities(
            device_id,
            lambda s, d: parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=d),
        )
        assert refreshed.get("accelerometer") == CapabilityStatus.PRESENT
        assert session.capability_profile == refreshed

    def test_refresh_device_capabilities_fails_on_offline(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """refresh_device_capabilities raises ValueError if device is offline."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]
        session_mgr.reconcile_android_discovery(entries)
        session = session_mgr.list_sessions()[0]
        device_id = session.device_id

        # Disconnect
        session_mgr.reconcile_android_discovery([])

        with pytest.raises(ValueError, match="is not connected"):
            session_mgr.refresh_device_capabilities(
                device_id,
                lambda s, d: parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=d),
            )

    def test_reconnect_failure_clears_stale_profile(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Failed capability discovery on reconnect must clear stale profile rather than keep it."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]

        def mock_cap_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            return parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=device_id)

        # 1. Connect and establish initial profile
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=mock_cap_fetcher)
        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is not None
        assert session.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT

        # 2. Device goes offline
        session_mgr.reconcile_android_discovery([])
        assert session.connection_state == ConnectionState.OFFLINE

        # 3. Device reconnects, but capability discovery now fails
        def failing_cap_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            raise RuntimeError("ADB capability discovery failed")

        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=failing_cap_fetcher)
        assert session.connection_state == ConnectionState.CONNECTED
        # Stale profile must NOT remain visible as current
        assert session.capability_profile is None

    def test_incomplete_profile_retry_suppression_and_interval(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Incomplete capability discovery is suppressed until retry interval elapses."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]
        call_count = 0

        def retryable_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return parse_pm_features(
                    _FLAGSHIP_FEATURES_OUTPUT, device_id=device_id, truncated=True
                )
            return parse_pm_features(
                _FLAGSHIP_FEATURES_OUTPUT, device_id=device_id, truncated=False
            )

        # 1. Initial reconcile triggers fetcher (incomplete profile)
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=retryable_fetcher)
        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is not None
        assert session.capability_profile.profile_complete is False
        assert call_count == 1

        # 2. Immediate second reconcile suppresses retry (< 30s)
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=retryable_fetcher)
        assert call_count == 1
        assert session.capability_profile.profile_complete is False

        # 3. Simulate elapsed interval (advance simulated monotonic clock or backdate last attempt)
        assert session.last_capability_attempt_mono is not None
        session.last_capability_attempt_mono -= 31.0

        # Now reconcile will retry
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=retryable_fetcher)
        assert call_count == 2
        assert session.capability_profile.profile_complete is True

    def test_reconnect_allows_immediate_capability_retry(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Disconnect and reconnect resets attempt tracker, allowing immediate retry."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]
        call_count = 0

        def failing_then_success_fetcher(serial: str, device_id: str) -> DeviceCapabilityProfile:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary ADB error")
            return parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=device_id)

        # Initial connect fails discovery
        session_mgr.reconcile_android_discovery(
            entries, adb_capability_fetcher=failing_then_success_fetcher
        )
        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is None
        assert call_count == 1

        # Immediate reconcile without reconnect: retry is suppressed
        session_mgr.reconcile_android_discovery(
            entries, adb_capability_fetcher=failing_then_success_fetcher
        )
        assert call_count == 1

        # Device disconnects then reconnects: resets tracker and immediately retries
        session_mgr.reconcile_android_discovery([])
        assert session.connection_state == ConnectionState.OFFLINE
        assert session.last_capability_attempt_mono is None

        session_mgr.reconcile_android_discovery(
            entries, adb_capability_fetcher=failing_then_success_fetcher
        )
        assert call_count == 2
        assert session.capability_profile is not None
        assert session.capability_profile.profile_complete is True

    def test_apply_guard_refuses_result_if_session_changes_state(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Capability profile is NOT applied if session changes state during discovery."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]
        session_mgr.reconcile_android_discovery(entries)
        session = session_mgr.list_sessions()[0]
        device_id = session.device_id
        assert session.connection_state == ConnectionState.CONNECTED
        assert session.capability_profile is None

        # Fake fetcher changes session state to OFFLINE during execution
        def state_mutating_fetcher(serial: str, dev_id: str) -> DeviceCapabilityProfile:
            s = session_mgr.get_session(dev_id)
            assert s is not None
            s.connection_state = ConnectionState.OFFLINE
            return parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=dev_id)

        with pytest.raises(DeviceNotConnectedError, match="disconnected or changed state"):
            session_mgr.refresh_device_capabilities(device_id, state_mutating_fetcher)

        # Profile was refused and remains None
        assert session.capability_profile is None
        assert session.connection_state == ConnectionState.OFFLINE

    def test_reconcile_identity_failure_does_not_log_raw_serial(
        self, session_mgr: DeviceSessionManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Raw serial from invalid input must never be interpolated into reconcile logs."""
        bad_serial = "BAD_SERIAL_INJECTION_!@#$"
        entries = [AdbDeviceEntry(serial=bad_serial, state=AdbDeviceState.DEVICE, qualifiers={})]

        def failing_identity_fetcher(serial: str) -> None:
            # Simulates validate_device_serial raising ValidationError
            raise ValueError(f"Simulated validation failure for {serial}")

        session_mgr.reconcile_android_discovery(
            entries,
            adb_identity_fetcher=failing_identity_fetcher,
        )

        assert bad_serial not in caplog.text
        assert "Identity fetch failed" in caplog.text
        assert "ValueError" in caplog.text

    def test_reconcile_stale_discovery_cannot_overwrite_reconnected_session(
        self, session_mgr: DeviceSessionManager
    ) -> None:
        """Older discovery result must not overwrite a session that reconnected concurrently."""
        entries = [AdbDeviceEntry(serial=_FAKE_SERIAL, state=AdbDeviceState.DEVICE, qualifiers={})]

        def slow_budget_fetcher(serial: str, dev_id: str) -> DeviceCapabilityProfile:
            # Concurrently, while discovery 1 is executing:
            # The device disconnects and reconnects with new flagship capability
            session_mgr.reconcile_android_discovery([])
            session_mgr.reconcile_android_discovery(
                entries,
                adb_capability_fetcher=lambda s, d: parse_pm_features(
                    _FLAGSHIP_FEATURES_OUTPUT, device_id=d
                ),
            )
            reconnected_session = session_mgr.get_session(dev_id)
            assert reconnected_session is not None
            assert reconnected_session.capability_profile is not None
            assert (
                reconnected_session.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT
            )

            # Return the stale budget profile from the slow first discovery
            return parse_pm_features(_BUDGET_FEATURES_OUTPUT, device_id=dev_id)

        # Execute discovery with the slow fetcher
        session_mgr.reconcile_android_discovery(entries, adb_capability_fetcher=slow_budget_fetcher)

        # Verify that the stale budget profile did NOT overwrite the reconnected flagship profile
        session = session_mgr.list_sessions()[0]
        assert session.capability_profile is not None
        assert session.capability_profile.get("gyroscope") == CapabilityStatus.PRESENT


# ============================================================
# Test Cases: API Endpoints & Truthful Semantics
# ============================================================


class TestCapabilitiesApiEndpoint:
    @pytest.fixture
    def app(self) -> typing.Any:
        return create_app()

    @pytest.fixture
    async def client(self, app: typing.Any) -> typing.AsyncGenerator[AsyncClient, None]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_unknown_device_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/devices/android-nonexistent/capabilities")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_unauthorized_device_returns_403(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="android-unauth-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.UNAUTHORIZED,
            last_seen=_NOW,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-unauth-test"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            resp = await client.get("/api/v1/devices/android-unauth-test/capabilities")
        assert resp.status_code == 403
        assert "unauthorized" in resp.json()["detail"].lower()

    async def test_offline_device_returns_400(self, client: AsyncClient) -> None:
        session = DeviceSession(
            device_id="android-offline-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.OFFLINE,
            last_seen=_NOW,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-offline-test"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            resp = await client.get("/api/v1/devices/android-offline-test/capabilities")
        assert resp.status_code == 400
        assert "not connected" in resp.json()["detail"].lower()

    async def test_connected_android_device_returns_200_profile(self, client: AsyncClient) -> None:
        profile = parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id="android-connected-test")
        session = DeviceSession(
            device_id="android-connected-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            capability_profile=profile,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-connected-test"] = session

        with patch("vector_agent.api.devices._trigger_discovery"):
            resp = await client.get("/api/v1/devices/android-connected-test/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "android-connected-test"
        assert data["platform"] == "ANDROID"
        assert data["profile_complete"] is True
        assert data["capabilities"]["gyroscope"]["status"] == "PRESENT"
        assert data["capabilities"]["barometer"]["status"] == "PRESENT"
        assert _FAKE_SERIAL not in resp.text

    async def test_capabilities_refresh_param(self, client: AsyncClient) -> None:
        """refresh=true forces a new discovery run via bridge."""
        old_profile = parse_pm_features(_BUDGET_FEATURES_OUTPUT, device_id="android-refresh-test")
        session = DeviceSession(
            device_id="android-refresh-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            capability_profile=old_profile,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-refresh-test"] = session

        new_profile = parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id="android-refresh-test")

        with (
            patch("vector_agent.api.devices._trigger_discovery"),
            patch(
                "vector_agent.devices.android.bridge.AndroidDeviceBridge.discover_capabilities",
                return_value=new_profile,
            ),
        ):
            resp = await client.get(
                "/api/v1/devices/android-refresh-test/capabilities?refresh=true"
            )

        assert resp.status_code == 200
        data = resp.json()
        # Should now be flagship (gyroscope present)
        assert data["capabilities"]["gyroscope"]["status"] == "PRESENT"

    async def test_capabilities_api_hides_raw_serial_on_failure(self, client: AsyncClient) -> None:
        """Raw serial in ADB stderr or internal exceptions must never leak to API responses."""
        session = DeviceSession(
            device_id="android-leak-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-leak-test"] = session

        with (
            patch("vector_agent.api.devices._trigger_discovery"),
            patch(
                "vector_agent.devices.android.bridge.AndroidDeviceBridge.discover_capabilities",
                side_effect=RuntimeError(
                    f"pm list features failed for {_FAKE_SERIAL}: device offline"
                ),
            ),
        ):
            resp = await client.get("/api/v1/devices/android-leak-test/capabilities?refresh=true")

        assert resp.status_code == 502
        assert _FAKE_SERIAL not in resp.text
        assert (
            resp.json()["detail"]
            == "Failed to discover capabilities for device 'android-leak-test'."
        )

    async def test_capabilities_api_timeout_returns_504(self, client: AsyncClient) -> None:
        """Timeout during capability discovery returns 504 Gateway Timeout."""
        session = DeviceSession(
            device_id="android-timeout-test",
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions["android-timeout-test"] = session

        with (
            patch("vector_agent.api.devices._trigger_discovery"),
            patch(
                "vector_agent.devices.android.bridge.AndroidDeviceBridge.discover_capabilities",
                side_effect=TimeoutError("Timed out after 10s"),
            ),
        ):
            resp = await client.get(
                "/api/v1/devices/android-timeout-test/capabilities?refresh=true"
            )

        assert resp.status_code == 504
        assert _FAKE_SERIAL not in resp.text
        assert "timed out" in resp.json()["detail"].lower()

    async def test_capabilities_endpoint_reconciles_disconnected_device_to_offline(
        self, client: AsyncClient
    ) -> None:
        """Endpoint must reconcile before returning cached data so unplugged phone returns 400."""
        # 1. Device initially discovered CONNECTED with capability profile
        device_id = "android-disconnect-test"
        profile = parse_pm_features(_FLAGSHIP_FEATURES_OUTPUT, device_id=device_id)
        session = DeviceSession(
            device_id=device_id,
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            capability_profile=profile,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions[device_id] = session

        # 2. Subsequent discovery reports the device absent (empty device list)
        empty_discovery = AndroidDiscoveryResult(
            state=AdbDeviceState.DEVICE,
            devices=[],
            message="No devices connected",
            adb_available=True,
        )

        with patch(
            "vector_agent.devices.android.bridge.AndroidDeviceBridge.discover_devices",
            return_value=empty_discovery,
        ):
            # 3. GET /api/v1/devices/{device_id}/capabilities
            resp = await client.get(f"/api/v1/devices/{device_id}/capabilities")

        # 4. Response must NOT return 200 cached capability data
        assert resp.status_code == 400
        # 5. Session becomes OFFLINE
        assert session.connection_state == ConnectionState.OFFLINE
        # 6. Endpoint returns the truthful offline response
        assert "not connected" in resp.json()["detail"].lower()

    async def test_capabilities_endpoint_discovery_failure_privacy(
        self, client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Exception containing raw serial or sensitive marker in _trigger_discovery must not leak to HTTP 503 or logs."""
        sensitive_marker = "CONFIDENTIAL_SERIAL_XYZ_987654"
        device_id = "android-privacy-fail-test"
        session = DeviceSession(
            device_id=device_id,
            platform=Platform.ANDROID,
            connection_state=ConnectionState.CONNECTED,
            last_seen=_NOW,
            raw_serial=_FAKE_SERIAL,
        )
        device_session_manager._sessions[device_id] = session

        with patch(
            "vector_agent.api.devices._trigger_discovery",
            side_effect=RuntimeError(f"ADB transport failure for {sensitive_marker}"),
        ):
            resp = await client.get(f"/api/v1/devices/{device_id}/capabilities")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Device discovery failed."
        assert sensitive_marker not in resp.text
        assert sensitive_marker not in caplog.text
        assert "Discovery trigger failed before capability check" in caplog.text
        assert "RuntimeError" in caplog.text
        # A failure to observe is not proof of disconnection: the committed session
        # (identity, state, epoch) is unchanged and the error is surfaced as the 503 above.
        assert session.connection_state == ConnectionState.CONNECTED
        assert session.session_epoch == 0
        assert session.raw_serial == _FAKE_SERIAL
        assert device_session_manager.get_session(device_id) is session
