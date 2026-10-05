---
paths:
  - "local-agent/**"
---

# Backend rules (local-agent)

- Public DTOs never expose internal hardware identifiers (raw ADB serial, IMEI, UDID, account data). Raw identifiers stay inside internal `DeviceSession` objects, excluded from repr/serialization/logs.
- Stale or unknown `device_id` values fail safely and must never retarget another physical device. A device that disappears transitions to OFFLINE; a failed discovery never returns stale CONNECTED sessions.
- Disconnected, offline, unauthorized, and restricted states fail truthfully with explicit status and user guidance. Offline/unauthorized devices never execute privileged diagnostics.
- No broad exception swallowing (`except Exception: pass`, catch-all defaults) that converts uncertainty into apparent success. Catch specific exceptions; map them to explicit domain states (ERROR, INCONCLUSIVE, RESTRICTED, UNSUPPORTED).
- The shared Session/domain layer owns common behavior. Android/iOS bridges implement platform specifics beneath platform-neutral contracts; do not leak platform details upward.
- Never fabricate capabilities. Report only what runtime discovery actually observed; "capability unavailable" is not "device missing", and "not implemented yet" is not "unsupported".
- Safe fixed subprocess policy only: fixed executable, argument arrays, `shell=False`, bounded timeout, bounded output, return-code checks, safe decoding. Never concatenate identifiers or frontend input into command strings. No arbitrary ADB/shell/command endpoint.
- Every PASS carries evidence. Battery telemetry PASS is not battery health.
- Tests use fabricated identifiers. Add negative tests (stale ID, offline, unauthorized, timeout, malformed output) for any new failure path. Never weaken existing tests.
