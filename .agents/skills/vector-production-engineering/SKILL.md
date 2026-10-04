---
name: vector-production-engineering
description: Production engineering rules and architecture for the VECTOR smartphone diagnostic platform. Use whenever designing, implementing, debugging, testing, reviewing, refactoring, or extending VECTOR backend, frontend, Android/iOS integration, device discovery, diagnostics, evidence collection, capability discovery, scan orchestration, VECTOR Probe, trust scoring, fuzzy inference, evolutionary optimization, reporting, or cross-phase integration.
---

# VECTOR Production Engineering

This skill defines permanent engineering rules for VECTOR.

VECTOR is no longer a hackathon prototype.

It is being developed as a production-grade smartphone diagnostic product.

Read PRODUCT.md, STATUS.md, README.md, docs/ARCHITECTURE.md, and docs/LIMITATIONS.md before making architecture-level changes.

The repository is the source of truth.

---

# 1. Core Product Principle

VECTOR converts smartphone claims into measurable evidence.

The system must never imply certainty that the evidence does not support.

Permanent rule:

> Every PASS must have evidence.

Never fabricate:

- hardware results
- diagnostic results
- device capabilities
- battery health
- Trust Scores
- benchmark results
- model specifications
- connected-device state

If VECTOR cannot establish something reliably, use an explicit state such as:

- UNSUPPORTED
- RESTRICTED
- INCONCLUSIVE
- ERROR
- NOT_AVAILABLE
- UNKNOWN

depending on the established domain model.

Unsupported must never mean failed.

---

# 2. Runtime Capability Discovery Is Primary

VECTOR must not depend entirely on a database of known phones.

For every connected device:

1. identify the platform
2. discover actual runtime capabilities
3. determine which diagnostics are applicable
4. build a device-specific test plan

Device-specific catalog data is an enhancement.

The device catalog may contain:

- manufacturer
- marketing name
- model aliases
- internal model identifiers
- device codename
- regional variants
- expected capabilities
- known quirks
- diagnostic overrides
- visual profile
- physical component coordinates
- trusted manufacturer specifications

However:

> Runtime discovery is the primary source of truth for what is currently accessible on the connected device.

A previously unknown compatible phone must still receive useful generic diagnostics.

Model-specific comparison may only occur when trusted reference data exists.

Never treat absence of catalog data as hardware failure.

---

# 3. Three Levels of Verification

Keep these concepts distinct.

## Runtime Discovery

Example:

"Gyroscope detected."

Requires no known-device catalog entry.

## Functional Verification

Example:

"Gyroscope generated valid motion samples."

Can often be performed on an unknown compatible device.

## Reference / Factory Comparison

Example:

"This model is expected to contain a gyroscope."

Requires trusted model-specific reference data.

Never claim a factory-specification mismatch without a trustworthy reference profile.

---

# 4. Diagnostic Status Semantics

Maintain explicit diagnostic states.

Preferred conceptual states include:

- PASS
- DEGRADED
- FAIL
- UNSUPPORTED
- RESTRICTED
- INCONCLUSIVE
- ERROR
- SKIPPED

Do not collapse these into binary pass/fail when doing so loses important meaning.

Examples:

Hardware does not exist:
UNSUPPORTED

OS prevents access:
RESTRICTED

Evidence is insufficient:
INCONCLUSIVE

Diagnostic execution crashed:
ERROR

Actual component malfunction:
FAIL

---

# 5. Evidence Architecture

Every meaningful diagnostic result should eventually be backed by an EvidenceRecord or equivalent domain structure.

Evidence should support fields conceptually similar to:

- evidence_id
- diagnostic_id
- device_id
- source_type
- source_name
- collection_method
- timestamp
- raw value
- normalized value
- unit
- reliability
- confidence
- metadata
- redaction state
- error state

Evidence provenance matters.

Examples of evidence sources:

- ADB_GETPROP
- ADB_DUMPSYS
- ADB_SHELL
- ANDROID_SYSTEM_SERVICE
- VECTOR_PROBE
- LIBIMOBILEDEVICE
- IDEVICEINFO
- IDEVICEDIAGNOSTICS
- DEVICE_METADATA
- USER_ASSISTED
- BENCHMARK
- SYNTHETIC_TEST_ONLY

