---
paths:
  - "frontend/**"
---

# Frontend rules

- LIVE mode renders truthful backend state. It never silently falls back to Demo; failures are shown as failures. Demo is always labeled DEMO DATASET.
- Never fabricate availability, timestamps, platform, capabilities, progress, or results. If the backend did not send it, show it as unknown/unavailable.
- Never infer platform (or anything else) from opaque IDs such as `device_id`.
- Do not hardcode the diagnostic/test list; it is derived from backend capabilities and registry (once available).
- Diagnostic motion follows real lifecycle state from the engine (started / progress / evidence / completed / failed / inconclusive). No timers or animations that simulate execution or completion.
- Accessibility is required (WCAG 2.2 AA minimum): semantic HTML, keyboard support, visible focus, status text in addition to color, `prefers-reduced-motion` support, clear loading/error/empty states, ARIA only where needed. Also required: focus not obscured (2.4.11), a non-drag alternative for any drag interaction (2.5.7), pointer targets of at least 24 px with 44 px for primary touch controls (2.5.8), consistent help location (3.2.6), and no flashing content (2.3.1).
- Battery percentage is never labeled or styled as battery health. PASS wording must not overstate what the evidence proves.
- The current UI is an engineering UI, not the final visual language. For production UI work avoid generic AI-dashboard aesthetics: neon/glow and glassmorphism outside the exceptions below, giant pills/cards, fake stats/reviews/logos, emoji icons, decorative animation. Prefer restrained typography, neutral surfaces, one accent, real charts/tables, modest radii, simple icons.
- Approved exceptions (narrow): translucent material is permitted only on the floating control layer through the shared `GlassSurface` primitive (scan dock, popovers, dialogs, segmented controls, selected-node actions, consent surface). Never on data or evidence surfaces, never nested, at most 3 backdrop-filter layers visible at once, each with an opaque fallback for reduced transparency, increased contrast, forced colors and missing `backdrop-filter`. Luminous effects are permitted only inside the VECTOR Core overlay and the genuinely active component halo, driven solely by real scan state; no glow on text, buttons, cards or borders. Radii follow the concentric `SurfaceShape` scale; no capsule controls.
- Tests: cover loading, error, offline/unauthorized, empty, and LIVE-failure-does-not-become-Demo paths. Never weaken existing tests.
