# Phase 8E — Closure checkpoint

Date: 2026-10-10. Repository `C:\Users\danis\vector`, branch `main`, HEAD and origin/main
`e6e7ff4cddf16e1797ce4b81e2d3ff7f5db6fba4`. Nothing committed or pushed by this document.
No Phase 8F work was started. No hardware was operated.

**Closure status:** implementation and remediation are committed in the Phase 8E checkpoint commit. The independent post-remediation acceptance re-gate is **PENDING**; it has not been performed or accepted, and full Phase 8E closure is NOT claimed.

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

Review 2 examined the RV-01 correction and its tests, again by reading only. Outcome: **NO BLOCKER/HIGH/MEDIUM FINDINGS**. These are focused reviews by the implementing session's delegated reviewer, not the independent re-gate of the remediation, which remains **PENDING** until it is actually performed and accepted.

| ID | Severity | Finding | State |
|---|---|---|---|
| RV-01 | MEDIUM | `performance.py` `evaluate_metric`: when a baseline lists `applicable_variant_ids` and `variant_id` is `None`, the variant guard is skipped and CONSISTENT / DIFFERS is returned (probe: obs 1.5 -> CONSISTENT, 99.0 -> DIFFERS; wrong variant -> REFERENCE_UNAVAILABLE, so only the unresolved case leaks). Same class as FR-06. Pre-existing logic, latent: nothing outside tests calls `evaluate_metric`. | FIXED (user-approved Option B): `evaluate_metric` returns VARIANT_AMBIGUOUS, observation preserved, when `applicable_variant_ids` is non-empty and the variant is None or empty. Verification and model checks still run first; a resolved variant outside the baseline is still REFERENCE_UNAVAILABLE; model-wide baselines and explicitly resolved variants are unchanged. Pinned by `local-agent/tests/test_phase8e_rv01.py` (33 cases, no existing test modified). |
| RV-02 | MEDIUM | An earlier draft of the `STATUS.md` gate line overclaimed (it read as if the remediation had passed an independent re-gate). | FIXED: the line now states the pre-remediation gate result only and records the re-gate as PENDING. |
| RV-03 | LOW | `import_catalog_payload` checks `curator_authorized` only on raw dict sources; `ReferenceSource` instances and direct `register_source` bypass it. Not reachable from HTTP or scan code (nothing outside the package imports it). | Open, accepted for 8G. |
| RV-04 | LOW | The ambiguous-variant consensus limitation is appended to items that have no reference value (noisy, not false). | Open, cosmetic. |
| RV-05 | INFO | Pre-existing: battery `technology` is a device-controlled string echoed without an allowlist or length bound; it does not affect PASS. | Open, 8G. |
| RV2-01 | LOW | Pre-existing: `evaluate_metric` checks that the variant is in `applicable_variant_ids` but not that it belongs to `model_id`; needs an inconsistent caller pairing and no production caller exists. | OPEN (LOW). MUST be resolved before the performance-evaluation path is exposed through any production API. Smallest fix: look up the variant in the catalog and compare its `model_id` with `model_id`. |
| RV2-02 | INFO | The new reason text said "Mismatch verdict withheld" although a match is withheld too. | FIXED: wording is now "Definitive verdict withheld". |

Note: `PHASE_8E_FINAL_REMEDIATION.md` is a point-in-time record. Its statements that `STATUS.md` is untouched and that nothing is staged were true when written and are superseded by this checkpoint.

## Remaining boundaries

All 642 seed assertions stay unverified and non-authoritative; the reference catalog is in-memory
only; MA-006 (Host validation) and MA-020 (registry bounds) belong to 8G; `TrustEngineStatus` stays
NOT_READY.
