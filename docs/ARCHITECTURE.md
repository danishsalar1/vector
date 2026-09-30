# VECTOR Architecture

## Overview

VECTOR (Verified Evidence-Based Computational Trust for Ownership Review) replaces seller claims about second-hand smartphones with measurable diagnostic evidence processed by a Perturbation-Aware Evolutionary Fuzzy Trust Engine.

## High-Level Architecture

```
[USB Cable]
    |
[Windows Laptop]
    |
    +-- [VECTOR Local Agent] (FastAPI, Python)
    |       |
    |       +-- [Android Bridge] (ADB / Platform Tools)
    |       +-- [iOS Bridge] (libimobiledevice)
    |       +-- [Diagnostic Engine] (capability-aware)
    |       +-- [Evidence Collector]
    |       +-- [Scan Orchestrator] (state machine)
    |       +-- [VECTOR Intelligence Engine] (fuzzy + evolutionary)
    |
    +-- [React Frontend] (Vite dev, or served by FastAPI in demo)
```

## Two Operating Modes

### Mode A: Local Hardware Mode (primary)

Used during actual hackathon demonstration.

- FastAPI binds to `127.0.0.1:8742` (loopback only).
- Real device connected via USB.
- ADB or libimobiledevice used to communicate with device.
- Frontend communicates with local agent via `/api/v1` proxy.

### Mode B: Vercel Public Demo Mode

Used for public hackathon evaluation link.

- No USB access possible (Vercel is a cloud host).
- Frontend uses `DemoDiagnosticProvider` instead of `LiveDiagnosticProvider`.
- All data is clearly labeled **DEMO DATASET**.
- Architecture, methodology, and benchmark visualizations are the primary value.

## Provider Abstraction

The frontend uses a clean provider abstraction so demo mode does not scatter `if (demoMode)` throughout components:

```typescript
export type ProviderMode = "live" | "demo";

export interface DiagnosticProvider {
  readonly mode: ProviderMode;
  checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult>;
  getPreflight(options?: CheckPreflightOptions): Promise<PreflightResult>;
  // Future milestones will extend this interface with getDevices(), startScan(), etc.
}

// Implementations:
// LiveDiagnosticProvider  -> /api/v1 on local FastAPI agent
// DemoDiagnosticProvider  -> static deterministic demo fixtures
```

### Mode Selection and Isolation

- Configured explicitly via `VITE_VECTOR_MODE` (`live` | `demo`), defaulting to `live`.
- Factory function `createDiagnosticProvider()` centralizes initialization.
- Invalid configuration fails fast with a descriptive error.
- **No Automatic Fallback:** If `LiveDiagnosticProvider` cannot reach the local agent, it reports `OFFLINE` or `ERROR`. It never silently switches to `demo` mode.

## System Preflight Service

The `SystemPreflightService` evaluates whether the host laptop environment is ready for future hardware operations before any smartphone scan begins.

### Environment Readiness vs. Device Discovery

There is a fundamental separation between environment checks and device discovery:
- **Environment Preflight (Phase 1C):** Answers *"Is the laptop prepared with necessary tools (Windows OS, Python runtime, local agent, ADB, iOS tooling)?"*
  - Checks executable presence safely using `shutil.which` and harmless `--version` invocations.
  - **Never** invokes `adb devices`, `idevice_id -l`, or device queries.
  - Absence of optional platform tools produces `NOT_INSTALLED` with overall status `PARTIAL`, never an API failure.
- **Device Discovery (Phase 2):** Answers *"Which specific smartphone is currently connected via USB, what is its authorization state, and what capabilities does it have?"*

Tool availability alone does not prove phone connection or authorization. Device discovery and interrogation belong strictly to Phase 2.



## Scan Lifecycle (State Machine)

```
IDLE
  -> DISCOVERING   (ADB/iOS device search)
  -> CONNECTED     (device found and identified)
  -> PROFILING     (building DeviceCapabilityProfile)
  -> PLANNING      (TestRegistry selects applicable tests)
  -> RUNNING       (diagnostic tests executing)
  -> SCORING       (evolutionary-fuzzy inference)
  -> REPORTING     (report generation)
  -> COMPLETE
  -> FAILED        (unrecoverable error)
  -> CANCELLED     (user or timeout)
  -> DISCONNECTED  (USB removed during scan)
```

## Capability-Aware Test Planning

Before running any test:

1. `DeviceCapabilityProfile` is built from device discovery.
2. Each capability is marked: `PRESENT | ABSENT | UNKNOWN | RESTRICTED`.
3. `TestRegistry` checks `diagnostic.supported(profile)`.
4. If `ABSENT` → mark `UNSUPPORTED` (never mark `FAIL`).
5. If `RESTRICTED` → mark `RESTRICTED`.
6. If `PRESENT` → plan and run the test.

**Critical invariant: UNSUPPORTED ≠ FAIL.**

A device without a barometer is not penalized for the missing barometer.

## Evidence Model

Every diagnostic result requires at least one `EvidenceRecord`:

```python
EvidenceRecord(
    diagnostic_id="battery",
    device_id="<masked>",
    source_type=EvidenceSourceType.ADB_DUMPSYS,
    source_name="dumpsys battery",
    collection_method="adb shell",
    raw_value="level: 83\nvoltage: 4127",
    normalized_value=0.83,
    reliability=0.95,
    confidence=0.90,
)
```

Synthetic evidence uses `EvidenceSourceType.SYNTHETIC_TEST_ONLY` and is technically separated from real hardware evidence.

## Intelligence Engine

### Offline Phase (Benchmark / Training)

```
SyntheticBenchmarkGenerator
    -> labeled (evidence, ground_truth) scenarios
    -> NSGA-II Optimizer
        -> population of fuzzy system configurations (genomes)
        -> evaluated on 4 objectives:
            1. prediction_error
            2. perturbation_instability
            3. rule_complexity
            4. latency_proxy
        -> Pareto-front selection
        -> best genome serialized to configs/attempt_XX.yaml
```

### Online Phase (Live Device Scan)

```
Collected Evidence
    -> normalized evidence vector
    -> load serialized FuzzyConfig
    -> FuzzyInferenceEngine.infer(evidence)
    -> (trust_score, confidence)
    -> explainable report
```

The expensive optimization runs **offline**, not during live scans.

## Security Model

- All subprocess calls use argument arrays (no `shell=True`).
- Device serials validated before use in commands.
- Output size capped at 512KB per command.
- Timeouts mandatory on all subprocess calls.
- IMEI and serial numbers redacted from logs.
- Local agent binds to loopback (`127.0.0.1`) by default.
- No arbitrary shell command execution through the API.

## API Design

Base path: `/api/v1`

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/system/preflight` | GET | Environment verification |
| `/devices` | GET | List connected devices |
| `/devices/{id}` | GET | Device details |
| `/devices/{id}/capabilities` | GET | Capability profile |
| `/scans` | POST | Start scan |
| `/scans/{id}` | GET | Scan status |
| `/scans/{id}/results` | GET | Full results |
| `/scans/{id}/events` | GET | SSE progress stream |

## Repository Structure

See the top-level `README.md` for the full directory layout.
