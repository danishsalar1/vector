---
name: vector-review
description: Read-only adversarial review of VECTOR changes (working tree, staged diff, or a commit range) for false confidence, stale-device hazards, privacy leaks, LIVE/DEMO contamination, platform-neutrality breaks, and weakened tests. Never edits files unless the user explicitly authorizes fixes.
argument-hint: "[target: working tree (default) | --staged | <rev-range>]"
disable-model-invocation: true
disallowed-tools: Edit Write NotebookEdit
---

# VECTOR adversarial review (READ-ONLY)

Do not edit, stage, commit, or run any mutating command. Fixes happen only if the user explicitly authorizes them in a later message.

Target: `$ARGUMENTS` (default: uncommitted working-tree changes).

## Procedure

1. Read `PRODUCT.md`, `STATUS.md`, and `REVIEW.md` (the review priorities and severity calibration live there). Consult `.agents/skills/vector-production-engineering/SKILL.md` sections relevant to what changed.
2. Inspect Git state: `git status --short`, `git rev-parse --short HEAD`, `git diff --stat` (or `--staged` / the given range). Read the full diff, then read the surrounding code of every changed function, not just hunks.
3. Review for, in `REVIEW.md` priority order:
   - correctness and regressions of verified behavior (`STATUS.md` "Do Not Redo")
   - stale state and stale-device retargeting
   - concurrency/races (discovery vs session vs diagnostic execution)
   - platform-neutrality of shared contracts
   - privacy (raw serial/IMEI/UDID/account data in DTOs, logs, repr, errors, fixtures)
   - false-confidence semantics (PASS without evidence; UNSUPPORTED/RESTRICTED/missing treated as FAIL; unknown -> average; battery % as health)
   - fabricated frontend facts (availability, timestamps, platform, capabilities, progress)
   - LIVE/DEMO separation and silent fallbacks
   - evidence correctness (provenance, synthetic vs real, verification level)
   - API compatibility (including legacy compatibility routes)
   - security (subprocess policy, authorization, endpoints)
   - weakened tests and negative-test gaps
   - broad exception swallowing and default/fallback behavior
   - scope creep (deferred features implemented; unrelated refactors)
4. Verify each candidate against actual code (`file:line`). Drop anything you cannot substantiate. Do not rewrite style, do not propose redesigns unless current behavior is concretely unsafe or incorrect. Do not reward complexity.

## Output format

For each finding:

- **Severity:** BLOCKER | HIGH | MEDIUM | LOW
- **File/location:** `path:line`
- **Observed behavior:** concrete input/state -> wrong output
- **Why it matters:** which VECTOR invariant it violates
- **Smallest correction:** minimal change, not a redesign

If there are no findings, say so explicitly and list what you checked. State anything you could not verify.

End with exactly one line:

`SAFE TO PROCEED` or `BLOCKED - corrections required`

(BLOCKED if any BLOCKER or HIGH finding stands.)
