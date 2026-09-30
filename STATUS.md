# VECTOR STATUS.md

**Purpose:** This file allows any new agent or developer to continue work without reading the entire conversation history.

---

## Project

**VECTOR** – Verified Evidence-Based Computational Trust for Ownership Review  
Standardized diagnostics and verification for the second-hand smartphone market.

Hackathon challenge: Advanced Computational Intelligence — Hybrid Evolutionary-Fuzzy Frameworks (CIS track)

---

## Current Phase

PHASE 1C VERIFIED - AWAITING USER COMMIT

---

## Baseline Commit at Milestone Start

dadc39a

---

## Last Updated

2026-09-30

---

## Last Green Commit SHA

dadc39a

---

## Current Branch

main

---

## Current Architecture Status

Phase 1C System Preflight Endpoint and Minimal Preflight UI implemented and verified.
Backend: `SystemPreflightService` evaluates host laptop platform readiness (OS platform, Python runtime, VECTOR Local Agent internal status, Android ADB tool presence, iOS libimobiledevice tooling presence) without executing any device discovery commands (`adb devices`, `idevice_id -l`, `dumpsys`, `getprop` are strictly prohibited and tested). Missing platform tools return `NOT_INSTALLED` resulting in overall status `PARTIAL` rather than HTTP failure.
Frontend: `DiagnosticProvider` extended with `getPreflight()`. `LiveDiagnosticProvider` delegates to relative `/api/v1/system/preflight`. `DemoDiagnosticProvider` returns deterministic demo preflight fixture explicitly identified as demo data. `PreflightStatus` component renders overall readiness badge, individual check text statuses, actionable guidance, and recheck button with visible focus states and aria-live announcements.
All 15 repository verification checks passing.

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
- [x] local-agent: 55 passing tests (errors, models, security, API, preflight)
- [x] intelligence: 21 passing tests (fuzzy, genome, perturbation, baseline)
- [x] .env.example for local-agent
- [x] Phase 1A: Typed frontend API client (`types.ts`, `health.ts`, `useHealthCheck.ts`, `client.ts`)
- [x] Phase 1A: HealthStatus UI with accessible status badges, retry control, and responsive layout
- [x] Phase 1A: Frontend automated tests (15/15 tests PASS across 3 test suites)
- [x] Phase 1B: DiagnosticProvider typed contract (`DiagnosticProvider.ts`)
- [x] Phase 1B: LiveDiagnosticProvider delegating to real FastAPI health client
- [x] Phase 1B: DemoDiagnosticProvider with deterministic demonstration fixtures
- [x] Phase 1B: Central provider factory (`createDiagnosticProvider.ts`) and explicit mode resolution
- [x] Phase 1B: React provider context injection (`DiagnosticProviderContext.ts`, `DiagnosticProviderComponent.tsx`)
- [x] Phase 1B: HealthStatus mode indicator and semantic DEMO READY state display
- [x] Phase 1B: Frontend automated tests (36/36 tests passing across 4 test suites)
- [x] Phase 1C: Backend typed PreflightCheck and PreflightResponse models (`local-agent/src/vector_agent/models/preflight.py`)
- [x] Phase 1C: SystemPreflightService with OS, Python, Agent, ADB, and iOS environment checks (`local-agent/src/vector_agent/services/preflight.py`)
- [x] Phase 1C: Hardened prohibition against device enumeration commands in preflight service
- [x] Phase 1C: Route implementation for GET /api/v1/system/preflight (`local-agent/src/vector_agent/api/system.py`)
- [x] Phase 1C: Backend automated preflight tests (14 new tests in `test_preflight.py` and `test_api.py`)
- [x] Phase 1C: Typed frontend preflight API client and hook (`types.ts`, `preflight.ts`, `usePreflight.ts`)
- [x] Phase 1C: Extended DiagnosticProvider with `getPreflight()` in Live and Demo providers
- [x] Phase 1C: Deterministic demo preflight fixture clearly labeled as demo data (`fixtures.ts`)
- [x] Phase 1C: PreflightStatus accessible UI component with text statuses, visible focus, aria-live, and retry button (`PreflightStatus.tsx`)
- [x] Phase 1C: Frontend automated tests (11 new tests in `PreflightStatus.test.tsx` and `DiagnosticProvider.test.ts`, 47 total)

