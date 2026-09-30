"""Genome encoding for the NSGA-II evolutionary optimizer.

The genome encodes:
1. Membership function parameters (boundaries for each linguistic term).
2. Rule weights (continuous, clipped to [0, 1]).
3. Rule enable/disable flags (binary).
4. Feature selection mask (binary).

Genome is a flat numpy array for efficient vectorized operations.
Decode functions extract meaningful structures from the flat array.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class GenomeSpec:
    """Specification for the genome layout."""

    n_features: int
    n_terms: int  # Linguistic terms per feature (e.g., LOW, MEDIUM, HIGH)
    n_params_per_term: int  # Parameters per membership function (e.g., 3 for triangular)
    n_rules: int

    @property
    def membership_size(self) -> int:
        return self.n_features * self.n_terms * self.n_params_per_term

    @property
    def rule_weight_size(self) -> int:
        return self.n_rules

    @property
    def rule_enable_size(self) -> int:
        return self.n_rules

    @property
    def feature_mask_size(self) -> int:
        return self.n_features

    @property
    def total_size(self) -> int:
        return (
            self.membership_size
            + self.rule_weight_size
            + self.rule_enable_size
            + self.feature_mask_size
        )


def encode_genome(
    membership_params: np.ndarray,
    rule_weights: np.ndarray,
    rule_enabled: np.ndarray,
    feature_mask: np.ndarray,
) -> np.ndarray:
    """Encode all genome components into a single flat float array."""
    return np.concatenate(
        [
            membership_params.flatten().astype(float),
            rule_weights.astype(float),
            rule_enabled.astype(float),
            feature_mask.astype(float),
        ]
    )


def decode_genome(
    genome: np.ndarray,
    spec: GenomeSpec,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Decode a flat genome array into its components.

    Returns:
        (membership_params, rule_weights, rule_enabled, feature_mask)
    """
    ms = spec.membership_size
    rws = spec.rule_weight_size
    res = spec.rule_enable_size
    fms = spec.feature_mask_size

    offset = 0
    membership_flat = genome[offset : offset + ms]
    offset += ms
    rule_weights = genome[offset : offset + rws]
    offset += rws
    rule_enabled_raw = genome[offset : offset + res]
    offset += res
    feature_mask_raw = genome[offset : offset + fms]

    membership_params = membership_flat.reshape(
        spec.n_features, spec.n_terms, spec.n_params_per_term
    )
    rule_enabled = rule_enabled_raw > 0.5
    feature_mask = feature_mask_raw > 0.5

    # Clamp rule weights to valid range.
    rule_weights = np.clip(rule_weights, 0.0, 1.0)

    return membership_params, rule_weights, rule_enabled, feature_mask


def validate_membership_ordering(
    membership_params: np.ndarray,
) -> bool:
    """Check that membership function parameters maintain monotonic ordering.

    For triangular MFs (a, b, c) we require a <= b <= c.
    Invalid orderings can produce nonsensical fuzzy degrees.
    """
    n_features, n_terms, n_params = membership_params.shape
    for f in range(n_features):
        for t in range(n_terms):
            params = membership_params[f, t]
            if not all(params[i] <= params[i + 1] for i in range(len(params) - 1)):
                return False
    return True


def repair_membership_ordering(membership_params: np.ndarray) -> np.ndarray:
    """Sort membership parameters within each term to restore monotonic ordering.

    Called after mutation to prevent invalid fuzzy configurations.
    """
    repaired = membership_params.copy()
    repaired.sort(axis=-1)  # Sort params within each (feature, term).
    return repaired


def random_genome(spec: GenomeSpec, rng: np.random.Generator) -> np.ndarray:
    """Generate a random initial genome within valid bounds."""
    # Membership params: random in [0, 1], then sorted per term.
    membership_params = rng.random((spec.n_features, spec.n_terms, spec.n_params_per_term))
    membership_params.sort(axis=-1)

    rule_weights = rng.random(spec.n_rules)
    rule_enabled = (rng.random(spec.n_rules) > 0.3).astype(float)  # ~70% enabled initially.
    feature_mask = (rng.random(spec.n_features) > 0.2).astype(float)  # ~80% features selected.

    return encode_genome(membership_params, rule_weights, rule_enabled, feature_mask)
