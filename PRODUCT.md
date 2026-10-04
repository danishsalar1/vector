# Product

<!-- impeccable:product-schema 1 -->

## Product Purpose

VECTOR (Verified Evidence-Based Computational Trust for Ownership Review) converts smartphone claims into measurable evidence. It connects to smartphones, discovers the device's actual capabilities, determines which diagnostics are applicable, collects evidence-backed diagnostic results, represents uncertainty and unsupported capabilities explicitly, and produces an explainable trust assessment.

VECTOR is being developed as a production-grade smartphone diagnostic product.

The existing implementation is preserved where it meets the production standard, audited aggressively, and refactored or replaced only where evidence shows it is necessary.

## Platform Strategy

VECTOR is Windows-first but not Windows-only.

### VECTOR Desktop

The immediate production host application. A React frontend communicates with a local FastAPI diagnostic agent.

Windows is the initial production platform because it currently provides the practical environment for:

- USB-connected device diagnostics
- Android ADB tooling
- local diagnostic orchestration
- local evidence processing
- report generation

macOS support is a future consideration.

### VECTOR Probe

A signed Android companion diagnostic application for deeper hardware verification when external interfaces alone cannot provide sufficient evidence. See the dedicated VECTOR Probe section below.

iOS Probe strategy will be developed later within Apple's supported restrictions.

### VECTOR Mobile

Potential future consumer applications for Android and iOS. These are not implemented and no timeline is established.

> Do not make cross-platform architectural changes without explicit authorization.

## Users

**Primary experience:**

- Individual used-smartphone buyers seeking an objective, evidence-backed trust assessment before purchase
- Individual sellers generating a shareable condition report to accompany a listing

The experience must remain understandable for non-technical users.

**The architecture must also be capable of supporting:**

- Refurbishers and resellers who need verifiable device condition records
- Repair and diagnostic shops running per-device or batch diagnostics
- Device trade-in businesses requiring standardized condition evidence
- Marketplace operators integrating device verification into their platform
- Enterprise refurbishment operations managing large-scale device intake
- Future batch workflows

Consumer-friendly experience with B2B-capable architecture.

> B2C vs B2B priority is UNDECIDED. Do not permanently resolve this split until commercial model decisions are made.

## Target Smartphone Platforms

Android and iOS are both first-class target smartphone platforms. Neither is commercially secondary.

Implementation follows a sequential strategy rather than attempting to build both transports simultaneously:

1. Shared platform-neutral domain contracts
2. Android implementation and validation
3. iOS implementation using the same domain contracts
4. Cross-platform regression

Android is implemented first because it provides broader diagnostic access, allowing the evidence and capability architecture to be validated before adapting to Apple's more restrictive environment. This sequence does not imply that iOS is less important.

### Platform-Neutral Diagnostic Core

The core diagnostic, evidence, and intelligence domain must not be tied directly to Android or iOS.

Platform-neutral domain concepts:

- DiagnosticResult
- EvidenceRecord
- DeviceCapability
- BatteryEvidence
- CameraEvidence
- SensorEvidence
- VerificationCoverage

Platform-specific implementation belongs beneath these interfaces:

- AndroidAdapter / AndroidDeviceBridge
- iOSAdapter / iOSDeviceBridge
- VECTOR Probe adapters

The Trust Engine consumes normalized evidence without needing to know whether the evidence came from any specific manufacturer or platform.

> Avoid intelligence-layer concepts such as AndroidTrustScore, iOSTrustScore, or AndroidCameraResult. Prefer platform-neutral abstractions.

## Three Levels of Verification

### Runtime Discovery

"What components and capabilities can VECTOR observe on this device?"

Can often work without catalog data.

### Functional Verification

"Does the discovered component actually respond or behave correctly?"

Can often work without catalog data.

### Factory / Reference Comparison

"Does the observed device match what this exact model is supposed to contain?"

Requires trustworthy reference data.

VECTOR must never infer factory truth merely from one connected phone. If trusted model reference data is unavailable, report reference comparison as unavailable or unknown. Do not treat lack of reference data as FAIL.

## Scan Architecture

### Standard Scan

Uses external and system-accessible diagnostics such as ADB and operating-system interfaces. Does not require VECTOR Probe where basic diagnostics can be performed without it.

### Deep Scan

Uses VECTOR Probe when additional on-device access or interaction is necessary. May enable additional diagnostics unavailable through external tooling alone.

> Do not invent exact diagnostic counts. Do not claim all Standard Scan or Deep Scan capabilities are already implemented.

### Scan Flexibility

The product must eventually support:

- Full Verification
- Category Verification
- Selected Diagnostics
- Single Component Test

The applicable test list is derived from:

