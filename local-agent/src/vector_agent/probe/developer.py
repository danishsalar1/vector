"""Explicit local development console; never starts a diagnostic automatically.

python -m vector_agent.probe.developer --live
No HTTP server, exported credential, automatic installation, permission grant,
pairing, saved results, or DEMO fallback.
"""

from __future__ import annotations

import argparse
import json
import threading

from vector_agent.core.config import get_settings
from vector_agent.devices.android.bridge import _parse_devices_output
from vector_agent.devices.session import DeviceSessionManager
from vector_agent.models.device import Platform
from vector_agent.models.probe import ProbeOperation as O
from vector_agent.probe.lifecycle import (
    DiagnosticSessionError,
    DiagnosticUnavailableError,
    ProbeService,
)
from vector_agent.probe.trust_build import load_trusted_artifact
from vector_agent.security.bounded_process import capture

UNAVAILABLE_MESSAGE = (
    "Diagnostic busy or cleaning up on the device; the session is still connected. Retry."
)
REJECTED_MESSAGE = "Command unavailable or rejected. Inspect state; reconnect with fresh consent after interruption."


def discover(manager: DeviceSessionManager, adb: str) -> None:
    """Bounded existing discovery parser; no raw output is printed or retained."""
    try:
        result = capture([adb, "devices", "-l"], timeout=3, limit=65536)
        if result.returncode:
            raise ConnectionError
        discovered = _parse_devices_output(result.stdout.decode("utf-8", errors="strict"))
        manager.reconcile_android_discovery(discovered.devices)
    except (OSError, ValueError, TimeoutError):
        manager.mark_platform_offline(Platform.ANDROID)


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

    def monitor() -> None:
        while not stopping.wait(2):
            discover(manager, settings.adb_path)

    discover(manager, settings.adb_path)
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
