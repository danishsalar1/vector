# Phase 8C Real-Device Validation Guide and Operational Reference

## Hardware Qualification Status: NOT RUN

Physical smartphone hardware qualification remains explicitly **NOT RUN** for Phase 8C.
All automated verification is JVM, Robolectric (API 26 and API 35), loopback socket and cross-language fixture based.
All physical diagnostic capabilities remain categorized as **`CODE_TESTED`**; never claim or record **`HARDWARE_VALIDATED`** without physical qualification on real devices with explicit on-screen consent.

---

## 1. Diagnostic Inventory and Automation Levels

VECTOR Phase 8C introduces 13 functional categories exposed over the authenticated Probe protocol v2:

| Diagnostic ID | Category | Automation Level | Public APIs / Subsystems | Output Outcomes |
|---|---|---|---|---|
| `battery` | Battery / Power | `AUTOMATIC` | `ACTION_BATTERY_CHANGED`, `BatteryManager` properties (21), `EXTRA_CYCLE_COUNT` (34) | `INCONCLUSIVE` (telemetry only) |
| `system` | SoC / Memory | `AUTOMATIC` | `ActivityManager.getMemoryInfo`, `PowerManager.getCurrentThermalStatus` (29) | `INCONCLUSIVE` (telemetry only) |
| `storage` | App-Private Storage | `AUTOMATIC` | `StatFs`, app-private cache 64KiB write/sync/close/reopen/readback | `PASS` / `FAIL` / `ERROR` / `INCONCLUSIVE` |
| `display` | Screen Properties | `AUTOMATIC` | `Display.getMode`, `Display.getSupportedModes`, `Settings.System.SCREEN_BRIGHTNESS` | `INCONCLUSIVE` (telemetry only) |
| `connectivity` | Radios / Ports | `AUTOMATIC` | `PackageManager` named features (`feature_wifi`, `feature_bluetooth`, etc.), `WifiManager.isWifiEnabled`, `NfcAdapter.isEnabled` | `INCONCLUSIVE` (capability only) |
| `audio_routes` | Audio Topology | `AUTOMATIC` | `AudioManager.getDevices(GET_DEVICES_INPUTS \| GET_DEVICES_OUTPUTS)` | `INCONCLUSIVE` (capability only) |
| `sensor_<N>` | Sensors (0..63) | `AUTOMATIC` | `SensorManager.getSensorList`, `SensorEventListener` (3-second window) | `INCONCLUSIVE` (samples or no samples) / `UNSUPPORTED` / `RESTRICTED` |
| `camera_<N>` | Cameras (0..15) | `AUTOMATIC` | `CameraManager`, `CameraCharacteristics`, `CameraDevice`, `ImageReader` (YUV_420_888) | `PASS` / `INCONCLUSIVE` / `RESTRICTED` / `UNSUPPORTED` / `ERROR` |
| `touch` | Digitizer | `ASSISTED` | `MotionEvent` on an interactive 4x6 grid; grid, app-window and physical-display geometry; pointer tracking | `PASS` (all 24 cells on a grid covering >=75% of the physical display) / `INCONCLUSIVE` (partial) |
| `pixels` | Display Uniformity| `ASSISTED` | Fullscreen 5-color cycle (Black, White, Red, Green, Blue), brightness toggle | `INCONCLUSIVE` (human-reported) |
| `speaker` | Speaker Output | `ASSISTED` | `AudioTrack` 440Hz sine wave (1.1s), per-diagnostic confirmation prompt | `INCONCLUSIVE` (human-reported) |
| `microphone` | Microphone Input| `ASSISTED` | `AudioRecord` non-blocking PCM read (3s, peak/RMS), measured live input level, per-diagnostic confirmation prompt | `INCONCLUSIVE` (human-reported) / `RESTRICTED` / `ERROR` |
| `vibration` | Haptic Actuator | `ASSISTED` | `Vibrator.vibrate(VibrationEffect.createOneShot(300, ...))`, per-diagnostic confirmation prompt | `INCONCLUSIVE` (human-reported) / `UNSUPPORTED` |

---

## 2. Automated vs. Interactive Execution Workflows

### Automatic Diagnostics
1. Initiated over protocol v2 via `START_CHALLENGE` with challenge binding.
2. The probe activity updates its status message while running non-blocking collection on the main looper or background worker.
3. Polling via `FETCH_OBSERVATIONS` returns state `RUNNING` until completion, cancellation, or deadline (max 60 seconds).
4. Automatic tests release all allocated listeners, camera devices, image readers, and file descriptors on completion or cancellation; a release failure is reported as `ERROR/CLEANUP_ERROR`.

