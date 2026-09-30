"""Multi-objective fitness functions for NSGA-II.

Objectives are MINIMIZED in NSGA-II (standard convention).
Where we want to maximize something (e.g., detection), negate it.

Objective vector:
  [0] prediction_error        - minimize MAE on trust score
  [1] perturbation_instability - minimize score variance under perturbation
  [2] rule_complexity          - minimize number of active rules (model simplicity)
  [3] latency_proxy            - minimize active feature count (inference speed proxy)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vector_intelligence.evolution.genome import GenomeSpec


def objective_prediction_error(
    predicted: np.ndarray,
    ground_truth: np.ndarray,
) -> float:
    """Mean Absolute Error between predicted trust scores and ground truth."""
    if len(predicted) == 0:
        return 1.0  # Worst case if no predictions.
    return float(np.mean(np.abs(predicted - ground_truth)))


def objective_perturbation_instability(
    scores_nominal: np.ndarray,
    scores_perturbed: np.ndarray,
) -> float:
    """Mean absolute deviation of trust scores under perturbation.

    A robust model should produce similar scores for small perturbations
    but correctly reflect large critical defects as WORSE, not just different.
    """
    if len(scores_nominal) == 0:
        return 1.0
    return float(np.mean(np.abs(scores_nominal - scores_perturbed)))


def objective_rule_complexity(
    rule_enabled: np.ndarray,
    max_rules: int,
) -> float:
    """Normalized count of active rules. Ranges in [0, 1]."""
    n_active = int(np.sum(rule_enabled > 0.5))
    return n_active / max(max_rules, 1)


def objective_latency_proxy(
    feature_mask: np.ndarray,
    max_features: int,
) -> float:
    """Normalized active feature count as inference-latency proxy."""
    n_active = int(np.sum(feature_mask > 0.5))
    return n_active / max(max_features, 1)


def evaluate_objectives(
    genome: np.ndarray,
    spec: GenomeSpec,
    benchmark_data: dict[str, np.ndarray],
) -> tuple[float, float, float, float]:
    """Evaluate all four objectives for a single genome.

    Args:
        genome: Flat genome array.
        spec: Genome layout specification.
        benchmark_data: Dictionary with keys:
            'evidence': shape (n_samples, n_features)
            'labels': shape (n_samples,) trust scores in [0, 1]
            'perturbed_evidence': shape (n_samples, n_features)

    Returns:
        (prediction_error, perturbation_instability, rule_complexity, latency_proxy)
        All values in [0, 1], all to be MINIMIZED.
    """
    from vector_intelligence.evolution.genome import decode_genome
    from vector_intelligence.fuzzy.inference import FuzzyConfig, FuzzyInferenceEngine

    membership_params, rule_weights, rule_enabled, feature_mask = decode_genome(genome, spec)

    config = FuzzyConfig(
        membership_params=membership_params,
        rule_weights=rule_weights,
        rule_enabled=rule_enabled,
        feature_mask=feature_mask,
        n_terms=spec.n_terms,
    )
    engine = FuzzyInferenceEngine(config)

    evidence = benchmark_data["evidence"]
    labels = benchmark_data["labels"]
    perturbed = benchmark_data.get("perturbed_evidence", evidence)

    predicted = np.array([engine.infer(ev)[0] for ev in evidence])
    predicted_perturbed = np.array([engine.infer(ev)[0] for ev in perturbed])

    e0 = objective_prediction_error(predicted, labels)
    e1 = objective_perturbation_instability(predicted, predicted_perturbed)
    e2 = objective_rule_complexity(rule_enabled, spec.n_rules)
    e3 = objective_latency_proxy(feature_mask, spec.n_features)

    return e0, e1, e2, e3
