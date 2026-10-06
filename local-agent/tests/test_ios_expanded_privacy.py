"""Pipeline privacy integration tests for iOS diagnostics.

Verifies that sensitive markers injected at the raw subprocess boundary (raw tool
output, raw plist strings, unparsed CLI output) are stripped by production parsers
and never leak into EvidenceRecords, DiagnosticEvents, ScanSummaries, or API responses.
"""

from __future__ import annotations

from unittest.mock import patch

from vector_agent.core.config import AgentSettings
from vector_agent.devices.ios.bridge import IOSDeviceBridge
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.diagnostics.registry import create_default_registry
from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    ScanLifecycleState,
    ScanMode,
    ScanRequest,
)
from vector_agent.scan import (
    DiagnosticEvent,
    ScanOrchestrator,
    ScanPlanner,
    ScanSession,
)
from vector_agent.security.subprocess_policy import CommandResult

SENSITIVE_MARKERS = [
    "IOS-UDID-SECRET-TEST",
    "FAKE-DEVICE-SERIAL",
    "Johns-iPhone-PRIVATE",
    "FAKE-IMEI",
    "FAKE-WIFI-MAC",
    "fake.account@example.invalid",
    "FAKE-HOST-ID",
    "FAKE-SYSTEM-BUID",
    "FAKE-ESCROW-BLOB",
]

_RAW_GASGAUGE_PLIST_WITH_SECRETS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Status</key>
    <string>Success</string>
    <key>Diagnostics</key>
    <dict>
        <key>GasGauge</key>
        <dict>
            <key>CycleCount</key>
            <integer>88</integer>
            <key>DesignCapacity</key>
            <integer>3200</integer>
            <key>FullChargeCapacity</key>
            <integer>3100</integer>
            <key>DeviceName</key>
            <string>Johns-iPhone-PRIVATE</string>
            <key>SerialNumber</key>
            <string>FAKE-DEVICE-SERIAL</string>
            <key>IMEI</key>
            <string>FAKE-IMEI</string>
            <key>WiFiAddress</key>
            <string>FAKE-WIFI-MAC</string>
            <key>AccountEmail</key>
            <string>fake.account@example.invalid</string>
            <key>HostID</key>
            <string>FAKE-HOST-ID</string>
            <key>SystemBUID</key>
            <string>FAKE-SYSTEM-BUID</string>
            <key>EscrowBag</key>
            <string>FAKE-ESCROW-BLOB</string>
        </dict>
    </dict>
</dict>
</plist>"""

_RAW_DISK_USAGE_KEY_VALUE_WITH_SECRETS = """AmountDataAvailable: 45000000000
TotalDataAvailable: 45000000000
TotalDataCapacity: 118000000000
TotalDiskCapacity: 128000000000
DeviceName: Johns-iPhone-PRIVATE
SerialNumber: FAKE-DEVICE-SERIAL
IMEI: FAKE-IMEI
"""

_RAW_IOREG_BATTERY_PLIST_WITH_SECRETS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>ExternalConnected</key>
    <true/>
    <key>IsCharging</key>
    <true/>
    <key>CycleCount</key>
    <integer>88</integer>
    <key>Voltage</key>
    <integer>3950</integer>
    <key>DeviceName</key>
    <string>Johns-iPhone-PRIVATE</string>
    <key>SerialNumber</key>
    <string>FAKE-DEVICE-SERIAL</string>
    <key>AccountEmail</key>
    <string>fake.account@example.invalid</string>
</dict>
</plist>"""


def _mock_run_command_boundary(cmd: list[str], timeout: float = 5.0) -> CommandResult:
    """Simulate raw subprocess outputs containing sensitive markers."""
    cmd_str = " ".join(cmd)

    if "idevice_id" in cmd_str:
        return CommandResult(
            command=cmd,
            return_code=0,
            stdout="00008030-IOS-UDID-SECRET-TEST\n",
            stderr="",
            duration_seconds=0.01,
        )

    if "idevicepair" in cmd_str and "validate" in cmd_str:
        return CommandResult(
            command=cmd,
            return_code=0,
            stdout="SUCCESS: Validated pairing with device 00008030-IOS-UDID-SECRET-TEST\n",
            stderr="",
            duration_seconds=0.01,
        )

    if "ideviceinfo" in cmd_str:
        if "-k" in cmd:
            k_idx = cmd.index("-k") + 1
            key = cmd[k_idx]
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
        if "-q" in cmd and "com.apple.disk_usage" in cmd:
            return CommandResult(
                command=cmd,
                return_code=0,
                stdout=_RAW_DISK_USAGE_KEY_VALUE_WITH_SECRETS,
                stderr="",
                duration_seconds=0.01,
            )
        if "-q" in cmd and "com.apple.mobile.battery" in cmd:
            # Contains sensitive secrets in raw key-value lines
            stdout = (
                "BatteryCurrentCapacity: 85\n"
                "BatteryIsCharging: true\n"
                "ExternalConnected: true\n"
                "HasBattery: true\n"
                "DeviceName: Johns-iPhone-PRIVATE\n"
                "SerialNumber: FAKE-DEVICE-SERIAL\n"
                "WiFiAddress: FAKE-WIFI-MAC\n"
            )
            return CommandResult(
                command=cmd,
                return_code=0,
                stdout=stdout,
                stderr="",
                duration_seconds=0.01,
            )

    if "idevicediagnostics" in cmd_str:
        if "GasGauge" in cmd_str:
            return CommandResult(
                command=cmd,
                return_code=0,
                stdout=_RAW_GASGAUGE_PLIST_WITH_SECRETS,
                stderr="Notice: device Johns-iPhone-PRIVATE connected\n",
                duration_seconds=0.02,
            )
        if "ioreg" in cmd_str:
            return CommandResult(
                command=cmd,
                return_code=0,
                stdout=_RAW_IOREG_BATTERY_PLIST_WITH_SECRETS,
                stderr="",
                duration_seconds=0.02,
            )

    if "idevicedevmodectl" in cmd_str:
        return CommandResult(
            command=cmd,
            return_code=0,
            stdout="00008030-IOS-UDID-SECRET-TEST: enabled\n",
            stderr="",
            duration_seconds=0.01,
        )

    return CommandResult(
        command=cmd,
        return_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.01,
    )


