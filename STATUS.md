# VECTOR STATUS.md

**Purpose:** This file allows any new agent or developer to continue work without reading the entire conversation history.

---

## Project

**VECTOR** â€“ Verified Evidence-Based Computational Trust for Ownership Review  
Standardized diagnostics and verification for the second-hand smartphone market.

Hackathon challenge: Advanced Computational Intelligence â€” Hybrid Evolutionary-Fuzzy Frameworks (CIS track)

---

## Current Phase

Canonical Phase 5 — Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events
Status: VERIFIED and committed
Baseline before Phase 5: 0a27a80
Last committed green SHA before this phase: 0a27a80
Phase 5 implementation commit: 1d168e8

### Canonical Production Roadmap
1. Foundation / Production Audit — COMPLETE
2. Diagnostic Protocol + Battery Migration — COMPLETE
3. DeviceSession + Platform-Neutral Device API — COMPLETE
4. Capability Foundation + Runtime Discovery — COMPLETE
5. Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events — COMPLETE
6. Additional Android Standard Diagnostics — NEXT (NOT STARTED)
7. iOS Discovery / Pairing + Basic iOS Diagnostics — NOT STARTED
8. VECTOR Probe + Deep Android Diagnostics — NOT STARTED
9. Cross-Platform Evidence Normalization + Verification Coverage — NOT STARTED
10. Real Sugeno Trust Engine — NOT STARTED
11. Benchmarks + NSGA-II + Perturbation Validation — NOT STARTED
12. Reporting — NOT STARTED
13. Production UX + Diagnostic Visualization / Motion — NOT STARTED
14. Windows Packaging — NOT STARTED
15. Security / Privacy + Compatibility Validation — NOT STARTED
16. Pilot + Release Candidate — NOT STARTED

### Verified Implementation Completed
- production DiagnosticDefinition extension: added platform-neutral required verification_level, requires_probe, and prerequisites to DiagnosticDefinition while maintaining backward compatibility with all existing definitions
- thread-safe DiagnosticRegistry: synchronized with threading.RLock, added typed definition lookups (get_definitions, get_definitions_by_platform, get_definitions_by_category), test-isolation clear(), and create_default_registry() factory
- platform-neutral scan request modes: supported FULL_VERIFICATION, CATEGORY_VERIFICATION, SELECTED_DIAGNOSTICS, and SINGLE_COMPONENT via ScanMode enum and hardened ScanRequest (extra fields forbidden, duplicate IDs rejected, invalid mode combos rejected)
- truthful ScanPlanner: derives executable plan from DeviceSession, DeviceCapabilityProfile, DiagnosticRegistry, platform, connection state, and prerequisites
- truthful applicability classification: categorizes diagnostics as APPLICABLE, NOT_APPLICABLE, UNSUPPORTED, RESTRICTED, UNAVAILABLE, BLOCKED_BY_PREREQUISITE, or UNKNOWN without inventing status systems
- capability dependency semantics: missing, uninspected, or unsupported capabilities skip diagnostics with explicit reasons; missing capability NEVER creates a diagnostic FAIL
- actually immutable ScanPlan: frozen Pydantic model using immutable tuples for sequences, frozen planned items, dynamically computed skip_reasons dict, and planning_session_epoch
- privacy boundary: raw serial numbers completely excluded from ScanPlan, ScanSession, DiagnosticEvent, and API responses
- formal ScanLifecycleState state machine: CREATED -> PLANNED -> RUNNING -> COMPLETED with explicit terminal failure (FAILED) and cancellation (CANCELLED) paths; invalid transitions rejected with InvalidLifecycleTransitionError
- lifecycle torn read prevention: timestamps and errors assigned before state publication; state assignment occurs last
- structured DiagnosticEvent stream: internal event taxonomy (scan.started, diagnostic.started, diagnostic.progress, diagnostic.evidence, diagnostic.completed, diagnostic.failed, diagnostic.inconclusive, scan.completed, scan.failed) carrying normalized safe payloads
- fixed diagnostic event semantics: PASS, FAIL, DEGRADED, UNSUPPORTED, RESTRICTED, SKIPPED map to diagnostic.completed; execution/infrastructure exceptions and crashes map to diagnostic.failed with status ERROR; inconclusive maps to diagnostic.inconclusive; unhandled statuses raise explicit error rather than silent fallthrough
- NO fake progress guarantee: progress metadata remains None unless intermediate progress is truthfully measurable; no timers, fake delays, or simulated percentages
- sequential execution orchestration: ScanOrchestrator drives Plan -> Start -> Diagnostic execution -> Evidence -> Result -> Events -> Finish outside the global session manager lock
- every PASS requires evidence: orchestrated enforcement converting evidence-less PASS/DEGRADED and non-terminal PENDING/RUNNING to ERROR / execution contract violation; measured hardware FAIL and INCONCLUSIVE preserved
- per-device scan exclusivity: ScanService under lock enforces one active scan per device; concurrent start attempts on the same device return HTTP 409 Conflict; different devices run concurrently; terminal scans unblock subsequent scans
- repeated start guard: run_scan requires session to be PLANNED before starting execution; non-PLANNED invocations are rejected immediately without mutating existing state (does not convert RUNNING -> FAILED)
- worker crash guard: ScanService execution wrapper catches unexpected worker/orchestrator exceptions, transitions session to FAILED with safe message, emits scan.failed once, prevents dangling RUNNING scans in both sync and async paths
- plan-time session epoch protection: ScanPlan records planning_session_epoch; disconnect/reconnect between planning and execution refuses execution as stale plan / device state changed; pre-diagnostic disconnect invokes 0 diagnostics
- execution failure separation: subprocess crashes or unhandled execution exceptions map to DiagnosticStatus.ERROR, not fabricated hardware FAIL
- safe battery error boundary: fixed safe error summary prevents leaking internal exception strings, ADB paths, command lines, or stderr
- battery telemetry semantics preserved: battery diagnostic PASS confirms valid telemetry was collected, not battery health; trust score remains None and Trust Engine remains NOT_READY
- safe plan visibility in ScanSummary: tightened public types with state as ScanLifecycleState, plan as ScanPlan | None (no Any), scan_id as consistent str; solves circular import without weakening types; frontend guards strengthened
- platform-neutral scan API: POST /api/v1/scans/plan, POST /api/v1/scans (supporting async and sync execution), GET /api/v1/scans/{scan_id}, GET /api/v1/scans/{scan_id}/results, and GET /api/v1/scans/{scan_id}/events (JSON polling)
- frontend TypeScript contract: added complete scan types (ScanMode, DiagnosticApplicability, PlannedDiagnostic, ScanPlan, ScanLifecycleState, DiagnosticEventType, DiagnosticEvent, ScanSummary), type guards, and client API helper functions in frontend/src/lib/api/scans.ts

