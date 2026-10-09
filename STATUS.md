# VECTOR STATUS.md

**Purpose:** This file allows any new agent or developer to continue work without reading the entire conversation history.

---

## Project

**VECTOR** â€“ Verified Evidence-Based Computational Trust for Ownership Review  
Standardized diagnostics and verification for the second-hand smartphone market.

Hackathon challenge: Advanced Computational Intelligence â€” Hybrid Evolutionary-Fuzzy Frameworks (CIS track)

---

## Current Phase

Canonical Phase 8 — VECTOR Probe + Deep Android Diagnostics
Phase 8 overall: IN PROGRESS
Current completed slices:
- Phase 8A - VECTOR Probe Protocol, Evidence Boundary + Security Foundation (COMPLETE / VERIFIED / FORMAL GATE PASSED / IMPLEMENTATION COMMITTED: 4f073da)
- Phase 8D - Platform-Neutral Component Authenticity / Provenance Domain (COMPLETE / VERIFIED / FORMAL GATE PASSED / IMPLEMENTATION COMMITTED: 03d80b4)
- Phase 8B - Signed Android Probe + Discovery / Consent / Lifecycle (COMPLETE / VERIFIED / FORMAL GATE PASSED / IMPLEMENTATION COMMITTED: 365f0e8)
- Phase 8C - Deep Android Functional Diagnostics (COMPLETE / INDEPENDENT GATE PASSED; baseline 0aa0cbe; committed in the Phase 8C completion commit that follows 0aa0cbe)
- Phase 8E - OEM Reference Catalog, Identity Resolution, Evidence-Based Comparison + Hardening (IMPLEMENTATION COMPLETE / REMEDIATED; committed in the Phase 8E checkpoint commit, SHA not recorded here; independent post-remediation acceptance re-gate PENDING, so full Phase 8E closure is NOT claimed). Android provenance/anomaly collectors are DEFERRED, not completed.
Baseline before Phase 8A: 638955c
Codex instructions commit: 638955c
Phase 8A implementation commit: 4f073da
Baseline before Phase 8D: acc5b56
Phase 8D implementation commit: 03d80b45f717ac3671232b1824f492d0fdd3be19 (03d80b4)
Baseline before Phase 8B: 8456e352053a802a7cff85eff4ad1751ef14878e
Phase 8B implementation commit: 365f0e88a3da172b27e5021a9ff95257aa83eb25 (365f0e8)
Formal Phase 8A Gate: PASSED
Final staged-boundary review (8A): APPROVED
Formal Phase 8D Gate: PASSED
Formal Phase 8B Gate: PASSED
Independent Phase 8C Gate: PASSED (0 BLOCKER, 0 HIGH, 0 MEDIUM, 2 LOW, 5 INFO accepted as nonblocking)
Independent Phase 8E Final Gate (before remediation): PASSED (0 BLOCKER, 0 HIGH, 0 MEDIUM; FR-01..FR-13 were LOW findings)
Phase 8E FR-01..FR-13 remediation: applied and verified by the implementer; focused post-remediation review raised RV-01 (MEDIUM), which is now FIXED and covered by `local-agent/tests/test_phase8e_rv01.py`; a second focused read-only review of the fix found no BLOCKER/HIGH/MEDIUM issue. The independent re-gate of the remediation is still PENDING (see docs/PHASE_8E_CLOSURE.md)
Final staged-boundary review (8B): APPROVED
Hardware qualification: NOT RUN
Trust Engine: NOT_READY
trust_score: None
Next implementation slice: 8F - Premium Frontend, Real Diagnostics Integration, Quick Scan, Optional Deep Scan + VECTOR Core Animation (NEXT / NOT STARTED; requires separate explicit authorization)

### Canonical Production Roadmap
1. Foundation / Production Audit — COMPLETE
2. Diagnostic Protocol + Battery Migration — COMPLETE
3. DeviceSession + Platform-Neutral Device API — COMPLETE
4. Capability Foundation + Runtime Discovery — COMPLETE
5. Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events — COMPLETE
6. Additional Android Standard Diagnostics — COMPLETE
7. iOS Discovery, Pairing + Advanced / Version-Aware iOS Diagnostics — COMPLETE
8. VECTOR Probe + Deep Android Diagnostics - IN PROGRESS (8A, 8D, 8B & 8C complete; 8E implementation complete with acceptance re-gate PENDING; 8F next)
9. Cross-Platform Evidence Normalization + Verification Coverage — NOT STARTED
10. Explainable Verification / Trust Engine — NOT STARTED
11. Real-Device Validation + Calibration — NOT STARTED
12. B2B SaaS Foundation — NOT STARTED
13. B2B Workflow + Reporting — NOT STARTED
14. SaaS Commercial Layer — NOT STARTED
15. Production UX + Windows Distribution — NOT STARTED
16. Security / Privacy + Enterprise Readiness — NOT STARTED
17. Pilot — NOT STARTED
18. Commercial Release Candidate — NOT STARTED

*(Note: Sugeno fuzzy inference and NSGA-II evolutionary optimization are optional R&D / research / paper / competition tracks, not mandatory production gating phases.)*

### Approved Phase 8 Implementation Order
- 8A - Probe Protocol + Evidence Boundary + Security Foundation - COMPLETE
- 8D - Platform-Neutral Component Authenticity / Provenance Domain - COMPLETE
- 8B - Signed Android Probe + Discovery / Consent / Lifecycle - COMPLETE (development-foundation scope; physical hardware qualification NOT RUN)
- 8C - Deep Android Functional Diagnostics - COMPLETE (Independent Gate PASSED; physical hardware qualification NOT RUN)
- 8E - OEM Reference Catalog, Identity Resolution, Evidence-Based Comparison + Associated Hardening - IMPLEMENTATION COMPLETE (remediation verified and committed; independent acceptance re-gate PENDING; physical hardware qualification NOT RUN)
- 8F - Premium Frontend, Real Diagnostics Integration, Quick Scan, Optional Deep Scan + VECTOR Core Animation - NEXT (NOT STARTED)
- 8G - Security, Reliability, Performance, Accessibility + Physical-Device Qualification - NOT STARTED
- DEFERRED (not completed, not assigned to a named slice): Android provenance/anomaly signal collectors (real OEM provenance collectors and anomaly detection) originally planned under the 8E name. Phase 8E did not implement them.
- Roadmap reconciliation for 8E / 8F / 8G approved by the user on 2026-10-10; it supersedes the earlier working titles (8E "Android Provenance / Anomaly Signals", 8F "Planner / Evidence / Coverage / Frontend Integration", 8G "Adversarial Regression + Hardware Qualification").

