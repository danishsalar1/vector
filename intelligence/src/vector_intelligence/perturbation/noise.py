"""Perturbation engine for adversarial stress testing.

Provides reproducible perturbation scenarios for benchmark evaluation.
Real mode and synthetic mode are technically separated.

Perturbation types:
- Noise: Gaussian noise added to continuous features.
- Missingness: Feature values set to NaN (unknown).
- Contradiction: Conflicting evidence signals.
- Shift: Distribution shift across device populations.
- Adversarial: Optimistically biased individual readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class PerturbationType(StrEnum):
    NOISE = "NOISE"
    MISSINGNESS = "MISSINGNESS"
    CONTRADICTION = "CONTRADICTION"
    SHIFT = "SHIFT"
    ADVERSARIAL = "ADVERSARIAL"


@dataclass
class PerturbationConfig:
    """Configuration for a perturbation experiment."""

    perturbation_type: PerturbationType
    magnitude: float
    """Scale of the perturbation. Interpretation depends on type."""
    seed: int = 42
    affected_fraction: float = 0.3
    """Fraction of features or samples affected."""


def apply_noise(
    evidence: np.ndarray,
    magnitude: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Add Gaussian noise to evidence values, clipped to [0, 1]."""
    noisy = evidence + rng.normal(0, magnitude, evidence.shape)
    return np.clip(noisy, 0.0, 1.0)


def apply_missingness(
    evidence: np.ndarray,
    affected_fraction: float,
    rng: np.random.Generator,
    missing_value: float = 0.5,
) -> np.ndarray:
    """Set a random subset of features to a neutral missing value.

    UNSUPPORTED/MISSING evidence is represented as 0.5 (neutral),
    NOT as 0.0 (which would incorrectly penalize unsupported hardware).
    """
    perturbed = evidence.copy()
    n_features = evidence.shape[-1]
    n_missing = max(1, int(n_features * affected_fraction))
    mask = rng.choice(n_features, size=n_missing, replace=False)
    perturbed[..., mask] = missing_value
    return perturbed


def apply_adversarial(
    evidence: np.ndarray,
    affected_fraction: float,
    rng: np.random.Generator,
    bias_direction: float = 1.0,
) -> np.ndarray:
    """Bias selected features in a given direction (optimistic or pessimistic).

    Simulates a seller providing selectively optimistic readings.
    """
    perturbed = evidence.copy()
    n_features = evidence.shape[-1]
    n_affected = max(1, int(n_features * affected_fraction))
    mask = rng.choice(n_features, size=n_affected, replace=False)
    # Push values toward 1.0 (optimistic bias) or 0.0 (pessimistic bias).
    perturbed[..., mask] = np.clip(
        perturbed[..., mask] + bias_direction * rng.uniform(0.2, 0.5, n_affected),
        0.0,
        1.0,
    )
    return perturbed


def perturb(
    evidence: np.ndarray,
    config: PerturbationConfig,
) -> np.ndarray:
    """Apply a configured perturbation to an evidence array.

    Args:
        evidence: Input evidence, shape (n_samples, n_features) or (n_features,).
        config: Perturbation configuration.

    Returns:
        Perturbed evidence array with the same shape.
    """
    rng = np.random.default_rng(config.seed)

    if config.perturbation_type == PerturbationType.NOISE:
        return apply_noise(evidence, config.magnitude, rng)
    elif config.perturbation_type == PerturbationType.MISSINGNESS:
        return apply_missingness(evidence, config.affected_fraction, rng)
    elif config.perturbation_type == PerturbationType.ADVERSARIAL:
        return apply_adversarial(evidence, config.affected_fraction, rng)
    elif config.perturbation_type == PerturbationType.SHIFT:
        # Distribution shift: shift entire feature distribution by a constant offset.
        shifted = evidence + config.magnitude * rng.uniform(-1, 1, evidence.shape[-1])
        return np.clip(shifted, 0.0, 1.0)
    elif config.perturbation_type == PerturbationType.CONTRADICTION:
        # Flip a fraction of features to their opposite.
        perturbed = evidence.copy()
        n_features = evidence.shape[-1]
        n_affected = max(1, int(n_features * config.affected_fraction))
        mask = rng.choice(n_features, size=n_affected, replace=False)
        perturbed[..., mask] = 1.0 - perturbed[..., mask]
        return perturbed
    else:
        raise ValueError(f"Unknown perturbation type: {config.perturbation_type}")