### Verification Results
- Focused Phase 5 tests: 57 passed (test_phase5_scan_orchestration.py)
- Full local-agent: 252 passed across 12 test files
- Intelligence: 21 passed
- Frontend: 90 passed across 9 test files
- scripts/verify.ps1: 15/15 PASS
- git diff --check: PASS
- Hardware smoke test: NOT RUN
- Hardware note: Phase 5 automated verification is fixture-based; no authorized real Android phone was available in this environment. Recorded: 'Phase 5 hardware smoke test NOT RUN.'

### Intentionally Deferred
- expanded Android standard diagnostics (camera deep test, sensors deep test, storage, connectivity)
- VECTOR Probe companion application
- iOS bridge, discovery, and pairing
- Trust Engine live integration (TrustEngineStatus remains NOT_READY)
- functional coverage scoring and final reporting
- final scan UX, animations, and progress UI
- packaging and cloud backend

### Permanent Guarantees / Do Not Redo
- stale-device safety and session epoch validation
- opaque device IDs (never raw serial)
- raw serial privacy boundary (never in plans, events, logs, or API)
- no silent false confidence (every PASS requires evidence)
- LIVE never silently falls back to DEMO
- Level 1 != Level 2 != Level 3
- battery telemetry PASS means telemetry collected, not battery health
- Trust Engine remains NOT_READY (trust_score is None)
- no fake progress (no timers, no simulated percentage)

### Next Phase
Phase 6 — Additional Android Standard Diagnostics (NOT STARTED).


---

## Historical Phase Record — Phase 4: Capability Foundation + Runtime Discovery
Status: VERIFIED and committed
Baseline before Phase 4: 68f3002
Last committed green SHA before this phase: 68f3002
Phase 4 implementation commit: 5f90447
Phase 4 status finalization commit: 0a27a80

