---
name: vector-production-engineering
description: Production engineering rules for VECTOR (smartphone diagnostics). Use when designing, implementing, debugging, or reviewing VECTOR backend, frontend, device discovery, diagnostics, evidence, capabilities, scan orchestration, Probe, trust scoring, or cross-phase integration. Also holds the model/quota policy and the Gemini-to-Claude handoff workflow.
when_to_use: Load before architecture-level or security/privacy-sensitive VECTOR work, before planning a phase, and when deciding which model should do a task.
---

# VECTOR production engineering (bridge)

This is a thin bridge. Do NOT restate the detailed rules here.

## Required reads (in this order)

1. `.agents/skills/vector-production-engineering/SKILL.md` — the **canonical detailed production engineering skill** (about 940 lines). Read it fully before architecture-level work; for a narrow task, read the sections relevant to it (e.g. 4 status semantics, 5 evidence, 14-17 security/privacy, 21-25 regression/phase/Git/STATUS).
2. `PRODUCT.md` — product intent and permanent brand commitments.
3. `STATUS.md` — current phase, baseline, verified behavior, "Do Not Redo", deferred work.

If the canonical skill and `CLAUDE.md` disagree, the stricter rule wins; report the conflict.

## Model and quota policy

Claude quota is scarce. Do not spend it on mechanical work.

| Model | Use for |
|---|---|
| Gemini 3.8 Flash High (Antigravity) | Bulk implementation, routine fixes, mechanical refactors within an authorized phase, test writing, frontend implementation. Primary workhorse. |
| Claude Sonnet | Adversarial review, architecture review, security/privacy review, contract review, difficult debugging. |
| Claude Opus | Escalation only: genuinely hard architecture, security, concurrency, or trust-engine problems, or failures Gemini/Sonnet cannot resolve efficiently. |

- Do not invoke subagents unless the task needs isolation or an independent review. Do not spawn parallel agents for work you can do inline.
- Use `/clear` between unrelated tasks. Compact only when continuing the same task.
- Usage credits (paid extra usage) must stay OFF. Never suggest enabling them.
- Model choice never reduces verification requirements.

## Gemini to Claude handoff

Exactly one write-capable agent may edit `C:\Users\danis\vector` at a time.

1. Gemini implements -> focused tests -> affected-project regression -> `scripts/verify.ps1` -> **Gemini STOPS** (no further edits, no staging).
2. Inspect Git state (`git status --short`, `git diff --stat`), then Claude runs a **read-only** adversarial review (`vector-review` skill or `vector-adversarial-reviewer` agent).
3. Routine finding -> Gemini fixes (Claude does not edit).
4. Genuinely difficult finding -> Claude may implement **only when the user explicitly authorizes it**, and only while Gemini is idle.
5. Re-verify (`scripts/verify.ps1`) -> `vector-phase-gate` -> localized `STATUS.md` update (only after green) -> user-authorized stage -> staged review -> commit -> push.

Never run Claude and Gemini writes concurrently in the same checkout. If a dirty tree appears that neither agent explains, stop and report.

## Phase boundary

Work only on the explicitly authorized phase. At the end: STOP and report per the canonical skill's section 31. Never start the next phase (the current next phase is deferred until the user authorizes it).