- runtime capabilities
- diagnostic registry
- platform permissions and restrictions
- trusted model-profile enhancements

The frontend must not permanently hardcode the test list.

## VECTOR Probe

VECTOR Probe is a signed Android companion diagnostic application intended for deeper hardware verification when ADB and system interfaces alone cannot provide sufficient evidence.

VECTOR Probe may eventually support evidence collection for:

- camera
- microphone
- speaker
- display
- touch
- proximity
- ambient light
- accelerometer
- gyroscope
- magnetometer
- connectivity
- other permitted interactive hardware diagnostics

**Permanent Probe principles:**

- User consent required
- No root
- No exploit
- No security bypass
- No arbitrary command execution
- Collect only necessary diagnostic evidence
- Return structured evidence
- Removable after diagnostics where appropriate

VECTOR Probe is primarily an evidence collector. It must not calculate or own the final Trust Score.

Conceptually:

```
VECTOR Probe
    → structured evidence
    → VECTOR Desktop diagnostic engine
    → evidence normalization and confidence
    → Trust Intelligence
```

> VECTOR Probe is approved architecture. It is not yet implemented.

## Device Knowledge Strategy

Runtime capability discovery remains the primary source of truth for what a connected device exposes.

A production Device Knowledge Base is also planned. The catalog may provide:

- manufacturer
- marketing name
- model aliases
- model number
- codename
- region and variant information
- release family
- expected capabilities
- manufacturer specifications
- known quirks
- diagnostic overrides
- visual profile
- physical component coordinates

The catalog enriches diagnostics. It must not become the sole reason VECTOR can operate. An unknown compatible device must still receive generic runtime discovery and functional diagnostics wherever technically possible.

> Never treat absence of catalog data as hardware failure.

## Real-Time Diagnostic Visualization

VECTOR intends to provide hardware-location-aware diagnostic visualization.

When a diagnostic starts, the interface may visually route attention toward the physical component being tested. Examples: battery test visualization travels toward battery location; camera test transitions toward camera module; sensor test indicates relevant device location where meaningful.

**Permanent rule:** Diagnostic execution drives animation. Animation never drives diagnostic execution.

Real engine events produce states such as:

- test.started
- test.progress
- test.evidence
- test.completed
- test.failed
- test.inconclusive

The UI responds visually to those states. Never fake progress using arbitrary timers.

Reduced-motion accessibility is required in the eventual implementation.

> Final visual language is not defined yet. Production visual design will be defined in a later dedicated phase.

## Capabilities and Constraints

- Supports Android (via ADB / Android Platform Tools) and iOS (via libimobiledevice).
- Runtime capability discovery is the primary source of truth; VECTOR must not require a hardcoded entry for every phone before it can function.
- A scalable device catalog records known models, aliases, expected capabilities, visual profiles, quirks, and overrides — it enhances accuracy and presentation but is not a prerequisite for generic operation.
- Previously unseen compatible devices receive graceful generic diagnostic support.
- Local agent: Python 3.12+, FastAPI, uvicorn (Windows-first; macOS support is a future consideration).
- Frontend: React, TypeScript, Vite.
- Intelligence engine: NSGA-II multi-objective evolutionary optimizer + Sugeno-style fuzzy inference with perturbation testing.
- iOS restricts most hardware diagnostics; battery health is estimated only when telemetry is available.
- Some physical defects cannot be detected via USB.
- Battery charge percentage must never be presented as battery health.

## Positioning

VECTOR's meaningful differentiators:

- **Evidence-backed rather than claim-based** — every diagnostic result is traceable to measured hardware evidence
- **Capability-aware** — the test plan is discovered from the device at runtime; missing hardware is never penalized
- **Local-first** — real diagnostics run on the user's machine, not in a cloud pipeline
- **Privacy-conscious** — device identifiers are not persisted by default
- **Explainable** — trust assessments are always accompanied by a human-readable breakdown
- **Uncertainty-aware** — missing, restricted, or ambiguous evidence surfaces as explicit uncertainty, not false confidence
- **Perturbation-robust computational intelligence** — the engine is stress-tested against noise, missingness, contradictory evidence, and adversarial readings
- **Modular cross-device diagnostic architecture** — not tied to a fixed device list; works generically on compatible devices it has never seen before
- **Platform-neutral diagnostic core** — the intelligence and evidence domain is independent of any specific smartphone platform or manufacturer

> Licensing, pricing, commercial model, and open-source strategy are UNDECIDED. Do not record any of these as resolved.

## Brand Commitments