### Verified Implementation Completed
- platform-neutral capability contracts: DeviceCapabilityProfile, CapabilityEntry, CapabilityEvidenceRecord, CapabilityStatus, VerificationLevel, PlatformCapabilityNamespace
- Android Level 1 runtime capability discovery via AndroidDeviceBridge.discover_capabilities() parsing pm list features
- PRESENT / NOT_REPORTED / UNKNOWN truth semantics: positive matches are PRESENT, features unlisted in complete output are NOT_REPORTED, uninspected/incomplete features remain UNKNOWN
- no fabricated battery capability: removed synthetic standard_battery_subsystem inspection; battery remains UNKNOWN until real hardware telemetry is collected
- evidence/provenance-backed runtime declarations: PRESENT capabilities carry Level 1 runtime-declaration evidence; NOT_REPORTED and UNKNOWN entries do not fabricate per-entry evidence
- truncated/incomplete output uncertainty handling: incomplete command output marks missing capabilities as UNKNOWN with verification_level=None and no fabricated evidence
- truncated final-line protection: when subprocess output is flagged truncated, the final potentially partial line is discarded before parsing so a cut feature name cannot create false PRESENT
- DeviceSession capability snapshot integration: DeviceSession stores the capability_profile and exposes it through to_connected_device() only while the session is CONNECTED; offline/unauthorized states mask stale capability knowledge
- reconnect and explicit refresh behavior: rediscovery refreshes stale capabilities; refresh=true query parameter forces explicit refresh via DeviceSessionManager.refresh_device_capabilities()
- 30-second bounded retry for incomplete/failed automatic discovery: prevents rapid repeated ADB discovery storms on failing devices
- session epoch / stale-result protection: apply-guard verifies session state before updating, preventing stale asynchronous discovery results from overwriting reconnected sessions
- capability endpoint reconciles physical connection state before returning cached data: GET /api/v1/devices/{device_id}/capabilities verifies connection state first, transitioning disconnected devices to OFFLINE and returning 400
- blocking ADB work moved off FastAPI event loop: run_in_threadpool offloads discovery and capability execution from the event loop
- slow ADB work outside manager-wide lock: subprocess execution runs outside the DeviceSessionManager lock, preventing discovery stalls from blocking concurrent session lookups
- safe raw-serial handling/redaction: raw serial numbers never leak through error messages, validation exceptions, discovery logs, or API responses; validation formatting uses opaque device IDs
- safe 503 discovery error boundary: GET /api/v1/devices and GET /api/v1/devices/{device_id}/capabilities return fixed 'Device discovery failed.' detail with safe exception type logging and suppressed exception chaining (from None)
- platform-neutral frontend TypeScript contract: added complete capability types, type guards, and namespaces in frontend/src/lib/api/types.ts
- unknown compatible Android models work without catalog dependency: runtime discovery functions generically without model catalog or device reference requirements

### Verification Results
- Focused Phase 4 tests: 73 passed (test_capabilities + test_api + test_security)
- Full local-agent: 193 passed
- Intelligence: 21 passed
- Frontend: 83 passed across 8 files
- scripts/verify.ps1: 15/15 PASS
- git diff --check: PASS
- Hardware smoke test: NOT RUN
- Hardware note: Phase 4 automated verification is fixture-based and no new real Android hardware regression was run during this phase. Real Android hardware was validated previously in the project and remains part of the project verification baseline.

### Intentionally Deferred
- ScanPlanner
- scan lifecycle/orchestration
- DiagnosticEvent stream
- broader Android Standard Diagnostics
- iOS discovery/pairing
- VECTOR Probe
- Trust Engine live integration
- reporting
- final product UX/motion
- packaging

### Permanent Guarantees / Do Not Redo
- stale-device safety
- opaque device IDs
- raw serial privacy boundary
- no silent false confidence
- LIVE never silently falls back to DEMO
- Level 1 != Level 2 != Level 3
- battery telemetry PASS means telemetry collected, not battery health
- Trust Engine remains NOT_READY

### Next Phase
Phase 5 — Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events (NOT STARTED).

---

## Historical Phase Record — Phase 2: DeviceSession + Platform-Neutral Device API Foundation
Status: VERIFIED and committed.
Phase 2 implementation commit: 6e66cf9

### Baseline
770663c

