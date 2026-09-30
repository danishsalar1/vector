# VECTOR Known Limitations

This document honestly states what VECTOR cannot do, what it can only partially verify, and where evidence may be incomplete or unavailable.

Being precise about limitations is a feature, not a weakness. A verification tool that claims to detect everything is not credible.

---

## Platform Limitations

### iOS (iPhone)

| Limitation | Reason | VECTOR Response |
|---|---|---|
| Most hardware sensor readings are unavailable | iOS sandbox restricts access to raw sensor data | Mark as RESTRICTED |
| Battery health percentage | iOS does not expose this through libimobiledevice by default | RESTRICTED unless idevicediagnostics provides it |
| IMEI availability | Restricted on modern iOS without entitlements | RESTRICTED |
| Camera functional test | Cannot activate camera via USB without an iOS app | ASSISTED or UNAVAILABLE |
| Microphone test | Same restriction as camera | ASSISTED or UNAVAILABLE |
| Display test | Physical display — cannot be verified via USB | ASSISTED |
| Touch screen test | Physical interaction required | ASSISTED |
| Internal storage integrity | iOS restricts filesystem access | RESTRICTED |

### Android

| Limitation | Reason | VECTOR Response |
|---|---|---|
| IMEI | Some OEMs restrict getprop output without root | RESTRICTED or INCONCLUSIVE |
| Camera functional test | Can invoke camera via ADB intent, but verifying output quality requires human or image capture | PARTIALLY_AUTOMATIC |
| Display pixel faults | Cannot detect dead pixels via ADB | UNSUPPORTED (requires physical inspection) |
| Touch screen precision | Cannot measure touch accuracy without on-device test app | ASSISTED |
| Speaker quality | Audio quality cannot be measured purely via USB | ASSISTED |
| Microphone quality | Same as speaker | ASSISTED |
| Battery degradation | Only available via dumpsys if OEM exposes design capacity | INCONCLUSIVE if unavailable |
| Root detection | Some devices hide root status | INCONCLUSIVE |
| OEM-specific behavior | ADB output format varies by Android version and OEM | Handled with fallbacks; marked INCONCLUSIVE if parse fails |

---

## Diagnostic Limitations

### Physical Defects

VECTOR cannot detect physical defects that have no software-visible signature:
- Cracked display glass (if touch still works)
- Dented chassis
- Damaged camera lens (if camera still initializes)
- Water damage (unless sensors or battery behavior shows evidence)
- Replaced/aftermarket parts (limited detectability)
- Screen bleed or discoloration

### Battery Health

Battery charge level ≠ battery health.

Battery charge level (e.g., 83%) does NOT mean battery health is 83%.

VECTOR presents:
- Battery level from `dumpsys battery` (reliable)
- Battery temperature from `dumpsys battery` (reliable)
- Battery voltage from `dumpsys battery` (reliable)
- Battery health classification from OS-reported state (reliable)
- Estimated capacity degradation ONLY if full_charge_capacity and design_capacity are available

If design capacity is unavailable, VECTOR does not fabricate a degradation percentage.

### IMEI Blacklist Verification

VECTOR currently has no connection to external IMEI databases.

The `DeviceIdentityVerifier` interface exists and `LocalIdentityVerifier` is implemented, but:
- IMEI blacklist check → NOT IMPLEMENTED until a real verified provider is configured
- Do not interpret the absence of a blacklist warning as confirmation the device is clean

---

## Data and Privacy Limitations

- VECTOR does not make legal compliance certifications (GDPR, etc.)
- VECTOR is designed for local-first operation; no diagnostic data leaves the laptop by default
- The demo/Vercel version does not access real devices

---

## Benchmark Limitations

- VECTOR's benchmark uses synthetic data, not real consumer used-phone data
- Synthetic scenarios are designed to be representative but cannot capture every real-world edge case
- Ground truth labels in the benchmark are defined by scenario generation rules, not by real device inspections

---

## Connectivity Limitations

- USB cable must support data transfer (charging-only cables will not work)
- ADB requires USB debugging to be enabled on Android
- iOS requires the device to trust the computer
- Some ADB commands may time out on older or heavily loaded devices
- Multiple simultaneous device connections are not supported in Phase 0/1

---

## What VECTOR Does Not Claim

- VECTOR does not claim to detect all forms of tampering
- VECTOR does not provide legal certification of device condition
- VECTOR Trust Score is a diagnostic estimate, not a warranty
- VECTOR does not replace physical inspection for certain defect categories
- Accuracy claims are only made based on benchmark results, never fabricated