Synthetic evidence must never appear as real hardware evidence.

---

# 6. Battery Semantics

Battery charge percentage is NOT battery health.

Example:

Battery level = 82%

must never become:

Battery health = 82%

unless a legitimate state-of-health measurement independently supports that conclusion.

Battery telemetry PASS means only that valid battery telemetry was successfully acquired and parsed unless a deeper battery diagnostic explicitly establishes more.

Do not invent:

- state-of-health percentage
- cycle count
- design capacity
- remaining useful life
- battery quality

without supported evidence.

---

# 7. Live and Demo Separation

VECTOR has explicit LIVE and DEMO execution modes.

LIVE mode must use real local services and hardware evidence.

DEMO mode must use clearly labeled deterministic demonstration data.

Permanent rule:

> LIVE must never silently fall back to DEMO.

If LIVE fails:

show the failure.

Do not substitute synthetic success.

Demo data must never masquerade as real hardware evidence.

---

# 8. VECTOR Desktop Architecture

The production direction is Windows-first.

Conceptually:

React Frontend
    ↓
DiagnosticProvider
    ↓
FastAPI Local Agent
    ↓
Platform Adapter
    ↓
Device Bridge
    ↓
Capability Discovery
    ↓
Diagnostic Registry
    ↓
Scan Planner
    ↓
Evidence Pipeline
    ↓
Trust Intelligence
    ↓
Report

Windows is the initial production platform.

macOS and additional surfaces may be considered later.

Do not make cross-platform architectural changes without explicit authorization.

---

# 9. VECTOR Probe

VECTOR will support a signed Android companion diagnostic application called:

VECTOR Probe

The Probe is intended for deeper hardware verification when ADB alone cannot provide sufficient evidence.

VECTOR Probe may support:

- camera testing
- SensorManager measurements
- microphone testing
- speaker tests
- touch testing
- display tests
- proximity
- ambient light
- accelerometer
- gyroscope
- magnetometer
- connectivity
- interactive diagnostics

VECTOR Probe must:

- require user consent
- require no root
- use no exploit
- expose no arbitrary command execution
- collect only diagnostic information needed by VECTOR
- use structured evidence
- be removable after diagnostics if appropriate

VECTOR Probe is primarily an evidence collector.

It must NOT own the final Trust Score.

Conceptually:

VECTOR Probe
    ↓
Evidence
    ↓
Desktop Diagnostic Engine
    ↓
Trust Intelligence

---

# 10. Standard Scan and Deep Scan

Do not force VECTOR Probe installation merely to perform basic diagnostics.

Target architecture:

STANDARD SCAN
- ADB/system interfaces
- no companion app required where possible

DEEP SCAN
- VECTOR Probe available
- broader hardware verification

The UI may eventually explain:

"X tests available with Standard Scan"

and:

"Y additional tests available with VECTOR Probe"

Never invent these counts.

---

# 11. Diagnostic Registry

Diagnostics must be modular.

Avoid giant conditionals based on specific phone models.

Each diagnostic should conceptually define:

- id
- name
- category
- supported platforms
- required capabilities
- automation level
- prerequisites
- timeout
- supported(device)
- execute(device)
- evidence schema
- confidence policy
- failure semantics

The architecture should make adding diagnostic #31 routine rather than requiring product-wide rewrites.

---

# 12. Scan Planner

VECTOR must eventually support:

- Full Verification
- Category Verification
- Selected Diagnostics
- Single Component Test

The frontend must not hardcode which tests exist.

The Scan Planner should determine applicable tests from:

runtime capabilities
+
diagnostic registry
+
trusted device profile enhancements
+
platform restrictions

Unsupported diagnostics are excluded or explicitly marked, not treated as failed.

---

# 13. Diagnostic Animations

Visual diagnostic animations must represent real execution state.

Animation must NEVER drive the diagnostic.

Correct direction:

Diagnostic Engine
    ↓
events
    ↓
Frontend Animation

Example events:

- test.started
- test.progress
- test.evidence
- test.completed
- test.failed
- test.inconclusive

The frontend may later animate light paths between physical component locations.

However:

> A visual animation must never imply that a hardware test completed before the actual diagnostic reports completion.

