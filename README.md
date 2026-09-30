# VECTOR

**Verified Evidence-Based Computational Trust for Ownership Review**

Standardized diagnostics and verification for the second-hand smartphone market.

---

## What Problem Does VECTOR Solve?

When buying a used smartphone, a buyer cannot independently verify:

- Device identity (is the IMEI genuine?)
- Battery condition (charge level ≠ battery health)
- Storage integrity
- Camera, microphone, speaker function
- Sensor availability
- Software tampering or modification
- Whether diagnostic claims are real or fabricated

VECTOR replaces seller claims with **measurable diagnostic evidence** collected automatically via USB.

---

## How VECTOR Works

```
Connect Device
    → Identify Platform (Android / iOS)
    → Discover Capabilities
    → Build Applicable Test Plan
    → Run Automatic Diagnostics
    → Collect Evidence
    → Estimate Evidence Confidence
    → Run Evolutionary-Fuzzy Reasoning
    → Generate Trust Score
    → Generate Explainable Report
```

Key principle: **UNSUPPORTED ≠ FAILED.** A phone without a barometer is not penalized for the missing barometer.

---

## Hackathon Context

VECTOR is an entry for the Advanced Computational Intelligence challenge:
**Hybrid Evolutionary-Fuzzy Frameworks** (CIS track).

### Computational Intelligence Architecture

VECTOR uses a **Perturbation-Aware Evolutionary Fuzzy Trust Engine**:

- **Fuzzy System**: Sugeno-style inference with triangular membership functions maps diagnostic evidence to trust degree.
- **NSGA-II**: Multi-objective evolutionary optimization simultaneously optimizes prediction accuracy, perturbation robustness, rule complexity, and inference latency.
- **Perturbation Engine**: Stress-tests the fuzzy model under noise, missingness, contradictory evidence, distribution shift, and adversarial readings.
- **Shift-Guided Mutation** (proposed): Per-feature mutation intensity adapts to detected distribution shift — directing evolutionary search toward features that need re-adaptation.

See [docs/FORMULATION.md](docs/FORMULATION.md) for the mathematical formulation.

---

## Reference Devices

| Device | Platform | Status |
|---|---|---|
| Redmi Note 14 Pro 5G | Android | Primary demo device |
| iPhone 17 Pro | iOS | Primary demo device |

VECTOR is capability-driven. It is not hardcoded to these models.

---

## Architecture

| Component | Technology |
|---|---|
| Local agent | Python 3.12+, FastAPI, uvicorn |
| Device bridge (Android) | ADB / Android Platform Tools |
| Device bridge (iOS) | libimobiledevice |
| Intelligence engine | Python, NumPy, NSGA-II |
| Frontend | React, TypeScript, Vite |
| CI | GitHub Actions |
| Public demo | Vercel |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

---

## Operating Modes

### Local Hardware Mode

The Windows laptop runs the VECTOR agent locally.

A real smartphone connects via USB-C.

All diagnostics run against the real device.

### Vercel Public Demo Mode

Deployed at: https://github.com/danishsalar1/vector (public demo URL TBD)

Shows demo scenarios clearly labeled **DEMO DATASET**.

The UI architecture, methodology, and benchmark results are accessible without a connected device.

---

## System Requirements

### Windows Laptop

- Windows 10 or 11
- Python 3.11+
- Node.js 22+ (for frontend development)
- Android Platform Tools (for Android devices)
- libimobiledevice (for iPhone)
- USB-C cable with data transfer support

### Android Device Setup

1. Enable Developer Options: Settings → About Phone → tap Build Number 7 times.
2. Enable USB Debugging: Developer Options → USB Debugging → On.
3. Connect via USB and accept the debugging authorization prompt.

### iPhone Setup

1. Connect via USB-C.
2. Unlock the iPhone.
3. Tap "Trust This Computer" when prompted.
4. Ensure libimobiledevice is installed on the laptop.

---

## Quick Start

```powershell
# 1. Clone
git clone https://github.com/danishsalar1/vector.git
cd vector

# 2. Bootstrap
.\scripts\bootstrap.ps1

# 3. Start local agent
cd local-agent
python -m vector_agent.main

# 4. Start frontend (separate terminal)
cd frontend
npm run dev
```

---

## Repository Structure

```
vector/
├── frontend/          # React / Vite frontend
├── local-agent/       # FastAPI Python agent
│   └── src/vector_agent/
│       ├── api/       # REST endpoints
│       ├── core/      # Config, errors, logging
│       ├── devices/   # Android & iOS bridges
│       ├── diagnostics/  # Diagnostic modules
│       ├── evidence/  # Evidence collection
│       ├── scan/      # State machine & orchestrator
│       └── security/  # Subprocess policy, redaction
├── intelligence/      # Evolutionary-fuzzy engine
│   └── src/vector_intelligence/
│       ├── fuzzy/     # Membership, inference
│       ├── evolution/ # NSGA-II, genome, objectives
│       ├── perturbation/  # Stress testing
│       └── baselines/ # Comparison baselines
├── benchmark/         # Benchmark generators and artifacts
├── tests/             # Integration and security tests
├── configs/           # Competition attempt configurations
├── docs/              # Technical documentation
├── scripts/           # Developer utilities
└── .github/workflows/ # CI
```

---

## Testing

```powershell
# Run all Python tests
cd local-agent && python -m pytest tests/ -v
cd intelligence && python -m pytest tests/ -v

# Run frontend tests
cd frontend && npm run test

# Run full verification
.\scripts\verify.ps1
```

---

## Benchmarks

See [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

Synthetic benchmark scenarios cover: healthy device, battery degradation, sensor failure, camera failure, conflicting evidence, adversarial readings, and distribution shift.

VECTOR is compared against 5 baselines. Results are only published after running actual code.

---

## Known Limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

iOS restricts most hardware diagnostics. Some physical defects cannot be detected via USB. Battery health is only estimated when telemetry is available.

---

## Privacy

VECTOR is local-first. Diagnostic data does not leave the laptop by default.

Device identifiers are redacted from logs. See [docs/PRIVACY.md](docs/PRIVACY.md).

---

## Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [FORMULATION.md](docs/FORMULATION.md) | Mathematical formulation |
| [LIMITATIONS.md](docs/LIMITATIONS.md) | Honest limitations |
| [SOURCES.md](docs/SOURCES.md) | Credits and references |
| [ATTEMPTS.md](docs/ATTEMPTS.md) | Competition attempt records |

---

## License

License not yet chosen. To be decided by the repository owner before public release.

---

## Status

See [STATUS.md](STATUS.md) for current development phase and handoff information.
