"""Explicit local development console; never starts a diagnostic automatically.

python -m vector_agent.probe.developer --live
No HTTP server, exported credential, automatic installation, permission grant,
pairing, saved results, or DEMO fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from typing import TextIO

from vector_agent.core.config import get_settings
from vector_agent.devices.android.bridge import AndroidDeviceBridge
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.probe.lifecycle import (
    DiagnosticSessionError,
    DiagnosticUnavailableError,
    ProbeService,
)
from vector_agent.probe.trust_build import load_trusted_artifact

UNAVAILABLE_MESSAGE = (
    "Diagnostic busy or cleaning up on the device; the session is still connected. Retry."
)
REJECTED_MESSAGE = "Command unavailable or rejected. Inspect state; reconnect with fresh consent after interruption."


def discover(manager: DeviceSessionManager, adb: str) -> bool:
    """Refresh sessions from ONE trustworthy ``adb devices -l`` listing; never guess.

    Uses the agent's own trust rule (``AndroidDeviceBridge.list_attached_devices``): a
    missing adb, non-zero exit, timeout, exception, truncated or malformed output, missing
    list header or daemon-restart notice is NOT evidence about the phone. In that case
    sessions, states and epochs stay exactly as last committed and False is returned so the
    console can say so. Only a trustworthy listing (including a genuinely empty one) is
    reconciled, which is the sole way a device becomes OFFLINE or UNAUTHORIZED here.
    """
    entries = AndroidDeviceBridge(adb_path=adb).list_attached_devices(timeout=3.0)
    if entries is None:
        return False
    try:
        manager.reconcile_android_discovery(entries)
    except (OSError, ValueError, TimeoutError):
        return False
    return True


def refresh_discovery(
    manager: DeviceSessionManager,
    adb: str,
    uncertain: threading.Event,
    out: TextIO | None = None,
) -> bool:
    """One discovery pass that keeps uncertainty visible (once per transition, no details)."""
    stream = out if out is not None else sys.stderr
    trusted = discover(manager, adb)
    if not trusted and not uncertain.is_set():
        uncertain.set()
        print("Device discovery is uncertain; device state left unchanged.", file=stream)
    elif trusted and uncertain.is_set():
        uncertain.clear()
        print("Device discovery recovered.", file=stream)
    return trusted


def run_command(
    command: list[str],
    *,
    manager: DeviceSessionManager,
    service: ProbeService,
    selected: str | None,
) -> tuple[str | None, str]:
    """Execute one console command; return (selected device, text to print).

    Rejections are reported, never raised: a retryable device answer keeps the session,
    and a session-ending failure names its reason instead of exiting the console.
    """
    try:
        if command == ["devices"]:
            return selected, json.dumps(
                [
                    {"device_id": s.device_id, "state": s.connection_state.value}
                    for s in manager.list_sessions()
                ]
            )
        if len(command) == 2 and command[0] == "select":
            if manager.get_session(command[1]) is None:
                raise ValueError
            return command[1], "Device selected. Launch and approve on-device consent explicitly."
        if selected is None:
            raise ValueError
        connection = service.connection(selected)
        if command == ["capabilities"]:
            return selected, json.dumps(
                [c.model_dump(mode="json") for c in connection.diagnostic_capabilities()]
            )
        if command[0] == "start" and len(command) == 2:
            return selected, connection.diagnostic(O.START_CHALLENGE, command[1]).model_dump_json(
                indent=2
            )
        if command in (["poll"], ["cancel"]):
            operation = O.FETCH_OBSERVATIONS if command[0] == "poll" else O.CANCEL_CHALLENGE
            return selected, connection.diagnostic(operation).model_dump_json(indent=2)
        if len(command) == 1 and command[0] in {"discover", "launch", "connect", "stop"}:
            actions = {
                "discover": connection.discover,
                "launch": connection.launch,
                "connect": connection.connect,
                "stop": connection.stop,
            }
            return selected, actions[command[0]]().model_dump_json(indent=2)
        raise ValueError
    except DiagnosticUnavailableError:
        return selected, UNAVAILABLE_MESSAGE
    except DiagnosticSessionError as exc:
        return selected, (
            f"Probe session ended ({exc.reason.value}). Reconnect with fresh on-device consent."
        )
    except (ValueError, ConnectionError):
        return selected, REJECTED_MESSAGE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    settings = get_settings()
    if settings.demo_mode:
        parser.error("Disable DEMO explicitly before using the LIVE Probe console.")
    artifact = load_trusted_artifact(settings.data_path / "probe-trust.json")
    if artifact is None or artifact.protocol_version != 2:
        parser.error("Enroll the verified Phase 8C APK first.")
    manager = DeviceSessionManager()
    service = ProbeService(manager, adb_path=settings.adb_path, artifact=artifact)
    stopping = threading.Event()
    uncertain = threading.Event()

    def monitor() -> None:
        while not stopping.wait(2):
            refresh_discovery(manager, settings.adb_path, uncertain)

    refresh_discovery(manager, settings.adb_path, uncertain)
    worker = threading.Thread(target=monitor, name="vector-developer-discovery", daemon=True)
    worker.start()
    selected: str | None = None
    print("LIVE development console. Use only with your test phone and on-device consent.")
    print(
        "Commands: devices, select <opaque-id>, discover, launch, connect, capabilities, start <diagnostic-id>, poll, cancel, stop, quit"
    )
    try:
        while True:
            command = input("vector> ").strip().split()
            if not command:
                continue
            if command == ["quit"]:
                break
            selected, text = run_command(
                command, manager=manager, service=service, selected=selected
            )
            print(text)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        stopping.set()
        worker.join(timeout=5)
        service.close()


if __name__ == "__main__":
    main()