- **UNSUPPORTED ≠ FAILED.** A device without a sensor is never penalized for the missing sensor. This is a core design principle, not a footnote.
- **RESTRICTED means RESTRICTED.** Restricted diagnostic access must be reported as RESTRICTED, never silently passed or failed.
- **Demo mode must always be explicitly labeled DEMO DATASET.** No fabricated evidence, claims, or results may appear. Live mode must never silently fall back to Demo mode.
- **Local-first.** Diagnostic data does not leave the user's machine by default. Device identifiers (IMEI, serial, UDID, account information) must not be persisted unless a future product requirement explicitly justifies it and privacy/security design is completed.
- **Trust scores must always be accompanied by an explainable breakdown.** A number alone is not a VECTOR result. No trust score should imply certainty beyond the underlying evidence.
- **Diagnostic animations must reflect actual execution state.** An animation must never simulate completion of a diagnostic that has not run.
- **Every PASS must be backed by real evidence.** Missing or uncertain evidence must remain explicit and must never be resolved by assumption.
- **No silent false confidence.** If VECTOR cannot verify something, it must say so explicitly. Unknown must not silently become average.
- **Battery charge is not battery health.** Battery charge percentage must never be presented as a state-of-health measurement unless a legitimate health assessment independently supports that conclusion.
- **Model-specific profiles enhance runtime discovery; they do not replace it.** The catalog enriches; runtime capability discovery remains the primary source of truth.
- Name is all-caps: **VECTOR**.

## Product Quality

Production quality means:

- Evidence-backed behavior
- Explicit uncertainty
- Deterministic error handling
- Security boundaries
- Privacy-conscious architecture
- Complete regression testing
- Recoverable failures
- Maintainability
- Scalable device support
- No silent false confidence

If VECTOR cannot verify something, it must say so explicitly.

## Development Philosophy

- Architecture correctness is more important than maximizing feature count.
- Every phase receives focused tests and full regression testing.
- Cross-phase regressions receive high-capability review.
- New features must preserve previously verified behavior.
- Existing verified architecture is not rewritten merely because a new agent prefers another style.

## Commercial Status

> **Pricing model: UNDECIDED.**
> Potential models may later include consumer, professional/refurbisher, enterprise, per-report, subscription, or hybrid offerings. Do not select or imply one yet.

> **License: UNDECIDED.** Intellectual-property and patent strategy remains under evaluation.

> **Open-source strategy: UNDECIDED.**

## Design Status

The current frontend is functional engineering UI only. The premium production visual system, device visualization, diagnostic motion system, and final design language are intentionally not defined yet. Do not use the current UI as the permanent visual reference.

## Operating Context

- A user connects a smartphone via USB on a Windows machine; VECTOR discovers device capabilities and runs the applicable diagnostic plan.
- A seller or refurbisher generates a shareable report to accompany a device listing.
- A public demo surface may run explicitly labeled DEMO DATASET scenarios without a connected device, making the methodology and architecture accessible without hardware.

## Evidence on Hand

- Engineering and research validation infrastructure: benchmark scenarios covering healthy device, battery degradation, sensor failure, camera failure, conflicting evidence, adversarial readings, and distribution shift. These are research and engineering validation artifacts, not commercial market validation.
- VECTOR is benchmarked against 5 baseline algorithms; results are published only after running actual code.
- Initial prototype/reference devices: Redmi Note 14 Pro 5G (Android), iPhone 17 Pro (iOS). These were early prototypes only — VECTOR's production design is capability-driven, not model-specific.
- Docs: ARCHITECTURE.md, FORMULATION.md, LIMITATIONS.md, SOURCES.md, BENCHMARKS.md, PRIVACY.md.

## Product Principles

1. **Evidence over claims.** Every trust signal must trace to a measurable diagnostic result, not a seller assertion.
2. **Absence is not failure.** Unsupported capabilities are excluded from scoring, never penalized.
3. **Explainability is non-negotiable.** Any trust assessment without a human-readable breakdown is incomplete.
4. **Local-first and privacy-conscious.** Data stays on the user's machine by default; identifiers are not persisted without an explicit justified requirement.
5. **Robustness by design.** The engine is stress-tested against noise, missingness, contradictory evidence, and adversarial input before results are reported.
6. **Uncertainty is explicit.** Missing, restricted, or ambiguous evidence must surface as stated uncertainty, never as a silent pass, fail, or default.
7. **Generic before specific.** VECTOR provides useful diagnostics on any compatible device; device-specific profiles enhance but never replace runtime capability discovery as the source of truth.
8. **Platform-neutral core.** The diagnostic, evidence, and intelligence domain is independent of any specific smartphone platform or manufacturer.

## Accessibility & Inclusion

Accessibility is a product requirement. Semantic HTML, keyboard accessibility, visible focus, sufficient contrast, status text in addition to color, reduced-motion support, clear loading and error states, and appropriate ARIA are required. WCAG 2.1 AA is the baseline. Do not sacrifice accessibility for visual effects.