### Verified Phase 8A Implementation
- versioned Probe protocol v1 with strict typed contracts and six allowlisted operations: HELLO, GET_CAPABILITIES, START_CHALLENGE, CANCEL_CHALLENGE, FETCH_OBSERVATIONS, HEARTBEAT
- strict bounded JSON ingestion with duplicate-key rejection, finite-number enforcement, and strict identifier validation
- bounded replay protection, secure random nonces, sequence handling, and exact request/response ownership binding to device-session epoch and scan / diagnostic / attempt / challenge context
- UTC expiry and monotonic deadlines; expired-pending-request replacement, exact scoped abandonment, synchronized pending-request timing lifecycle, and concurrency-safe dispatch ownership
- abstract Probe transport with typed outcomes; validated, attributed Probe observation boundary and additive VECTOR_PROBE evidence source
- process-local authorization foundation using a secure random token and constant-time comparison; no arbitrary shell / command / path / URL / intent / code support
- this layer generates no hardware PASS, authenticity verdict, Trust Score, confidence, or reliability; confidence and reliability remain None
- Probe responsiveness != hardware PASS. Authenticated/correlated Probe data != truthful physical measurement.
- Phase 8A contains no real Android Probe app and no physical diagnostics. Hardware qualification was NOT RUN.

### Phase 8A Verification Results
- Phase 8A focused: 254 passed
- Full local-agent: 949 passed
- Intelligence: 21 passed
- Frontend: 96 passed across 10 test files
- Root verify.ps1: 15 / 15 passed
- Ruff: PASS; Ruff format: PASS; Mypy: PASS
- ESLint: PASS; TypeScript: PASS; Frontend production build: PASS
- Independent review and correction re-review completed; Formal Phase 8A Gate: PASSED
- Final staged-boundary review: APPROVED
- Hardware qualification: NOT RUN

### Phase 8A Accepted Non-Blocking Debt
- R-01 LOW: production sequence and operation request-binding checks are correct and were directly verified during review, but two comparisons do not each have a dedicated isolated negative unit test.
- R-02 INFO: two existing assertions could be stronger.
- R-03 INFO: two negative tests reach owner mismatch before the nominal comparison; other tests still cover those production clauses.
- G-01 INFO: current_device_epoch() is called while the transport lock is held. No current deadlock exists; lock ordering is a future 8B/8D integration consideration.
- G-02 INFO: injected clock test seams do not explicitly finiteness-check values; these seams are not peer-controlled.
- G-03 INFO: EXPIRED maps to TIMEOUT, including a request that was never dispatched.
- G-04 INFO: protocol documentation mentions wall-clock rollback; implementation also fails closed on monotonic rollback.
- Inherited debt: subprocess capture_output buffering remains potentially unbounded before post-read truncation. Phase 8A added no subprocess commands and did not worsen this debt.

### Verified Phase 8D Implementation
- Platform-Neutral Component Authenticity / Provenance Domain candidate fully implemented and committed in `03d80b45f717ac3671232b1824f492d0fdd3be19` (`03d80b4`).
- Session-scoped component identity: `cmp-<128-bit SHA-256>` derived from version tag (`vector-component-v1`), opaque `device_id`, desktop-owned `session_scope_id` (UUIDv4), `device_session_epoch`, `component_kind`, `component_role`, and `ordinal`. Delimiter-separated to resist field boundary collapse. Golden vector pinned independently: `cmp-4a9cdaa1d85350c8a6679540a1431969`.
- Strict separation of functionality and provenance: `DiagnosticStatus` (PASS/FAIL/ERROR/RESTRICTED/UNSUPPORTED/INCONCLUSIVE) and functionality references are retained solely as opaque references; never read to infer provenance. Successful function never implies OEM/genuine, and functional failure never implies aftermarket.
- Discrete, independent provenance dimensions: manufacturing origin (`VERIFIED_OEM`, `NON_OEM_INDICATED`, `UNKNOWN`), installation history (`ORIGINAL_VERIFIED`, `REPLACEMENT_VERIFIED`, `UNKNOWN`), prior use (`USED_VERIFIED`, `NOT_ESTABLISHED`), manipulation (`INDICATED`, `UNKNOWN`), and anomaly (`INDICATED`, `NO_ANOMALY_OBSERVED`, `UNKNOWN`).
- Cross-dimension conflict resolution:
  - `NON_OEM_INDICATED` + `ORIGINAL_INSTALLATION_ASSERTED`: origin `NON_OEM_INDICATED`, installation `UNKNOWN`, sufficiency `INCONCLUSIVE`, label `NON_OEM_INDICATED`, reason `CONFLICTING_ORIGIN_INSTALLATION_EVIDENCE`.
  - `ORIGINAL_VERIFIED` + `USED_VERIFIED`: installation `UNKNOWN`, prior use `USED_VERIFIED`, sufficiency `INCONCLUSIVE`, label `SUSPICIOUS`, reason `CONFLICTING_ORIGINAL_USED_EVIDENCE`.
  - Both opposing evidence sets preserved in `contradicting_evidence_ids`.
- Derived authenticity label precedence: origin conflict → `SUSPICIOUS`; resolved non-OEM origin → `NON_OEM_INDICATED`; other conflict / manipulation / anomaly → `SUSPICIOUS`; verified OEM + installation/use → `VERIFIED_OEM_ORIGINAL`, `VERIFIED_OEM_REPLACEMENT`, `VERIFIED_OEM_USED_REPLACEMENT`, `VERIFIED_OEM_ORIGIN_ONLY`; otherwise `UNKNOWN`.
- Strict `ComponentAssessment` validation rejecting forged claims: verifies policy version (`vector-provenance-v1`), matching reasons for all facts, non-empty supporting evidence if and only if facts exist, prohibition of negative manipulation assertions in v1, impossibility of coexisting original + non-OEM or original + used, and matching derived summary label.
- Platform-neutrality: zero Android or iOS adapter/collector imports in Phase 8D modules; enforced by AST lint checks.
- Pure and deterministic evaluation: no I/O, no network, no database, no wall-clock reads (`assessed_at` is caller-supplied UTC).

