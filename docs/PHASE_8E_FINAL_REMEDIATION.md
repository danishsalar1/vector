# Phase 8E — Final remediation of the independent audit findings (FR-01 … FR-13)

Date: 2026-10-10. Repository `C:\Users\danis\vector`, branch `main`, HEAD and origin/main
`e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`. Nothing staged, committed or pushed.
No Phase 8F work was started. No hardware was operated.
`STATUS.md`, `AGENTS.md`, `PRODUCT.md`, `frontend/vitest.config.ts` and
`local-agent/3.11/` are untouched. Independent re-gate of this remediation: PENDING.

## Fixes

| ID | Change | File |
|---|---|---|
| FR-01 | Six guards pinned by negative tests (see below) | `local-agent/tests/test_phase8e_final_remediation.py` |
| FR-02 | Performance observations are sanitised before any result is built; NaN/inf/str/bool/huge ints become a missing observation for every outcome (unknown metric, unverified, wrong model, wrong variant, verified). Out-of-range comparison runs before `isfinite`, so a 10^400 int cannot overflow. | `reference/performance.py` |
| FR-03 | `reference_std_dev < 0` rejected at model validation; 0 allowed | `models/reference.py` (`PerformanceMetricReference.validate_range`) |
| FR-04 | `register_source` rejects synthetic sources unless the catalog is test-only. `import_catalog_payload(..., curator_authorized=False)` rejects any source that carries `verified_claims` unless the caller passes `curator_authorized=True` or the catalog is test-only. The seed payload carries none. | `reference/catalog.py`, `reference/importer.py` |
| FR-05 | A declared platform must agree with the catalogued maker (Apple ⇒ iOS, every other catalogued maker ⇒ Android). Disagreement ⇒ `CONFLICTING_IDENTIFIERS`; an agreeing platform may narrow candidates; UNKNOWN platform is unchanged. | `reference/resolver.py` (`_catalog_platform`) |
| FR-06 | While the variant is unresolved, a DIFFERS result becomes `VARIANT_AMBIGUOUS` with the observation preserved and an explicit "Mismatch verdict withheld" limitation. A match with every catalogued, individually-verified candidate stays a labeled consensus. | `reference/comparator.py` (`_withhold_ambiguous_mismatch`) |
| FR-07 | Every report is built by one `_build_report`; in a test-only catalog every item (including the unresolved-identity item) carries a `TEST-ONLY CATALOG` limitation as well as the report disclaimer. | `reference/comparator.py` |
| FR-08 | Battery integers must match `-?[0-9]{1,12}` ASCII; `8_3`, `+83`, Unicode digits, `1e2`, `0x53`, `83.0` and 5,000-digit strings are invalid fields (INCONCLUSIVE), never coerced. | `devices/android/bridge.py` |
| FR-09 | Only recognised plug sources are published (`0,1,2,4,8` → Unplugged/AC/USB/Wireless/Dock, or the same names). An unrecognised value is not echoed and does not change PASS. | `devices/android/bridge.py` |
| FR-10 | UNKNOWN and MISSING_DRIVER have explicit guidance; any other un-interpreted state shows its state name instead of a blank box. `AndroidConnectionState` gained the two members the provider already emitted. | `frontend/src/components/AndroidStatus.tsx`, `frontend/src/lib/api/types.ts` |
| FR-11 | OFFLINE wording no longer asserts that ADB reported the phone offline; it says the record is offline, the phone may be disconnected, and the response does not say which. No presence is invented. | `frontend/src/components/AndroidStatus.tsx` |
| FR-13 | Stale backend test count reconciled in `PHASE_8E_RECOVERY.md`. | `docs/PHASE_8E_RECOVERY.md` |

Deliberately not changed: FR-12 (`local-agent/3.11/` kept), PG-18 (`frontend/vitest.config.ts`
kept pending the user's decision), PG-19 roadmap naming, STATUS.md.

## Existing tests that had to change (intentional behaviour changes, no coverage removed)

- `test_phase8e_checkpoint2b.py::test_only_completed_feature_declarations_are_comparable_unit_control`:
  ambiguous-variant barometer mismatch is now `VARIANT_AMBIGUOUS` + "Mismatch verdict withheld" (FR-06).
- `test_phase8e_checkpoint2c.py::test_multiple_conflicting_sources_for_single_property`:
  counts the two conflict limitations explicitly and asserts the added single TEST-ONLY label (FR-07).
- `test_recovery_reference.py::test_verified_exact_claim_does_not_authorize_other_properties_or_values`:
  the curator import passes `curator_authorized=True` (FR-04).
- `test_recovery_reference.py::test_performance_baseline_cannot_bypass_source_authority`:
  registration of a synthetic source is now rejected up front (asserted); the original
  metric-level guard is still exercised by injecting the source into corrupted state (FR-04).

## Tests added

`local-agent/tests/test_phase8e_final_remediation.py` — 135 collected cases:

- FR-01a shared variant code never EXACT (both registration orders); FR-01b claim for another
  variant does not authorize (with positive control); FR-01c variant without spec/variant
  citations never authoritative; FR-01d ten invalid mmWave values (2, -1, 0.5, NaN, inf, strings,
  containers, None) and valid 0/1/True/False; FR-01e performance claim must bind
  `performance.baseline`; FR-01f negative observations are insufficient, not a mismatch.
- FR-02: 8 malformed observations × 5 scenarios = 40 cases.
- FR-03, FR-04 (five), FR-05 (four contradictions, three unchanged resolutions), FR-06 (five
  properties: withheld mismatch, kept consensus, exact-variant control), FR-07, FR-08 (ten bad
  spellings × four fields plus valid controls), FR-09.

`frontend/src/__tests__/final_remediation.test.tsx` — 4 tests (UNKNOWN, MISSING_DRIVER, OFFLINE
wording, uninterpretable state).

Non-vacuity: against the pre-remediation sources 46 of the new backend cases fail, and 4/4 frontend
tests fail against the HEAD `AndroidStatus.tsx`. Scratch mutants of the remediated code
(`PHASE_8E_FINAL_REMEDIATION_MUTATIONS.json`): 12 killed by assertion, 8 detected through a
non-assertion failure (DID NOT RAISE / exception; the strict harness classifies these INVALID,
not as kills), 0 survivors, control passes.

## Verification (this tree)

| Check | Result |
|---|---|
| local-agent pytest | 2,694 passed, 1 existing httpx/Starlette warning (was 2,559; +135) |
| Ruff check / format, mypy (100 files) | clean |
| Intelligence | 21 passed; ruff, format, mypy clean |
| Frontend (scratch copy) | vitest 111 passed (12 files); tsc app+root, ESLint, Vite build exit 0 |
| Android JVM (scratch copy, offline) | 141 tests, 0 failures/errors/skipped |
| `scripts/verify_reference_mutations.py` | control passes, 20/20 killed (`PHASE_8E_RECOVERY_MUTATIONS.json` regenerated; comparator `d383818f…`) |

Not run: `scripts/verify.ps1` (installs into system Python / npm), physical device qualification.

Remaining boundaries: all 642 seed assertions stay unverified and non-authoritative; reference
catalog is in-memory only; MA-006 (Host validation) and MA-020 (registry bounds) belong to 8G;
PG-18/PG-19 await the user.
