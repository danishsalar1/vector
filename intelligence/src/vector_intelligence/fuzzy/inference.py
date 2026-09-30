"""Fuzzy inference engine interface.

Implements a Sugeno-style fuzzy system for trust scoring.

Architecture:
- Membership functions map diagnostic evidence to fuzzy degrees [0, 1].
- Rules combine membership degrees via T-norms (min or product).
- Weighted Sugeno output combines rule activations with rule consequents.

The evolutionary optimizer (NSGA-II) tunes:
- Membership function boundaries (theta_jk)
- Rule weights (w_r)
- Rule enable/disable states
- Feature selection mask

This module handles INFERENCE ONLY.
Training/optimization lives in vector_intelligence.evolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class FuzzyConfig:
    """Serializable fuzzy system configuration.

    Produced by the evolutionary optimizer and loaded at inference time.
    """

    # Membership boundaries for each feature: shape (n_features, n_terms, n_params)
    membership_params: np.ndarray

    # Rule weights: shape (n_rules,)
    rule_weights: np.ndarray

    # Rule enable mask: shape (n_rules,) boolean
    rule_enabled: np.ndarray

    # Feature selection mask: shape (n_features,) boolean
    feature_mask: np.ndarray

    # Number of linguistic terms per feature
    n_terms: int = 3

    # Small epsilon to prevent division by zero in Sugeno output
    epsilon: float = 1e-9


class MembershipFunction(Protocol):
    """Protocol for fuzzy membership functions.

    Each function maps a crisp value to a degree in [0, 1].
    """

    def __call__(self, x: float) -> float:
        """Return the membership degree of value x."""
        ...


def trimf(x: float, a: float, b: float, c: float) -> float:
    """Triangular membership function.

    Args:
        x: Input value.
        a: Left foot (membership = 0).
        b: Peak (membership = 1).
        c: Right foot (membership = 0).

    Returns:
        Membership degree in [0, 1].
    """
    if a == b == c:
        return 1.0 if x == a else 0.0
    left = (x - a) / (b - a) if b != a else 0.0
    right = (c - x) / (c - b) if c != b else 0.0
    return float(np.clip(min(left, right), 0.0, 1.0))


def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership function."""
    left = (x - a) / (b - a) if b != a else (1.0 if x >= b else 0.0)
    right = (d - x) / (d - c) if d != c else (1.0 if x <= c else 0.0)
    return float(np.clip(min(left, right, 1.0), 0.0, 1.0))


class FuzzyInferenceEngine:
    """Sugeno-style fuzzy inference engine.

    Usage (inference only)::

        engine = FuzzyInferenceEngine(config)
        score, confidence = engine.infer(evidence_vector)

    The config is produced offline by the NSGA-II optimizer.
    """

    def __init__(self, config: FuzzyConfig) -> None:
        self._config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Basic sanity checks on the fuzzy configuration."""
        if self._config.rule_weights.shape != self._config.rule_enabled.shape:
            raise ValueError("rule_weights and rule_enabled must have the same shape.")

    def infer(self, evidence_vector: np.ndarray) -> tuple[float, float]:
        """Run fuzzy inference on an evidence vector.

        Args:
            evidence_vector: Normalized diagnostic evidence, shape (n_features,).
                Values should be in [0, 1].

        Returns:
            (trust_score, confidence) where both are in [0, 1].

        Raises:
            ValueError: If evidence_vector has wrong shape.
        """
        # Placeholder implementation.
        # Phase 5 will replace this with the full NSGA-II optimized inference.
        n_features = evidence_vector.shape[0]
        active_features = evidence_vector[self._config.feature_mask[:n_features]]

        if len(active_features) == 0:
            return 0.5, 0.0  # Inconclusive: no usable features.

        # Naive weighted mean as placeholder.
        score = float(np.clip(np.mean(active_features), 0.0, 1.0))
        confidence = min(len(active_features) / n_features, 1.0)

        return score, confidence
