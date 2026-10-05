---
name: vector-hard-bug
description: Disciplined debugging for hard VECTOR bugs (intermittent device state, stale sessions, evidence/status mismatches, LIVE/DEMO leaks, cross-phase integration failures) using Observe -> Execute -> Verify. Forbids shotgun edits, retries, fake defaults, broad catches, weakened assertions, and fallback state.
argument-hint: "[bug description or failing test]"
---

# VECTOR hard-bug protocol: Observe -> Execute -> Verify

Bug: `$ARGUMENTS`

Read `PRODUCT.md` and `STATUS.md` first. Inspect Git state before editing; if the working tree is dirty with changes you did not make, stop and report. Edit only if the user has authorized implementation for this bug and no other agent is writing to the checkout.

## 1. Observe (no edits yet)

Write down, before touching code:

- **Evidence:** exact reproduction output, failing test, log, or captured response (redact serials/IMEI/UDID).
- **Expected behavior** (cite the contract, `PRODUCT.md`, or `STATUS.md` semantics) and **observed behavior**.
- **Smallest reproduction** (ideally a failing test with fabricated identifiers).
- **Affected layer:** frontend / API / session manager / platform bridge / diagnostic / evidence / intelligence.
- **Violated invariant:** e.g. stale ID retargets a device; UNSUPPORTED mapped to FAIL; PASS without evidence; LIVE falls back to DEMO.
- **Explicit hypotheses**, ranked, each with a cheap test that would falsify it.

If a bug involves two previously completed phases interacting, inspect both contracts; do not patch one side blindly.

## 2. Execute

- Test hypotheses **one at a time**. Change one thing, observe, revert if disproven. No shotgun edits combining several theories.
- Prefer the smallest correction that restores the violated invariant. No opportunistic refactors, no scope expansion.
- Add a regression test that fails before the fix and passes after, when practical.
- **Never** hide a failure with: retries or sleeps, fake/default values, broad `except`, loosened or deleted assertions, skipped/xfail tests, or fallback state (especially LIVE -> DEMO).

## 3. Verify

- Regression test fails without the fix, passes with it.
- Focused tests, then affected-project regression, then `scripts/verify.ps1`, then `git diff --check`.
- Review the diff for unrelated changes. Report root cause, the invariant restored, and anything still unverified.
- Do not stage, commit, or push. Do not update `STATUS.md` until everything is green and the user approves.

## Escalation

Gemini handles routine fixes. Claude Sonnet debugs the difficult ones. Escalate to Opus only after concrete evidence that Sonnet cannot resolve it efficiently (hard concurrency, security, or trust-engine problems).
