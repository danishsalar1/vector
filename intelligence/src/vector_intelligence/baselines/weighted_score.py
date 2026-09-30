"""Baseline A: Fixed Weighted Score.

Purpose: Represents ordinary manually-weighted condition scoring.
This is the simplest possible baseline and serves as the floor VECTOR must beat.

No fuzzy logic.
No evolutionary optimization.
Fixed weights chosen by a domain expert heuristic.
"""

from __future__ import annotations

import numpy as np

# Expert-defined diagnostic weights.
# Weights sum to 1.0 after normalization.
# These reflect subjective importance, NOT trained values.
DEFAULT_WEIGHTS: dict[str, float] = {
    "battery_health": 0.20,
    "storage_integrity": 0.15,
    "device_identity": 0.15,
    "camera_functional": 0.10,
    "microphone_functional": 0.08,
    "speaker_functional": 0.07,
    "display_functional": 0.08,
    "connectivity": 0.07,
    "sensors_present": 0.05,
    "software_integrity": 0.05,
}


class FixedWeightedScoreBaseline:
    """Baseline A: Fixed expert-weighted trust score.

    Does NOT use fuzzy logic.
    Does NOT use evolutionary optimization.
    Weight vector is static and manually defined.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        raw = weights or DEFAULT_WEIGHTS
        total = sum(raw.values())
        self._weights = {k: v / total for k, v in raw.items()}
        self._feature_names = list(self._weights.keys())
        self._weight_array = np.array([self._weights[k] for k in self._feature_names])

    @property
    def name(self) -> str:
        return "Baseline A: Fixed Weighted Score"

    def predict(self, evidence_vector: np.ndarray) -> float:
        """Return a weighted trust score in [0, 1].

        Args:
            evidence_vector: Normalized evidence array, shape (n_features,).
                UNSUPPORTED features should be passed as 0.5 (neutral).
                Never pass 0.0 for UNSUPPORTED to avoid false penalty.

        Returns:
            Scalar trust score in [0, 1].
        """
        n = min(len(evidence_vector), len(self._weight_array))
        weights = self._weight_array[:n]
        evidence = evidence_vector[:n]
        weight_sum = np.sum(weights)
        if weight_sum < 1e-9:
            return 0.5  # Avoid division by zero; return neutral.
        return float(np.clip(np.dot(weights, evidence) / weight_sum, 0.0, 1.0))

    def predict_batch(self, evidence_matrix: np.ndarray) -> np.ndarray:
        """Predict trust scores for a batch of evidence vectors."""
        return np.array([self.predict(ev) for ev in evidence_matrix])
