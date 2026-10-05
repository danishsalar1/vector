# VECTOR — Claude Code project instructions

VECTOR is a production smartphone diagnostic product (evidence-based trust assessment for used phones). Not a prototype. The repository is the source of truth.

## Before any production work

1. Read `PRODUCT.md` and `STATUS.md`. For design/architecture/security-sensitive work, also load the `vector-production-engineering` skill (it points to the canonical detailed skill in `.agents/skills/`).
2. Inspect Git state first: `git status --short`, `git rev-parse --short HEAD`, `git log -3 --oneline`.
3. If the working tree is dirty and you did not make the changes, STOP and report. Never discard, overwrite, or "tidy" existing uncommitted work.
4. Work only on the explicitly authorized phase. Stop at the phase boundary. Do not start the next phase.

## Permanent principles

- Every PASS requires evidence. No silent false confidence.
- UNSUPPORTED != FAILED. RESTRICTED != FAILED. Unknown must never silently become average.
- Battery percentage != battery health. Battery telemetry PASS only means valid telemetry was collected.
- Missing reference/reference-profile/catalog data != failure.
- Demo data must never masquerade as live hardware. LIVE must never silently fall back to DEMO. Demo is always labeled DEMO DATASET.
- Trust certainty must never exceed evidence quality.
- Diagnostic engine drives animation; animation never drives diagnostics. No fake progress or timers.

## Architecture

- Shared/domain layer stays platform-neutral. `DeviceSession`, `DiagnosticDefinition`, `DiagnosticResult`, `EvidenceRecord`, `DeviceCapability`, `VerificationCoverage` are shared concepts. No `AndroidTrustScore`-style names.
- Android/iOS code lives below the platform-neutral contracts (bridges/adapters). No cross-platform architectural change without explicit authorization.
- Runtime capability discovery is operational truth. Catalog/reference profiles only enrich. Unknown compatible Android phones must work generically. Capability knowledge is refreshable and evidence-backed, never permanent truth.
- Keep three verification levels distinct: (1) runtime detection, (2) functional verification, (3) factory/reference comparison.

## Security and privacy

- Raw ADB serial stays internal and transient (never in public DTOs, logs, persisted data, repr/serialization).
- Do not expose, persist, or log IMEI, UDID, raw serial, account data, or personal files without an explicitly approved future requirement. Fixtures use fabricated identifiers.
- Subprocess policy: fixed executable, argument arrays, `shell=False`, bounded timeout, bounded output, return-code checks. No arbitrary ADB/shell/command endpoint, ever.
- Never bypass Android authorization (no root/exploit requirement). No iOS jailbreak or security bypass; report RESTRICTED instead.
- VECTOR Probe (not yet implemented): user consent, no root, no exploit, no arbitrary command execution; it collects evidence and never owns the Trust Score.

## Intelligence

- `TrustEngineStatus` stays NOT_READY until production inference is calibrated. Never connect placeholder inference to production scans.
- Never fabricate benchmark metrics. Synthetic data/results must be labeled synthetic. Live trust inference consumes normalized evidence only.

## Workflow

inspect -> implement -> focused tests -> affected-project regression -> `scripts/verify.ps1` -> `git diff --check` -> diff review -> localized STATUS update -> user approval -> stage -> staged review -> commit -> push

- Do not weaken or delete existing tests to get green. Add negative tests for new failure semantics.
- `STATUS.md` receives only localized edits, only after code and tests are green. Preserve historical content and existing encoding/BOM. Never invent a future commit SHA or claim uncommitted work is pushed.

## Git safety

- Never run destructive Git: `reset --hard`, `clean -fd`/`-fdx`, force push (incl. `--force-with-lease`), `branch -D`, reflog expiry, history rewrite. A project hook blocks these; do not work around it.
- Do not stage, commit, push, merge, rebase, restore, switch/checkout branches, or create/remove worktrees unless the user explicitly authorizes it for this task.
- One write-capable agent per physical checkout. Never let Claude and Antigravity/Gemini write to `C:\Users\danis\vector` at the same time.

## Model and quota policy (short form; details in the `vector-production-engineering` skill)

- Gemini (Antigravity) does bulk implementation. Claude Sonnet does review, architecture/security/privacy review, and hard debugging. Opus is escalation-only. Do not spend Claude quota on mechanical work.
- Do not spawn subagents unless needed. Usage credits stay OFF.

## UI

Premium diagnostic hardware/software feel: restrained typography, neutral surfaces, one accent, real charts/tables, modest radii, simple icons, accessibility and reduced motion. Avoid fake progress/timers/metrics/reviews/logos, neon/glow/glassmorphism, giant pills/cards, and generic AI-dashboard looks. `frontend/` is currently an engineering UI, not the final visual language.

## Scoped rules and review aids

Path-scoped rules in `.claude/rules/` load for `local-agent/**`, `frontend/**`, `intelligence/**`. `REVIEW.md` defines review priorities. Skills: `vector-review`, `vector-phase-gate`, `vector-hard-bug`, `vector-ui-review`. Subagent: `vector-adversarial-reviewer`.
