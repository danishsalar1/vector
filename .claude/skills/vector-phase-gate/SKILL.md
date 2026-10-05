---
name: vector-phase-gate
description: Verify a completed VECTOR implementation phase - scope, focused tests, regression, scripts/verify.ps1, git diff --check, diff review, no weakened tests, no fake evidence or state, LIVE/DEMO isolation, no deferred features implemented. Returns PHASE GATE PASS or PHASE GATE FAIL. Does not stage, commit, or push.
argument-hint: "[phase name or scope description]"
disable-model-invocation: true
disallowed-tools: Edit Write NotebookEdit
---

# VECTOR phase gate

Phase under gate: `$ARGUMENTS`

This gate verifies; it does not fix. Do not edit source, tests, or `STATUS.md` here. Do not stage, commit, push, switch branches, or change the working tree. `STATUS.md` is updated only AFTER a PASS, as a separate localized edit.

## Procedure

1. Read `PRODUCT.md` and `STATUS.md` (note baseline SHA, "Do Not Redo", and "Intentionally Deferred"). Confirm the intended scope with the user's phase statement; if the scope is unclear, say so and stop.
2. Git state: `git status --short`, `git rev-parse --short HEAD`, `git diff --stat`. Identify files changed and confirm nothing is staged or committed unexpectedly. Any file outside the declared scope is a finding.
3. Run, in order, and record exact results:
   - focused tests for the new capability
   - affected-project regression (`local-agent`, `intelligence`, `frontend` as touched; full suites for the touched projects)
   - `scripts/verify.ps1` (note: it installs dependencies; run it from the repo root)
   - `git diff --check` (distinguish real whitespace errors from CRLF warnings)
4. Review the diff against `REVIEW.md` priorities:
   - tests not weakened, deleted, skipped, or loosened; negative tests exist for new failure paths
   - no fake evidence/state; every PASS has evidence; UNSUPPORTED/RESTRICTED/missing are not FAIL
   - no privacy regression (raw serial, IMEI, UDID, account data in DTOs/logs/repr/fixtures)
   - no stale-device hazards (stale IDs cannot retarget; stale sessions not CONNECTED)
   - LIVE/DEMO isolation; no silent fallback
   - shared contracts remain platform-neutral
   - subprocess policy intact (fixed exe, arg arrays, shell=False, bounded timeout/output)
   - no deferred feature accidentally implemented; no unrelated refactor
5. If any check could not be run or its result is unknown, that is a blocker (do not infer a pass).

## Output

List each check with its exact result. List blockers with `file:line`, observed behavior, and the smallest correction.

End with exactly one of:

`PHASE GATE PASS`

`PHASE GATE FAIL` followed by the blockers.

After PASS, remind the user: localized `STATUS.md` update next (after green only; no invented SHA), then user-authorized stage -> staged review -> commit -> push.