### Interactive Diagnostics
1. Initiated via `START_CHALLENGE` with challenge binding.
2. The Android companion displays dedicated, purpose-built foreground UI in `ProbeActivity`:
   - **Touch**: A fullscreen dialog displaying a 4x6 grid of 24 cells across the grid view. The user touches/swipes across cells and optionally applies multi-finger touches. Completed cells turn green. The report records `touch_cells`, `cell_coverage_percent`, `max_contacts`, the grid (`tested_width`/`tested_height`), the app window hosting it (`window_width`/`window_height`), the physical display (`display_width`/`display_height`), `tested_window_area_percent`, `tested_display_area_percent` and `layout_generation`. The user taps "Finish with current coverage" or "Cancel diagnostic".
   - **Pixels**: A fullscreen dialog cycles through 5 primary colors (Black, White, Red, Green, Blue) with an in-app brightness toggle button. The user inspects the panel for dead or stuck subpixels and taps "Next color".
   - **Microphone**: during the 3-second sampling window the status shows the measured input level ("Make a sound near the microphone now. Measured input level: N%."), driven by the collected samples.
   - **Speaker / Microphone / Vibration / Pixels**: each ends with a diagnostic-specific question and answer labels, plus "Unsure". Polarity is uniform: `user_report = 1` means the person observed the expected behavior, `user_report = 0` means they reported a problem; "Unsure" records no report (`INCONCLUSIVE/USER_UNCERTAIN`).

     | Diagnostic | Question | `user_report = 1` | `user_report = 0` |
     |---|---|---|---|
     | `speaker` | Did you clearly hear the test tone from the speaker? | Yes, I heard the tone | No, I did not hear it |
     | `microphone` | Did the measured input level rise when you made a sound? | Yes, the level rose | No, the level did not rise |
     | `vibration` | Did you feel the phone vibrate during the test? | Yes, I felt it | No, I did not feel it |
     | `pixels` | Did all displayed colors look normal, without visible dead, stuck or discolored pixels? | Yes, all colors looked normal | No, I saw a defect |
3. Human input is transmitted strictly as structured evidence (`user_report`, `source_type=USER_ASSISTED`) and never creates a hardware PASS or FAIL.

---

## 3. Protocol Changes (v1 -> v2)

- **Version Header**: `protocol_version` bumped from `1` to `2`.
- **Supported Operations**:
  - v1 allowed: `HELLO`, `GET_CAPABILITIES`, `HEARTBEAT`.
  - v2 adds: `START_CHALLENGE`, `CANCEL_CHALLENGE`, `FETCH_OBSERVATIONS`.
- **Capability Discovery**:
  - `GET_CAPABILITIES` response includes `diagnostic_capabilities` array enumerating discovered diagnostics, interaction requirements (`interactive: bool`), and optional metadata (`sensor_type`, `reporting_mode`, `max_range`, `resolution`, camera facing, hardware level, flash, AF). An absent default sensor is reported unavailable with the probed `sensor_type` and null metadata.
- **Payload Envelopes**:
  - `START_CHALLENGE`: includes `binding` with `scan_id`, `diagnostic_id`, `attempt_id`, `challenge_id`, and `collection_not_before`.
  - `FETCH_OBSERVATIONS` / `CANCEL_CHALLENGE`: matches existing active binding.
  - Response carries `diagnostic`: structured `DiagnosticReport` with state, outcome, reason, elapsed milliseconds, and bounded metrics.
- **Cancellation**: `CANCEL_CHALLENGE` stops collection immediately and normally answers `RUNNING/INCONCLUSIVE/STOPPING` with frozen evidence; the device then releases resources on its main thread and a later `FETCH_OBSERVATIONS` returns `CANCELLED/INCONCLUSIVE/CANCELLED`, or `CANCELLED/ERROR/CLEANUP_ERROR` if a resource could not be released. Timeouts end the same way as `EXPIRED`. The desktop rejects any report that resumes collection or changes evidence after `STOPPING`.
- **Session Preservation on Benign UNAVAILABLE**:
  - If the device cannot accept a command now (cleanup in progress, unknown or stale binding), it returns `UNAVAILABLE`. The desktop maps this to `DiagnosticUnavailableError` without dropping the authenticated session (`CONNECTED` is preserved).
