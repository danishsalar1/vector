---
paths:
  - "intelligence/**"
---

# Intelligence rules

- No placeholder inference in live scans. `TrustEngineStatus` stays NOT_READY until production inference is calibrated; do not wire anything into scan lifecycle before then.
- Trust certainty must never exceed evidence certainty. Poor coverage must lower confidence, and unknown must never silently become average.
- Unsupported, restricted, and missing evidence are not negative evidence. They reduce coverage/confidence; they never act as a failure signal.
- Never fabricate benchmark results (accuracy, F1, robustness, latency, calibration, convergence). Report only numbers produced by executed, reproducible code.
- Synthetic data and results are explicitly labeled synthetic (`SYNTHETIC_TEST_ONLY` evidence must never look like real hardware evidence).
- Baselines are honest and not intentionally weakened. Compare against the documented baseline set.
- Sugeno inference, NSGA-II evolution, and perturbation work are reproducible: seeded, deterministic, configuration recorded.
- Evolutionary optimization is offline. Keep optimization complexity out of lightweight live inference; never run NSGA-II per device scan.
- Live inference consumes normalized, platform-neutral evidence only (no Android/iOS-specific inputs or names).
- Every trust output ships with an explainable breakdown, confidence, and verification coverage.