### Phase 8D Verification Results
- Focused Phase 8D tests: 884 passed
- Full local-agent: 1833 passed (1 known pre-existing Starlette/httpx testclient warning)
- Intelligence: 21 passed
- Frontend: 96 passed across 10 test files
- Root `scripts/verify.ps1`: 15 / 15 PASS
- Ruff lint: PASS (src/ and tests/)
- Ruff format: PASS (120 files)
- Mypy: PASS (81 source files)
- Frontend lint (ESLint): PASS
- TypeScript (`npx tsc --noEmit`): PASS
- Frontend production build (`vite build`): PASS
- Formal gate totals: 0 BLOCKER, 0 HIGH, 0 MEDIUM, 3 LOW, 8 INFO
- Formal Phase 8D Gate: PASSED
- Hardware qualification: NOT RUN (`CODE_TESTED` only; synthetic fixtures)
- Trust Engine: NOT_READY; trust_score: None

### Phase 8D Formal Gate Findings and Technical Debt

#### Accepted Low Debt
- **F-01 — Aggregate sufficiency limitation:** `AssessmentSufficiency` remains aggregate rather than per-dimension. An eligible observation (such as `NO_ANOMALY_OBSERVED`) may cause aggregate sufficiency to be `SUPPORTED` while `origin`, `installation`, and `manipulation` remain `UNKNOWN`. Consumers must NOT interpret aggregate `SUPPORTED` as meaning every provenance dimension is established. Refinement deferred to Phase 8F / Phase 9.
- **N-1 — ComponentAssessment defense-in-depth parity:** A hand-built / externally forged `ComponentAssessment` can represent `origin = UNKNOWN` and `installation = ORIGINAL_VERIFIED` with an origin-conflict reason, even though the production provenance policy itself cannot emit that shape. It remains conservative (cannot produce a positive `VERIFIED_OEM_*` label), and no external API/persistence boundary currently exposes it. Required future action: before `ComponentAssessment` is exposed through an API, persistence boundary, or untrusted deserialization path, tighten the validator so origin conflict cannot coexist with `ORIGINAL_VERIFIED` installation.
- **N-2 — Cross-conflict regression test depth:** Production behavior for cross-dimensional conflicts is correct and was independently stress-tested across counts, timestamps, authority classes, dependency keys, and input ordering, but repository regression tests do not yet directly pin all of those no-winner variants. This is accepted LOW test debt. When provenance policy tests are next materially touched, add parameterized count/time/authority/dependency-key no-winner tests for `NON_OEM + ORIGINAL` and `ORIGINAL + USED`.

#### Deferred Items & Gate Observations
- **F-06 (INFO):** Real source authentication, evidence ownership, session binding, freshness, cryptographic validation, and adapter-boundary trust deferred to future adapter phases.
- **F-07 (INFO):** `COMPONENT_BOUND` vs `DEVICE_SLOT_BOUND` refinement deferred.
- **F-08 (INFO):** Persistent opaque device-ID / `ComponentReference` privacy and persistence design deferred.
- **F-09 (INFO):** Relative-import / `# ruff: noqa: TID252` cleanup and minor syntax polish deferred.
- **G-1 (INFO):** Stale provenance lifecycle wording in documentation — resolved in this documentation finalization pass.
- **G-2 (INFO):** Working-tree CRLF normalized to LF in Git index; no defect.
- **G-3 (INFO):** Positive derived labels can coexist with additional dimensions such as `USED_VERIFIED` or `INCONCLUSIVE` weak counterclaims; future UI/reporting must show the underlying dimensions and sufficiency, not only the derived label.
- **G-4 (INFO):** `OpaqueDeviceId` currently recognizes `android|ios` prefixes; revisit only when a new platform or F-08 work requires it.

### Component Authenticity and Permanent Guarantees
- Functionality and authenticity/provenance are strictly independent dimensions. A component may function correctly while being aftermarket, replaced, manipulated, or of unknown origin. Never infer genuine/original from successful function; use UNKNOWN / INCONCLUSIVE when origin cannot be defensibly established.
- Future phases will gather evidence for as many device components as technically defensible: battery / BMS, display, cameras, biometric modules, logic board, charging components, audio components, haptics, sensors, storage, wireless modules, and other replaceable / identity-bearing parts.
- Phase 8D provides the platform-neutral domain foundation only. No actual component authenticity detection has yet been hardware-implemented or qualified.
- Every PASS requires evidence; certainty never exceeds evidence.
- Unsupported != Failed; Restricted != Failed; Inconclusive != Failed; execution ERROR != hardware FAIL.
- LIVE never silently falls back to DEMO; Level 1 != Level 2 != Level 3.
- Raw serial / UDID / IMEI and private data remain protected; no automatic iOS pairing.
- Physical claims remain CODE_TESTED; never claim HARDWARE_VALIDATED without physical qualification.
- Trust Engine remains NOT_READY and trust_score remains None.
- No real Android OEM collector yet.
- No Apple Parts & Service History collector yet.
- No battery-manipulation detector yet.
- No display-authenticity detector yet.
- No hardware genuineness claim yet.

### Verified Phase 8B Implementation
- **Signed Android Probe companion application (`org.vector.probe`)**:
  - Target Android SDK Platform 35, compileSdk 35, minSdk 26.
  - Clean manifest declaring **0 permissions** (no network, storage, location, camera, phone, or privileged permissions).
  - Complete data extraction and backup policy fail-closed: `android:allowBackup="false"`, `dataExtractionRules` (Android 12+) and `fullBackupContent` (pre-Android 12) explicitly excluding all storage domains (`root`, `file`, `database`, `sharedpref`, `external`) via `<exclude path="." />`.
  - Normal orientation and multi-window support: fixed portrait orientation lock removed, runtime configuration changes handled via `android:configChanges="orientation|screenSize|screenLayout|keyboardHidden"` without Activity teardown.
- **Explicit foreground-only on-device consent (`ProbeActivity`)**:
  - Protected with `FLAG_SECURE` against screenshots/screen capture; touch events filtered against obscured/overlay taps (`setFilterTouchesWhenObscured(true)`).
  - Purpose-specific on-screen UI with explicit Allow and Deny buttons; ignores all Intent extras; launch never implies consent.
  - `FLAG_KEEP_SCREEN_ON` enabled only during active authorized sessions; cleared immediately upon user Deny, Revoke, `onPause`, `onDestroy`, or server termination (`resource == R.string.stopped`).
  - Strict generation tracking prevents stale server callbacks from clearing flags or modifying status of newer consent sessions.
  - Ephemeral in-memory consent only; strictly revokes on pause/destroy/backgrounding; never persisted across process death.
