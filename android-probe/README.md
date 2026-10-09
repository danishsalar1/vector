# VECTOR Probe — Android Companion (Phase 8C Development Build)

This is the Android companion source for the VECTOR diagnostic control plane.

## Overview and Historical Context

- **Phase 8B (Historical Baseline)**: Established the initial authenticated transport, foreground consent, abstract Unix domain socket IPC over ADB, and protocol v1 (`HELLO`, `GET_CAPABILITIES`, `HEARTBEAT`). In Phase 8B, challenge operations returned `UNAVAILABLE` without performing diagnostics, and the manifest declared zero permissions.
- **Phase 8C (Current Implementation)**: Introduces authenticated protocol v2, exposing 13 functional diagnostic categories. Automatic and interactive tests execute bounded, privacy-preserving checks. No component authenticity verdict, provenance assessment, or scoring is performed (`authenticity: UNKNOWN`, `qualification: CODE_TESTED`). Physical hardware qualification has **NOT RUN**.

## Permission Audit

The manifest declares **5 permissions**:

### Normal / Install-Time Permissions
1. `android.permission.VIBRATE`: Enables the 300 ms haptic actuator pulse for interactive vibration testing.
2. `android.permission.ACCESS_WIFI_STATE`: Queries Wi-Fi enabled status for connectivity telemetry. Does not scan for networks or read SSIDs/BSSIDs.

### Dangerous / Runtime Permissions
3. `android.permission.CAMERA`: Enables single ephemeral YUV frame capture via Camera2. Camera metadata (facing, hardware level, flash, AF) is discovered permission-free via `CameraCharacteristics`.
4. `android.permission.RECORD_AUDIO`: Enables ephemeral 3-second non-blocking audio level sampling (RMS/peak). Zero audio is recorded to disk or streamed over the wire.
5. `android.permission.ACTIVITY_RECOGNITION`: Required on Android 10+ (API >= 29) for step counter/detector sensor sampling. Not requested on API < 29.

### Permission Workflow and Safety
- **No Automatic Prompting**: Permissions are not requested silently or en masse.
- **Pre-Connection Preparation**: The idle Probe screen provides user-initiated preparation actions for Camera, Microphone, and Activity Recognition before connecting.
- **Settings Recovery**: Only a permission that was requested before and is now denied without a rationale ("Don't ask again") shows a button that opens the app's system Settings details page (`ACTION_APPLICATION_DETAILS_SETTINGS`). A never-requested permission is offered a normal request instead.
- **Denial Semantics**: Permission absence or denial produces `RESTRICTED (PERMISSION_REQUIRED)` or `RESTRICTED (PERMISSION_DENIED)`. It **never produces a hardware `FAIL`**.
- **Fail-Closed Session Revocation**: If a runtime permission dialog appears during an active session, the resulting `onPause` revokes the ephemeral session in accordance with Phase 8B consent rules.

## Protocol and Diagnostic Capabilities

Protocol v2 adds three challenge operations:
- `START_CHALLENGE`: Binds `scan_id`, `diagnostic_id`, `attempt_id`, `challenge_id`, and `collection_not_before`.
- `CANCEL_CHALLENGE`: Stops an active job at once (`RUNNING/STOPPING`, evidence frozen); after the main thread releases its resources the job reports `CANCELLED`, or `ERROR/CLEANUP_ERROR` if a release failed.
- `FETCH_OBSERVATIONS`: Polls the bound job report (`RUNNING`, `COMPLETED`, `CANCELLED`, `EXPIRED`).
- After 256 challenges in one session only `START_CHALLENGE` answers `ERROR`; the desktop then ends the session (`SESSION_EXPIRED`). A stale `FETCH`/`CANCEL` answers `UNAVAILABLE`.