class TestRealPipelinePrivacy:
    """Execute real production bridge -> parser -> diagnostic -> orchestrator pipeline."""

    def test_pipeline_purges_all_injected_sensitive_markers(self) -> None:
        settings = AgentSettings(
            idevice_id_path="idevice_id",
            idevicepair_path="idevicepair",
            ideviceinfo_path="ideviceinfo",
            idevicediagnostics_path="idevicediagnostics",
            idevicedevmodectl_path="idevicedevmodectl",
        )
        bridge = IOSDeviceBridge(settings=settings)

        with (
            patch(
                "vector_agent.devices.ios.bridge.run_command",
                side_effect=_mock_run_command_boundary,
            ),
            patch("shutil.which", return_value="C:\\tools\\idevice.exe"),
        ):
            # 1. Device discovery & session setup
            mgr = DeviceSessionManager()
            target_udid = "00008030-IOS-UDID-SECRET-TEST"

            def pair_fetcher(u: str) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
                return bridge.validate_pairing(u)

            def id_fetcher(u: str):
                return bridge.get_identity(u)

            mgr.reconcile_ios_discovery(
                [target_udid],
                pair_state_fetcher=pair_fetcher,
                identity_fetcher=id_fetcher,
            )

            session = mgr.list_sessions()[0]
            dto = session.to_connected_device()
            dto_json = dto.model_dump_json()

            # Ensure UDID and markers are not in DTO
            for marker in SENSITIVE_MARKERS:
                assert marker not in dto_json

            # 2. Build scan plan with full registry
            registry = create_default_registry(ios_bridge=bridge)
            planner = ScanPlanner()
            req = ScanRequest(device_id=session.device_id, mode=ScanMode.FULL_VERIFICATION)
            plan = planner.plan(session=session, registry=registry, request=req)

            # Ensure all 6 iOS diagnostics are planned
            assert len(plan.diagnostics_planned) == 6

            scan_session = ScanSession(device_id=plan.device_id, plan=plan)
            scan_session.transition_to(ScanLifecycleState.PLANNED)

            emitted_events: list[DiagnosticEvent] = []
            orchestrator = ScanOrchestrator(session_manager=mgr, registry=registry)

            # 3. Execute scan
            completed_session = orchestrator.run_scan(
                scan_session=scan_session,
                event_callback=emitted_events.append,
            )

            assert completed_session.state == ScanLifecycleState.COMPLETED
            summary = completed_session.to_summary()
            summary_json = summary.model_dump_json()

            # 4. Assert explicit PASS status for all 6 diagnostics to prove non-vacuity
            from vector_agent.models.device import DiagnosticStatus

            expected_statuses = {
                "software_inventory": DiagnosticStatus.PASS,
                "battery_charge_telemetry": DiagnosticStatus.PASS,
                "charging_power_telemetry": DiagnosticStatus.PASS,
                "battery_extended_telemetry": DiagnosticStatus.PASS,
                "developer_mode_state": DiagnosticStatus.PASS,
                "storage_accounting": DiagnosticStatus.PASS,
            }
            assert len(completed_session.diagnostic_results) == 6
            for res in completed_session.diagnostic_results:
                assert res.status == expected_statuses[res.diagnostic_id], (
                    f"Diagnostic {res.diagnostic_id} status {res.status} != {expected_statuses[res.diagnostic_id]}: {res.summary}"
                )

            # 5. Strict assertions: not a single sensitive marker anywhere in pipeline output
            for marker in SENSITIVE_MARKERS:
                assert marker not in summary_json, f"Marker {marker} leaked into ScanSummary"

            for res in completed_session.diagnostic_results:
                res_dump = res.model_dump_json()
                for marker in SENSITIVE_MARKERS:
                    assert marker not in res_dump, (
                        f"Marker {marker} leaked into DiagnosticResult {res.diagnostic_id}"
                    )

                for ev in res.evidence:
                    ev_dump = ev.model_dump_json()
                    for marker in SENSITIVE_MARKERS:
                        assert marker not in ev_dump, (
                            f"Marker {marker} leaked into EvidenceRecord {ev.diagnostic_id}"
                        )

            for event in emitted_events:
                ev_json = event.model_dump_json()
                for marker in SENSITIVE_MARKERS:
                    assert marker not in ev_json, (
                        f"Marker {marker} leaked into DiagnosticEvent {event.event_type}"
                    )
