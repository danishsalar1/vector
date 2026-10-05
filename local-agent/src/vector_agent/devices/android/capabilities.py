"""Android runtime capability discovery and parsing.

Maps Android system features (from 'pm list features') to platform-neutral
VECTOR capability profiles with Level 1 runtime evidence.

Invariants:
- Level 1 Runtime Detection only — does NOT claim Level 2 Functional Verification
  or Level 3 Factory Reference Comparison.
- Evidence-backed: Every capability entry includes provenance.
- Opaque device IDs only — raw serial numbers are never accepted or stored.
- Missing runtime features are marked NOT_REPORTED or UNKNOWN, never FAIL or fake ABSENT.
- No model catalog required: works generically on unknown Android devices.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vector_agent.core.logging import get_logger
from vector_agent.models.device import (
    CapabilityEntry,
    CapabilityStatus,
    DeviceCapabilityProfile,
    EvidenceRecord,
    EvidenceSourceType,
    Platform,
    VerificationLevel,
)

logger = get_logger(__name__)

# Map from Android PackageManager feature string to platform-neutral capability name
_ANDROID_FEATURE_MAP: dict[str, str] = {
    # Sensors
    "android.hardware.sensor.accelerometer": "accelerometer",
    "android.hardware.sensor.gyroscope": "gyroscope",
    "android.hardware.sensor.compass": "magnetometer",
    "android.hardware.sensor.light": "ambient_light",
    "android.hardware.sensor.proximity": "proximity",
    "android.hardware.sensor.barometer": "barometer",
    "android.hardware.sensor.stepcounter": "step_counter",
    "android.hardware.sensor.stepdetector": "step_detector",
    "android.hardware.sensor.hinge_angle": "hinge_angle",
    "android.hardware.sensor.relative_humidity": "relative_humidity",
    "android.hardware.sensor.ambient_temperature": "ambient_temperature",
    "android.hardware.sensor.heartrate": "heartrate",
    # Camera
    "android.hardware.camera": "camera",
    "android.hardware.camera.front": "camera.front",
    "android.hardware.camera.any": "camera.any",
    "android.hardware.camera.autofocus": "camera.autofocus",
    "android.hardware.camera.flash": "camera.flash",
    "android.hardware.camera.level.full": "camera.level_full",
    "android.hardware.camera.capability.manual_sensor": "camera.manual_sensor",
    "android.hardware.camera.capability.raw": "camera.raw",
    # Biometrics & Security
    "android.hardware.fingerprint": "biometrics.fingerprint",
    "android.hardware.biometrics.face": "biometrics.face",
    "android.hardware.biometrics.iris": "biometrics.iris",
    "android.hardware.strongbox_keystore": "security.strongbox",
    # Connectivity
    "android.hardware.bluetooth": "bluetooth",
    "android.hardware.bluetooth_le": "bluetooth_le",
    "android.hardware.wifi": "wifi",
    "android.hardware.wifi.direct": "wifi.direct",
    "android.hardware.wifi.aware": "wifi.aware",
    "android.hardware.wifi.rtt": "wifi.rtt",
    "android.hardware.nfc": "nfc",
    "android.hardware.nfc.hce": "nfc.hce",
    "android.hardware.nfc.hcef": "nfc.hcef",
    "android.hardware.uwb": "uwb",
    "android.hardware.telephony": "telephony",
    "android.hardware.telephony.gsm": "telephony.gsm",
    "android.hardware.telephony.cdma": "telephony.cdma",
    "android.hardware.telephony.ims": "telephony.ims",
    # Location
    "android.hardware.location": "location",
    "android.hardware.location.gps": "location.gps",
    "android.hardware.location.network": "location.network",
    # Audio
    "android.hardware.microphone": "microphone",
    "android.hardware.audio.output": "audio.output",
    "android.hardware.audio.low_latency": "audio.low_latency",
    "android.hardware.audio.pro": "audio.pro",
    # Input / Screen / Ports
    "android.hardware.touchscreen": "touchscreen",
    "android.hardware.touchscreen.multitouch": "touchscreen.multitouch",
    "android.hardware.touchscreen.multitouch.distinct": "touchscreen.multitouch_distinct",
    "android.hardware.touchscreen.multitouch.jazzhand": "touchscreen.multitouch_jazzhand",
    "android.hardware.screen.portrait": "screen.portrait",
    "android.hardware.screen.landscape": "screen.landscape",
    "android.hardware.usb.host": "usb.host",
    "android.hardware.usb.accessory": "usb.accessory",
    # Graphics
    "android.hardware.vulkan.version": "graphics.vulkan",
    "android.hardware.vulkan.level": "graphics.vulkan_level",
    "reqGlEsVersion": "graphics.opengles",
}

# Standard smartphone capabilities tracked for diagnostic applicability.
# If pm list features ran successfully but did not declare one of these,
# it is explicitly marked NOT_REPORTED rather than assumed absent or failed.
# Standard smartphone capabilities tracked for diagnostic applicability.
# If pm list features ran successfully but did not declare one of these,
# it is explicitly marked NOT_REPORTED rather than assumed absent or failed.
_TRACKED_STANDARD_CAPABILITIES: tuple[str, ...] = (
    "accelerometer",
    "gyroscope",
    "magnetometer",
    "ambient_light",
    "proximity",
    "barometer",
    "step_counter",
    "camera",
    "camera.front",
    "camera.flash",
    "camera.autofocus",
    "biometrics.fingerprint",
    "biometrics.face",
    "bluetooth",
    "bluetooth_le",
    "wifi",
    "nfc",
    "uwb",
    "telephony",
    "location.gps",
    "microphone",
    "audio.output",
    "touchscreen",
    "usb.host",
)


def parse_pm_features(
    raw_output: str,
    device_id: str,
    collected_at: datetime | None = None,
    truncated: bool = False,
) -> DeviceCapabilityProfile:
    """Parse 'pm list features' output into a platform-neutral DeviceCapabilityProfile.

    Args:
        raw_output: Raw stdout from 'adb shell pm list features'.
        device_id: Opaque device ID (safe for public exposure; never raw serial).
        collected_at: Timestamp of collection (defaults to now UTC).
        truncated: True if command output was capped by subprocess policy.

    Returns:
        DeviceCapabilityProfile with Level 1 runtime detection evidence.
    """
    now = collected_at or datetime.now(UTC)
    capabilities: dict[str, CapabilityEntry] = {}
    all_evidence: list[EvidenceRecord] = []
    metadata: dict[str, Any] = {}

    if truncated:
        metadata["truncated"] = True

    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if truncated and lines:
        # Discard final possibly-partial line before parsing to prevent partial lines creating false PRESENT
        lines.pop()
    raw_feature_map: dict[str, str | None] = {}
    malformed_lines: list[str] = []

    for line in lines:
        if not line.startswith("feature:"):
            if line.startswith("reqGlEsVersion:"):
                raw_feature_map["reqGlEsVersion"] = line[len("reqGlEsVersion:") :].strip()
            else:
                malformed_lines.append(line)
            continue
        feat_decl = line[len("feature:") :].strip()
        if not feat_decl:
            malformed_lines.append(line)
            continue
        feat_name: str
        feat_val: str | None = None
        if "=" in feat_decl:
            feat_name, _, feat_val = feat_decl.partition("=")
            feat_name = feat_name.strip()
            feat_val = feat_val.strip()
        else:
            feat_name = feat_decl

        # Idempotently record
        raw_feature_map[feat_name] = feat_val

    metadata["raw_feature_count"] = len(raw_feature_map)
    metadata["raw_platform_features"] = dict(raw_feature_map)
    if malformed_lines:
        metadata["malformed_lines_count"] = len(malformed_lines)

    # If output was completely empty or had no features, report incomplete profile safely
    if not raw_feature_map:
        logger.warning("Empty or unparseable 'pm list features' output for device %s", device_id)
        metadata["empty_output"] = True
        error_evidence = EvidenceRecord(
            diagnostic_id="capability_discovery",
            device_id=device_id,
            source_type=EvidenceSourceType.ADB_SHELL,
            source_name="pm list features",
            collection_method="adb shell pm list features",
            timestamp=now,
            raw_value=None,
            reliability=0.5,
            confidence=0.0,
            metadata={"status": "EMPTY_OR_UNPARSEABLE"},
            error="pm list features returned empty or unparseable output",
        )
        all_evidence.append(error_evidence)

        for tracked in _TRACKED_STANDARD_CAPABILITIES:
            entry = CapabilityEntry(
                name=tracked,
                status=CapabilityStatus.UNKNOWN,
                verification_level=None,
                source="ADB_SHELL / pm list features",
                note="Runtime feature discovery returned empty or unparseable output",
                evidence=[],
            )
            capabilities[tracked] = entry

        return DeviceCapabilityProfile(
            device_id=device_id,
            platform=Platform.ANDROID,
            capabilities=capabilities,
            profiled_at=now,
            profile_complete=False,
            evidence=all_evidence,
            metadata=metadata,
        )

    profile_complete = not truncated

    # Shared snapshot evidence for the successful pm list features run
    snapshot_evidence = EvidenceRecord(
        diagnostic_id="capability_discovery",
        device_id=device_id,
        source_type=EvidenceSourceType.ADB_SHELL,
        source_name="pm list features",
        collection_method="adb shell pm list features",
        timestamp=now,
        raw_value=f"Discovered {len(raw_feature_map)} system features",
        reliability=0.95,
        confidence=1.0,
        metadata={
            "feature_count": len(raw_feature_map),
            "truncated": truncated,
            "verification_level": VerificationLevel.RUNTIME_DETECTION.value,
        },
    )
    all_evidence.append(snapshot_evidence)

    # 1. Map discovered features to platform-neutral capabilities
    mapped_features: set[str] = set()
    unmapped_features: dict[str, str | None] = {}

    for feat_name, feat_val in raw_feature_map.items():
        canonical_name = _ANDROID_FEATURE_MAP.get(feat_name)
        if canonical_name:
            target_name = canonical_name
            note = f"Declared present by Android system as '{feat_name}'"
            if feat_val:
                note += f" (version/level={feat_val})"

            raw_str = f"feature:{feat_name}" + (f"={feat_val}" if feat_val else "")

            ev = EvidenceRecord(
                diagnostic_id="capability_discovery",
                device_id=device_id,
                source_type=EvidenceSourceType.ADB_SHELL,
                source_name="pm list features",
                collection_method="adb shell pm list features",
                timestamp=now,
                raw_value=raw_str,
                reliability=0.95,
                confidence=1.0,
                metadata={
                    "android_feature": feat_name,
                    "version": feat_val,
                    "verification_level": VerificationLevel.RUNTIME_DETECTION.value,
                },
            )
            all_evidence.append(ev)

            entry = CapabilityEntry(
                name=target_name,
                status=CapabilityStatus.PRESENT,
                verification_level=VerificationLevel.RUNTIME_DETECTION,
                source="ADB_SHELL / pm list features",
                note=note,
                evidence=[ev],
            )
            capabilities[target_name] = entry
            mapped_features.add(target_name)
        else:
            # Preserve vendor/unknown features in metadata without polluting canonical capability namespace
            unmapped_features[feat_name] = feat_val

    metadata["unmapped_features_count"] = len(unmapped_features)

    # 2. Check tracked standard capabilities that were not reported
    for tracked in _TRACKED_STANDARD_CAPABILITIES:
        if tracked in mapped_features:
            continue

        if truncated:
            # If output was truncated, omitted capabilities cannot truthfully be claimed NOT_REPORTED
            capabilities[tracked] = CapabilityEntry(
                name=tracked,
                status=CapabilityStatus.UNKNOWN,
                verification_level=None,
                source="ADB_SHELL / pm list features",
                note="Output was truncated; capability presence could not be determined",
                evidence=[],
            )
        else:
            # Complete output where feature was not reported in runtime declarations
            capabilities[tracked] = CapabilityEntry(
                name=tracked,
                status=CapabilityStatus.NOT_REPORTED,
                verification_level=None,
                source="ADB_SHELL / pm list features",
                note="Not reported in runtime system features snapshot (pm list features)",
                evidence=[],
            )

    return DeviceCapabilityProfile(
        device_id=device_id,
        platform=Platform.ANDROID,
        capabilities=capabilities,
        profiled_at=now,
        profile_complete=profile_complete,
        evidence=all_evidence,
        metadata=metadata,
    )