No fake progress.

No fixed timer pretending a real hardware operation is executing.

Reduced-motion accessibility must eventually be supported.

---

# 14. Security

Local agent security is mandatory.

Prefer binding local services to:

127.0.0.1

unless a reviewed requirement explicitly changes this.

Subprocess execution must use:

- fixed executable
- argument arrays
- shell=False
- bounded timeout
- return-code checks
- bounded output
- safe decoding

Never expose:

executeShell(command)

executeAdb(command)

runCommand(text)

or any equivalent arbitrary-command API.

Frontend input must never become shell command text.

Device identifiers used internally must not be concatenated into shell strings.

---

# 15. Device Identifier Privacy

Avoid persisting:

- IMEI
- ADB serial
- UDID
- account information
- phone number
- personal files
- user application data

unless an explicitly approved product requirement justifies it and privacy/security design has been completed.

Use fabricated identifiers in fixtures.

Logs must redact sensitive identifiers where possible.

Diagnostic data should remain local by default.

---

# 16. Android Authorization

Never bypass Android's ADB trust model.

Possible Android device states must be handled explicitly:

- DEVICE
- UNAUTHORIZED
- OFFLINE
- NO_DEVICE
- MULTIPLE_DEVICES
- ERROR

An unauthorized device must result in user guidance to approve normal Android USB debugging authorization.

No exploit.

No root requirement.

No automatic trust bypass.

---

# 17. iOS Security

Never use jailbreak-dependent architecture for normal VECTOR operation.

Use legitimate Apple device services and supported local tooling.

When iOS prevents access to information:

report RESTRICTED.

Do not fabricate equivalent Android-level access.

---

# 18. Trust Intelligence

VECTOR's research direction includes:

Perturbation-Aware Evolutionary-Fuzzy Trust Intelligence.

Fuzzy reasoning exists to handle:

- uncertain evidence
- incomplete evidence
- noisy evidence
- contradictory evidence
- heterogeneous devices

Evolutionary optimization may tune:

- membership boundaries
- rule weights
- rule activation
- selected features
- grade thresholds
- confidence parameters

NSGA-II is the current planned multi-objective evolutionary approach unless later evidence justifies another method.

Potential objectives include:

- predictive error
- perturbation instability
- complexity
- inference latency
- critical-defect performance

Evolution occurs offline.

Live device scans should perform lightweight inference.

Do not rerun NSGA-II during every device scan.

---

# 19. Trust Score Truthfulness

A Trust Score must never imply precision unsupported by evidence.

Trust Score should eventually be accompanied by concepts such as:

- confidence
- verification coverage
- model-reference coverage
- important positive evidence
- risk evidence
- unsupported evidence
- restricted evidence

If evidence coverage is poor, confidence must reflect that.

Unknown must not silently become average.

---

# 20. Benchmarks

Benchmark results must come from executable experiments.

Never manually invent:

- accuracy
- F1
- robustness improvements
- latency
- benchmark victories
- calibration
- convergence

Synthetic benchmark data must be labeled synthetic.

Baselines must be honest.

Do not intentionally weaken competing baselines.

Potential baselines include:

- fixed weighted score
- static fuzzy system
- evolutionary linear score
- logistic regression
- random forest
- VECTOR evolutionary-fuzzy system

Results must be reproducible.

---

# 21. Full Regression Rule

Every completed engineering phase requires:

1. focused tests for the new capability
2. complete regression testing of all previously completed functionality

A phase is not verified merely because its own tests pass.

The whole product must remain coherent.

Preferred verification layers:

scripts/verify.ps1
- fast repository-wide verification

scripts/verify-full.ps1
- complete automated regression and integration validation

scripts/verify-hardware.ps1
- explicit real-device validation where hardware is required

Do not weaken tests to make a phase pass.

---

# 22. Cross-Phase Integration Failures

If a failure occurs because two previously completed phases interact incorrectly:

treat it as an integration problem.

Do not patch one side blindly.

Inspect both contracts.

Preserve existing verified semantics.

High-risk cross-phase integration fixes should be handled or reviewed using a high-capability Claude model.

---

# 23. Phase Execution

Work only on the explicitly authorized phase/subphase.

Before changes:

