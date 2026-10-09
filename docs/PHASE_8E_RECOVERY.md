# Emergency recovery — Stages A–D

Date: 2026-10-09. Canonical repository: `C:\Users\danis\vector`.
Branch `main`; HEAD and origin/main `e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`.
Independent review and formal gate: PENDING. No Phase 8F implementation authorized
until the user's frontend requirements are supplied. No hardware actions performed.

## Scope and protection

One implementation agent. Initial tree: preexisting modified
`frontend/vitest.config.ts`; untracked Phase 8E source/tests/handoffs and 16
`local-agent/3.11/cache.*.db` files. All preserved. `STATUS.md`, `AGENTS.md`,
`PRODUCT.md`, trust enrollment, signed fixtures, existing APKs and local config
were not intentionally edited. No staging, commits, pushes, branches, worktrees,
resets, restores, clean, stash, merge or rebase. Final hash proof accompanies this
handoff. The Desktop junction was not used.

Audit limitation: the initial SHA-256 manifest was captured before editing in a
per-command sandbox temp directory, which was subsequently removed by the runtime.
That full initial manifest is unavailable. `PHASE_8E_RECOVERY_INTEGRITY.json`
records final hashes, retained initial comparator hash and the external pre-catalog
source snapshot. Do not characterize this as complete retained before/after proof
for every original dirty file. Git confirms AGENTS/STATUS/PRODUCT remain unchanged;
the preexisting five-line vitest relaxation remains the only change to that config.

## A — Safety corrections

- MA-001: `devices/android/bridge.py` records invalid reported fields and removes
  invalid numeric readings from usable telemetry. A reported invalid field
  prevents PASS. Percent 0–100; explicit scale must be 100. Voltage must be
  positive and at most 20,000 mV. Temperature envelope is −100 to +200 Celsius.
  These deliberately broad **ingestion policy** bounds are not OEM operating
  limits, health classifications, or physical calibration. Invalid/malformed or
  unavailable readings produce INCONCLUSIVE, never hardware FAIL. Cold −40°C,
  hot 85°C, and charge 0/100 remain representable.
