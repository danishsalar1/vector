# VECTOR Sources and Credits

This document credits all third-party algorithms, tools, datasets, and libraries used in VECTOR.

## Core Algorithms

### NSGA-II (Non-dominated Sorting Genetic Algorithm II)

**Reference:**  
K. Deb, A. Pratap, S. Agarwal, and T. Meyarivan,  
"A fast and elitist multiobjective genetic algorithm: NSGA-II,"  
IEEE Transactions on Evolutionary Computation, vol. 6, no. 2, pp. 182–197, Apr. 2002.  
DOI: 10.1109/4235.996017

**Status:** Established method. VECTOR implements a clean version for multi-objective fuzzy optimization. VECTOR does not claim NSGA-II as its invention.

---

### Sugeno-Type Fuzzy Inference

**Reference:**  
T. Takagi and M. Sugeno,  
"Fuzzy identification of systems and its applications to modeling and control,"  
IEEE Transactions on Systems, Man, and Cybernetics, vol. 15, no. 1, pp. 116–132, 1985.  
DOI: 10.1109/TSMC.1985.6313399

**Status:** Established method. VECTOR uses a Sugeno-style system with evolutionary-optimized parameters. VECTOR's contribution is the application to capability-aware smartphone trust scoring, not the underlying fuzzy inference methodology.

---

## Device Interfaces

### Android Platform Tools (ADB)

**Source:** Android Open Source Project  
**URL:** https://developer.android.com/studio/releases/platform-tools  
**License:** Apache 2.0

Used for device communication, capability discovery, and diagnostic evidence collection on Android.

---

### libimobiledevice

**Source:** libimobiledevice project  
**URL:** https://libimobiledevice.org/  
**URL:** https://github.com/libimobiledevice/libimobiledevice  
**License:** LGPL-2.1

Used for iOS device communication, pairing, and diagnostics via documented protocols.

**Note:** VECTOR uses the command-line tools (`ideviceinfo`, `idevicediagnostics`, `idevice_id`) which are legitimate, non-jailbreak interfaces.

---

## Libraries

### FastAPI

**URL:** https://fastapi.tiangolo.com/  
**License:** MIT

REST API framework for the local agent.

---

### Pydantic v2

**URL:** https://docs.pydantic.dev/  
**License:** MIT

Data validation and settings management.

---

### NumPy

**URL:** https://numpy.org/  
**License:** BSD-3-Clause

Numerical computation for fuzzy inference, genome encoding, and perturbation engine.

---

### SciPy

**URL:** https://scipy.org/  
**License:** BSD-3-Clause

Statistical utilities for benchmark evaluation.

---

### Uvicorn

**URL:** https://www.uvicorn.org/  
**License:** BSD-3-Clause

ASGI server for the FastAPI local agent.

---

### React

**URL:** https://react.dev/  
**License:** MIT

Frontend framework.

---

### Vite

**URL:** https://vite.dev/  
**License:** MIT

Frontend build tool.

---

### Lucide Icons

**URL:** https://lucide.dev/  
**License:** ISC

Icon library used in the frontend.

---

## Reference Products Studied

The following tools were studied for architectural comparison. No proprietary code was copied. No internal algorithms are claimed.

- **3uTools**: Windows phone management software. Architectural reference only.
- **iMazing**: iOS device management. Architectural reference only.
- **Cashify Diagnostics**: Used-phone diagnostic service. Problem domain reference only.

---

## VECTOR's Original Contributions

The following are VECTOR's proposed original contributions (validated only by what the implementation actually achieves):

1. **Capability-Aware Evidence Acquisition**: Automatically discovering actual hardware capabilities and excluding unsupported hardware from scoring without penalty.
2. **Confidence-Weighted Fuzzy Reasoning**: Separating Trust Score from Confidence as distinct outputs; accounting for evidence quality in confidence.
3. **Shift-Guided Mutation**: Adapting per-feature mutation intensity based on detected distribution shift (proposed; subject to empirical validation).
4. **Multi-Platform Diagnostic Evidence**: Unified evidence model across Android and iOS.
5. **Perturbation-Aware Joint Optimization**: Simultaneously optimizing accuracy, robustness, complexity, and latency as four independent objectives.

Claims marked as "proposed" are validated only when benchmark results confirm them.
