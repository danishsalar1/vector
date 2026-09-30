# VECTOR STATUS.md

**Purpose:** This file allows any new agent or developer to continue work without reading the entire conversation history.

---

## Project

**VECTOR** – Verified Evidence-Based Computational Trust for Ownership Review  
Standardized diagnostics and verification for the second-hand smartphone market.

Hackathon challenge: Advanced Computational Intelligence — Hybrid Evolutionary-Fuzzy Frameworks (CIS track)

---

## Current Phase

PHASE 1B VERIFIED - AWAITING USER COMMIT

---

## Baseline Commit at Milestone Start

7844ebb

---

## Last Updated

2026-09-30

---

## Last Green Commit SHA

7844ebb

---

## Current Branch

main

---

## Current Architecture Status

Foundation scaffolded, Phase 1A health handshake verified, and Phase 1B DiagnosticProvider abstraction verified. Frontend cleanly abstracts diagnostic data sources into LiveDiagnosticProvider (local FastAPI agent via relative /api/v1/health) and DemoDiagnosticProvider (deterministic demonstration datasets). Mode selection is explicit via VITE_VECTOR_MODE with fail-fast validation and no automatic live-to-demo fallback. All 15 repository verification checks passing.

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
- [x] local-agent: 41 passing tests (errors, models, security, API)
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

---

## Verified Features

- [x] local-agent: 41/41 tests PASS, 0 warnings (pytest)
- [x] local-agent: ruff check PASS (0 lint errors)
- [x] local-agent: ruff format PASS (all 35 files clean)
- [x] local-agent: mypy PASS (30 files checked, 0 errors)
- [x] intelligence: 21/21 tests PASS (pytest)
- [x] intelligence: ruff check PASS (0 lint errors)
- [x] intelligence: ruff format PASS (all 17 files clean)
- [x] intelligence: mypy PASS (15 files checked, 0 errors)
- [x] frontend: npm install PASS
- [x] frontend: ESLint PASS (exit 0, 0 errors, 0 warnings)
- [x] frontend: TypeScript check PASS (tsc --noEmit, 0 errors)
- [x] frontend: Vitest PASS (36/36 tests in 4 test suites)
- [x] frontend: Production build PASS (`tsc -b && vite build`)
- [x] verify.ps1: 15/15 checks PASS

---

## Partially Implemented Features

- [ ] Device discovery (Android ADB): architecture in place, bridge stubs not yet implemented
- [ ] Device discovery (iOS): architecture in place, bridge stubs not yet implemented
- [ ] Scan state machine: state enum defined, orchestrator not yet implemented
- [ ] NSGA-II full optimizer: objectives defined, main loop not yet implemented
- [ ] Baseline B (Static Fuzzy), C (Evolutionary Linear), D (Logistic), E (RF): not yet implemented
- [ ] Synthetic benchmark generator: not yet implemented
- [ ] Frontend full UI (home, scan, results, methodology pages): not yet implemented (Phase 7)

---

## Not Started

- [ ] System preflight UI (Phase 1C)
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

- In LIVE mode, the local FastAPI service must be running for ONLINE state.
- In DEMO mode, data is deterministic demo fixture data; no live hardware communication is performed.
- Automatic fallback from Live to Demo is explicitly disabled by design.
- See docs/LIMITATIONS.md for comprehensive list.
- Key: iOS restricts most hardware diagnostics, some physical defects are not detectable via USB.

---

## Technical Decisions Made

1. Python 3.14.7 environment (not ideal, requires-python is ">=3.11" for CI compatibility)
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
12. React 19 safe async effect pattern in useHealthCheck avoiding synchronous setState in effect bodies
13. DiagnosticProvider abstraction with LiveDiagnosticProvider and DemoDiagnosticProvider
14. Explicit mode resolution via VITE_VECTOR_MODE (default: "live"); invalid values fail fast with a descriptive Error
15. Strict isolation: Demo mode never contacts live hardware; Live mode failure never falls back silently to demo mode

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

---

## Required External Tools