### Implementation Completed
- platform-neutral DeviceSession model
- DeviceSessionManager
- opaque device IDs
- raw ADB serial retained only inside internal DeviceSession
- public ConnectedDevice DTO contains NO raw_serial
- raw serial excluded from repr/serialization
- stale device IDs fail safely and never retarget another phone
- disappeared devices transition OFFLINE
- unauthorized/offline devices cannot execute privileged diagnostics
- canonical platform-neutral:
  GET /api/v1/devices
  GET /api/v1/devices/{device_id}
- frontend LIVE discovery now uses GET /api/v1/devices
- frontend does NOT infer platform from opaque device_id
- frontend does NOT fabricate adb_available or discovered_at
- legacy Android route remains compatibility adapter
- Android battery diagnostic remains available through legacy compatibility path
- discovery failure does not silently return stale CONNECTED sessions
- discovery failure marks affected platform sessions OFFLINE and returns HTTP 503
- capabilities endpoint:
    unknown device -> 404
    known device but capability discovery not implemented -> 501
- capability discovery remains deferred
- iOS remains deferred
- no Live -> Demo silent fallback

### Verification
- Focused backend: 34 passed
- Full local-agent: 148 passed
- Intelligence: 21 passed
- Focused frontend: 28 passed
- Full frontend: 83 passed
- scripts/verify.ps1: 15/15 PASS
- git diff --check: PASS, zero real whitespace errors
- Hardware note: Real Android hardware was validated previously in the project, but this Phase 2 refactor verification was automated. Phase 2 did not receive a new hardware regression run.

### Intentionally Deferred
- capability discovery (runtime capability snapshot, deeper resolution)
- iOS bridge implementation
- ScanPlanner / scan lifecycle orchestration
- DiagnosticEvent streaming
- VECTOR Probe companion app
- additional diagnostics beyond battery
- Trust Intelligence inference on live scans

### Permanent Semantic Notes
- Battery telemetry PASS means sufficient telemetry was collected.
- PASS does not mean battery health is good.
- Battery percentage is not battery health.
- Every PASS requires evidence.
- Trust Engine remains NOT_READY.
- No silent false confidence: stale sessions must never be presented as connected.
- LIVE must never silently fall back to DEMO.

### Next Recommended Phase
Capability Foundation + Runtime Discovery.
Do NOT jump directly to deep diagnostics or intelligence optimization.
The next phase should establish:
- lightweight runtime capability snapshot
- deeper/lazy capability resolution
- refreshable capability state
- capability evidence semantics
iOS remains important and should follow the shared platform-neutral contracts rather than creating Android-specific architecture.

### Do Not Redo
Preserve:
- Phase 1 Diagnostic Protocol + Battery Migration
- Phase 2 DeviceSession architecture
- canonical platform-neutral device API
- stale-device safety
- raw-serial privacy boundary
- no silent false confidence
- LIVE/Demo separation

### Risks and Limitations
- Full capability discovery not implemented (endpoint returns 501 for connected devices).
- iOS device discovery not implemented yet.
- Device sessions are in-memory and transient.
- Trust Intelligence remains intentionally disconnected from scan lifecycle.

---

## Baseline Commit at Phase 2A Start

1ae24fa

---

## Last Updated

2026-10-05

---

## Last Green Commit SHA

5f90447 (Canonical Phase 4 implementation commit)

---

## Current Branch

main

---

## Current Architecture Status

Phase 2A adds real Android device discovery and battery telemetry verification on top of the Phase 1 foundation.

- **AndroidDeviceBridge** (`local-agent/src/vector_agent/devices/android/bridge.py`): All ADB operations use safe subprocess policy â€” argument arrays, bounded timeouts, no shell strings. Handles: `discover_devices()`, `get_identity()`, `get_battery_telemetry()`.
- **Android API Router** (`/api/v1/devices/android`): GET lists devices; GET `/{device_id}/battery` runs battery telemetry. `device_id` is an opaque SHA256 hash â€” never the raw ADB serial. Registry maps device_id â†’ validated serial in-memory.
- **Pydantic models** (`models/android.py`): `AndroidDeviceResponse`, `AndroidDeviceListResponse`, `BatteryTelemetryResponse`.
- **Frontend**: Types, hooks, API client, and `AndroidStatus` component fully wired. Manual detection only. Battery test enabled only after single authorized device confirmed.
- **PASS disclaimer**: Battery PASS status always displays `status_note` explicitly stating this is evidence collection, not battery-health assessment.
- **Verification**: 15/15 verify.ps1 checks pass. 85 backend tests (58 existing + 27 new). 80 frontend tests (64 existing + 16 new Android tests). Total: 166 tests.

