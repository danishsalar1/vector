# VECTOR Competition Attempts

Maximum competition attempts: 3

## Attempt 01

**Status:** CONFIGURATION DRAFT — not yet run

**Configuration file:** `configs/attempt_01.yaml`

### Configuration Summary

| Parameter | Value |
|---|---|
| Population size | 100 |
| Generations | 200 |
| Crossover probability | 0.9 |
| Mutation probability | 1/genome_length |
| Random seed | 42 |
| n_terms | 3 |
| n_params_per_term | 3 (triangular MF) |
| Perturbation type | NOISE (magnitude=0.1) |
| Benchmark seeds | 42, 1337, 2026 |

### Objective Results

*Not yet run. Will be updated after benchmark execution.*

| Objective | Value |
|---|---|
| Prediction error (MAE) | TBD |
| Perturbation instability | TBD |
| Rule complexity | TBD |
| Latency proxy | TBD |

### Baseline Comparison

*Not yet run.*

| Model | MAE | Robustness | Notes |
|---|---|---|---|
| Baseline A: Fixed Weighted | TBD | TBD | Static expert weights |
| Baseline B: Static Fuzzy | TBD | TBD | No optimization |
| Baseline C: Evolutionary Linear | TBD | TBD | No fuzzy membership |
| Baseline D: Logistic Regression | TBD | TBD | Statistical |
| Baseline E: Random Forest | TBD | TBD | ML |
| VECTOR (Attempt 01) | TBD | TBD | Evolutionary-fuzzy |

### Notes

Initial attempt. Establishes baseline configuration. No innovation techniques applied yet.
Shift-Guided Mutation not yet activated.

---

## Attempt 02

**Status:** NOT YET STARTED

*Configuration and results will be completed after Attempt 01 is evaluated.*

**What changed and why:** *(Required: one line describing change from Attempt 01.)*

---

## Attempt 03

**Status:** NOT YET STARTED

*Configuration and results will be completed after Attempt 02 is evaluated.*

**What changed and why:** *(Required: one line describing change from Attempt 02.)*