---

## Verified Features

- [x] local-agent: 55/55 tests PASS, 0 warnings (pytest)
- [x] local-agent: ruff check PASS (0 lint errors)
- [x] local-agent: ruff format PASS (all 39 files clean)
- [x] local-agent: mypy PASS (33 source files checked, 0 errors)
- [x] intelligence: 21/21 tests PASS (pytest)
- [x] intelligence: ruff check PASS (0 lint errors)
- [x] intelligence: ruff format PASS (all 17 files clean)
- [x] intelligence: mypy PASS (15 files checked, 0 errors)
- [x] frontend: npm install PASS
- [x] frontend: ESLint PASS (exit 0, 0 errors, 0 warnings)
- [x] frontend: TypeScript check PASS (tsc --noEmit, 0 errors)
- [x] frontend: Vitest PASS (47/47 tests in 5 test suites)
- [x] frontend: Production build PASS (`tsc -b && vite build`)
- [x] verify.ps1: 15/15 checks PASS

---

## Partially Implemented Features

- [ ] Device discovery (Android ADB): architecture in place, bridge stubs not yet implemented (Phase 2)
- [ ] Device discovery (iOS): architecture in place, bridge stubs not yet implemented (Phase 2)
- [ ] Scan state machine: state enum defined, orchestrator not yet implemented (Phase 3)
- [ ] NSGA-II full optimizer: objectives defined, main loop not yet implemented (Phase 5)
- [ ] Baseline B (Static Fuzzy), C (Evolutionary Linear), D (Logistic), E (RF): not yet implemented (Phase 5)
- [ ] Synthetic benchmark generator: not yet implemented (Phase 5)
- [ ] Frontend full UI (home, scan, results, methodology pages): not yet implemented (Phase 7)

---

## Not Started

- [ ] Android ADB bridge implementation (Phase 2)
- [ ] iOS libimobiledevice bridge implementation (Phase 2)
- [ ] DeviceCapabilityProfile real population (Phase 2)
- [ ] DiagnosticPlanner and TestRegistry (Phase 3)
- [ ] Real battery/storage/identity/sensor diagnostics (Phase 4)
- [ ] NSGA-II main optimizer loop (Phase 5)
- [ ] Synthetic benchmark generator (Phase 5)
- [ ] Full benchmark run with real metrics (Phase 6)
- [ ] VECTOR UI (home, scan, results, methodology pages) (Phase 7)
- [ ] Vercel deployment (Phase 8)
- [ ] Judge demo hardening (Phase 9)

---

## Known Bugs

None currently.

---

## Known Limitations

- Preflight environment verification checks only local tooling presence (`shutil.which` and harmless `--version`), NOT smartphone connectivity or trust authorization.
- In LIVE mode, the local FastAPI service must be running for ONLINE state.
- In DEMO mode, data is deterministic demo fixture data; no live hardware communication is performed.
- Automatic fallback from Live to Demo is explicitly disabled by design.
- See docs/LIMITATIONS.md for comprehensive list.
- Key: iOS restricts most hardware diagnostics, some physical defects are not detectable via USB.

---

## Technical Decisions Made

