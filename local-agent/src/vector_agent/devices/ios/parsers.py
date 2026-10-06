"""Pure parsers for iOS device discovery, pairing, and diagnostic outputs.

All parsing functions in this module are pure and side-effect free.
They never log, never execute subprocesses, and never leak raw identifiers,
raw stderr, or private user data.
"""

from __future__ import annotations

import contextlib
import plistlib
import re
from typing import Any

from vector_agent.models.device import (
    ConnectionState,
    DeviceAuthorizationState,
    PairingState,
)
from vector_agent.security.validation import validate_ios_udid

# Safe UDID: alphanumeric characters and hyphens, bounded 16 to 64 chars.
_SAFE_UDID_PATTERN = re.compile(r"^[A-Za-z0-9\-]{16,64}$")
_ASCII_INT_RE = re.compile(r"^-?[0-9]+\Z", re.ASCII)

# Allowlisted keys in com.apple.mobile.battery domain
_BATTERY_BOOLEAN_KEYS = {
    "BatteryIsCharging",
    "ExternalConnected",
    "FullyCharged",
    "HasBattery",
}


def parse_idevice_id_output(stdout: str) -> list[str]:
    """Parse output from 'idevice_id -l' into a list of safe device UDIDs.

    Enforces:
    - Trims whitespace and ignores blank lines
    - Calls validate_ios_udid to guarantee consistent identifier validation
    - Rejects lines with control characters, whitespace, or invalid characters
    - Deduplicates UDIDs while preserving discovery order
    """
    if not stdout:
        return []

    discovered: list[str] = []
    seen: set[str] = set()

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            valid_udid = validate_ios_udid(line)
        except Exception:
            continue

        if valid_udid not in seen:
            seen.add(valid_udid)
            discovered.append(valid_udid)

    return discovered


def parse_pairing_validate_output(
    return_code: int,
    stdout: str,
    stderr: str,
) -> tuple[ConnectionState, DeviceAuthorizationState, str]:
    """Parse output of 'idevicepair -u <udid> validate'.

    Returns:
        (connection_state, authorization_state, safe_human_message)

    Invariants:
    - Never echoes raw stdout or stderr.
    - Requires rc=0 and anchored positive match for "validated pairing" / "success".
    - Negative indicators ("not paired", "unsuccessful", "not validated") reject positive match.
    - Does NOT treat rc=0 with empty output as automatically authorized.
    - Classifies user denial truthfully.
    - Unknown non-zero output returns UNKNOWN, not automatically pairing-required.
    - Hardware is not blamed for pairing / passcode / trust requirements.
    """
    combined = f"{stdout}\n{stderr}".lower().strip()

    # Positive match on exit code 0 and validated pairing pattern
    has_pos = bool(re.search(r"\b(?:validated pairing|success)\b", combined))
    has_neg = bool(re.search(r"\b(?:not validated|unsuccessful|not paired|failed)\b", combined))

    if return_code == 0 and combined and has_pos and not has_neg:
        return (
            ConnectionState.CONNECTED,
            DeviceAuthorizationState.AUTHORIZED,
            "Device is paired and trusted.",
        )

    # User denied trust prompt
    if "denied" in combined or "user denied" in combined:
        return (
            ConnectionState.UNAUTHORIZED,
            DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            "Pairing trust was denied on device. Disconnect, reconnect, and tap Trust to authorize.",
        )

    # Classify failure output safely
    if "passwordprotected" in combined or "passcode" in combined or "device is locked" in combined:
        return (
            ConnectionState.UNAUTHORIZED,
            DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            "Device is locked with a passcode. Unlock the device.",
        )

    if (
        "not paired" in combined
        or "trust dialog" in combined
        or "trust required" in combined
        or "unpaired" in combined
        or "could not validate with device" in combined
    ):
        return (
            ConnectionState.UNAUTHORIZED,
            DeviceAuthorizationState.AUTHORIZATION_REQUIRED,
            "Device pairing and trust required. Tap Trust on the device.",
        )

    if (
        "no device found" in combined
        or "no device" in combined
        or "could not connect to lockdownd" in combined
    ):
        return (
            ConnectionState.OFFLINE,
            DeviceAuthorizationState.UNKNOWN,
            "Device is disconnected or not responding.",
        )

    if "could not connect to usbmuxd" in combined or "usbmuxd" in combined:
        return (
            ConnectionState.UNKNOWN,
            DeviceAuthorizationState.UNKNOWN,
            "Host usbmux service is unavailable.",
        )

    # Unknown exit code or empty output returns UNKNOWN / INCONCLUSIVE
    return (
        ConnectionState.UNKNOWN,
        DeviceAuthorizationState.UNKNOWN,
        "Device pairing status could not be verified.",
    )


