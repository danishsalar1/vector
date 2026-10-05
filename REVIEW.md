# VECTOR review instructions

Review confirmed defects, not style. Do not propose rewrites, renames, or refactors unless current behavior is concretely unsafe or incorrect. Do not reward complexity. Every finding needs a `file:line` citation and an observed (not inferred-from-naming) behavior.

Read `PRODUCT.md` and `STATUS.md` first. Treat semantics in them as permanent unless the change explicitly and legitimately amends them.

## What is Important / BLOCKER here

In priority order:

1. **False PASS / false confidence.** A PASS without evidence; unknown, missing, or restricted data resolving to average/pass; trust certainty above evidence quality; battery percentage presented as health.
2. **Fabricated hardware/device state.** Invented capabilities, availability, timestamps, platform, progress, or results (backend or frontend).
3. **Stale device IDs retargeting devices.** Any path where an old or reused `device_id` can act on a different physical device, or a stale session reads as CONNECTED.
4. **Private/raw identifier leakage.** Raw ADB serial, IMEI, UDID, account data, or personal files in public DTOs, logs, errors, repr/serialization, fixtures, or persistence.
5. **LIVE/DEMO contamination.** LIVE silently falling back to DEMO, demo data unlabeled or mixed into live views.
6. **Privileged execution on offline/unauthorized/restricted devices.**
7. **Platform-specific assumptions leaking into shared contracts** (Android/iOS details in `DeviceSession`, `DiagnosticResult`, `EvidenceRecord`, `DeviceCapability`, `VerificationCoverage`, or intelligence code).
8. **Incorrect evidence semantics.** Wrong status mapping (UNSUPPORTED/RESTRICTED treated as FAIL, missing reference treated as failure), conflated verification levels, synthetic evidence presented as real.
9. **Weakened tests.** Deleted, loosened, skipped, or xfail'd assertions; tests that pass vacuously; new failure paths with no negative test.
10. **Broad exception handling hiding failures.** `except Exception`/bare except or catch-all that converts uncertainty into apparent success or a fake default.
11. **Subprocess/device-security regression.** `shell=True`, string commands, unbounded timeout/output, arbitrary ADB/shell endpoint, Android authorization bypass, iOS bypass.
12. **Fake UI diagnostic progress.** Timers/animations that imply execution or completion not reported by the diagnostic engine; missing reduced-motion handling.

Also Important: regressions of previously verified behavior (see "Do Not Redo" in `STATUS.md`), API contract breaks, races between discovery/session/diagnostic execution, and placeholder inference connected to live scans.

## Nit at most

Naming, formatting, comment wording, import order, and anything `ruff`/`eslint`/`tsc`/`mypy` already enforce. Cap nits at five; summarize the rest as a count. If only nits remain, lead with "No blocking issues."

## Do not report

- Generated files, lockfiles, `frontend/dist/`, `node_modules/`.
- Pure documentation wording in `STATUS.md` unless it makes a false claim (e.g., claims uncommitted work is pushed, invents a SHA, claims unverified hardware validation).
- Speculative future-phase concerns for features explicitly deferred in `STATUS.md`. Do flag deferred features that were accidentally implemented (scope creep).

## Verification bar

- Behavior claims need a `file:line` citation; name the concrete input/state that produces the wrong output.
- Prefer a failing-test sketch over prose when practical.
- State the smallest correction, not a redesign.
- If something could not be verified, say so; never guess.

## Output

Per finding: Severity (BLOCKER/HIGH/MEDIUM/LOW), file/location, observed behavior, why it matters, smallest correction. End with `SAFE TO PROCEED` or `BLOCKED - corrections required`.

## Note on scope of this file

Anthropic's managed GitHub Code Review reads this file automatically. The local `/code-review` command does not; the project's `vector-review` skill and `vector-adversarial-reviewer` agent read it explicitly.