### Diagnostic Categories
1. **Battery** (`AUTOMATIC`): Voltage, temperature, status, level, health enums. API 34+ cycle count.
2. **System** (`AUTOMATIC`): MemoryInfo (available/total RAM, low memory) and PowerManager thermal status (API 29+).
3. **Storage** (`AUTOMATIC`): App-private cache 64 KiB write, `getFD().sync()`, file close and reopen, byte-for-byte readback, and immediate deletion. Self-check only; physical filesystem cache eviction cannot be guaranteed by Android user-space APIs. Does not claim flash media durability or health.
4. **Display** (`AUTOMATIC`): Resolution, display modes, refresh rates, screen brightness.
5. **Connectivity** (`AUTOMATIC`): Declared system features (`feature_wifi`, `feature_bluetooth`, etc.), Wi-Fi/NFC enabled state.
6. **Audio Routes** (`AUTOMATIC`): Discovered input/output device types via `AudioManager.getDevices`.
7. **Sensors** (`AUTOMATIC`, `sensor_0`..`sensor_63`): Discovered sensors sampled for up to 3 seconds. Permission-free metadata (type, range, resolution, reporting mode); no vendor or name strings. Malformed, non-finite or beyond-2^53 samples are excluded and counted (`rejected_samples`).
8. **Camera** (`AUTOMATIC`, `camera_0`..`camera_15`): Ephemeral single YUV frame capture measuring dimensions, payload bytes, timestamp match, luma mean, and luma variance; PASS needs a matching timestamp and a non-empty luma plane. Permission-free metadata enumeration.
9. **Touch** (`ASSISTED`): 4x6 interactive grid tracking cell completion and simultaneous contacts, with grid, app-window and physical-display sizes. PASS needs all 24 cells on a grid covering at least 75% of the physical display; app-window coverage alone never qualifies.
10. **Pixels** (`ASSISTED`): Fullscreen 5-color cycle (Black, White, Red, Green, Blue) for human visual defect inspection.
11. **Speaker** (`ASSISTED`): 440 Hz tone via `AudioTrack` followed by user audibility confirmation.
12. **Microphone** (`ASSISTED`): AudioRecord non-blocking level sampling with the measured input level shown live, then the person confirms whether that level rose when they made a sound.
13. **Vibration** (`ASSISTED`): 300 ms pulse via `Vibrator` followed by user confirmation.

## Privacy and Consent Controls

- **Window Security**: `FLAG_SECURE` blocks screenshots, screen recording, non-secure display mirroring and task-switcher previews (it does not stop accessibility services from reading on-screen text).
- **Touch Filtering**: `filterTouchesWhenObscured` blocks tapjacking and overlay attacks.
- **Zero Content Persistence**:
  - Camera frames are analyzed in memory and immediately discarded; zero image bytes are stored or transmitted.
  - Audio buffers are zeroed in memory; zero audio recordings are stored or transmitted.
  - Storage creates a temporary 64 KiB file that is deleted upon completion, error, cancellation, or timeout; a failed deletion is reported as `CLEANUP_ERROR`.
- **Consent Disclosure**: The consent text lists the derived numeric results that are sent to the computer and states that leaving the screen ends the session.
  - No device identifiers (IMEI, MAC, serial, SSID, GPS) are read or transmitted.
- **Active Diagnostic Notification**: `ProbeActivity` displays the currently active diagnostic while running, preventing silent background execution.

## Build and Verification

Use JDK 17, Gradle **8.11.1**, Android SDK platform **35**, and Build Tools **35.0.0**.
Pinned dependencies: AGP 8.9.2, Gson 2.11.0, JUnit 4.13.2, Robolectric 4.16.

```powershell
gradle :app:testDebugUnitTest :app:lintDebug :app:compileDebugJavaWithJavac :app:assembleDebug
```

The unit tests include the cross-language contract (`DiagnosticCrossLanguageExportTest`), which only
reads `local-agent/tests/fixtures/cross_language/`. After an approved protocol change, regenerate the
Python requests first (`uv run python -m tests.cross_language_contract --write-requests` in
`local-agent`), then the Java responses with `gradle testDebugUnitTest -Pvector.updateCrossLanguageFixtures=true`,
and review the fixture diff.

## Enrollment and Trust Boundary

1. Build and inspect `app/build/outputs/apk/debug/app-debug.apk`.
2. Compute the APK SHA-256 and verify the certificate fingerprint against trusted local tooling.
3. Enroll the artifact in the desktop trust store:
   ```powershell
   uv run python -m vector_agent.probe.trust_build --sdk-root <SDK-directory> --java <JDK-java.exe> --expected-signer 865ccb6a14342e0ff166b9082d94d145ab7c828b17c1a75b95cd0fc03ce8eafb
   ```
4. The Probe is signed with the Android debug key and intended exclusively for development and qualification environments. Production pairing and cryptographic enrollment are future roadmap items.

## Physical Qualification Status

**PHYSICAL HARDWARE QUALIFICATION: NOT RUN.**
All automated verifications are JVM, Robolectric, or loopback-based (`CODE_TESTED`). Handset HAL behaviors and real OEM hardware paths require on-device qualification before production deployment.
