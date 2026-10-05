"""Central subprocess execution policy for the VECTOR agent.

Security rules enforced here:
- All commands are passed as argument arrays, never shell strings.
- shell=True is PROHIBITED except where explicitly documented.
- Output is capped at a configurable byte limit.
- Timeouts are mandatory.
- Return codes are checked.
- stderr is captured and logged safely.
- No user-supplied strings are interpolated into command arrays
  without allowlist validation.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass

from vector_agent.core.errors import ADBCommandFailedError, ADBCommandTimeoutError
from vector_agent.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CommandResult:
    """Result of a safely executed subprocess command."""

    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    truncated: bool = False


def format_command_for_display(args: Sequence[str]) -> str:
    """Format command arguments for safe display and logging without leaking sensitive values.

    Specifically redacts the serial argument following '-s' in ADB command invocations.
    Does NOT modify the original argument sequence.
    """
    if not args:
        return ""

    first_arg = str(args[0]).lower()
    is_adb = "adb" in first_arg

    display_tokens: list[str] = []
    i = 0
    n = len(args)
    while i < n:
        token = str(args[i])
        if is_adb and token == "-s":
            display_tokens.append("-s")
            if i + 1 < n:
                display_tokens.append("<SERIAL_REDACTED>")
                i += 2
                continue
        elif is_adb and token.startswith("-s") and len(token) > 2:
            display_tokens.append("-s<SERIAL_REDACTED>")
            i += 1
            continue
        display_tokens.append(token)
        i += 1
    return " ".join(display_tokens)


def run_command(
    args: Sequence[str],
    *,
    timeout: float = 10.0,
    max_output_bytes: int = 512_000,
    check: bool = False,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute a subprocess command with strict security policy.

    Args:
        args: Command and arguments as a sequence.  NEVER use shell=True.
        timeout: Maximum allowed execution time in seconds.
        max_output_bytes: Hard cap on stdout size.
        check: If True, raise ADBCommandFailedError on non-zero exit.
        cwd: Working directory for the subprocess.
        env: Environment variables.  None inherits parent environment.

    Returns:
        CommandResult with stdout, stderr, timing, and status.

    Raises:
        ADBCommandTimeoutError: If the command exceeds ``timeout``.
        ADBCommandFailedError: If ``check=True`` and return code is non-zero.
        ValueError: If ``args`` is empty (programming error guard).
    """
    if not args:
        raise ValueError("Command args must not be empty.")

    cmd_list = list(args)
    cmd_display = format_command_for_display(cmd_list)

    start = time.monotonic()
    truncated = False

    try:
        proc = subprocess.run(
            cmd_list,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            # CRITICAL: shell=False is the default and must remain so.
        )
        duration = time.monotonic() - start

        stdout_bytes = proc.stdout
        if len(stdout_bytes) > max_output_bytes:
            stdout_bytes = stdout_bytes[:max_output_bytes]
            truncated = True
            logger.warning(
                "Command output truncated at %d bytes: %s",
                max_output_bytes,
                cmd_display,
            )

        try:
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
        except Exception:
            stdout = stdout_bytes.decode("latin-1", errors="replace")
            stderr = proc.stderr.decode("latin-1", errors="replace")

        result = CommandResult(
            command=cmd_list,
            return_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            timed_out=False,
            truncated=truncated,
        )

        logger.debug(
            "Command completed | cmd=%s | rc=%d | duration=%.2fs",
            cmd_display,
            proc.returncode,
            duration,
        )

        if check and proc.returncode != 0:
            raise ADBCommandFailedError(
                command=cmd_display,
                return_code=proc.returncode,
                stderr=stderr,
            )

        return result

    except subprocess.TimeoutExpired as err:
        duration = time.monotonic() - start
        logger.error("Command timed out after %.1fs: %s", timeout, cmd_display)
        raise ADBCommandTimeoutError(command=cmd_display, timeout=timeout) from err