- Units checked against [AOSP HealthInfo](https://android.googlesource.com/platform/hardware/interfaces/+/master/health/aidl/android/hardware/health/HealthInfo.aidl):
  percent, millivolts, tenths Celsius. No conversion from charge to health.
- MA-002: the LIVE provider excludes retained OFFLINE Android sessions from
  active selection. Backend session history and epochs remain intact. Unauthorized,
  unknown and missing-driver states are retained; iOS entries are excluded from
  this Android-specific view. No shared reconciliation rewrite.
- MA-010: all six Android standard diagnostics publish null evidence reliability
  and confidence. The legacy battery response accepts/publishes null confidence;
  TypeScript validation is synchronized. No replacement numerical score.
- MA-011: battery telemetry is Level 1 RUNTIME_DETECTION. It does not exercise the
  battery under a controlled workload and therefore does not establish Level 2.
- MA-012: legacy Android discovery and battery endpoints are synchronous FastAPI
  handlers, using the framework's bounded worker pool. Battery collection rejects
  non-Android sessions and results collected across an epoch/connection change.

Before the battery correction, 12 new invalid-input cases reproduced false PASS;
7 positive/missing-data controls passed. After correction, focused legacy/parser/
diagnostic checks passed. New API tests use real discovery, capabilities, planning,
registry, scan execution, results and event routes with controlled subprocess
outputs. A held subprocess proves health remains responsive before release.

## B — Checkpoint 2C.1 mutation evidence

`scripts/verify_reference_mutations.py` copies production package and tests to an
external unique temporary directory. The live comparator is never edited. Every
mutation requires exactly one target, is compiled, and runs in a fresh Python
process with scratch-only package import verification. An unmodified control is
mandatory. A pytest hook distinguishes call-phase AssertionError from setup,
collection, syntax, import and other execution errors. Each run saves source,
pytest output, exact old/new target, source SHA-256 and actual killer node IDs.
Live source SHA-256 is checked after each run and in `finally`.

The original historical 16/16 claim is withdrawn in the 2C.1 handoff; its failed
gate remains recorded. The recovery run killed the intended sixteen mutants plus
four new guard mutants. Final source-specific evidence is recorded separately in
`PHASE_8E_RECOVERY_MUTATIONS.json`; survivors/equivalents would not count as kills.

The four new parameterized report regressions pin unknown multi-segment domains,
unknown fields within a known domain, and single/nested connectivity aliases.
They assert unavailable reference values, preserved conflict sources/limitations,
sibling isolation and report counts. Existing structural matching, variant scope,
epoch/challenge dedup and earlier passing corrections remain covered.

## C — Reference integrity

- Recursive catalog citation validation covers model base specifications, variant
  specifications and nested components, along with existing parent relationships.
  Incompatible source/entity/conflict IDs and manufacturer alias collisions reject.
  Conflict targets must exist. Standalone component conflicts are rejected because
  v1 has no globally unique component entity ID; use an actual model/variant target.
  Blank paths reject. Unknown nonblank paths retain the documented fail-closed policy.
- Import clone, validation and replacement now hold one RLock transaction. Invalid
  batches roll back; concurrent imports/registrations cannot overwrite accepted
  changes. A deterministic staging test proves a competing thread cannot acquire
  the transaction lock; accepted updates from both operations remain present.
- Production seed builds exclude synthetic sources/manufacturers/models/variants.
  Synthetic models are explicitly classified and require `test_only=True`.
  Synthetic citations under a real model reject even in test catalogs. Existing
  fixture tests explicitly opt in; comparator reports carry a TEST-ONLY disclaimer.
- Production definitive comparison requires source inspection recorded for the
  exact variant, property and canonical JSON reference value. A source's URL,
  classification or retrieval timestamp does not establish claim support. All
  contributing citations/candidates must qualify. These are local curator records,
  not cryptographic attestation or a public ingestion API. Source edits still reject
  incompatible duplicate IDs; curate a coherent fresh catalog for revised sources.
- Comparator rejects unknown/synthetic authority even when invalid state bypasses
  registration. Missing citations are not promoted into definitive verdicts.
  Candidate source sets include all contributors for SoC and camera comparisons.
- Flat counts reject strings, booleans, fractions, nonfinite values and invalid
  ranges. Numeric capability booleans are restricted to 0/1. Canonical normalized
  floats representing integral counts remain supported. No truthy-string coercion.
- Shared candidate properties can be compared as explicitly labeled model-level
  consensus while resolution remains ambiguous. Variant-specific disagreements
  remain unavailable/ambiguous; no candidate is silently chosen as exact.
- `network_configuration` conflicts affect network comparisons. SKU/region conflicts
  retain conservative blocking because reference selection can depend on the
  disputed identity mapping; a concrete disputed-SKU regression pins this boundary.
  Further identity-dependent narrowing is deferred, not claimed complete.
  Unknown unsafe paths remain conservative. Telemetry incompatibility limitations
  remain visible alongside reference-conflict limitations.
- Network presence comparison recognizes explicit supported configuration values;
  arbitrary prose cannot imply mmWave absence. Shared candidate network values
  produce a consensus item without inventing an exact variant.
- Reports now include `not_comparable_count` and `total_items`; every outcome is
  accounted for. Resolver/comparator use detached catalog snapshots. Registration
  copies mutable component maps; model/variant reads also return detached copies.

### Source truth and coverage (PG-07)

`PHASE_8E_SEED_SOURCE_AUDIT.json` inventories 642 source-associated leaf assertions
from every production manufacturer/model/variant and seven sources, including the
exact asserted value, entity/path and citations. All remain explicitly unverified
and excluded from definitive production comparisons. No false OEM facts were added.

Primary-source checks on 2026-10-09: Google's Pixel specifications page includes
the Pixel 7 Pro section; Apple's SP875 redirects to its iPhone 14 Pro specifications
page; Samsung's seeded S23 Ultra URL redirects to a general India Galaxy S listing.
Generic manufacturer portals and the FCC document identifier do not establish
every seeded property or regional SKU. No full per-variant source audit is claimed.
The assertion inventory preserves legitimate-but-unverified claims rather than
deleting them. Retrieved pages are not a substitute for exact claim verification.

Redmi Note 14 Pro 5G and iPhone 17 Pro were not added without sourced specifications.
Unknown compatible phones remain eligible for generic scans; reference comparison
truthfully remains unavailable.

### Persistence and performance (PG-16 / PG-20)

The reference catalog is an explicitly constructed in-memory library. It is not
loaded by a reference HTTP endpoint or a durable database. Imports last only for
that instance/process; restarts lose imported edits unless the caller reconstructs
the catalog. No persistence contract/database/cloud dependency was introduced.
The seed has no performance metric baselines. Performance tests use fabricated
distributions to exercise comparison rules; test durations measure software runs,
not phone performance, calibration or benchmark improvements.
The diff audit also reproduced an unverified registered performance distribution
yielding CONSISTENT. Production evaluation now requires a source-verification
record bound to the complete distribution/methodology JSON; synthetic citations
are rejected in production registration and test-only output is explicitly labeled.
Invalid benchmark observations become unavailable evidence rather than a definitive
comparison. No real benchmark baseline was added.

## D — Executed verification

Installed Python: `C:\Users\danis\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
Initial backend baseline 2,476 passed; frontend baseline 96 passed.
Interim full backend run (before the RR-01..RR-07 reconciliation): 2,551 passed, one existing
Starlette/httpx deprecation warning. Superseded: 2,559 passed after reconciliation (section E),
and 2,694 passed after the final remediation (`PHASE_8E_FINAL_REMEDIATION.md`). Section D's
frontend (107) and other counts are likewise the pre-remediation figures; the remediation
handoff holds the current ones.
Frontend: 107 passed; TypeScript and ESLint passed; Vite production build passed
with output under external temp. Intelligence: 21 passed; Ruff/format/mypy passed.
Android: offline `gradle testDebugUnitTest` in an external copy, 141 tests, zero
failures/errors/skips. Source/fixture/APK files in the canonical repo preserved.

Commands (no installs):

```text
python.exe -m pytest tests -q -o addopts='' -p no:cacheprovider --tb=short
python.exe -m ruff check src tests
python.exe -m ruff format --check src tests
python.exe -m mypy src --cache-dir <external-temp-cache>
python.exe scripts/verify_reference_mutations.py
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js .
node node_modules/vite/bin/vite.js build --outDir <external-temp-build>
gradle -p <external-copy>/android-probe --offline --no-daemon testDebugUnitTest
```

`scripts/verify.ps1` was inspected, **not run**: it invokes system pip/uv installs
and npm install. Its installed-tool checks were run individually. Original sandbox
Python startup and frontend realpath checks could not execute; approved execution
outside that sandbox ran the installed checks. No test failures were counted as
passes. Git diff checks likewise required read-only execution outside the sandbox.

| Workflow | Expected / actual | Executable evidence | Result |
|---|---|---|---|
| Android discovery → capabilities → plan → scan → results/events | Valid telemetry PASS; impossible charge INCONCLUSIVE, no raw serial | `test_recovery_safety.py::test_discovery_plan_scan_results_events_use_validated_telemetry` | PASS |
| Phone swap and mixed platforms/states | OFFLINE history does not block connected Android | `frontend/src/__tests__/recovery_safety.test.tsx` | PASS |
| API responsiveness | Health responds while battery subprocess is held | `test_recovery_safety.py::test_blocking_battery_subprocess_does_not_block_health` | PASS |
| Scan lifecycle / ownership / concurrency | Existing stale-session and same/separate-device invariants preserved | `test_phase5_scan_orchestration.py`, `test_phase6_orchestration.py` | PASS in full regression |
| iOS discovery / pairing / scans | Existing controlled service/route fixtures retain restrictions | `test_ios_session_and_pairing.py`, `test_ios_diagnostics.py`, `test_ios_expanded_diagnostics.py` | PASS in full regression |
| iOS authorization errors | Shared scan plan/start errors no longer give Android USB-debugging instructions | `test_recovery_safety.py::test_unauthorized_scan_guidance_is_platform_neutral` | PASS |
| Signed Probe replay | Java/Python fixture validation preserved | `test_phase8c_cross_language.py` and full Phase 8A/B/C regression | PASS |
| Evidence adapter | Canonical versus foreign-session evidence remains distinct | `test_phase8e_checkpoint2b.py` | PASS |
| Catalog / source authority / importer | Invalid batches reject, no false reference authority | `test_recovery_reference.py` | PASS |
| Provenance | Function remains separate from authenticity | Full Phase 8D suites | PASS |
| Future Phase 8F UI integration | User vision and implementation required | Not executed | NOT IMPLEMENTED |

## Pending decisions and remaining boundaries

- PG-18: leave `frontend/vitest.config.ts` unchanged. Recommendation: separately
  approve removal of the preexisting `server.fs.strict=false` relaxation; exclude
  it from this recovery finalization. No restore/edit performed.
- PG-19 roadmap proposal: describe the current implemented 8E library as **OEM
  reference catalog, identity resolution and comparison**. Historical STATUS calls
  8E Android Provenance / Anomaly Signals. Real OEM provenance collectors and
  anomaly detection are not implemented by this work. Proposed 8F is the user's
  diagnostic product UI/integration; proposed 8G is the specified control-plane
  hardening/lifecycle work. User approval is required to reconcile numbering/names
  and update STATUS. This proposal does not itself amend the roadmap.
- Phase 8D F-01/N-1/N-2 remain accepted domain debt. This repair adds no provenance
  API or authenticity claims; those items must be revisited before such exposure.
- Phase 8F inventory: real device/capability/scan APIs exist; reference resolver,
  comparator and performance manager are libraries. Probe HTTP operations require
  the existing local token and consent; no browser orchestration boundary has been
  added. The frontend still exposes its existing health/preflight/discovery/battery
  workflow plus the safety corrections. It is not the finished product dashboard.
- MA-006 Host validation, FG lifecycle/resource-bound work, iOS/unknown-state UX
  messaging and root verifier redesign remain within the later authorized stages,
  after frontend requirements and scope confirmation. Do not call them repaired.
- Physical qualification NOT RUN. CODE_TESTED only; authenticity UNKNOWN;
  trust engine NOT_READY; trust_score None. No live-device, pairing, permission,
  Probe installation or cloud/deployment actions performed.

SAFE TO COMMIT: NO pending independent review, formal gate, roadmap decision and
explicit Git authorization.

## E — Claude Independent Review Reconciliation & Gemini Continuation

The recovery candidate was reviewed by Claude (`docs/PHASE_8E_RECOVERY_CLAUDE_REVIEW.txt`), which identified findings RR-01 through RR-07. All findings were addressed surgically and verified on the frozen tree:

1. **RR-01 (Manifest discrepancies / writer freeze)**:
   - Writer stopped; live tree frozen.
   - `local-agent/src/vector_agent/scan/service.py` added to manifest (covers neutral iOS authorization message).
   - Re-hashed all 62 production, test, document and protected files into `docs/PHASE_8E_RECOVERY_INTEGRITY.json`.
   - `docs/PHASE_8E_RECOVERY_MUTATIONS.json` updated with live run.
2. **RR-02 (Battery status PASS with invalid/unknown status)**:
   - In `bridge.py`: `_parse_battery_output` now places unrecognised status and health values in `invalid_fields` and sets them to `None`.
   - In `bridge.py`: `_evaluate_battery_telemetry` only counts recognised AOSP charging statuses (`Charging`, `Discharging`, `Not Charging`, `Full` - codes 2–5) toward passing telemetry. Status `Unknown` (code 1) does NOT count toward passing telemetry.
   - Added 3 parameterized regression tests in `test_recovery_safety.py` covering codes 1, 99, and garbage with temperature omitted, asserting `INCONCLUSIVE`.
3. **RR-03 (Live view shows NO_DEVICE for phone offline in ADB)**:
   - In `LiveDiagnosticProvider.ts`: If `activeAndroid.length === 0 && allAndroid.length > 0`, return `overallState = "OFFLINE"`, with `targetDevices = allAndroid`.
   - Updated `recovery_safety.test.tsx` line 24 to assert `OFFLINE` with count 1.
   - Allows `AndroidStatus.tsx` offline guidance to render properly in LIVE mode when an attached phone is reported offline by ADB.
4. **RR-04 (mmWave item silently dropped under ambiguous variant)**:
   - In `comparator.py`: `_compare_network_configuration` now attaches `observed_value: bool(obs_mmwave)` under `VARIANT_AMBIGUOUS` and `REFERENCE_UNAVAILABLE`.
   - Added `else: items.append(reference.model_copy(update={"observed_value": bool(obs_mmwave)}))` when `reference_value is None`.
   - Added candidate consensus note when `target_variant is None` in match/differ reasons.
   - Added regression test `test_ambiguous_variant_with_unspecified_network_preserves_network_item`.
5. **RR-05 (MULTIPLE_CANDIDATES resolution not stopped early in comparator)**:
   - In `comparator.py`: Added `ResolutionStatus.MULTIPLE_CANDIDATES` to the early-return tuple alongside `UNKNOWN_DEVICE`, `UNSUPPORTED_DEVICE`, `CONFLICTING_IDENTIFIERS`.
   - Added regression test `test_multiple_candidates_resolution_returns_reference_unavailable_report`.
6. **RR-06 (mmWave text substring parsing)**:
   - Verified present safe behaviour: `comparator.py:81-89` matches explicit configurations (`5g sub-6`, `5g sub-6 + mmwave`, `5g mmwave + sub-6`, `5g mmwave`). Unspecified/unknown text returns `None` and fails closed to `REFERENCE_UNAVAILABLE`.
7. **RR-07 (Test quality gaps)**:
   - In `test_recovery_reference.py:294`: Mutated `cat._models["pixel-7-pro"]` directly instead of the detached copy from `get_model()`, proving genuine snapshot detachment.
   - In `test_recovery_safety.py`: Patched `AndroidDeviceBridge._require_adb` on lines 85 and 122, removing real ADB PATH dependency.

### Final Verification Suite Summary
> Historical record of the RR-01..RR-07 reconciliation. The counts below are preserved as
> results of that point in time and are superseded by the final remediation and closure:
> local-agent 2,727 passed (2,694 after the final remediation, plus 33 RV-01 cases), frontend 111 passed (12 test files), intelligence 21 passed,
> Android JVM 141 passed (unchanged), mutation harness control passes and 20/20 killed
> (see `PHASE_8E_FINAL_REMEDIATION.md` and `PHASE_8E_CLOSURE.md`).

- **local-agent**: 2,559 passed, 0 failed, 1 warning (exit code 0).
- **frontend**: 107 passed (11 test files), `tsc --noEmit` passed, `eslint .` passed, `npm run build` passed.
- **intelligence**: 21 passed, `ruff check` passed, `ruff format --check` passed, `mypy src` passed.
- **android-probe**: 141 passed in scratch sandbox (`testDebugUnitTest`), 0 failed, 0 skipped.
- **mutation harness**: `verify_reference_mutations.py` executed in scratch sandbox: CONTROL passed, 20/20 mutants killed (M01–M16, G01–G04). Live comparator hash invariant before and after.
- **Git status**: 0 staged files. No commits, pushes, resets, or tree manipulation performed.
