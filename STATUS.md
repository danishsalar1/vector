# VECTOR STATUS.md

**Purpose:** This file allows any new agent or developer to continue work without reading the entire conversation history.

---

## Project

**VECTOR** – Verified Evidence-Based Computational Trust for Ownership Review  
Standardized diagnostics and verification for the second-hand smartphone market.

Hackathon challenge: Advanced Computational Intelligence — Hybrid Evolutionary-Fuzzy Frameworks (CIS track)

---

## Current Phase

PHASE 1A VERIFIED

---

## Last Updated

2026-09-30

---

## Last Green Commit SHA

d8c88df

---

## Current Branch

main

---

## Current Architecture Status

Foundation scaffolded and Phase 1A health handshake implemented. React frontend communicates reliably with FastAPI local agent via relative `/api/v1/health` through Vite dev proxy. All 15 verification checks passing.

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
- [x] frontend: Vitest PASS (15/15 tests in 3 test suites)
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

- [ ] DiagnosticProvider abstraction: Live vs Demo (Phase 1B)
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

- The local FastAPI service must be running for ONLINE state.
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
11. Explicit ConnectionState model: "CHECKING" | "ONLINE" | "OFFLINE"
12. React 19 safe async effect pattern in useHealthCheck avoiding synchronous setState in effect bodies

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

Not connected during Phase 1A.

---

## iPhone Device Status

Not connected during Phase 1A.

---

## Frontend Status

Phase 1A health handshake implemented and verified:
- Typed health API client (`frontend/src/lib/api/`) communicating with local agent via relative `/api/v1/health` request.
- Explicit connection states: CHECKING, ONLINE, OFFLINE.
- AbortSignal support on unmount and retry to prevent state update errors.
- Default 5000ms timeout handling with user-safe error messaging.
- Malformed response and HTTP non-success safely caught without crashing.
- Accessible `HealthStatus` UI with live status indicator, version/mode metadata display on ONLINE, clear actionable guidance on OFFLINE, visible keyboard focus state on Retry control, and semantic HTML adhering to restrained design system.
- 15 passing tests across 3 test suites (`health.test.ts`, `HealthStatus.test.tsx`, `App.test.tsx`).
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

.github/workflows/ci.yml created. Pushed to origin/main at commit d8c88df.

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
# - Frontend: Tests [PASS] (15/15)
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
- frontend Vitest tests: PASS (15/15 tests across 3 suites)
- frontend production build: PASS (`tsc -b && vite build`)

---

## Current Uncommitted Files

NONE (working tree clean before this metadata update).

---

## Important Files Changed Recently

- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/api/health.ts`
- `frontend/src/lib/api/useHealthCheck.ts`
- `frontend/src/lib/api/client.ts`
- `frontend/src/components/HealthStatus.tsx`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/src/__tests__/HealthStatus.test.tsx`
- `frontend/src/lib/api/__tests__/health.test.ts`
- `STATUS.md`

---

## Next Recommended Action

Phase 1B - Live/Demo Provider Abstraction

---

## Next Three Tasks

1. Design and specify DiagnosticProvider interface for Live and Demo modes (Phase 1B planning).
2. Implement LiveDiagnosticProvider (/api/v1 adapter) and DemoDiagnosticProvider (static fixture adapter).
3. Integrate DiagnosticProviderContext into frontend with comprehensive unit and integration tests.

---

## Do Not Redo

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

Phase 1A is verified, committed, and pushed at d8c88df. The health handshake operates between React frontend and FastAPI local agent via relative /api/v1/health proxied by Vite. All 15 verify checks pass. Do not implement device discovery, ADB, or iPhone bridges yet. The next task is Phase 1B: Live/Demo provider abstraction.

---

## HANDOFF PROMPT

VECTOR Phase 1A is complete, verified, committed, and pushed to origin/main at commit d8c88df, which is the latest trusted checkpoint. The frontend <-> FastAPI health handshake is implemented with a typed API client (types.ts, health.ts, useHealthCheck.ts, client.ts), accessible HealthStatus UI, and 15 frontend tests passing alongside 62 Python tests (41 agent + 21 intelligence). Full repository verification (.\scripts\verify.ps1) passes 15/15 checks with exit code 0. Before making any changes, the next agent must verify the repository baseline using .\scripts\verify.ps1. The next task is Phase 1B: designing and implementing the DiagnosticProvider abstraction (LiveDiagnosticProvider and DemoDiagnosticProvider).