---

## Completed Features

- [x] Repository structure scaffolded
- [x] .gitignore created
- [x] .editorconfig created
- [x] README.md written
- [x] docs/ARCHITECTURE.md written
- [x] docs/FORMULATION.md written (full mathematical spec)
- [x] docs/LIMITATIONS.md written (honest limitations)
- [x] docs/SOURCES.md written (full citations)
- [x] docs/ATTEMPTS.md skeleton written
- [x] configs/attempt_01.yaml skeleton written
- [x] scripts/verify.ps1 written
- [x] .github/workflows/ci.yml written
- [x] local-agent Python package scaffolded (pyproject.toml, src layout)
- [x] intelligence Python package scaffolded (pyproject.toml, src layout)
- [x] Core models (device, capability, evidence, diagnostic, scan)
- [x] Error model (all error classes and VectorErrorCode enum)
- [x] Logging module with redaction support
- [x] Security: subprocess_policy.py (no shell=True, array args, timeouts)
- [x] Security: redaction.py (mask_identifier, hash_identifier, redact_imei)
- [x] Security: validation.py (serial, UDID, scan_id validation)
- [x] FastAPI main application (lifespan, error handlers, CORS, routers)
- [x] API: /api/v1/health, /api/v1/system/preflight
- [x] API: /api/v1/devices (stub), /api/v1/scans (stub)
- [x] Intelligence: fuzzy/inference.py (FuzzyInferenceEngine, trimf, trapmf)
- [x] Intelligence: fuzzy/membership.py (TriangularMF, default_three_term_mfs)
- [x] Intelligence: fuzzy/rules.py (FuzzyRule, T-norm activation)
- [x] Intelligence: fuzzy/explanation.py (TrustExplanation)
- [x] Intelligence: evolution/genome.py (encode, decode, validate, repair, random)
- [x] Intelligence: evolution/objectives.py (4-objective NSGA-II fitness functions)
- [x] Intelligence: perturbation/noise.py (NOISE, MISSINGNESS, ADVERSARIAL, SHIFT, CONTRADICTION)
- [x] Intelligence: baselines/weighted_score.py (Baseline A: fixed weighted score)
- [x] Frontend: React + Vite + TypeScript + ESLint + Vitest scaffold
- [x] Frontend: vite.config.ts with /api proxy to local agent
- [x] Frontend test setup (testing-library, jsdom, vitest)
- [x] local-agent: 58 passing tests (errors, models, security, API, preflight, resilience) [Phase 1]
- [x] intelligence: 21 passing tests (fuzzy, genome, perturbation, baseline)
- [x] .env.example for local-agent
- [x] Phase 1A: Typed frontend API client (types.ts, health.ts, useHealthCheck.ts, client.ts)
- [x] Phase 1A: HealthStatus UI
- [x] Phase 1B: DiagnosticProvider abstraction and Live/Demo providers
- [x] Phase 1C: SystemPreflightService and PreflightStatus UI
- [x] Phase 1D: Error taxonomy, request sequencing, integration hardening (64 frontend tests)
- [x] **Phase 2A: AndroidDeviceBridge** â€” safe ADB device enumeration via argument arrays
- [x] **Phase 2A: ADB state handling** â€” DEVICE, UNAUTHORIZED, OFFLINE, NO_DEVICE, MULTIPLE_DEVICES, ERROR
- [x] **Phase 2A: Android identity retrieval** â€” manufacturer, model, android_version, sdk_level via getprop
- [x] **Phase 2A: Battery Telemetry Verification** â€” dumpsys battery evidence, PASS/INCONCLUSIVE/ERROR
- [x] **Phase 2A: Opaque device_id** â€” SHA256 hash prevents raw serial exposure in API/URL
- [x] **Phase 2A: Android API router** â€” GET /api/v1/devices/android, GET /api/v1/devices/android/{device_id}/battery
- [x] **Phase 2A: Pydantic models** â€” AndroidDeviceResponse, AndroidDeviceListResponse, BatteryTelemetryResponse
- [x] **Phase 2A: Frontend types** â€” AndroidDevice, AndroidDeviceListResponse, BatteryTelemetryResponse
- [x] **Phase 2A: Frontend hooks** â€” useAndroidDiscovery, useAndroidBattery (request sequencing + cancellation)
- [x] **Phase 2A: AndroidStatus component** â€” manual detect, state-driven UI, battery test with PASS disclaimer
- [x] **Phase 2A: 27 new backend tests** â€” bridge parser tests + API tests (fixture-based, no real hardware)
- [x] **Phase 2A: 16 new frontend tests** â€” AndroidStatus.test.tsx covering all 15 required behaviors
- [x] **Phase 2A: 15/15 verify.ps1 PASS** â€” all lint, type-check, test, and build checks clean