- **Ephemeral session bootstrap & authentication**:
  - On user Allow, `ProbeServer` generates fresh 256-bit secret and random abstract Unix-domain socket endpoint (`vector_probe_<16-hex-bytes>`).
  - Bootstrap state written atomically to app private files directory (`files/vector-probe-session`).
  - Desktop reads bootstrap via development-only `run-as org.vector.probe cat files/vector-probe-session` (ordinary Android debugging authorization, not root/exploit).
  - The first successful `HELLO` exchange immediately consumes and overwrites the private bootstrap with `REQUIRED`, preventing secondary connections.
- **Bounded ADB transport (`AdbProbeTransport`)**:
  - Allocates local loopback port forward via `adb forward tcp:0 localabstract:<endpoint>`.
  - Rejects connections from any UID other than shell UID 2000 (`getPeerCredentials().getUid() == 2000`). App UIDs and root rejected.
  - Framing: 4-byte big-endian length prefix, 32-byte HMAC-SHA256 digest, bounded UTF-8 JSON payload.
  - Directional HMAC prefix (`request\0` and `response\0`) prevents reflection attacks.
  - Bounded 12-second complete frame watchdog; 900-second session-expiry deadline; cancellation-aware 100ms socket read slices.
- **Strict JVM Control Protocol (`ControlProtocol`)**:
  - Bounded, strict JSON parsing via Gson streaming reader; rejects ambiguous numbers, duplicate keys, surrogate pairs, deep nesting (>16), and oversized frames (>64KB).
  - Enforces protocol version 1, exact session ID, monotonic sequence numbers, distinct nonces, and bounded clock skew (30s TTL).
  - Supports 3 active control operations: `HELLO`, `GET_CAPABILITIES`, `HEARTBEAT`.
  - Challenge operations (`START_CHALLENGE`, `CANCEL_CHALLENGE`, `FETCH_OBSERVATIONS`) fail closed with `UNAVAILABLE` without executing hardware work or allocating state.
- **Desktop Probe Lifecycle Service (`ProbeService` & `ProbeConnection`)**:
  - Object identity and session epoch binding: `ProbeConnection` binds to specific `DeviceSession` instance and epoch. Epoch invalidation supersedes transport errors, reporting `SESSION_CHANGED` rather than `DEVICE_UNAVAILABLE`.
  - Concurrency & state query lock behavior: GET does not allocate a new connection or worker. Cross-device service-wide lock contention was mitigated (service-wide lock released before querying connection state or executing stop/join calls). However, state queries are not universally non-blocking: same-device GET/connection operations may still wait behind an in-flight operation. FG-06 remains an accepted LOW finding requiring correction before Phase 8F.
  - Concurrency cap: enforces maximum of 16 live connections; rejects 17th device when 16 live connections exist, and admits new device when an existing connection is retired.
  - Background monitor thread per connection polls ownership every 1s and sends heartbeat after 5s.
- **Development Trust Enrollment Utility (`trust_build.py`)**:
  - Verifies debug APK (`app-debug.apk`) using host `apksigner.bat` and `aapt2.exe`.
  - Validates signer certificate SHA-256 fingerprint, package name `org.vector.probe`, `versionCode=1`, `versionName="0.1.0"`, and `application-debuggable`.
  - Computes and records APK SHA-256 digest in ignored local store `local-agent/.data/probe-trust.json`.
- **API and Security Boundaries**:
  - Typed FastAPI endpoints (`GET /api/v1/devices/{id}/probe` and POST `discover`, `launch`, `connect`, `heartbeat`, `stop`), protected by process-local `X-Vector-Local-Auth` token.
  - Bounded subprocess execution (`BoundedProcess`) with concurrent pipe draining and fixed retained byte buffers.
  - Cross-language golden test vectors pinned for literal request and response envelopes and HMAC-SHA256 signatures in both Python and Java test suites.

### Phase 8B Verification Results
- Implementation commit: `365f0e88a3da172b27e5021a9ff95257aa83eb25` (`365f0e8`)
- Formal Claude phase gate: PASSED (0 BLOCKER, 0 HIGH, 0 MEDIUM, 6 LOW, 9 INFO)
- Staged-boundary review: PASSED
- Phase 8B focused Python tests: 120 passed
- Full local-agent regression: 1,953 passed (1 Starlette/httpx testclient deprecation warning)
- Phase 8A regression: 254 passed
- Intelligence: 21 passed
- Frontend: 96 passed across 10 test files
- Android JVM tests: 6 passed (all in `ControlProtocolTest`)
- Android lint: 0 errors, 0 warnings (clean build with `warningsAsErrors = true`)
- Android Java compilation: PASSED (`compileDebugJavaWithJavac`)
- Android debug APK assembly: PASSED (`app-debug.apk`, SHA-256: `a0ec37eca13bc3009bc33a3d07b7db60fd9940052232144eb8c61275c27d32eb`)
- APK signing and package verification: PASSED (`apksigner` Scheme v2 verified, signer SHA-256: `865ccb6a14342e0ff166b9082d94d145ab7c828b17c1a75b95cd0fc03ce8eafb`; `aapt2` verified)
- VECTOR development trust enrollment: PASSED (`probe-trust.json` recorded and verified)
- Root `scripts/verify.ps1`: 15/15 passed (writer-reported; formal reviewer independently reproduced non-installing checks)

### Phase 8B Important Boundaries and Operational Constraints
- **DEVELOPMENT-ONLY**: Probe application is strictly a development companion.
- **Debuggable APK**: Built with `application-debuggable`; production release builds are unsigned and reject the development bootstrap.
- **`run-as` Bootstrap**: Private bootstrap exchange relies on standard Android `run-as` debugging facility. Production non-debuggable pairing/bootstrap is NOT IMPLEMENTED.
- **Production Signer Trust**: Production release signing and production trust roots are NOT IMPLEMENTED.
- **Physical Hardware Qualification**: NOT RUN. All tests are software integration, bounded subprocess, and loopback socket tests.
- **Trust Engine**: Remains `NOT_READY`; `trust_score` remains `None`.
- **Authenticity Claims**: No hardware PASS, component authenticity verdict, or OEM claims arise from Phase 8B.
- **No Fallback**: LIVE never silently falls back to DEMO.
- **SDK Target**: Android minSdk is 26, targetSdk is 35, compileSdk is 35.

### Phase 8B Formal Gate Findings and Accepted Technical Debt