1. Python 3.14.7 environment (requires-python is ">=3.11" for CI compatibility)
2. FastAPI uses lifespan context manager (not deprecated on_event)
3. uv used for fast Python package management
4. All TOML files written without BOM (System.Text.UTF8Encoding(False))
5. Vite proxy to /api routes to localhost:8742 (avoids CORS in dev)
6. Frontend package name: "vector-frontend"
7. NSGA-II minimizes 4 objectives: prediction_error, perturbation_instability, rule_complexity, latency_proxy
8. UNSUPPORTED evidence uses 0.5 (neutral) not 0.0 (false penalty) in evidence vectors
9. All subprocess calls use argument arrays, shell=False mandatory
10. Health check client uses relative URL `/api/v1/health` and standard fetch with AbortSignal cancellation and configurable timeout
11. Explicit ConnectionState model: "CHECKING" | "ONLINE" | "OFFLINE" | "DEMO_READY"
12. React 19 safe async effect pattern in useHealthCheck and usePreflight avoiding synchronous setState in effect bodies
13. DiagnosticProvider abstraction with LiveDiagnosticProvider and DemoDiagnosticProvider
14. Explicit mode resolution via VITE_VECTOR_MODE (default: "live"); invalid values fail fast with a descriptive Error
15. Strict isolation: Demo mode never contacts live hardware; Live mode failure never falls back silently to demo mode
16. SystemPreflightService checks local laptop environment only; strictly NO device discovery commands (`adb devices`, `idevice_id -l`) are executed
17. Missing optional platform tools (ADB / iOS) produce status `NOT_INSTALLED` resulting in overall readiness `PARTIAL`, never an API failure

---

## Dependencies Installed

### Python (global system env)
- fastapi 0.142.1
- uvicorn 0.54.0
- pydantic 2.13.5
- pydantic-settings 2.15.0
- pytest 9.1.1
- pytest-asyncio 1.4.0
- httpx 0.28.1
- ruff 0.16.9
- mypy 2.3.1
- numpy 2.5.3
- scipy 1.18.1
- matplotlib 3.11.2
- uv 0.12.21

### Node.js
- Node.js 24.19.0 LTS
- npm 11.17.0
- React 19.2.8
- Vite 8.3.0
- TypeScript 6.0.2
- ESLint 10.10.0
- Vitest 3.2.7
- lucide-react 0.475.0
- @testing-library/react 16.3.0

Dependencies added in Phase 1C: NONE

---

## Required External Tools

| Tool | Purpose | Status |
|---|---|---|
| ADB (Android Platform Tools) | Android device communication | Checked via Preflight (NOT_INSTALLED / PASS depending on host PATH) |
| libimobiledevice | iOS device communication | Checked via Preflight (NOT_INSTALLED / PASS depending on host PATH) |
| Git | Version control | INSTALLED (C:\Program Files\Git) |
| Python 3.14.7 | Agent and intelligence | INSTALLED |
| Node.js 24.19.0 | Frontend | INSTALLED |
| uv | Python package management | INSTALLED |

---

## Android Device Status

Not connected during Phase 1C (preflight checks tooling only, no device enumeration).

---

## iPhone Device Status

Not connected during Phase 1C (preflight checks tooling only, no device enumeration).

---

## Frontend Status

Phase 1C Preflight UI and provider integration verified:
- Provider contract extended: `getPreflight(options?: CheckPreflightOptions): Promise<PreflightResult>`.
- `LiveDiagnosticProvider`: Calls relative `/api/v1/system/preflight` via `fetchPreflight()`.
- `DemoDiagnosticProvider`: Returns deterministic `DEMO_PREFLIGHT_FIXTURE` (`PARTIAL`, with simulated demo checks).
- `PreflightStatus`: Accessible component with text badges, visible focus outline, `role="status"`, `aria-live="polite"`, recheck button, and clear guidance for missing tools.
- App integration: `App.tsx` renders `HealthStatus` and `PreflightStatus`.
- 47 passing tests across 5 test suites (`health.test.ts`, `DiagnosticProvider.test.ts`, `App.test.tsx`, `PreflightStatus.test.tsx`, `HealthStatus.test.tsx`).
- ESLint: 0 errors, 0 warnings. TypeScript: 0 errors. Build: clean.