---

## Verified Features

- [x] local-agent: 85/85 tests PASS, 0 warnings (pytest)
- [x] local-agent: ruff check PASS (0 lint errors)
- [x] local-agent: ruff format PASS (all files clean)
- [x] local-agent: mypy PASS (36 source files checked, 0 errors)
- [x] intelligence: 21/21 tests PASS (pytest)
- [x] intelligence: ruff check PASS (0 lint errors)
- [x] intelligence: ruff format PASS
- [x] intelligence: mypy PASS
- [x] frontend: npm install PASS
- [x] frontend: ESLint PASS (0 errors, 0 warnings)
- [x] frontend: TypeScript check PASS (0 errors)
- [x] frontend: Vitest PASS (80/80 tests in 8 test suites)
- [x] frontend: Production build PASS
- [x] verify.ps1: 15/15 checks PASS

---

## Partially Implemented Features

- [ ] Device discovery (iOS): architecture in place, bridge stubs not yet implemented (Phase 2B)
- [ ] Scan state machine: state enum defined, orchestrator not yet implemented (Phase 3)
- [ ] NSGA-II full optimizer: objectives defined, main loop not yet implemented (Phase 5)
- [ ] Baseline B/C/D/E: not yet implemented (Phase 5)
- [ ] Synthetic benchmark generator: not yet implemented (Phase 5)
- [ ] Frontend full UI (home, scan, results, methodology pages): not yet implemented (Phase 7)

---

## Not Started

- [ ] iOS libimobiledevice bridge implementation (Phase 2B)
- [ ] DeviceCapabilityProfile real population (Phase 2)
- [ ] DiagnosticPlanner and TestRegistry (Phase 3)
- [ ] Additional diagnostics beyond battery (Phase 4)
- [ ] NSGA-II main optimizer loop (Phase 5)
- [ ] Synthetic benchmark generator (Phase 5)
- [ ] Full benchmark run with real metrics (Phase 6)
- [ ] VECTOR UI (home, scan, results, methodology pages) (Phase 7)
- [ ] Vercel deployment (Phase 8)
- [ ] Judge demo hardening (Phase 9)

---

## Known Bugs

None.

---

## Known Limitations

- Preflight checks local tooling presence only (shutil.which). NOT phone connectivity.
- Battery Telemetry PASS = evidence successfully collected. NOT battery-health assessment.
- In LIVE mode, the local FastAPI service must be running for ONLINE state.
- In DEMO mode, data is deterministic demo fixture; no live hardware communication.
- Automatic fallback from Live to Demo is explicitly disabled by design.
- ADB device registry is in-memory/transient; lost on agent restart.
- See docs/LIMITATIONS.md for comprehensive list.

---

## Technical Decisions Made

