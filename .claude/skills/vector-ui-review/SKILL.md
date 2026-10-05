---
name: vector-ui-review
description: Review VECTOR frontend UI for non-technical used-phone buyers - hierarchy and readability, premium diagnostic aesthetic, responsiveness, accessibility, keyboard and reduced-motion support, loading/error/empty states, truthful state, and absence of fake progress/metrics or generic AI-dashboard styling. Read-only.
argument-hint: "[component, page, or diff to review]"
disable-model-invocation: true
disallowed-tools: Edit Write NotebookEdit
---

# VECTOR UI review (READ-ONLY)

Target: `$ARGUMENTS` (default: frontend changes in the working tree).

Do not edit files. Read `PRODUCT.md` (Design Status, Accessibility, Real-Time Diagnostic Visualization) and `.claude/rules/frontend.md` first. The current UI is an engineering UI, not the final visual language; judge against the target below, not against the existing prototype.

## Review dimensions

1. **Hierarchy and readability** for non-technical buyers: plain-language status, the key answer first, evidence/detail on demand, no jargon without explanation.
2. **Aesthetic:** premium diagnostic hardware/software feel - restrained typography, neutral surfaces, one accent, real charts/tables, modest radii, simple icons.
3. **Responsive behavior:** usable at narrow and wide widths; no clipped or overlapping content.
4. **Accessibility (WCAG 2.1 AA baseline):** semantic HTML, visible focus, contrast, status text in addition to color, correct ARIA only where needed.
5. **Keyboard support:** all actions reachable and operable, logical focus order, no traps.
6. **Reduced motion:** `prefers-reduced-motion` respected; information never conveyed by motion alone.
7. **Loading / error / empty states:** present, explicit, and honest (LIVE failure is shown as failure, never replaced by Demo).
8. **Truthful state:** nothing fabricated - availability, timestamps, platform (never inferred from opaque IDs), capabilities, results. Unsupported/restricted/unknown are distinct from failed. Battery percentage is not shown as health. Demo is labeled DEMO DATASET.
9. **No fake progress/timers:** no arbitrary timers or animation standing in for execution.
10. **No fake social proof:** no invented reviews, metrics, counts, or logos.
11. **Avoid:** excessive neon/glow/glassmorphism, giant pills/cards, gradients for their own sake, emoji icons, generic AI-dashboard look.

## Motion contract (for any future animation work)

Motion must consume real engine lifecycle events - `started`, `progress`, `evidence`, `completed`, `failed`, `inconclusive` - and nothing else. Animation never determines diagnostic timing, never implies completion before a `completed`/`failed`/`inconclusive` event, and must have a reduced-motion equivalent.

## Output

Per finding: Severity (BLOCKER/HIGH/MEDIUM/LOW), file/location, observed behavior, why it matters (user impact or violated principle), smallest correction. Truthfulness and accessibility violations are HIGH or above. End with `SAFE TO PROCEED` or `BLOCKED - corrections required`.