1. read STATUS.md
2. read PRODUCT.md
3. inspect relevant architecture documentation
4. run git status
5. inspect recent commits
6. run the existing verification baseline

If baseline is red:

STOP.

Do not begin the new phase until the cause is understood.

During implementation:

- avoid unrelated refactors
- do not opportunistically implement future phases
- keep changes bounded
- preserve verified behavior
- update tests with implementation

After implementation:

1. focused tests
2. complete regression
3. build/type/lint/security checks
4. update STATUS.md
5. inspect git diff
6. STOP at the phase boundary

Do not automatically begin the next phase.

---

# 24. Git Policy

Agents may inspect Git state.

Safe read-only commands include:

- git status
- git diff
- git diff --check
- git diff --stat
- git log
- git rev-parse

Do not automatically perform destructive Git operations.

Never run without explicit authorization:

- git reset --hard
- git clean -fd
- force push
- history rewriting
- destructive checkout/restore

Do not commit or push unless the current task explicitly authorizes it.

The user controls production checkpoints unless the prompt clearly delegates that action.

---

# 25. STATUS.md Handoff

STATUS.md is the durable cross-model handoff.

After every verified milestone record:

- current phase
- trusted baseline commit
- completed features
- verified features
- partial features
- known issues
- known limitations
- exact tests/results
- hardware verification
- Android status
- iOS status
- frontend status
- backend status
- intelligence status
- benchmark status
- dependencies
- files changed
- next authorized task
- notes for the next agent

Never claim uncommitted changes are already pushed.

Never invent the future commit SHA.

---

# 26. Model Responsibility

Use model capability strategically.

Architecture, security, hard debugging, algorithm design and cross-phase failure analysis should receive high-capability review.

Routine mechanical implementation may use a lower-cost model if authorized.

Model choice must never reduce verification requirements.

If model quota expires mid-phase:

- preserve working files
- record truthful partial status
- record exact unfinished work
- do not falsely mark the phase verified
- do not commit broken work
- continue from the same repository using STATUS.md

Changing models does not justify rewriting already verified architecture.

---

# 27. UI Product Standards

The current interface is an engineering UI, not the final VECTOR visual language.

Do not permanently anchor design decisions to the current prototype.

When production UI work is explicitly authorized:

avoid generic AI-generated design patterns.

Avoid:

- excessive gradients
- purple/neon AI styling
- glassmorphism everywhere
- giant rounded cards
- pill buttons everywhere
- fake statistics
- fake testimonials
- fake scans
- emoji icons
- meaningless animations
- excessive parallax
- fake progress
- vague startup buzzwords

Target:

- precision
- clarity
- restraint
- excellent typography
- premium hardware-software feel
- diagnostic credibility
- accessibility
- purposeful motion

Production visual design will be defined in a later dedicated phase.

---

# 28. Accessibility

Accessibility is a product requirement.

Use:

- semantic HTML
- keyboard accessibility
- visible focus
- sufficient contrast
- status text in addition to color
- reduced-motion support
- clear loading/error states
- appropriate ARIA only where required

Do not sacrifice accessibility for visual effects.

---

# 29. Commercial Claims

Pricing is currently UNDECIDED.

Open-source strategy is currently UNDECIDED.

Licensing is currently UNDECIDED.

Patent/IP strategy remains under evaluation.

Do not introduce claims such as:

- free forever
- open source forever
- patented
- certified
- medically validated
- market-leading
- industry-first

unless explicitly supported.

---

# 30. Definition of Production Quality

Production quality does not mean pretending errors are impossible.

It means:

- no silent false confidence
- explicit uncertainty
- predictable failure states
- security boundaries
- privacy-aware design
- reproducible tests
- evidence-backed results
- strong observability
- recoverable failure
- maintainable architecture
- complete regression testing

If something cannot be verified safely:

say so.

Never fake success.

---

# 31. Mandatory Stop Rule

At the end of the authorized phase:

STOP.

Report:

- task completed
- architecture changes
- files created
- files modified
- dependencies
- focused tests
- full regression result
- known issues
- known limitations
- hardware verification
- Git state
- next recommended task
- SAFE TO COMMIT: YES / NO

Do not begin the next phase without explicit user authorization.