1. Python 3.14.7 environment (requires-python is ">=3.11" for CI compatibility)
2. FastAPI uses lifespan context manager (not deprecated on_event)
3. uv used for fast Python package management
4. All TOML files written without BOM
5. Vite proxy to /api routes to localhost:8742 (avoids CORS in dev)
6. Frontend package name: "vector-frontend"
7. NSGA-II minimizes 4 objectives: prediction_error, perturbation_instability, rule_complexity, latency_proxy
8. UNSUPPORTED evidence uses 0.5 (neutral) not 0.0 (false penalty)
9. All subprocess calls use argument arrays, shell=False mandatory
10. Explicit ConnectionState model: "CHECKING" | "ONLINE" | "OFFLINE" | "DEMO_READY"
11. React 19 safe async effect pattern in hooks
12. DiagnosticProvider abstraction with Live/Demo separation
13. Mode resolution via VITE_VECTOR_MODE (default: "live"); invalid values fail fast
14. SystemPreflightService checks local laptop environment ONLY â€” no device discovery
15. Shared safeFetchJson<T> with bounded timeouts, cancellation, and structured error categorization
16. Request sequencing (requestIdRef) prevents out-of-order race conditions
17. Check isolation in SystemPreflightService prevents endpoint crashes
18. **Phase 2A:** device_id is opaque SHA256 hash (12 chars) â€” ADB serial never exposed in API/URL
19. **Phase 2A:** Device registry in-memory only (dict); serial never persisted or logged
20. **Phase 2A:** Battery PASS â‰  battery health assessment; status_note always displayed
21. **Phase 2A:** ADB command list: ["adb", "devices", "-l"], ["adb", "-s", SERIAL, "shell", "getprop", PROP], ["adb", "-s", SERIAL, "shell", "dumpsys", "battery"] â€” fixed lists, never user-supplied strings
22. **Phase 2A:** Plugged state inferred from AC/USB powered boolean fields (not from string "ac powered" key which is always present)

---

## Android Device Status

- ADB environment availability checking: IMPLEMENTED (Phase 1C preflight)
- ADB device enumeration: IMPLEMENTED (Phase 2A â€” 'adb devices -l' via safe subprocess)
- ADB state handling (DEVICE/UNAUTHORIZED/OFFLINE/NO_DEVICE/MULTIPLE_DEVICES): IMPLEMENTED
- Android identity retrieval (manufacturer, model, android_version, sdk_level): IMPLEMENTED
- Battery Telemetry Verification ('adb shell dumpsys battery'): IMPLEMENTED
- Opaque device_id (SHA256, never raw serial): IMPLEMENTED
- Real Redmi Note 14 Pro 5G connection: NOT YET VERIFIED (ADB not on system PATH during implementation â€” see Required External Tools section)

---

## iPhone Device Status

- iPhone device discovery: NOT STARTED (Phase 2B)
- iOS tooling availability checking: IMPLEMENTED (Phase 1C)

---

## Frontend Status

Phase 2A adds Android device discovery and battery UI on top of Phase 1:
- Provider contract extended: `discoverAndroidDevices()`, `getAndroidBatteryTelemetry(deviceId)`.
- Client layer: `lib/api/android.ts` with `fetchAndroidDevices` and `fetchAndroidBatteryTelemetry` using `safeFetchJson<T>`.
- State management: `useAndroidDiscovery` and `useAndroidBattery` hooks with request sequencing, stale data clearing, and unmount cancellation.
- UI: `AndroidStatus` component with manual detection, all ADB state cases, battery section (only for DEVICE state), PASS disclaimer note.
- 80 passing tests across 8 test suites.
- ESLint: 0 errors. TypeScript: 0 errors. Build: clean.

---

## Backend Status

FastAPI agent operational. Phase 2A backend additions:
- `GET /api/v1/devices/android` â€” ADB device discovery with identity retrieval for authorized devices.
- `GET /api/v1/devices/android/{device_id}/battery` â€” Battery telemetry from 'adb shell dumpsys battery'.
- Security: All ADB commands use validated fixed argument lists. device_id path param never reaches ADB.
- Privacy: Serial numbers internal/transient only. Not in API response or logs.
- 85 tests pass in local-agent (58 existing + 27 new Phase 2A tests). Ruff: 0 errors. Mypy: 0 errors across 36 files.

---

## Intelligence Engine Status

Fuzzy inference, genome encoding, perturbation engine, and Baseline A implemented. 21 tests pass.
NSGA-II main optimizer loop: NOT YET IMPLEMENTED (Phase 5).

---

## Exact Verification Commands Last Run

```powershell
$env:PATH = "C:\Program Files\nodejs;C:\Program Files\Git\cmd;" + $env:PATH; .\scripts\verify.ps1
# Result: 15/15 checks passed, exit code 0
# - Agent: Install deps (uv) [PASS]
# - Agent: Ruff lint [PASS]
# - Agent: Ruff format [PASS]
# - Agent: Mypy [PASS]
# - Agent: Pytest [PASS] (85/85)
# - Intelligence: Install deps [PASS]
# - Intelligence: Ruff lint [PASS]
# - Intelligence: Ruff format [PASS]
# - Intelligence: Mypy [PASS]
# - Intelligence: Pytest [PASS] (21/21)
# - Frontend: npm install [PASS]
# - Frontend: ESLint [PASS]
# - Frontend: TypeScript check [PASS]
# - Frontend: Tests [PASS] (80/80)
# - Frontend: Build [PASS]
```