---

## Backend Status

FastAPI agent operational. Phase 1C system preflight implemented and verified:
- `PreflightCheck` and `PreflightResponse` typed Pydantic models in `models/preflight.py`.
- `SystemPreflightService` in `services/preflight.py` evaluating OS, Python runtime, agent readiness, ADB availability, and iOS tooling availability.
- Endpoint `GET /api/v1/system/preflight` mounted via `api/system.py`.
- Invariant verified: NO device discovery commands executed during preflight.
- 55 tests pass in local-agent (pytest). Ruff: 0 errors, formatted. Mypy: 0 errors across 33 files.

---

## Intelligence Engine Status

Fuzzy inference, genome encoding, perturbation engine, and Baseline A implemented. 21 tests pass.
NSGA-II main optimizer loop: NOT YET IMPLEMENTED (Phase 5).

---

## Benchmark Status

configs/attempt_01.yaml scaffold created.
Synthetic benchmark generator: NOT YET IMPLEMENTED.
No actual benchmark results yet.

---

## CI Status

.github/workflows/ci.yml created.

---

## Vercel Status

Not deployed. Phase 8.

---

## Custom Domain Status

Not configured.

---

## Privacy Page Status

Not implemented. Will be /privacy route in Phase 7.

---

## Terms Page Status

Not implemented. Will be /terms route in Phase 7.

---

## Exact Verification Commands Last Run

```powershell
$env:PATH = "C:\Program Files\nodejs;C:\Program Files\Git\cmd;" + $env:PATH; .\scripts\verify.ps1
# Result: 15/15 checks passed, exit code 0
# - Agent: Install deps (uv) [PASS]
# - Agent: Ruff lint [PASS]
# - Agent: Ruff format [PASS]
# - Agent: Mypy [PASS]
# - Agent: Pytest [PASS] (55/55)
# - Intelligence: Install deps [PASS]
# - Intelligence: Ruff lint [PASS]
# - Intelligence: Ruff format [PASS]
# - Intelligence: Mypy [PASS]
# - Intelligence: Pytest [PASS] (21/21)
# - Frontend: npm install [PASS]
# - Frontend: ESLint [PASS]
# - Frontend: TypeScript check [PASS]
# - Frontend: Tests [PASS] (47/47)
# - Frontend: Build [PASS]
```

---

## Last Successful

- All 15 verification checks passed via `.\scripts\verify.ps1` on 2026-09-30
- local-agent pytest: 55/55 PASS (0 warnings)
- intelligence pytest: 21/21 PASS
- local-agent ruff & format: PASS
- local-agent mypy: PASS (33 source files)
- intelligence ruff & format: PASS
- intelligence mypy: PASS (15 source files)
- frontend npm install: PASS
- frontend ESLint: PASS (0 errors, 0 warnings)
- frontend TypeScript check: PASS (0 errors)
- frontend Vitest tests: PASS (47/47 tests across 5 suites)
- frontend production build: PASS (`tsc -b && vite build`)

---

## Current Uncommitted Files

The working tree contains verified Phase 1C changes awaiting checkpoint:
- `docs/ARCHITECTURE.md` (modified)
- `docs/LIMITATIONS.md` (modified)
- `frontend/src/App.css` (modified)
- `frontend/src/App.tsx` (modified)
- `frontend/src/__tests__/HealthStatus.test.tsx` (modified)
- `frontend/src/__tests__/PreflightStatus.test.tsx` (created)
- `frontend/src/components/PreflightStatus.tsx` (created)
- `frontend/src/lib/api/client.ts` (modified)
- `frontend/src/lib/api/preflight.ts` (created)
- `frontend/src/lib/api/types.ts` (modified)
- `frontend/src/lib/api/usePreflight.ts` (created)
- `frontend/src/providers/DiagnosticProvider.ts` (modified)
- `frontend/src/providers/LiveDiagnosticProvider.ts` (modified)
- `frontend/src/providers/DemoDiagnosticProvider.ts` (modified)
- `frontend/src/providers/demo/fixtures.ts` (modified)
- `frontend/src/providers/__tests__/DiagnosticProvider.test.ts` (modified)
- `local-agent/src/vector_agent/api/health.py` (modified)
- `local-agent/src/vector_agent/api/system.py` (created)
- `local-agent/src/vector_agent/main.py` (modified)
- `local-agent/src/vector_agent/models/preflight.py` (created)
- `local-agent/src/vector_agent/services/preflight.py` (created)
- `local-agent/tests/test_api.py` (modified)
- `local-agent/tests/test_preflight.py` (created)
- `STATUS.md` (modified)