_PAIR_SUCCESS_PATTERNS = (
    re.compile(r"^success:\s*paired\s+with\s+device(?:\s+[A-Za-z0-9\-]+)?\.?$", re.IGNORECASE),
    re.compile(
        r"^successfully\s+paired(?:\s+with\s+device(?:\s+[A-Za-z0-9\-]+)?)?\.?$",
        re.IGNORECASE,
    ),
    re.compile(r"^device\s+paired\s+successfully\.?$", re.IGNORECASE),
    re.compile(r"^success\.?$", re.IGNORECASE),
)


def parse_pairing_pair_output(
    return_code: int,
    stdout: str,
    stderr: str,
) -> tuple[PairingState, str]:
    """Parse output of 'idevicepair -u <udid> pair'.

    Returns:
        (PairingState, safe_human_message)

    Invariants:
    - Never echoes raw stdout or stderr.
    - Evaluates output lines using strict positive fullmatch grammar only (F5).
    - No substring detection or negative blocklists for success.
    - Non-zero exit code never returns PAIRED.
    - Bounded, safe return states.
    """
    combined = f"{stdout}\n{stderr}".lower().strip()

    # User denied trust dialog
    if "denied" in combined:
        return (
            PairingState.USER_ACTION_REQUIRED,
            "Pairing trust was denied on device. Reconnect USB cable and accept the Trust prompt.",
        )

    if (
        "trust dialog" in combined
        or "accept the trust" in combined
        or "response pending" in combined
    ):
        return (
            PairingState.USER_ACTION_REQUIRED,
            "Unlock the device and accept the trust prompt on the screen.",
        )

    if "passwordprotected" in combined or "device is locked" in combined or "passcode" in combined:
        return (
            PairingState.USER_ACTION_REQUIRED,
            "Unlock the device with passcode and retry pairing.",
        )

    if "no device found" in combined or "no device" in combined:
        return (
            PairingState.DEVICE_DISCONNECTED,
            "Device disconnected during pairing attempt.",
        )

    if return_code != 0:
        return (
            PairingState.ERROR,
            "Device pairing attempt failed.",
        )

    # For return_code == 0: evaluate lines against strict positive fullmatch grammar
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in lines:
        if any(pat.fullmatch(line) for pat in _PAIR_SUCCESS_PATTERNS):
            return (
                PairingState.PAIRED,
                "Device paired successfully.",
            )

    return (
        PairingState.INCONCLUSIVE,
        "Pairing result is inconclusive.",
    )


def parse_ideviceinfo_key_value(output: str) -> str | None:
    """Parse a single value returned by 'ideviceinfo -k <Key>'.

    Validates:
    - Non-empty after trimming
    - Single line (no embedded newlines)
    - Bounded length (<= 128 chars)
    - No control characters
    - Does not contain common error prefixes
    """
    if not output:
        return None

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        return None

    val = lines[0]
    if len(val) > 128:
        return None

    if any(ord(c) < 32 or ord(c) == 127 for c in val):
        return None

    lower_val = val.lower()
    if lower_val.startswith("error:") or lower_val.startswith("could not"):
        return None

    return val


