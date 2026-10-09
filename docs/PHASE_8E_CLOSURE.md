# Phase 8E — Closure checkpoint

Date: 2026-10-10. Repository `C:\Users\danis\vector`, branch `main`.
Phase 8E checkpoint commit: `11720a0ebadf7510e8b06cfa3b2c1532c6d5bed7` (parent `e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`). This document does not assert
that the checkpoint or the closure documentation was pushed.
No Phase 8F work was started. No hardware was operated.

Document history: as first written (before the checkpoint commit existed) this header read "HEAD and
origin/main `e6e7ff4`... Nothing committed or pushed". That described the pre-checkpoint baseline
and became stale when the checkpoint was committed; it was corrected by the closure documentation
(AG-04). `e6e7ff4` is the baseline the work started from, not the checkpoint.

**Closure status: Phase 8E is CLOSED.** Implementation and remediation are committed in checkpoint commit `11720a0ebadf7510e8b06cfa3b2c1532c6d5bed7`. The independent post-remediation acceptance gate was performed on that commit and **PASSED** (0 BLOCKER, 0 HIGH, 0 MEDIUM; LOW/INFO findings below). The closure documentation is recorded in a separate documentation commit after the checkpoint. Closure does not assert physical-device qualification (NOT RUN) or any OEM authenticity or provenance verification: all 642 seed assertions remain unverified and non-authoritative. RV2-01 and RV-03 are required fixes before their functionality is exposed through any production API.

## Scope of Phase 8E (reconciled, user-approved)

OEM reference catalog, identity resolution, evidence-based comparison, and associated hardening.
Android provenance/anomaly collectors that the earlier roadmap placed under the 8E name are
**deferred, not completed**: Phase 8E implements no real OEM provenance collector and no anomaly
detection, and makes no authenticity, provenance or anomaly claim.

Reconciled roadmap (user-approved 2026-10-10): 8F — premium frontend, real diagnostics integration,
Quick Scan, optional Deep Scan, VECTOR Core animation. 8G — security, reliability, performance,
accessibility, physical-device qualification.

## FR-01 … FR-13 closure

| Finding | Closure |
|---|---|
| FR-01 … FR-11 | Fixed in `PHASE_8E_FINAL_REMEDIATION.md`; reproduced and re-probed at closure (hostile numeric spellings, malformed performance observations, platform/maker contradictions, ambiguous-variant mismatch withholding, untrusted `verified_claims`) |
| FR-12 | `local-agent/3.11/` (16 untracked mypy cache databases) preserved unchanged; excluded from the checkpoint; nothing deleted |
| FR-13 | The "Final Verification Suite Summary" in `PHASE_8E_RECOVERY.md` keeps its 2,559 / 107 counts as historical results and now carries a note pointing to the superseding counts below |
| PG-18 | `frontend/vitest.config.ts` left with its preexisting uncommitted modification; excluded from the checkpoint |
| PG-19 | Roadmap reconciled in `STATUS.md` (localized edit, authorized) |

## Verification at closure

| Check | Result |
|---|---|
| Integrity manifest `PHASE_8E_RECOVERY_INTEGRITY.json` | Regenerated after the documentation and `STATUS.md` edits; every listed file re-hashed |
| local-agent pytest | 2,727 passed (2,694 + 33 RV-01 cases), 1 existing httpx/Starlette warning |
| Ruff check / format, mypy (100 files) | clean |
| Intelligence | 21 passed |
| Frontend (scratch copy) | vitest 111 passed (12 files); `tsc -b` and ESLint clean. Last run before the RV-01 fix; NOT re-run (no frontend file changed since) |
| Reference mutation harness | control passes, 20/20 killed (re-run after the RV-01 fix). Separately, 7 scratch mutants of the RV-01 guard are all killed; 16 of the 33 new cases fail against the pre-fix `performance.py` |
| Android JVM | 141 passed on the earlier run; no Android or fixture file is in the diff, so NOT re-run |
| `scripts/verify.ps1` | NOT RUN (installs into system Python and npm); checks above were run individually |
| Physical-device qualification | NOT RUN |

## Focused post-remediation reviews (read-only, static)

Review 1 examined the staged remediation by reading code only (it could not execute probes). Its findings were checked by probe where stated. The FR-01..FR-13 fixes themselves were found sound and no invariant violation was found inside the remediation deltas. Outcome: FINDINGS REQUIRE ATTENTION (RV-01, RV-02).

Review 2 examined the RV-01 correction and its tests, again by reading only. Outcome: **NO BLOCKER/HIGH/MEDIUM FINDINGS**. These are focused reviews by the implementing session's delegated reviewer, not the independent re-gate of the remediation. That independent acceptance gate was subsequently performed and PASSED (section below).