---

## Important Files Changed Recently

- `local-agent/src/vector_agent/models/preflight.py`
- `local-agent/src/vector_agent/services/preflight.py`
- `local-agent/src/vector_agent/api/system.py`
- `local-agent/tests/test_preflight.py`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/api/preflight.ts`
- `frontend/src/lib/api/usePreflight.ts`
- `frontend/src/components/PreflightStatus.tsx`
- `frontend/src/__tests__/PreflightStatus.test.tsx`
- `frontend/src/providers/DiagnosticProvider.ts`
- `frontend/src/providers/LiveDiagnosticProvider.ts`
- `frontend/src/providers/DemoDiagnosticProvider.ts`
- `STATUS.md`

---

## Next Recommended Action

Phase 1D - Phase 1 Error Handling and Integration Hardening

---

## Next Three Tasks

1. Review and consolidate error models, failure states, and boundary conditions across Phase 1.
2. Hardening integration between health, preflight, and provider abstraction.
3. Final Phase 1 verification pass prior to beginning Phase 2 device discovery.

---

## Do Not Redo

- Do not rewrite frontend/src/providers/ (DiagnosticProvider, LiveDiagnosticProvider, DemoDiagnosticProvider, createDiagnosticProvider, DiagnosticProviderContext, DiagnosticProviderComponent).
- Do not rewrite frontend/src/lib/api/ (types.ts, health.ts, preflight.ts, useHealthCheck.ts, usePreflight.ts, client.ts).
- Do not rewrite PreflightStatus, HealthStatus, or App.tsx.
- Do not rewrite SystemPreflightService or /api/v1/system/preflight route.
- Don't rewrite the error model — it is comprehensive and tested.
- Don't rewrite the device models — they implement all required fields.
- Don't rewrite the subprocess_policy.py — security requirements are correctly enforced.

---

## Risks

1. Python 3.14.7 is newer than required-python ">=3.11" — CI uses Python 3.12 which is fully supported.
2. libimobiledevice on Windows requires manual installation; preflight safely reports NOT_INSTALLED and overall PARTIAL if absent.
3. Device discovery is strictly deferred to Phase 2; preflight must never run device interrogation.

---

## Notes for Next AI Agent

Phase 1C is verified and awaiting user commit. The preflight endpoint (`/api/v1/system/preflight`) and minimal preflight UI evaluate host laptop platform readiness without executing device discovery commands. All 15 verify checks pass (55 backend agent tests, 21 intelligence tests, 47 frontend tests). The latest trusted baseline commit is dadc39a. Run `git rev-parse HEAD`, `git status`, and `.\scripts\verify.ps1` before continuing with Phase 1D.

---

## HANDOFF PROMPT

VECTOR Phase 1C is complete and verified awaiting user commit. Baseline commit is dadc39a. System preflight endpoint and minimal preflight UI are implemented with explicit separation between host environment readiness and device discovery. All 15 repository verification checks (.\scripts\verify.ps1) pass with 123 total automated tests (55 agent + 21 intelligence + 47 frontend). Check git status to review uncommitted Phase 1C files. Once committed by the user, proceed to Phase 1D: Phase 1 Error Handling and Integration Hardening.