| Tool | Purpose | Status |
|---|---|---|
| ADB (Android Platform Tools) | Android device communication | NOT YET CHECKED |
| libimobiledevice | iOS device communication | NOT YET CHECKED |
| Git | Version control | INSTALLED (C:\Program Files\Git) |
| Python 3.14.7 | Agent and intelligence | INSTALLED |
| Node.js 24.19.0 | Frontend | INSTALLED |
| uv | Python package management | INSTALLED |

---

## Android Device Status

Not connected during Phase 1B.

---

## iPhone Device Status

Not connected during Phase 1B.

---

## Frontend Status

Phase 1B DiagnosticProvider abstraction implemented and verified:
- Provider boundary defined in `frontend/src/providers/`: `DiagnosticProvider` interface with `mode` and `checkHealth()`.
- `LiveDiagnosticProvider`: Delegates directly to `checkHealth()` relative `/api/v1/health` request without duplicating fetch logic.
- `DemoDiagnosticProvider`: Returns deterministic demonstration fixtures (`DEMO_READY`) without calling fetch or contacting any backend service.
- Mode selection: `createDiagnosticProvider()` evaluates `VITE_VECTOR_MODE` (default: `live`); throws descriptive Error on invalid mode values.
- Isolation: No automatic live-to-demo fallback; failed live checks stay explicitly `OFFLINE`.
- React integration: `DiagnosticProviderComponent` and `useDiagnosticProvider()` allow injection via props or context.
- UI: `HealthStatus` displays `Mode: LIVE` or `Mode: DEMO`, distinct semantic status badges (`ONLINE`, `OFFLINE`, `DEMO READY`), and distinct subtitles.
- 36 passing tests across 4 test suites (`health.test.ts`, `DiagnosticProvider.test.ts`, `HealthStatus.test.tsx`, `App.test.tsx`).
- ESLint: 0 errors, 0 warnings. TypeScript: 0 errors. Build: clean.

---

## Backend Status

FastAPI agent operational. No backend modifications were required. The existing `/api/v1/health` endpoint already adheres to the deterministic schema: `{"status": "OK", "timestamp": "...", "version": "0.1.0", "mode": "LIVE"}`. 41 tests pass.

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