- **Challenge Budget**: a Probe session accepts at most 256 challenges. Once spent, only `START_CHALLENGE` answers `ERROR`; the desktop raises `DiagnosticExhaustedError` and ends the session as `DISCONNECTED/SESSION_EXPIRED`, so a new connection with fresh on-device consent is required. `ERROR` for `FETCH`/`CANCEL` is a protocol violation (`INVALID_RESPONSE`).
- **Desktop exception contract**: `DiagnosticUnavailableError` is retryable (session kept). Every session-ending failure raises a `DiagnosticSessionError` whose `reason` equals the recorded drop reason (`DiagnosticTransportError` and `DiagnosticExhaustedError` are subclasses); transport failures use the same reasons as control exchanges (for example `TIMEOUT`, `DEVICE_UNAVAILABLE`, `SESSION_EXPIRED`, `CANCELLED`, `AUTHENTICATION_FAILED`). Plain `ValueError` is caller misuse rejected before any I/O.
- **Backward Compatibility**:
  - A v1 desktop peer connecting to a v1 Probe artifact retains v1 strict contracts (`supported_operations = ["HELLO", "GET_CAPABILITIES", "HEARTBEAT"]`, zero diagnostic fields allowed in envelopes).
  - A v2 desktop peer enforces v2 protocol with enrolled v2 Probe artifact (`0.2.0`, `versionCode=2`).

---

## 4. Evidence and Result Semantics

VECTOR strictly enforces honest evidence semantics across all layers:
- **Certainty Never Exceeds Evidence**: Hardware presence alone NEVER constitutes a functional PASS.
- **Restricted != Failed**: Missing runtime permissions or disabled subsystems produce `RESTRICTED` (with reason `PERMISSION_REQUIRED` or `PERMISSION_DENIED`), never `FAIL`.
- **Unsupported != Failed**: Hardware absence, missing OEM properties, or unavailable OS APIs produce `UNSUPPORTED`, never `FAIL`.
- **Error != Failed**: Subsystem initialization errors, cleanup failures or exceptions produce `ERROR`; timeouts produce `INCONCLUSIVE`; neither is ever `FAIL`.
- **Telemetry / Human Report != Hardware PASS**:
  - Battery metrics and system telemetry produce `INCONCLUSIVE (TELEMETRY_ONLY)`.
  - User confirmations produce `INCONCLUSIVE (USER_REPORTED)`. Desktop predicates reject any manufactured PASS from human buttons.
- **Missing values are labelled, never zero**: a null metric is labelled `NOT_YET_MEASURED` (still running), `INTERRUPTED_BEFORE_MEASUREMENT` (cancelled/expired), `NO_SAMPLES_OBSERVED` (no valid sensor or audio sample) or `UNSUPPORTED_MEASUREMENT` (the device or OS did not report it).
- **Sensor samples**: samples that are malformed, non-finite or beyond the desktop numeric contract (|value| > 2^53) are excluded from the statistics and counted in `rejected_samples`; they never invalidate the whole report.
- **Bounded Predicates**:
  - `storage`: `PASS` requires exactly 65,536 bytes written, `getFD().sync()` flush, close, reopen, and exact 65,536 bytes read back with bitwise match (`READBACK_MATCH`). Any mismatch produces `FAIL (READBACK_MISMATCH)`. A temporary file that cannot be deleted produces `ERROR (CLEANUP_ERROR)`. This is strictly an app-private filesystem I/O self-check; physical filesystem cache eviction cannot be guaranteed by Android user-space APIs. It does NOT claim flash media durability, endurance, or block health.
  - `touch`: `PASS (TOUCH_COVERED)` requires `touch_cells == 24`, `cell_coverage_percent == 100`, `max_contacts >= 1`, `layout_generation >= 1`, all six width/height metrics present and positive, a grid of at least 200x200 px, grid <= app window <= physical display on each axis, `tested_window_area_percent` and `tested_display_area_percent` equal to the round-half-up recomputation from those dimensions, and `tested_display_area_percent >= 75`. Coverage of the app window alone (for example split-screen) never stands in for touchscreen coverage. Strips outside the grid (system bars, cutouts) are not tested; the exact share is reported. Partial, tiny or unmeasured coverage produces `INCONCLUSIVE (PARTIAL)`. The 75% threshold is a code policy that still needs hardware calibration.
  - `camera_<N>`: `PASS (CAPTURE_MATCH)` requires a completed capture (`capture_completed == 1`), a sensor timestamp equal to the frame timestamp (`frame_metadata_match == 1`), positive `frame_width`, `frame_height` and `frame_bytes`, and recorded `luma_mean` and `luma_variance` (a valid frame needs a non-empty luma plane). Brightness statistics are observational telemetry; no uncalibrated lighting or image-quality threshold is applied.