---

## Required External Tools

| Tool | Purpose | Status |
|---|---|---|
| ADB (Android Platform Tools) | Android device communication | Not found on system PATH during Phase 2A. Install before running live device test. |
| libimobiledevice | iOS device communication | Checked via Preflight (NOT_INSTALLED / PASS depending on host PATH) |
| Git | Version control | INSTALLED (C:\Program Files\Git) |
| Python 3.14.7 | Agent and intelligence | INSTALLED |
| Node.js 24.19.0 | Frontend | INSTALLED |
| uv | Python package management | INSTALLED |

---

## Phase 2A New Files

**Backend:**
- `local-agent/src/vector_agent/devices/android/bridge.py` â€” AndroidDeviceBridge + parsing functions
- `local-agent/src/vector_agent/devices/android/__init__.py` â€” updated exports
- `local-agent/src/vector_agent/api/android.py` â€” GET /devices/android, GET /devices/android/{id}/battery
- `local-agent/src/vector_agent/models/android.py` â€” Pydantic API models
- `local-agent/src/vector_agent/main.py` â€” android router registered
- `local-agent/tests/test_android_bridge.py` â€” 18 fixture-based parser tests
- `local-agent/tests/test_android_api.py` â€” 9 API endpoint tests

**Frontend:**
- `frontend/src/lib/api/android.ts` â€” fetchAndroidDevices, fetchAndroidBatteryTelemetry
- `frontend/src/lib/api/useAndroidDiscovery.ts` â€” hook
- `frontend/src/lib/api/useAndroidBattery.ts` â€” hook
- `frontend/src/components/AndroidStatus.tsx` â€” full UI component
- `frontend/src/__tests__/AndroidStatus.test.tsx` â€” 16 tests

**Modified:**
- `frontend/src/lib/api/types.ts` â€” added Android types + type guards
- `frontend/src/providers/DiagnosticProvider.ts` â€” extended interface
- `frontend/src/providers/LiveDiagnosticProvider.ts` â€” implemented Android methods
- `frontend/src/providers/DemoDiagnosticProvider.ts` â€” demo stubs for Android methods
- `frontend/src/App.tsx` â€” added AndroidStatus component
- `frontend/src/__tests__/HealthStatus.test.tsx` â€” updated mock to include new interface methods

---

## Current Uncommitted Files

All Phase 2A files listed above are uncommitted (untracked/modified).
Working tree is clean only of Phase 1 committed files.

---

## Do Not Redo

- Do not rewrite any Phase 1 files unless fixing a bug.
- Do not rewrite AndroidDeviceBridge â€” all ADB paths are fixed lists.
- Do not add fallback demo data to live ADB paths.
- Do not expose raw ADB serial numbers in the API or logs.
- Battery PASS note must always disclaim health assessment.

---

## Notes for Next AI Agent

Phase 2A is complete and verified awaiting user commit. All 15 verify.ps1 checks pass. 166 total automated tests (85 agent + 21 intelligence + 80 frontend). Baseline committed SHA is 1ae24fa.

ADB is not on the system PATH â€” the next agent or user needs to install Android Platform Tools and add to PATH to test with a real Redmi Note 14 Pro 5G. The VECTOR local agent (`local-agent/`) must be running before discovery can function.

To start the agent: `cd local-agent && uv run uvicorn vector_agent.main:create_app --factory --host 127.0.0.1 --port 8742`
To start the frontend: `cd frontend && npm run dev`

---

## HANDOFF PROMPT

VECTOR Phase 2A is complete and verified awaiting user commit. Real ADB device discovery (argument-array subprocess policy), identity retrieval, battery telemetry, opaque device_id registry, AndroidStatus frontend component, and 43 new tests (27 backend + 16 frontend) are all green. verify.ps1 15/15. Total: 166 tests. Baseline commit: 1ae24fa. ADB not on PATH â€” install Android Platform Tools to test with real Redmi Note 14 Pro 5G device.
Discovery.