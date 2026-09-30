"""Fuzzy rule definitions and T-norm operations."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class FuzzyRule:
    """A single fuzzy IF-THEN rule.

    Antecedent: AND-combination of (feature_index, term_index) pairs.
    Consequent: A scalar output value (Sugeno constant).
    """

    antecedent: list[tuple[int, int]] = field(default_factory=list)
    """List of (feature_index, term_index) pairs."""
    consequent: float = 0.5
    weight: float = 1.0
    enabled: bool = True

    def activation(self, membership_degrees: np.ndarray) -> float:
        """Compute rule activation using product T-norm (algebraic product).

        Args:
            membership_degrees: shape (n_features, n_terms) — pre-computed degrees.

        Returns:
            Rule activation strength in [0, 1].
        """
        if not self.enabled or not self.antecedent:
            return 0.0
        degrees = [membership_degrees[fi, ti] for fi, ti in self.antecedent]
        return float(np.prod(degrees))
