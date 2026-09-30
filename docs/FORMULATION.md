# VECTOR Mathematical Formulation

## Problem Statement

Given a connected smartphone, produce a Trust Score T ∈ [0, 1] and Confidence C ∈ [0, 1] from a vector of diagnostic evidence x ∈ ℝ^n.

Trust Score and Confidence are distinct quantities:
- A device can have T = 0.86 with C = 0.97 (high evidence, high trust).
- A device can have T = 0.86 with C = 0.41 (limited evidence, uncertain trust).

## Evidence Vector

Let x = (x₁, x₂, ..., xₙ) where each xⱼ ∈ [0, 1] is a normalized diagnostic signal:
- 0.0: strongly failing indicator
- 0.5: neutral / unsupported / missing
- 1.0: strongly passing indicator

**Critical convention:** UNSUPPORTED hardware maps to 0.5 (neutral), NOT 0.0. Penalizing missing hardware is architecturally incorrect.

## Fuzzy System

### Membership Functions

For each diagnostic variable xⱼ and linguistic term k (e.g., LOW, MEDIUM, HIGH):

    μⱼₖ(xⱼ; θⱼₖ) ∈ [0, 1]

VECTOR uses triangular membership functions (trimf) parameterized by θⱼₖ = (aⱼₖ, bⱼₖ, cⱼₖ):

    μⱼₖ(x) = clip(min((x - a)/(b - a), (c - x)/(c - b)), 0, 1)
    subject to: aⱼₖ ≤ bⱼₖ ≤ cⱼₖ

### Rule Activation

For rule r combining terms via product T-norm:

    αᵣ(x) = ∏ⱼ μⱼₖᵣ(xⱼ) for features j in rule r

### Sugeno Output

    S(x) = Σᵣ [αᵣ(x) · wᵣ · cᵣ] / (Σᵣ [αᵣ(x) · wᵣ] + ε)

Where:
- wᵣ ∈ [0, 1] is the rule weight (optimized by NSGA-II)
- cᵣ is the rule consequent (constant output per rule)
- ε = 1e-9 prevents division by zero

### Feature Selection

A binary mask fⱼ ∈ {0, 1} selects active features:

    x̃ = x ⊙ f

This allows the evolutionary optimizer to identify which diagnostic signals contribute most to trust accuracy.

## Evolutionary Optimization (NSGA-II)

### Genome Encoding

A flat real-valued genome g encodes:

1. Membership parameters: θⱼₖ for all (j, k) pairs — shape (n_features × n_terms × n_params)
2. Rule weights: wᵣ ∈ [0, 1] — shape (n_rules,)
3. Rule enable flags: eᵣ ∈ {0, 1} (threshold at 0.5) — shape (n_rules,)
4. Feature selection mask: fⱼ ∈ {0, 1} (threshold at 0.5) — shape (n_features,)

### Multi-Objective Fitness

NSGA-II minimizes a 4-objective vector:

    F(g) = (e₀, e₁, e₂, e₃)

| Objective | Symbol | Formula | Interpretation |
|---|---|---|---|
| Prediction error | e₀ | MAE(S(x), y) | Accuracy on benchmark labels |
| Perturbation instability | e₁ | Mean |S(x) - S(x̃)| where x̃ is perturbed | Robustness |
| Rule complexity | e₂ | Σeᵣ / n_rules | Model simplicity |
| Latency proxy | e₃ | Σfⱼ / n_features | Inference efficiency |

All objectives are minimized (standard NSGA-II convention).

### Algorithm Parameters (Attempt 01 — Initial)

| Parameter | Value |
|---|---|
| Population size | 100 |
| Generations | 200 |
| Crossover probability | 0.9 |
| Mutation probability | 1/genome_length |
| Tournament size | 2 |
| Random seed | 42 |
| n_features | TBD after benchmark design |
| n_terms | 3 (LOW, MEDIUM, HIGH) |
| n_rules | TBD |

These will be updated in `configs/attempt_01.yaml` when benchmark runs.

## Shift-Guided Mutation (Innovation)

VECTOR's proposed architectural innovation is Shift-Guided Mutation.

When diagnostic feature distributions shift between training and test populations (e.g., older devices vs. newer devices), standard evolutionary operators apply uniform mutation pressure regardless of which features changed.

Shift-Guided Mutation adapts per-feature mutation intensity based on detected distribution shift:

    Dⱼ = |μ_test(xⱼ) - μ_train(xⱼ)| / σ_train(xⱼ)

    pⱼ = clip(p₀ · (1 + λ · Dⱼ), p_min, p_max)

Where:
- Dⱼ: estimated distribution shift for feature j (normalized by training std)
- p₀: base mutation probability
- λ: shift sensitivity hyperparameter
- pⱼ: adapted per-feature mutation probability

Features that shifted most receive higher mutation pressure, directing the optimizer toward regions that need re-adaptation.

**Assumptions:**
- Distribution shift is estimated from population statistics, not individual samples.
- The clamping ensures mutation probability remains in a safe range.
- This is validated empirically before being claimed as a contribution.

## Confidence Computation

Confidence C accounts for evidence quality:

    C = (1/n) · Σⱼ rⱼ · fⱼ · (1 - mⱼ)

Where:
- rⱼ: reliability of evidence source for feature j ∈ [0, 1]
- fⱼ: feature selected flag ∈ {0, 1}
- mⱼ: missingness flag ∈ {0, 1} (1 if evidence is absent/restricted)

C ∈ [0, 1]. Low confidence does NOT increase or decrease the Trust Score — it is reported separately.

## Hard Rules (Safety Caps)

Certain conditions may trigger hard caps on Trust Score, documented here:

| Condition | Action | Status |
|---|---|---|
| Verified IMEI blacklist hit | T capped at 0.0 | NOT YET IMPLEMENTED — requires verified data source |
| Evidence count < minimum threshold | C = 0 (inconclusive) | Implemented |

No hard rules are implemented without a verified data source.

## Baselines

See `docs/BENCHMARKS.md` for comparison methodology.

- **Baseline A**: Fixed Weighted Score — expert-defined static weights, no ML.
- **Baseline B**: Static Fuzzy System — fuzzy logic, no evolutionary optimization.
- **Baseline C**: Evolutionary Linear Score — NSGA-II, no fuzzy membership.
- **Baseline D**: Logistic Regression — standard statistical baseline.
- **Baseline E**: Random Forest — standard nonlinear ML baseline.