| ID | Severity | Finding | State |
|---|---|---|---|
| RV-01 | MEDIUM | `performance.py` `evaluate_metric`: when a baseline lists `applicable_variant_ids` and `variant_id` is `None`, the variant guard is skipped and CONSISTENT / DIFFERS is returned (probe: obs 1.5 -> CONSISTENT, 99.0 -> DIFFERS; wrong variant -> REFERENCE_UNAVAILABLE, so only the unresolved case leaks). Same class as FR-06. Pre-existing logic, latent: nothing outside tests calls `evaluate_metric`. | FIXED (user-approved Option B): `evaluate_metric` returns VARIANT_AMBIGUOUS, observation preserved, when `applicable_variant_ids` is non-empty and the variant is None or empty. Verification and model checks still run first; a resolved variant outside the baseline is still REFERENCE_UNAVAILABLE; model-wide baselines and explicitly resolved variants are unchanged. Pinned by `local-agent/tests/test_phase8e_rv01.py` (33 cases, no existing test modified). |
| RV-02 | MEDIUM | An earlier draft of the `STATUS.md` gate line overclaimed (it read as if the remediation had passed an independent re-gate). | FIXED: the line now states the pre-remediation gate result only and records the re-gate as PENDING (historical state at the time; superseded by the independent acceptance gate PASS recorded below and in `STATUS.md`). |
| RV-03 | LOW | `import_catalog_payload` checks `curator_authorized` only on raw dict sources; `ReferenceSource` instances and direct `register_source` bypass it. Not reachable from HTTP or scan code (nothing outside the package imports it). The acceptance gate reproduced both bypasses: `register_source` and a `ReferenceSource` instance in an import payload both carry `verified_claims` into a production catalog. | OPEN (LOW). REQUIRED FIX BEFORE EXPOSURE: must be resolved before catalog import or source registration is reachable from any production API or scan path. Earlier recorded as "accepted for 8G"; superseded by this requirement. |
| RV-04 | LOW | The ambiguous-variant consensus limitation is appended to items that have no reference value (noisy, not false). | Open, cosmetic. |
| RV-05 | INFO | Pre-existing: battery `technology` is a device-controlled string echoed without an allowlist or length bound; it does not affect PASS. | Open, 8G. |
| RV2-01 | LOW | Pre-existing: `evaluate_metric` checks that the variant is in `applicable_variant_ids` but not that it belongs to `model_id`; needs an inconsistent caller pairing and no production caller exists. | OPEN (LOW). REQUIRED FIX BEFORE EXPOSURE: MUST be resolved before the performance-evaluation path is exposed through any production API (reproduced by the acceptance gate in a production-mode catalog: 120 mispaired cells in a 16,800-cell grid). Smallest fix: look up the variant in the catalog and compare its `model_id` with `model_id`. |
| RV2-02 | INFO | The new reason text said "Mismatch verdict withheld" although a match is withheld too. | FIXED: wording is now "Definitive verdict withheld". |

Note: `PHASE_8E_FINAL_REMEDIATION.md` is a point-in-time record. Its statements that `STATUS.md` is untouched, that nothing is staged, and that HEAD and origin/main are `e6e7ff4` were true when written and are superseded by this checkpoint.

## Independent post-remediation acceptance gate (PASSED)

Target: checkpoint commit `11720a0ebadf7510e8b06cfa3b2c1532c6d5bed7`. Read-only; the gate modified, staged, committed and pushed nothing. Verdict: **PASSED, 0 BLOCKER / 0 HIGH / 0 MEDIUM**; Phase 8E closure READY; Phase 8F technical readiness READY (separate explicit authorization required, subject to the required fixes below before exposure).

| Check | Gate result |
|---|---|
| FR-01..FR-13, RV-01 | Verified by independent probes, not by implementer statements |
| Variant-restricted performance evaluator | 16,800-cell grid (catalog mode x restricted/model-wide x 5 claim states x 2 distributions x 5 models x 7 variants x 12 observations): 0 unsupported definitive verdicts; unresolved variant on a verified, applicable restricted baseline always VARIANT_AMBIGUOUS; the only definitive-but-mispaired cells are RV2-01 |
| 642 unverified seed assertions | Audit file: 642, all UNVERIFIED_EXCLUDED_FROM_DEFINITIVE_COMPARISON; production seed: 0 `verified_claims`, 0 synthetic sources, 0 performance metrics; 36 resolve-and-compare reports (324 items) over all 6 seed variants: no CONSISTENT / DIFFERS outcome and no non-zero consistent/differs count |
| local-agent pytest | 2,727 passed, 1 existing warning |
| Ruff check / format, mypy (100 files) | clean |
| Intelligence | 21 passed |
| Frontend (scratch copy) | vitest 111 passed with both the committed and the uncommitted `vitest.config.ts`; `tsc -b` and ESLint exit 0 |
| `scripts/verify_reference_mutations.py` | control passes, 20/20 killed; mutant hashes and assertion counts identical to the committed record; live comparator unchanged |
| RV-01 guard removed | 16 of the 33 `test_phase8e_rv01.py` cases fail, as claimed |
| Gate's own harness (47 mutants of the remediation guards) | 37 killed, 3 detected through exception-type failures, 7 survived (redundant or unpinned-but-correct guards, see AG-01..AG-03) |
| Android JVM, `scripts/verify.ps1` | NOT re-run by the gate (no Android or fixture file in the checkpoint commit; `verify.ps1` installs into system Python/npm) |
| Physical-device qualification | NOT RUN |