#### Accepted Low Debt
- **FG-01 (LOW, Remediation: PRE-8F):** Unbounded per-device lock registry. `ProbeService._device_locks` grows monotonically with new device IDs. Must be bounded or pruned before Phase 8F frontend/token access.
- **FG-02 (LOW, Remediation: PRE-8F):** Cancellation, timeout and expiry reason-fidelity gaps. In `AdbProbeTransport`, cancellation, socket timeouts, or frame expiry can collapse to generic disconnect or session-expired reasons. Refine reason fidelity before Phase 8F.
- **FG-03 (LOW, Remediation: Phase 8G):** ADB forward cleanup failure during transport-constructor failure. In `AdbProbeTransport.__init__`, if an exception occurs after creating `adb forward`, cleanup error handling is incomplete and could leak the forward rule until ADB daemon restart.
- **FG-04 (LOW, Remediation: Phase 8G / Next Relevant Implementation):** Five identified test-quality gaps (distinct from FG-03's ADB forward-cleanup issue):
  - Session-change regression test bypasses the intended exception branch.
  - Cross-device contention test does not exercise a genuinely blocked replacement.
  - A concurrency-named test performs sequential assertions.
  - Some assertions are overly broad; HELLO application-version negative coverage is incomplete.
  - One monitor timing test has a narrow scheduling margin.
- **FG-05 (LOW, Remediation: Phase 8G):** No executable Android Activity/Server lifecycle tests. JVM tests cover `ControlProtocolTest` (6 tests), but `ProbeActivity` and `ProbeServer` lack Robolectric/instrumentation unit tests in CI. Address in Phase 8G.
- **FG-06 (LOW, Remediation: PRE-8F):** Same-device state query and connection operation waits. GET does not allocate a new connection or worker, and cross-device service-wide lock contention was mitigated. However, same-device GET/connection operations may still wait behind an in-flight operation. FG-06 remains an accepted LOW finding requiring correction before Phase 8F.

#### Accepted Info Debt & Gate Observations
- **FG-07 (INFO, Remediation: Phase 8G):** Coarse run-as failure classification. Distinction between missing package vs permission-denied run-as responses could be more granular.
- **FG-08 (INFO, Remediation: Phase 8G / Production):** Stale private bootstrap file/process-death edge cases. Edge cases where the app dies without deleting the session file are bounded by randomized endpoint names and socket failure, but explicit recovery can be hardened.
- **FG-09 (INFO, Remediation: Phase 8G):** Only HELLO has fully pinned cross-language golden vectors. Other message envelopes (GET_CAPABILITIES, HEARTBEAT) have schema coverage, but literal cross-language golden byte vectors should be pinned for all operations in Phase 8G.
- **FG-10 (INFO, Remediation: Phase 8F / Phase 9):** Minor Android-specific assumptions in shared models. Small assumptions in device models (such as adb serial defaults) should be generalized when normalizing cross-platform models.
- **FG-11 (INFO, Remediation: Resolved in Phase 8B Finalization):** Documentation precision issues (test counts, file inventories, operator instructions). Corrected during this documentation finalization pass.
- **FG-12 (INFO, Remediation: Later Production Phases):** Missing Android CI, Gradle wrapper and reproducible build metadata. Gradle and Android SDK are currently host-installed; wrapper and reproducible build configurations deferred to production tooling setup.
- **FG-13 (INFO, Remediation: Resolve alongside FG-02):** Broad exception mapping. Exception handlers catch generic `Exception` in several lifecycle guards. Narrow down alongside FG-02.
- **FG-14 (INFO, Remediation: Phase 8G / Production):** Local forwarding and development ADB-host trust limitations. Relies on ADB host trust boundary; production pairing and host authentication deferred.
- **FG-15 (INFO, Remediation: Test branches in Phase 8G):** Benign working-copy line endings and untested enrollment branches (such as negative hash-checking branches). Exercise remaining negative branches in Phase 8G.

#### Production-Blocking Deferred Items
- Production non-debuggable bootstrap (independent of `run-as`).
- Release signing keys and production certificate trust infrastructure.
- Cryptographic host-to-device pairing outside the authorized ADB boundary.

### Phase 8C - COMPLETE (Independent Gate PASSED)

#### Verified Phase 8C Implementation (approved scope)
- Authenticated Android diagnostic collection over the Phase 8B signed control plane.
- Protocol v2 diagnostics (diagnostic start/fetch operations with strict envelope validation).
- Android collectors for battery, camera, sensor, touch, audio, storage and system diagnostics (`org.vector.probe`).
- Desktop diagnostic ingestion and validation (`probe_diagnostics.py`, `diagnostic_evidence.py`, evidence validation).
- Cross-language integration regression coverage (pinned Java/Python wire fixtures under `local-agent/tests/fixtures/cross_language/`).
- Consent and permission lifecycle enforcement (foreground consent, permission history, fail-closed on revoke/pause).
- Strict evidence qualification: every PASS requires evidence; UNSUPPORTED, RESTRICTED, INCONCLUSIVE and execution ERROR are never reported as hardware FAIL.
- Documentation: `docs/PHASE_8C_ANDROID_DIAGNOSTIC_MATRIX.md`, `docs/PHASE_8C_REAL_DEVICE_VALIDATION.md`.

#### Phase 8C Independent Gate Verification Results
- Baseline: `0aa0cbec629d5d0eb71c5720aaec8e513e5638a1` (`0aa0cbe`)
- Android JVM/Robolectric tests: 141 passed
- Local-agent Python: 2,120 passed
- Intelligence: 21 passed
- Frontend: 96 passed
- Root `scripts/verify.ps1`: 15/15 passed
- Findings: 0 BLOCKER, 0 HIGH, 0 MEDIUM, 2 LOW, 5 INFO (accepted as nonblocking)
- Physical hardware qualification: NOT RUN. Diagnostic claims remain CODE_TESTED, not HARDWARE_VALIDATED.
- Trust Engine remains NOT_READY; `trust_score` remains `None`. No OEM authenticity or provenance claim is made.

#### Phase 8C Accepted Independent-Gate Findings
- **UG-01 (LOW):** Touch input-source validation. Resolve before a touchscreen PASS is presented as a comprehensive hardware result.
- **UG-02 (LOW):** Eight surviving negative-test mutations. Address in the relevant follow-up testing/qualification phase.
- **UG-03 through UG-07 (INFO):** Informational limitations, documentation qualifications and development-tooling notes.
- Inherited Phase 8B debt (including FG-01, FG-02 and FG-06) is preserved unchanged, with its established pre-8F remediation boundary.

### Phase 8E - IMPLEMENTATION COMPLETE (remediation verified and committed; independent acceptance re-gate PENDING)

#### Verified Phase 8E Implementation (reconciled scope)
- Platform-neutral reference domain models (`models/reference.py`) and an in-memory OEM reference catalog (`local-agent/src/vector_agent/reference/`): sources, manufacturers, models, variants, specifications and performance baselines, with atomic import. Test-only catalogs are labeled TEST-ONLY at report and item level.
- Seed catalog: 642 source assertions, all UNVERIFIED and non-authoritative (0 verified claims). A definitive CONSISTENT / DIFFERS outcome requires an exact curator verification record bound to the entity, property and value. Missing, unverified or unresolved reference data yields REFERENCE_UNAVAILABLE / INSUFFICIENT_EVIDENCE / NOT_COMPARABLE, never a failure.
- Identity resolution (`resolver.py`): exact model-code / variant resolution, explicit ambiguity and conflict states; a platform that contradicts the catalogued maker yields CONFLICTING_IDENTIFIERS. No identity is invented.
- Evidence-based comparison (`comparator.py`, `evidence_adapter.py`): consumes canonical diagnostic evidence; while the variant is unresolved a mismatch is withheld (VARIANT_AMBIGUOUS) rather than asserted. A specification match is not proof of a genuine/original part, and a mismatch is not proof of a counterfeit.
- Performance baselines (`performance.py`): malformed observations are treated as missing; a negative reference standard deviation is rejected.
- Android battery parsing hardening (`bridge.py`): ASCII-decimal integers only, bounded ingestion ranges, only recognized plug sources published. Battery PASS still means valid telemetry was collected, not battery health.
- Frontend `AndroidStatus`: explicit UNKNOWN, MISSING_DRIVER and OFFLINE guidance; no device presence is invented.
- Documentation: `docs/PHASE_8E_CHECKPOINT_*.md`, `docs/PHASE_8E_RECOVERY.md`, `docs/PHASE_8E_FINAL_REMEDIATION.md`, `docs/PHASE_8E_CLOSURE.md`, `docs/PHASE_8E_SPECIFICATION_CATALOG.md` and the JSON integrity/mutation records.

#### Phase 8E Verification Results
- Local-agent Python: 2,727 passed (2,694 before the RV-01 fix plus 33 new RV-01 cases; 1 existing httpx/Starlette deprecation warning); Ruff check, Ruff format and mypy clean
- Intelligence: 21 passed; Ruff, format and mypy clean
- Frontend: 111 passed (12 test files); `tsc -b` and ESLint clean (verified in a scratch copy; NOT re-run after the RV-01 fix, which changed no frontend file)
- Android JVM/Robolectric: 141 passed (no Android or fixture files changed in Phase 8E; NOT re-run after the RV-01 fix)
- Reference mutation harness (`scripts/verify_reference_mutations.py`): control passes, 20/20 mutants killed (re-run after the RV-01 fix); 7 separate scratch mutants of the RV-01 guard all killed
- Independent final gate findings FR-01 through FR-13: remediated (FR-12 and PG-18 preserved per user decision, below); independent re-gate of the remediation: PENDING
- Root `scripts/verify.ps1`: NOT RUN (it installs into system Python/npm); equivalent checks were run individually
- Physical hardware qualification: NOT RUN. Trust Engine remains NOT_READY; `trust_score` remains `None`. No OEM authenticity or provenance claim is made.

#### Phase 8E Deferred Work and Boundaries
- DEFERRED, NOT COMPLETED: Android provenance/anomaly signal collectors (real OEM provenance collectors and anomaly detection) originally planned under the 8E name. Phase 8E did not implement them.
- The reference catalog is in-memory only; all seed assertions remain UNVERIFIED until a curator verifies them against source documents.
- FIXED (RV-01, MEDIUM, focused review): `PerformanceReferenceManager.evaluate_metric` returned CONSISTENT / DIFFERS for a variant-restricted baseline when the variant was unresolved. It now returns VARIANT_AMBIGUOUS (observation preserved) when the baseline lists applicable variants and the variant is None or empty; explicitly resolved variants and model-wide baselines are unchanged. The manager was never wired to a production scan path. Remaining low-severity review items RV-03, RV-04 (LOW) and RV-05 (INFO) are recorded in `docs/PHASE_8E_CLOSURE.md`.
- OPEN (RV2-01, LOW): `PerformanceReferenceManager.evaluate_metric` checks that the variant is in `applicable_variant_ids` but not that it belongs to `model_id`. It needs an inconsistent caller pairing and nothing calls it in production. It MUST be resolved before the performance-evaluation path is exposed through any production API.
- MA-006 (Host validation) and MA-020 (registry bounds) are carried to Phase 8G.
- `frontend/vitest.config.ts` carries a preexisting uncommitted modification (PG-18, user decision: leave untouched); it is excluded from the Phase 8E checkpoint. `local-agent/3.11/` (untracked tool cache, FR-12) is preserved unchanged and excluded.

### Next Implementation Slice
8F - Premium Frontend, Real Diagnostics Integration, Quick Scan, Optional Deep Scan + VECTOR Core Animation - NEXT (NOT STARTED; requires separate explicit authorization). Phase 8 remains IN PROGRESS; this status update does not start later work.

---

## Historical Phase Record — Phase 7: iOS Discovery, Pairing + Advanced / Version-Aware iOS Diagnostics

Canonical Phase 7 — iOS Discovery, Pairing + Advanced / Version-Aware iOS Diagnostics
Status: COMPLETE / VERIFIED and committed
Baseline before Phase 7: 059cdce
Implementation commit: 4859ba8
Phase 7 status finalization commit: 0b44dc6
Formal Phase Gate: PASSED
Hardware qualification: NOT RUN

### Verified Implementation Completed
- implemented safe, typed libimobiledevice subprocess bridge (IOSDeviceBridge) with toolchain detection, discovery, validation, and user-initiated pairing
- hardened subprocess policy for iOS tooling (idevice_id, idevicepair, ideviceinfo, idevicediagnostics, idevicedevmodectl) with shell=False, strict argv allowlists, bounded timeouts, and raw UDID redaction in logs/exceptions
- pure, deterministic parsers with zero side-effects: parse_idevice_id_output, parse_pairing_validate_output, parse_pairing_pair_output, parse_ideviceinfo_key_value, parse_battery_telemetry, parse_gasgauge_plist, parse_disk_usage_output, and parse_developer_mode_output
- pair output parser (parse_pairing_pair_output) uses strict positive full-match grammar (re.fullmatch), eliminating substring/blocklist guessing and ensuring non-zero exit codes never return PAIRED
- battery telemetry parsing strictly enforces ASCII decimal integers (re.ASCII), with strict ASCII decimal parsing rejecting non-ASCII digits, underscores, plus-prefixed values, and out-of-range battery percentages
- developer mode parser enforces row-level targeting against target UDID, eliminating global error text guessing on rc!=0
- semantic Apple OS version parsing via AppleOSVersion with structured major/minor/patch components, build strings, and semantic comparisons
- version and model compatibility matrix (IOSCompatibilityResolver) mapping OS versions to strategy statuses: SUPPORTED, KNOWN_UNSUPPORTED, KNOWN_BROKEN, RESTRICTED, and RUNTIME_PROBE_REQUIRED
- all iOS diagnostic strategies remain explicitly CODE_TESTED only; no unverified claims of hardware validation (do not claim HARDWARE_VALIDATED)
- developer mode diagnostic strictly respects all resolver statuses: bails out before subprocess execution for KNOWN_BROKEN (UNSUPPORTED) and RESTRICTED (RESTRICTED), resulting in zero idevicedevmodectl calls
- GasGauge XML plist parser handles raw cycle counts and capacity fields neutrally without magnitude-based unit inference; FullChargeCapacity=100 does not create a 100mAh PASS; never fabricates health percentages; battery telemetry PASS means telemetry was successfully collected, not that battery health passed
- storage accounting diagnostic distinguishes AmountDataAvailable, TotalDataAvailable, and TotalDataCapacity without conflating free vs purgeable disk storage
- registered Phase 7 diagnostics use canonical IDs at VerificationLevel.RUNTIME_DETECTION: software_inventory, battery_charge_telemetry, battery_extended_telemetry, charging_power_telemetry, storage_accounting, and developer_mode_state (no Level 2 functional verification or Level 3 factory comparison implied)
- confidence and reliability for Phase 7 iOS evidence remain None
- multi-provider discovery truthfulness: Android bridge inspects non-zero return codes (mapping to ERROR instead of NO_DEVICE), preserving device isolation so single-provider failures return HTTP 200 with truthful statuses
- pairing endpoint (POST /api/v1/devices/{device_id}/pair) enforces upfront UDID syntax validation (returning HTTP 400 on malformed input) and inspects typed IOSCommandStatus.TIMEOUT; message text is not used as timeout authority
- pairing security: no automatic pairing; pairing only via explicit POST pair action; UNKNOWN, TIMEOUT, TOOL_UNAVAILABLE, and OFFLINE validation never trigger pair; non-zero pair command result never becomes PAIRED
- malformed UDIDs cannot create sessions or pair targets; session reconciliation defensively drops malformed or injection-like UDIDs (validate_ios_udid); raw UDID remains internal/transient; public DTOs, evidence, and logs do not expose raw UDID
- ScanPlanner and ScanService fully integrate iOS diagnostics with capability discovery, platform filtering, and heterogeneous multi-device scanning
- frontend TypeScript models and API client methods fully synchronized with iOS device discovery and pairing endpoints
- unwired companion_spec.py was intentionally excluded from the Phase 7 implementation commit
- Trust Engine remains NOT_READY and trust_score remains None; Phase 7 computes no trust score, health score, or factory comparisons

### Verification Results
- Local-agent pytest: 695 passed
- Intelligence pytest: 21 passed
- Frontend: 96 passed across 10 test files
- Root verify.ps1: 15 / 15 passed
- Ruff: PASS
- Ruff format: PASS
- Mypy: PASS
- ESLint: PASS
- TypeScript: PASS
- Frontend production build: PASS
- Formal Phase Gate: PASSED
- Hardware qualification: NOT RUN (Phase 7 automated verification is fixture-based; no real iPhone hardware smoke test was run in this environment. Recorded: 'Phase 7 hardware smoke test NOT RUN.')

### Known Non-Blocking Technical Debt
- **N16 (Session Provider Offline State Reconciler):** On provider failure, mark_platform_offline currently forces CONNECTED sessions OFFLINE. An UNAUTHORIZED session can remain UNAUTHORIZED until the next healthy discovery.
  - Formal gate judged this non-blocking because:
    - such sessions cannot execute diagnostics
    - planner treats them as restricted
    - provider_statuses exposes provider failure
    - pairing re-validates live
    - next healthy discovery reconciles the state
- **Accepted LOW Observations:**
  1. iOS pairing regex uses IGNORECASE without re.ASCII.
  2. A canonical pair-success line can theoretically coexist with contradictory secondary output.
  3. AppleOSVersion currently accepts Unicode decimal digits via \d.
  4. adb rc=0 with completely empty stdout maps to NO_DEVICE / AVAILABLE.

### Intentionally Deferred
- VECTOR Probe + Deep Android Diagnostics — Phase 8
- Cross-Platform Evidence Normalization + Verification Coverage — Phase 9
- Explainable Verification / Trust Engine — Phase 10
- Real-Device Validation + Calibration — Phase 11
- B2B SaaS Foundation — Phase 12
- B2B Workflow + Reporting — Phase 13
- SaaS Commercial Layer — Phase 14
- Production UX + Windows Distribution — Phase 15
- Security / Privacy + Enterprise Readiness — Phase 16
- Pilot — Phase 17
- Commercial Release Candidate — Phase 18
- iOS ActivationState diagnostic
- real iPhone hardware qualification
- optional Sugeno / NSGA-II R&D

### Permanent Guarantees / Do Not Redo
- every PASS requires real evidence
- telemetry/inventory success does not imply hardware health
- Unsupported != Failed
- Restricted != Failed
- Inconclusive != Failed
- execution ERROR != hardware FAIL
- stale-device safety and session epoch validation
- one active nonterminal scan per opaque device
- opaque device IDs; raw serial/UDID is internal/transient only
- raw serial, raw UDID, raw stderr, exception detail, and raw dumps never enter public evidence/events/API
- LIVE never silently falls back to DEMO
- Level 1 != Level 2 != Level 3
- battery telemetry PASS means telemetry collected, not battery health
- Trust Engine remains NOT_READY and trust_score remains None
- all iOS compatibility strategies remain CODE_TESTED only; never claim HARDWARE_VALIDATED without live hardware smoke tests

### Next Phase
Phase 8 — VECTOR Probe + Deep Android Diagnostics (NOT STARTED).

---

## Historical Phase Record — Phase 6: Additional Android Standard Diagnostics

Canonical Phase 6 — Additional Android Standard Diagnostics
Status: VERIFIED and committed
Baseline before Phase 6: 786280a
Last committed green SHA before this phase: 786280a
Phase 6 implementation commit: ee53940
Phase 6 status finalization commit: 059cdce

### Canonical Production Roadmap
1. Foundation / Production Audit — COMPLETE
2. Diagnostic Protocol + Battery Migration — COMPLETE
3. DeviceSession + Platform-Neutral Device API — COMPLETE
4. Capability Foundation + Runtime Discovery — COMPLETE
5. Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events — COMPLETE
6. Additional Android Standard Diagnostics — COMPLETE
7. iOS Discovery / Pairing + Basic iOS Diagnostics — NEXT (NOT STARTED)
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
- added five conservative Android standard diagnostics: storage_telemetry, memory_telemetry, thermal_telemetry, display_metrics, and camera_inventory alongside existing battery_telemetry
- all five new diagnostics use VerificationLevel.RUNTIME_DETECTION; no Phase 6 telemetry/inventory diagnostic overstates Level 2 functional verification
- storage telemetry uses fixed read-only `df -k /data`; normalizes total, used, available, and utilization evidence without claiming storage health
- storage parser enforces total > 0, non-negative used/available, used <= total, and available <= total; impossible values are INCONCLUSIVE and no invalid used+available==total assumption is imposed
- memory telemetry uses fixed read-only `/proc/meminfo`; requires valid kB units, never fabricates MemAvailable, rejects conflicting duplicate keys, and validates values against MemTotal
- thermal telemetry uses fixed read-only `dumpsys thermalservice`; rejects NaN/infinite samples, deduplicates cached/HAL readings by logical sensor identity, and prefers current HAL readings where structurally identifiable
- display metrics use fixed read-only `wm size` and `wm density`; physical and override values remain distinct and partial command failures cannot create PASS
- camera inventory uses fixed read-only `dumpsys media.camera`; no camera IDs are synthesized, facing is never guessed, count/device mismatches are INCONCLUSIVE, and oversized reported counts are bounded defensively
- camera parser suppresses client/package/process sections and emits only normalized inventory evidence; raw dumpsys content never becomes result/evidence/event payload
- real fabricated privacy-marker flow verifies raw serial, package-name, and Wi-Fi-like markers do not leak through bridge -> parser -> diagnostic -> orchestrator -> evidence/events/summary
- all Android commands continue through the hardened bridge/subprocess policy with fixed argv arrays, shell=False, validated serials, bounded timeouts, safe decoding, return-code handling, and redacted public errors
- diagnostic timeout budgeting uses monotonic remaining-time accounting; multi-command display diagnostics share one total budget rather than receiving a fresh timeout per command
- real ADBCommandTimeoutError paths are covered for storage, memory, thermal, camera, and both display commands; timeout becomes ERROR, never hardware FAIL
- zero/exhausted diagnostic budget executes no blocking command
- create_default_registry() now registers battery plus the five Phase 6 Android standard diagnostics with unique IDs, Android platform metadata, requires_probe=False, and no fabricated capability prerequisites
- ScanPlanner remains generic and unchanged; Full, Category, Selected, and Single Component modes derive Phase 6 diagnostics dynamically from registry metadata
- Phase 5 evidence, lifecycle, event, concurrency, stale-session, privacy, and worker-crash guarantees remain intact
- TrustEngineStatus remains NOT_READY; Phase 6 computes no health score, trust score, confidence score, penalties, or factory/reference comparisons
- frontend remains dynamic and unchanged; no diagnostic IDs, counts, progress, or category-to-test lists were hardcoded

### Verification Results
- Focused Phase 6 tests: 111 passed
- Full local-agent: 363 passed, 1 existing warning
- Intelligence: 21 passed
- Frontend: 90 passed across 9 test files
- scripts/verify.ps1: 15/15 PASS
- git diff --check: PASS
- Phase 6 formal gate: PASS
- Hardware smoke test: NOT RUN
- Hardware note: Phase 6 automated verification is fixture-based; no authorized real Android hardware smoke test was run in this environment. Recorded: 'Phase 6 hardware smoke test NOT RUN.'

### Intentionally Deferred
- iOS discovery, pairing, and basic iOS diagnostics
- VECTOR Probe and deep Android/interactive diagnostics
- Wi-Fi and Bluetooth functional verification
- active camera capture / optical verification
- microphone, speaker, touchscreen, motion-sensor, biometric, flashlight, and vibration functional tests
- model/factory reference comparison
- Cross-Platform Evidence Normalization and Verification Coverage
- Trust Engine live integration and Sugeno inference
- benchmark/NSGA-II/perturbation validation
- final reporting
- production UX, animations, and diagnostic visualization
- Windows packaging and release validation
- subprocess capture buffering hardening remains a later architectural hardening item
- real-hardware/OEM parser validation remains required before release-level validation

### Permanent Guarantees / Do Not Redo
- every PASS requires real evidence
- telemetry/inventory success does not imply hardware health
- Unsupported != Failed
- Restricted != Failed
- Inconclusive != Failed
- execution ERROR != hardware FAIL
- stale-device safety and session epoch validation
- one active nonterminal scan per opaque device
- opaque device IDs; raw ADB serial is internal/transient only
- raw serial, raw stderr, exception detail, package/client data, and raw dumps never enter public evidence/events/API
- LIVE never silently falls back to DEMO
- Level 1 != Level 2 != Level 3
- battery telemetry PASS means telemetry collected, not battery health
- no synthetic camera IDs or guessed camera facing
- no fake progress, fake timers, or simulated percentage
- Trust Engine remains NOT_READY and trust_score remains None

### Next Phase
Phase 7 — iOS Discovery / Pairing + Basic iOS Diagnostics (NOT STARTED).

---

## Historical Phase Record — Phase 5: Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events

Canonical Phase 5 — Diagnostic Registry + Scan Planner + Scan Lifecycle + Diagnostic Events
Status: VERIFIED and committed
Baseline before Phase 5: 0a27a80
Last committed green SHA before this phase: 0a27a80
Phase 5 implementation commit: 1d168e8
Phase 5 status finalization commit: 786280a

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