def parse_battery_telemetry(
    raw_output: str,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse output from 'ideviceinfo -q com.apple.mobile.battery'.

    Strict validation:
    - return_code must be 0
    - Output must be non-empty
    - BatteryCurrentCapacity must be present, integer, and within 0..100
    - Boolean fields must strictly parse as True/False
    - Missing optional keys are allowed; missing capacity is NOT
    - Truncated or malformed key-value pairs cause rejection

    Returns:
        (parsed_facts_dict, None) on success, or (None, safe_error_reason) on failure.
    """
    if return_code != 0:
        return None, "Command exited with non-zero return code"

    if not raw_output or not raw_output.strip():
        return None, "Empty battery telemetry output"

    facts: dict[str, Any] = {}

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if ":" not in line:
            return None, "Malformed output line missing separator"

        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if not key or not val:
            return None, "Malformed key-value pair"

        if key == "BatteryCurrentCapacity":
            capacity_int = _safe_int(val)
            if capacity_int is None:
                return None, "BatteryCurrentCapacity is not an integer"

            if not (0 <= capacity_int <= 100):
                return None, f"BatteryCurrentCapacity out of range (0..100): {capacity_int}"

            facts["battery_current_capacity"] = capacity_int

        elif key in _BATTERY_BOOLEAN_KEYS:
            # Map snake_case key
            snake_key = {
                "BatteryIsCharging": "battery_is_charging",
                "ExternalConnected": "external_connected",
                "FullyCharged": "fully_charged",
                "HasBattery": "has_battery",
            }[key]

            lower_val = val.lower()
            if lower_val == "true":
                facts[snake_key] = True
            elif lower_val == "false":
                facts[snake_key] = False
            else:
                return None, f"Malformed boolean value for {key}"

        # Unknown extra keys are ignored safely without failing

    if "battery_current_capacity" not in facts:
        return None, "Required BatteryCurrentCapacity field was not found"

    return facts, None


def _safe_int(val: Any) -> int | None:
    """Safely convert a value to int, strictly rejecting bool, non-integer floats, and non-ASCII digit strings."""
    if isinstance(val, bool) or val is None:
        return None
    try:
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            if not val.is_integer():
                return None
            return int(val)
        if isinstance(val, str):
            if not _ASCII_INT_RE.match(val):
                return None
            return int(val)
        return None
    except (ValueError, TypeError, OverflowError):
        return None


def _find_dict_in_plist(
    data: Any,
    target_keys: set[str],
    depth: int = 0,
    max_depth: int = 8,
) -> dict[str, Any] | None:
    """Recursively search for a dictionary containing at least one target key."""
    if depth > max_depth:
        return None
    if isinstance(data, dict):
        if any(k in data for k in target_keys):
            return data
        for v in data.values():
            found = _find_dict_in_plist(v, target_keys, depth=depth + 1, max_depth=max_depth)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_dict_in_plist(item, target_keys, depth=depth + 1, max_depth=max_depth)
            if found is not None:
                return found
    return None


def parse_gasgauge_plist(
    raw_input: str | bytes,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse output from 'idevicediagnostics diagnostics GasGauge'.

    Output is XML plist. Validates:
    - return_code must be 0
    - Valid XML plist structure
    - Contains at least one core battery telemetry key
    - Enforces strict numeric types and reasonable bounds
    - Units: GasGauge capacity keys do not have an established mAh contract;
      emitted strictly as source-labelled neutral raw fields (R1).
    - Removes all magnitude-based unit inference.
    - Never fabricates health percentage or battery health claims.
    """
    if return_code != 0:
        return None, "Command exited with non-zero return code"

    if not raw_input:
        return None, "Empty GasGauge output"

    raw_bytes = raw_input.encode("utf-8") if isinstance(raw_input, str) else raw_input
    if not raw_bytes.strip():
        return None, "Empty GasGauge output"

    try:
        parsed = plistlib.loads(raw_bytes)
    except Exception as exc:
        return None, f"Failed to parse GasGauge XML plist: {type(exc).__name__}"

    target_keys = {
        "CycleCount",
        "Cycle Count",
        "DesignCapacity",
        "Design Capacity",
        "FullChargeCapacity",
        "AppleRawMaxCapacity",
        "NominalChargeCapacity",
        "CurrentCapacity",
    }
    battery_dict = _find_dict_in_plist(parsed, target_keys)
    if not battery_dict:
        return None, "No GasGauge battery dictionary found in plist response"

    facts: dict[str, Any] = {}

    # 1. Cycle count
    raw_cycle = None
    if "CycleCount" in battery_dict:
        raw_cycle = battery_dict["CycleCount"]
    elif "Cycle Count" in battery_dict:
        raw_cycle = battery_dict["Cycle Count"]
    if raw_cycle is not None:
        c = _safe_int(raw_cycle)
        if c is not None and 0 <= c <= 20000:
            facts["cycle_count"] = c
        else:
            return None, f"CycleCount invalid or out of reasonable bounds: {raw_cycle}"

    # 2. Design capacity (neutral raw field, GasGauge does not establish mAh unit contract)
    raw_design = None
    if "DesignCapacity" in battery_dict:
        raw_design = battery_dict["DesignCapacity"]
    elif "Design Capacity" in battery_dict:
        raw_design = battery_dict["Design Capacity"]
    if raw_design is not None:
        d = _safe_int(raw_design)
        if d is not None and 0 <= d <= 50000:
            facts["design_capacity_raw"] = d
        else:
            return None, f"DesignCapacity invalid or out of reasonable bounds: {raw_design}"

    # 3. Full / nominal charge capacity
    if "FullChargeCapacity" in battery_dict:
        raw_full = battery_dict["FullChargeCapacity"]
        f = _safe_int(raw_full)
        if f is not None and 0 <= f <= 50000:
            facts["full_charge_capacity_raw"] = f
        else:
            return None, f"FullChargeCapacity invalid or out of reasonable bounds: {raw_full}"

    if "NominalChargeCapacity" in battery_dict:
        raw_nom = battery_dict["NominalChargeCapacity"]
        n = _safe_int(raw_nom)
        if n is not None and 0 <= n <= 50000:
            facts["nominal_charge_capacity_raw"] = n
        else:
            return None, f"NominalChargeCapacity invalid or out of reasonable bounds: {raw_nom}"

    if "AppleRawMaxCapacity" in battery_dict:
        raw_max = battery_dict["AppleRawMaxCapacity"]
        m = _safe_int(raw_max)
        if m is not None and 0 <= m <= 50000:
            facts["raw_max_capacity_raw"] = m

    if "CurrentCapacity" in battery_dict:
        raw_cur = battery_dict["CurrentCapacity"]
        cur = _safe_int(raw_cur)
        if cur is not None and 0 <= cur <= 50000:
            facts["current_capacity_raw"] = cur

    # 4. Voltage (mV)
    raw_voltage = None
    if "Voltage" in battery_dict:
        raw_voltage = battery_dict["Voltage"]
    elif "BatteryVoltage" in battery_dict:
        raw_voltage = battery_dict["BatteryVoltage"]
    if raw_voltage is not None:
        v = _safe_int(raw_voltage)
        if v is not None and 0 <= v <= 20000:
            facts["voltage_mv"] = v

    # 5. Is charging
    raw_charging = None
    if "IsCharging" in battery_dict:
        raw_charging = battery_dict["IsCharging"]
    elif "BatteryIsCharging" in battery_dict:
        raw_charging = battery_dict["BatteryIsCharging"]
    if raw_charging is not None and isinstance(raw_charging, bool):
        facts["is_charging"] = raw_charging

    if not facts:
        return None, "No valid battery telemetry fields could be extracted from GasGauge response"

    return facts, None


def parse_ioreg_battery_plist(
    raw_input: str | bytes,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse output from 'idevicediagnostics ioregentry AppleSmartBattery' or AppleARMPMUCharger.

    Output is XML plist. Validates:
    - return_code must be 0
    - Valid XML plist structure
    - Contains core battery fields (AppleRawMaxCapacity, DesignCapacity, CycleCount)
    - Source contract: AppleSmartBattery schema explicitly establishes mAh units for
      DesignCapacity and AppleRawMaxCapacity (R1).
    - Enforces numeric bounds and strict boolean types
    """
    if return_code != 0:
        return None, "Command exited with non-zero return code"

    if not raw_input:
        return None, "Empty IORegistry output"

    raw_bytes = raw_input.encode("utf-8") if isinstance(raw_input, str) else raw_input
    if not raw_bytes.strip():
        return None, "Empty IORegistry output"

    try:
        parsed = plistlib.loads(raw_bytes)
    except Exception as exc:
        return None, f"Failed to parse IORegistry XML plist: {type(exc).__name__}"

    target_keys = {
        "CycleCount",
        "DesignCapacity",
        "AppleRawMaxCapacity",
        "AppleRawCurrentCapacity",
        "ExternalConnected",
        "IsCharging",
        "ChargerState",
    }
    entry_dict = _find_dict_in_plist(parsed, target_keys)
    if not entry_dict:
        return None, "No battery/charger dictionary found in IORegistry response"

    facts: dict[str, Any] = {}

    # Cycle count
    if "CycleCount" in entry_dict:
        c = _safe_int(entry_dict["CycleCount"])
        if c is not None and 0 <= c <= 20000:
            facts["cycle_count"] = c

    # Design capacity (AppleSmartBattery source contract establishes mAh)
    if "DesignCapacity" in entry_dict:
        d = _safe_int(entry_dict["DesignCapacity"])
        if d is not None and 0 <= d <= 50000:
            facts["design_capacity_mah"] = d

    # AppleRawMaxCapacity (AppleSmartBattery source contract establishes mAh)
    if "AppleRawMaxCapacity" in entry_dict:
        f = _safe_int(entry_dict["AppleRawMaxCapacity"])
        if f is not None and 0 <= f <= 50000:
            facts["raw_max_capacity_mah"] = f

    # External connected
    if "ExternalConnected" in entry_dict:
        raw_ext = entry_dict["ExternalConnected"]
        if isinstance(raw_ext, bool):
            facts["external_connected"] = raw_ext

    # Is charging
    if "IsCharging" in entry_dict:
        raw_chg = entry_dict["IsCharging"]
        if isinstance(raw_chg, bool):
            facts["is_charging"] = raw_chg

    # Voltage (mV)
    if "Voltage" in entry_dict:
        v = _safe_int(entry_dict["Voltage"])
        if v is not None and 0 <= v <= 20000:
            facts["voltage_mv"] = v

    if not facts:
        return None, "No valid battery/charger fields extracted from IORegistry entry"

    return facts, None


def parse_disk_usage_output(
    raw_output: str,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse output from 'ideviceinfo -q com.apple.disk_usage'.

    Key-value output format.
    Validates:
    - return_code must be 0
    - TotalDiskCapacity must be present and positive
    - Available storage must not exceed total disk capacity
    - Numbers must parse strictly as integers
    - Disclaims NAND hardware health claims
    - Keeps AmountDataAvailable and TotalDataAvailable distinct (LOW 24).
    """
    if return_code != 0:
        return None, "Command exited with non-zero return code"

    if not raw_output or not raw_output.strip():
        return None, "Empty disk_usage output"

    raw_map: dict[str, str] = {}
    for line in raw_output.splitlines():
        trimmed = line.strip()
        if not trimmed or ":" not in trimmed:
            continue
        k, _, v = trimmed.partition(":")
        raw_map[k.strip()] = v.strip()

    total_disk_raw = raw_map.get("TotalDiskCapacity")
    if not total_disk_raw:
        return None, "Required TotalDiskCapacity field not found"

    total_disk = _safe_int(total_disk_raw)
    if total_disk is None or total_disk <= 0:
        return None, f"Invalid TotalDiskCapacity value: {total_disk_raw}"

    facts: dict[str, Any] = {
        "total_disk_capacity_bytes": total_disk,
    }

    # Data capacity
    if "TotalDataCapacity" in raw_map:
        data_cap = _safe_int(raw_map["TotalDataCapacity"])
        if data_cap is not None:
            if data_cap > total_disk:
                return None, "TotalDataCapacity exceeds TotalDiskCapacity"
            if data_cap > 0:
                facts["total_data_capacity_bytes"] = data_cap

    # Total data available (includes purgeable)
    if "TotalDataAvailable" in raw_map:
        tot_avail = _safe_int(raw_map["TotalDataAvailable"])
        if tot_avail is not None:
            if tot_avail > total_disk:
                return None, "TotalDataAvailable exceeds TotalDiskCapacity"
            if tot_avail >= 0:
                facts["total_data_available_bytes"] = tot_avail

    # Amount data available (free unallocated)
    if "AmountDataAvailable" in raw_map:
        amt_avail = _safe_int(raw_map["AmountDataAvailable"])
        if amt_avail is not None:
            if amt_avail > total_disk:
                return None, "AmountDataAvailable exceeds TotalDiskCapacity"
            if amt_avail >= 0:
                facts["amount_data_available_bytes"] = amt_avail

    return facts, None


_DEVMODE_ROW_RE = re.compile(
    r"^([A-Za-z0-9\-]+)\s*[:\-\s]\s*(enabled|disabled|n/a|unsupported)\b",
    re.IGNORECASE | re.ASCII,
)


def parse_developer_mode_output(
    return_code: int,
    stdout: str,
    stderr: str,
    target_udid: str | None = None,
) -> tuple[str, str]:
    """Parse output from 'idevicedevmodectl -u <udid> list'.

    Read-only command. Never triggers Developer Mode mutations.
    Enforces row-level parsing targeting ONLY the specific target_udid (R2).
    """
    if return_code != 0:
        combined_err = f"{stdout}\n{stderr}".lower()
        if (
            "could not connect" in combined_err
            or "no device found" in combined_err
            or "no device" in combined_err
        ):
            return "UNKNOWN", "Device was unreachable during Developer Mode query."
        return "UNKNOWN", f"Developer Mode query exited with error (return code {return_code})."

    if not target_udid:
        return "UNKNOWN", "Target UDID required for Developer Mode row parsing."

    clean_target = target_udid.strip().lower()

    # Parse stdout line by line, selecting ONLY the row matching target_udid exactly
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _DEVMODE_ROW_RE.match(line)
        if not match:
            continue

        row_udid = match.group(1).lower()
        if row_udid != clean_target:
            continue

        state_token = match.group(2).lower()
        if state_token == "enabled":
            return "ENABLED", "Developer Mode is enabled on the device."
        if state_token == "disabled":
            return "DISABLED", "Developer Mode is disabled on the device."
        if state_token in ("n/a", "unsupported"):
            return "NOT_APPLICABLE", "Developer Mode is not supported on this iOS version."

        return "UNKNOWN", "Developer Mode state could not be conclusively determined."

    return "UNKNOWN", "Target device status not found in developer mode list."


def parse_nand_plist(
    raw_input: str | bytes,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse output from 'idevicediagnostics diagnostics NAND' (investigation / experimental).

    Validates:
    - return_code must be 0
    - Non-empty XML plist
    - Extracts controller/chip metadata if present
    - Disclaims NAND health claims
    """
    if return_code != 0:
        return None, "Command exited with non-zero return code"

    if not raw_input:
        return None, "Empty NAND diagnostics output"

    raw_bytes = raw_input.encode("utf-8") if isinstance(raw_input, str) else raw_input
    if not raw_bytes.strip():
        return None, "Empty NAND diagnostics output"

    try:
        parsed = plistlib.loads(raw_bytes)
    except Exception as exc:
        return None, f"Failed to parse NAND XML plist: {type(exc).__name__}"

    target_keys = {"BytesPerPage", "PagesPerBlock", "BlocksPerChunk"}
    nand_dict = _find_dict_in_plist(parsed, target_keys)
    if not nand_dict:
        return None, "No NAND diagnostic data found in response"

    facts: dict[str, Any] = {}
    for k in ("BytesPerPage", "PagesPerBlock", "BlocksPerChunk"):
        if k in nand_dict:
            with contextlib.suppress(ValueError, TypeError):
                facts[k.lower()] = int(nand_dict[k])

    if not facts:
        facts["diagnostics_relay_present"] = True

    return facts, None