### Findings preserved after the gate

| ID | Severity | Finding | State |
|---|---|---|---|
| RV2-01 | LOW | See the table above | REQUIRED FIX BEFORE EXPOSURE |
| RV-03 | LOW | See the table above | REQUIRED FIX BEFORE EXPOSURE |
| RV-04 | LOW | Ambiguous-variant consensus note appended to items without a reference value; the text is conditional ("where a reference value is present"), so noisy, not false | Open, cosmetic |
| RV-05 | INFO | Device-controlled battery `technology` string echoed unbounded (100,000 characters, control and bidi characters reproduced); bounded by the 512 KB subprocess cap, not rendered by the frontend, PASS unaffected | Open, 8G |
| AG-01 | LOW | The performance claim's entity binding (`performance.py`, `claim.entity_id == metric.metric_id`) is not pinned by any test (mutant survives); the guard itself works | Open, test gap |
| AG-02 | LOW | Correct but unpinned: battery voltage upper bound, "unrecognized battery status makes telemetry INCONCLUSIVE", rejection of boolean counts in the comparator | Open, test gap |
| AG-03 | INFO | The evaluator-level `not source.is_synthetic` check is unpinned (the existing corrupted-state test exercises the registration guard; under corrupted state the evaluator still returns REFERENCE_UNAVAILABLE); `isfinite` checks in `performance.py` and `comparator.py` are redundant | Open |
| AG-04 | LOW (documentation) | Stale commit state, manifest provenance and CRLF-dependent hashes | RESOLVED by this documentation (below), except the retained-artifact sub-item, which remains INFO |
| AG-05 | INFO | The test-only seed yields definitive items (20 observed), all labeled TEST-ONLY; `test_only=True` is not reachable from `src` outside the reference package | By design |
| AG-06 | INFO | Compat `compare()` treats a rear camera count of 0 as a valid count (can yield DIFFERS in a verified or test-only catalog); the evidence adapter admits only `feature_nfc` / `feature_barometer` | Open |

### AG-04 resolution (documentation only; no evidence rewritten)

- Stale commit-state statements in this document's header were corrected; the original wording is quoted in the document history above rather than silently overwritten. A parallel statement in `PHASE_8E_FINAL_REMEDIATION.md` is a point-in-time record and is annotated in the note above rather than edited.
- `docs/PHASE_8E_RECOVERY_INTEGRITY.json` is preserved byte-for-byte (SHA-256 `76d16c26b12b3cb3836b049a2ab2b6f1b218405a244ae524dbe633a705b3c509`). Its `head` and `origin_main` (`e6e7ff4`) are the pre-checkpoint baseline, not the checkpoint commit. Its file hashes are working-tree bytes on the Windows checkout (`core.autocrlf=true`). Compared with the checkpoint blobs, 42 of its 69 entries match exactly, 10 differ only by line endings (CRLF in the working tree versus LF as committed), and 17 are the preserved items outside the checkpoint (the 16 untracked `local-agent/3.11` cache databases and the uncommitted `frontend/vitest.config.ts`). The 10 line-ending-only entries will not verify on a clean or non-Windows checkout. Its `STATUS.md` entry (and that of any file edited later, including this document's own revision) describes the checkpoint state and no longer matches the working tree after the closure edit, by design.
- `docs/PHASE_8E_CLOSURE_INTEGRITY.json` (new) records the 51 files of checkpoint commit `11720a0ebadf7510e8b06cfa3b2c1532c6d5bed7` by git blob SHA-256 and git blob id, independent of line endings, and records the comparison above. It lists `STATUS.md` and this document as superseded after the checkpoint, so their checkpoint hashes remain valid historical evidence for that commit only. The commit that records this closure is not self-referenced (its SHA is not known to the document).
- The three existing assertions in `local-agent/tests/test_phase1_diagnostic_protocol.py` changed by the checkpoint (uncalibrated confidence and reliability published as `None`, MA-010) are itemized here: `test_evidence_confidence_propagated` became `test_uncalibrated_bridge_confidence_is_not_published` (asserts `confidence is None`), and `test_evidence_reliability_range` now asserts `reliability is None`.
- Not resolvable by documentation: the "7 scratch mutants of the RV-01 guard" have no retained artifact in the repository. The gate reproduced the kills independently and the 16-of-33 pre-fix failure count; the sub-item remains INFO.

## Remaining boundaries

All 642 seed assertions stay unverified and non-authoritative; the reference catalog is in-memory
only; MA-006 (Host validation) and MA-020 (registry bounds) belong to 8G; `TrustEngineStatus` stays
NOT_READY.
