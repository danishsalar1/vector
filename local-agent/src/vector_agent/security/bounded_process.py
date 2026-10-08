"""Bounded capture for the Probe boundary; never logs commands or peer output."""

from __future__ import annotations

import io
import math
import subprocess
import threading
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoundedOutput:
    returncode: int
    stdout: bytes = field(repr=False)


def capture(args: list[str], *, timeout: float = 5.0, limit: int = 65_536) -> BoundedOutput:
    """Internal primitive; callers own the fixed executable/argv allowlist.

    Both pipes are drained concurrently. Each retains at most limit bytes; any
    overflow kills the process and fails closed. No raw subprocess errors escape.
    """
    if not args or not math.isfinite(timeout) or not 0 < timeout <= 30 or not 0 < limit <= 262_144:
        raise ValueError("Invalid process budget.")
    overflow = threading.Event()
    failed = threading.Event()
    output = bytearray()
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise FileNotFoundError("Probe tool unavailable.") from None
    except OSError:
        raise OSError("Probe tool could not start.") from None

    def drain(stdout: bool) -> None:
        stream = process.stdout if stdout else process.stderr
        assert stream is not None
        assert isinstance(stream, io.BufferedReader)
        count = 0
        try:
            while block := stream.read1(4096):
                count += len(block)
                if count > limit:
                    overflow.set()
                    break
                if stdout:
                    output.extend(block)
        except OSError:
            failed.set()
        finally:
            stream.close()

    readers = [threading.Thread(target=drain, args=(v,), daemon=True) for v in (True, False)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while process.poll() is None or any(r.is_alive() for r in readers):
            timed_out = time.monotonic() >= deadline
            if timed_out or overflow.is_set() or failed.is_set():
                break
            time.sleep(0.005)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        for reader in readers:
            reader.join(timeout=0.5)
    if timed_out:
        raise TimeoutError("Probe tool timed out.")
    if overflow.is_set() or failed.is_set() or any(r.is_alive() for r in readers):
        raise OSError("Probe tool output rejected.")
    return BoundedOutput(process.returncode, bytes(output))