.github/workflows/ci.yml created. Pushed to origin/main at commit d8c88df / 7844ebb.

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
# - Agent: Pytest [PASS] (41/41)
# - Intelligence: Install deps [PASS]
# - Intelligence: Ruff lint [PASS]
# - Intelligence: Ruff format [PASS]
# - Intelligence: Mypy [PASS]
# - Intelligence: Pytest [PASS] (21/21)
# - Frontend: npm install [PASS]
# - Frontend: ESLint [PASS]
# - Frontend: TypeScript check [PASS]
# - Frontend: Tests [PASS] (36/36)
# - Frontend: Build [PASS]
```

---

## Last Successful

- All 15 verification checks passed via `.\scripts\verify.ps1` on 2026-09-30
- local-agent pytest: 41/41 PASS (0 warnings)
- intelligence pytest: 21/21 PASS
- local-agent ruff & format: PASS
- local-agent mypy: PASS (30 source files)
- intelligence ruff & format: PASS
- intelligence mypy: PASS (15 source files)
- frontend npm install: PASS
- frontend ESLint: PASS (0 errors, 0 warnings)
- frontend TypeScript check: PASS (0 errors)
- frontend Vitest tests: PASS (36/36 tests across 4 suites)
- frontend production build: PASS (`tsc -b && vite build`)

---

## Current Uncommitted Files

The working tree contains verified Phase 1B changes awaiting checkpoint:
- `docs/ARCHITECTURE.md` (modified)
- `frontend/.env.example` (created)
- `frontend/src/App.css` (modified)
- `frontend/src/App.tsx` (modified)
- `frontend/src/__tests__/App.test.tsx` (modified)
- `frontend/src/__tests__/HealthStatus.test.tsx` (modified)
- `frontend/src/components/HealthStatus.tsx` (modified)
- `frontend/src/lib/api/types.ts` (modified)
- `frontend/src/lib/api/useHealthCheck.ts` (modified)
- `frontend/src/providers/DiagnosticProvider.ts` (created)
- `frontend/src/providers/LiveDiagnosticProvider.ts` (created)
- `frontend/src/providers/DemoDiagnosticProvider.ts` (created)
- `frontend/src/providers/createDiagnosticProvider.ts` (created)
- `frontend/src/providers/DiagnosticProviderContext.ts` (created)
- `frontend/src/providers/DiagnosticProviderComponent.tsx` (created)
- `frontend/src/providers/index.ts` (created)
- `frontend/src/providers/demo/fixtures.ts` (created)
- `frontend/src/providers/__tests__/DiagnosticProvider.test.ts` (created)
- `STATUS.md` (modified)

---

## Important Files Changed Recently

- `docs/ARCHITECTURE.md`
- `frontend/src/providers/DiagnosticProvider.ts`
- `frontend/src/providers/LiveDiagnosticProvider.ts`
- `frontend/src/providers/DemoDiagnosticProvider.ts`
- `frontend/src/providers/createDiagnosticProvider.ts`
- `frontend/src/providers/DiagnosticProviderContext.ts`
- `frontend/src/providers/DiagnosticProviderComponent.tsx`
- `frontend/src/providers/demo/fixtures.ts`
- `frontend/src/providers/__tests__/DiagnosticProvider.test.ts`
- `frontend/src/lib/api/useHealthCheck.ts`
- `frontend/src/components/HealthStatus.tsx`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `STATUS.md`

---

## Next Recommended Action

Phase 1C - System Preflight Endpoint and Minimal Preflight UI

---

## Next Three Tasks

1. Review and test GET /api/v1/system/preflight contract and requirements (Phase 1C planning).
2. Implement typed frontend preflight API client and provider integration.
3. Build minimal, accessible preflight status UI.

---

## Do Not Redo

- Do not rewrite frontend/src/providers/ (DiagnosticProvider, LiveDiagnosticProvider, DemoDiagnosticProvider, createDiagnosticProvider, DiagnosticProviderContext, DiagnosticProviderComponent).
- Do not rewrite frontend/src/lib/api/ (types.ts, health.ts, useHealthCheck.ts, client.ts).
- Do not rewrite HealthStatus component or App.tsx.
- Do not modify FastAPI health endpoint (/api/v1/health).
- Don't rewrite the error model — it is comprehensive and tested.
- Don't rewrite the device models — they implement all required fields.
- Don't rewrite the subprocess_policy.py — security requirements are correctly enforced.

---

## Risks

1. Python 3.14.7 is newer than required-python ">=3.11" — CI uses Python 3.12 which should be fine.
2. libimobiledevice on Windows requires manual installation (no winget package verified).
3. Production build and tests are verified locally; CI runner validation pending on pushed commits.

---

## Notes for Next AI Agent

Phase 1B is verified and awaiting user commit. The DiagnosticProvider abstraction cleanly separates LiveDiagnosticProvider (local FastAPI) from DemoDiagnosticProvider (deterministic fixtures) with explicit configuration and no automatic fallback. All 15 verify checks pass. The latest trusted baseline commit is 7844ebb. Run `git rev-parse HEAD`, `git status`, and `.\scripts\verify.ps1` before continuing with Phase 1C.

---

## HANDOFF PROMPT

VECTOR Phase 1B is complete and verified awaiting user commit. Baseline commit is 7844ebb. The DiagnosticProvider abstraction (LiveDiagnosticProvider and DemoDiagnosticProvider) is implemented with explicit mode resolution, no automatic fallback, and 36 passing frontend tests alongside 62 passing Python tests (41 agent + 21 intelligence). Full repository verification (.\scripts\verify.ps1) passes 15/15 checks with exit code 0. Check git status to review uncommitted Phase 1B files. Once committed by the user, proceed to Phase 1C: System Preflight Endpoint and Minimal Preflight UI.