- **No Authenticity or Provenance Inference**: Successful function never implies OEM/genuine. All evidence records carry `authenticity: UNKNOWN` and `qualification: CODE_TESTED`.

---

## 5. Privacy, Permission, and Usability Controls

1. **Window Security**: `ProbeActivity` and fullscreen interaction dialogs set `FLAG_SECURE`, which blocks screenshots, screen recording, non-secure display mirroring and task-switcher previews. It does not stop accessibility services from reading on-screen text.
2. **Overlay Filtering**: All buttons and custom views enforce `setFilterTouchesWhenObscured(true)` and check `MotionEvent.FLAG_WINDOW_IS_OBSCURED` to block tapjacking.
3. **Pre-Session Permission Preparation**:
   - The idle Probe screen provides user-initiated buttons to prepare Camera, Microphone, and Activity Recognition permissions before initiating connection consent.
   - Current status is displayed (`Granted`, `Not requested`, `Denied (can request again)`, or `Denied / Settings required`).
   - Only a permission that was requested before and is now denied without a rationale (Android's "Don't ask again" state) shows "Open Settings" (pre-session) or "Open App Settings" (during a session), which open `Settings.ACTION_APPLICATION_DETAILS_SETTINGS`. A permission that was never requested never shows a Settings button.
4. **Consent disclosure**: the consent text (scrollable on small screens) states that camera frames and audio samples stay on the phone, lists the derived numeric results that are sent (audio level RMS/peak, camera frame size and luma statistics, sensor statistics, touch coverage and screen size, battery and system telemetry, on-screen answers), and states that leaving the screen, locking the phone or opening a permission dialog ends the session.
5. **No Audio Persistence**: `AudioRecord` PCM buffers are read in non-blocking slices, aggregated to sample count, peak, and RMS, and immediately zeroed out in memory via `Arrays.fill(buffer, (short) 0)`. Zero audio is stored or transmitted.
6. **No Image Persistence**: `CameraCollector` acquires ephemeral YUV frames to measure plane byte length, timestamp, and luma statistics, then closes the `Image` immediately. Zero pixel buffers escape to storage or the wire.
7. **No Private Identifiers**: No MAC addresses, Wi-Fi SSIDs, BSSIDs, IMEI numbers, IMSI numbers, GPS coordinates, or USB serial numbers are read or transmitted.
8. **Ephemeral Storage File**: `StorageCollector` writes a single temporary file (`vector-io-*.tmp`) in app-private cache, synchronizes, closes, reopens, reads back, and deletes it on completion, cancellation, and error paths; a failed deletion is reported as `CLEANUP_ERROR`.
9. **Permission Dialog Session Boundary**: If a runtime permission dialog is triggered while a session is active, the OS dialog causes the activity to pause. In accordance with Phase 8B fail-closed consent rules, `onPause` revokes the session. Pre-session preparation eliminates this disruption for normal workflows.

---

## 6. Supported and Restricted Capabilities Across Android API Levels

- **API Floor**: MinSdk is 26 (Android 8.0 Oreo).
- **Target SDK**: TargetSdk is 35 (Android 15), CompileSdk is 35.
- **Cycle Count**: Supported on API >= 34 (`BatteryManager.EXTRA_CYCLE_COUNT`). On API < 34 or when OEM extra is absent, reported as `null` / `UNSUPPORTED`.
- **Thermal Status**: Supported on API >= 29 (`PowerManager.getCurrentThermalStatus`). On API < 29, reported as `null` / `UNSUPPORTED`.
- **Step Recognition**: Guarded by runtime permission `ACTIVITY_RECOGNITION` on API >= 29.
- **Audio Routing**: Uses `AudioManager.getDevices` (API 23+), compatible across all supported versions.
- **Display size for touch**: `WindowManager.getMaximumWindowMetrics` on API >= 30, `Display.getRealSize` below.

---

## 7. Developer Result-Inspection Instructions

To manually run and inspect diagnostics on a test device:

### Step 1: Build and Enroll Debug APK
```powershell
# From repository root:
cd android-probe
gradle --no-daemon assembleDebug

# Enroll newly built APK in local agent trust store:
cd ..\local-agent
uv run python -m vector_agent.probe.trust_build `
    --sdk-root "C:\Users\danis\AppData\Local\Android\Sdk" `
    --java "C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot\bin\java.exe" `
    --expected-signer 865ccb6a14342e0ff166b9082d94d145ab7c828b17c1a75b95cd0fc03ce8eafb
```

### Step 2: Install APK on Test Device
```powershell
adb install -r android-probe\app\build\outputs\apk\debug\app-debug.apk
```

### Step 3: Launch Developer Console
```powershell
cd local-agent
uv run python -m vector_agent.probe.developer --live
```

### Step 4: Interactive Console Commands
```text
vector> devices
[{"device_id": "android-...", "state": "CONNECTED"}]

vector> select android-...
Device selected. Launch and approve on-device consent explicitly.

vector> discover
{"availability": "INSTALLED_COMPATIBLE", "installed": true, ...}

vector> launch
{"availability": "CONSENT_REQUIRED", "consent_required": true, ...}

# (On test phone screen, tap "Allow connection")

vector> connect
{"availability": "CONNECTED", "transport_connected": true, ...}

vector> capabilities
[{"diagnostic_id": "battery", "available": true, "interactive": false, ...}, ...]

vector> start battery
{"diagnostic_id": "battery", "status": "RUNNING", ...}

vector> poll
{"diagnostic_id": "battery", "status": "INCONCLUSIVE", "summary": "TELEMETRY_ONLY. ...", "evidence": [...]}

vector> start touch
{"diagnostic_id": "touch", "status": "RUNNING", ...}

# (Complete the 4x6 touch grid on phone screen, tap "Finish with current coverage")

vector> poll
{"diagnostic_id": "touch", "status": "PASS", "summary": "TOUCH_COVERED. ...", "evidence": [...]}

vector> start storage
vector> cancel
{"diagnostic_id": "storage", "status": "RUNNING", "summary": "STOPPING. ...", ...}

vector> poll
{"diagnostic_id": "storage", "status": "INCONCLUSIVE", "summary": "CANCELLED. ...", ...}

vector> stop
{"availability": "DISCONNECTED", "reason": "STOPPED", ...}

vector> quit
```
A retryable device answer prints "Diagnostic busy or cleaning up on the device; the session is still connected. Retry." A session-ending failure prints "Probe session ended (REASON). Reconnect with fresh on-device consent." Neither exits the console.

---

## 8. Cross-Language Contract Fixtures

`local-agent/tests/fixtures/cross_language/contract.json` specifies the Java<->Python scenarios.
`python_requests.json` holds the production Python session's framed requests and
`java_responses.json` the framed responses of the real Android controller, collectors and
`ControlProtocol` (Robolectric API 35). The 17 older `wire_*.bin` / `capabilities_*.json` files are
byte-exact extracts of those transcripts. Ordinary test runs only read and compare them. After an
approved protocol change, regenerate explicitly, review the diff, and rerun both suites:

```powershell
cd local-agent
uv run python -m tests.cross_language_contract --write-requests
cd ..\android-probe
gradle testDebugUnitTest -Pvector.updateCrossLanguageFixtures=true
```

---

## 9. Known Limitations and Technical Debt

1. **Hardware Qualification NOT RUN**: Automated tests are executed via JVM, Robolectric (API 26/35) and synthetic socket fixtures. Physical hardware smoke tests remain NOT RUN.
2. **Camera HAL delivery simulated**: Robolectric runs the real Camera2 open/session/capture calls (API 35 only) but cannot deliver frames or capture results; those enter at the `CameraCollector` event methods. Real HAL behaviour, including `Image.getPlanes()`, is untested.
3. **Touch thresholds uncalibrated**: the 200 px minimum and 75% display-coverage threshold are code policy; Robolectric's grid, window and display are the same size, so real split-screen, freeform and cutout geometry is untested.
4. **Permission Revocation on Active Pause**: Requesting a runtime permission while connected prompts an OS dialog that triggers `onPause`, terminating the active session. The idle pre-connection setup flow should be used instead.
5. **Inherited Phase 8B Debt**:
   - `FG-01`: Unbounded per-device lock registry (remediation target: PRE-8F).
   - `FG-02`: Cancellation and timeout reason fidelity in transport (remediation target: PRE-8F).
   - `FG-06`: Same-device GET/state query lock waits (remediation target: PRE-8F).
6. **OEM Custom Sensor Formats**: Non-standard proprietary OEM sensor types beyond Android public standard sensor list are enumerated but not sampled, reporting `UNSUPPORTED (SAMPLING_UNSUPPORTED)`.
