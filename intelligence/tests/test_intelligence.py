"""Tests for intelligence package: fuzzy, genome, perturbation, baselines."""

from __future__ import annotations

import numpy as np
import pytest

from vector_intelligence.baselines.weighted_score import FixedWeightedScoreBaseline
from vector_intelligence.evolution.genome import (
    GenomeSpec,
    decode_genome,
    random_genome,
    repair_membership_ordering,
    validate_membership_ordering,
)
from vector_intelligence.fuzzy.inference import FuzzyConfig, FuzzyInferenceEngine, trapmf, trimf
from vector_intelligence.perturbation.noise import (
    PerturbationConfig,
    PerturbationType,
    perturb,
)


class TestMembershipFunctions:
    def test_trimf_peak(self) -> None:
        assert trimf(0.5, 0.0, 0.5, 1.0) == pytest.approx(1.0)

    def test_trimf_left_foot(self) -> None:
        assert trimf(0.0, 0.0, 0.5, 1.0) == pytest.approx(0.0)

    def test_trimf_right_foot(self) -> None:
        assert trimf(1.0, 0.0, 0.5, 1.0) == pytest.approx(0.0)

    def test_trimf_clipped_above(self) -> None:
        result = trimf(2.0, 0.0, 0.5, 1.0)
        assert result == pytest.approx(0.0)

    def test_trapmf_flat_top(self) -> None:
        assert trapmf(0.5, 0.0, 0.3, 0.7, 1.0) == pytest.approx(1.0)

    def test_trapmf_left_slope(self) -> None:
        result = trapmf(0.15, 0.0, 0.3, 0.7, 1.0)
        assert 0.0 < result < 1.0


class TestGenome:
    def test_encode_decode_roundtrip(self) -> None:
        spec = GenomeSpec(n_features=5, n_terms=3, n_params_per_term=3, n_rules=10)
        rng = np.random.default_rng(42)
        genome = random_genome(spec, rng)
        assert genome.shape == (spec.total_size,)

        mp, rw, re, fm = decode_genome(genome, spec)
        assert mp.shape == (spec.n_features, spec.n_terms, spec.n_params_per_term)
        assert rw.shape == (spec.n_rules,)
        assert re.shape == (spec.n_rules,)
        assert fm.shape == (spec.n_features,)

    def test_rule_weights_clamped(self) -> None:
        spec = GenomeSpec(n_features=3, n_terms=3, n_params_per_term=3, n_rules=5)
        rng = np.random.default_rng(0)
        genome = random_genome(spec, rng)
        _, rw, _, _ = decode_genome(genome, spec)
        assert np.all(rw >= 0.0)
        assert np.all(rw <= 1.0)

    def test_validate_membership_ordering(self) -> None:
        mp = np.array([[[0.1, 0.5, 0.9]]])  # sorted: valid
        assert validate_membership_ordering(mp) is True

    def test_validate_membership_ordering_invalid(self) -> None:
        mp = np.array([[[0.9, 0.1, 0.5]]])  # unsorted: invalid
        assert validate_membership_ordering(mp) is False

    def test_repair_restores_ordering(self) -> None:
        mp = np.array([[[0.9, 0.1, 0.5]]])
        repaired = repair_membership_ordering(mp)
        assert validate_membership_ordering(repaired) is True


class TestFuzzyEngine:
    def _make_engine(self, n_features: int = 5) -> FuzzyInferenceEngine:
        spec = GenomeSpec(n_features=n_features, n_terms=3, n_params_per_term=3, n_rules=4)
        rng = np.random.default_rng(42)
        genome = random_genome(spec, rng)
        mp, rw, re, fm = decode_genome(genome, spec)
        config = FuzzyConfig(
            membership_params=mp,
            rule_weights=rw,
            rule_enabled=re,
            feature_mask=fm,
        )
        return FuzzyInferenceEngine(config)

    def test_infer_returns_valid_range(self) -> None:
        engine = self._make_engine()
        ev = np.array([0.8, 0.6, 0.9, 0.4, 0.7])
        score, confidence = engine.infer(ev)
        assert 0.0 <= score <= 1.0
        assert 0.0 <= confidence <= 1.0

    def test_infer_all_zero_stays_in_range(self) -> None:
        engine = self._make_engine()
        ev = np.zeros(5)
        score, confidence = engine.infer(ev)
        assert 0.0 <= score <= 1.0


class TestPerturbationEngine:
    def test_noise_stays_in_range(self) -> None:
        ev = np.full((10, 5), 0.5)
        cfg = PerturbationConfig(
            perturbation_type=PerturbationType.NOISE,
            magnitude=0.1,
            seed=42,
        )
        perturbed = perturb(ev, cfg)
        assert np.all(perturbed >= 0.0)
        assert np.all(perturbed <= 1.0)

    def test_missingness_changes_values(self) -> None:
        ev = np.ones((1, 10))
        cfg = PerturbationConfig(
            perturbation_type=PerturbationType.MISSINGNESS,
            magnitude=0.0,
            seed=0,
            affected_fraction=0.5,
        )
        perturbed = perturb(ev, cfg)
        # Some values should be changed to 0.5 (neutral missing value).
        assert not np.all(perturbed == 1.0)

    def test_adversarial_stays_in_range(self) -> None:
        ev = np.full((5, 8), 0.3)
        cfg = PerturbationConfig(
            perturbation_type=PerturbationType.ADVERSARIAL,
            magnitude=0.5,
            seed=7,
            affected_fraction=0.4,
        )
        perturbed = perturb(ev, cfg)
        assert np.all(perturbed >= 0.0)
        assert np.all(perturbed <= 1.0)

    def test_contradiction_flips_values(self) -> None:
        ev = np.zeros((1, 10))
        cfg = PerturbationConfig(
            perturbation_type=PerturbationType.CONTRADICTION,
            magnitude=0.0,
            seed=1,
            affected_fraction=0.3,
        )
        perturbed = perturb(ev, cfg)
        # Contradicted features should now be 1.0 (flipped from 0.0).
        assert np.any(perturbed == 1.0)


class TestBaselineA:
    def test_predict_in_range(self) -> None:
        baseline = FixedWeightedScoreBaseline()
        ev = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.9, 0.8, 0.7, 0.6, 0.5])
        score = baseline.predict(ev)
        assert 0.0 <= score <= 1.0

    def test_predict_all_ones(self) -> None:
        baseline = FixedWeightedScoreBaseline()
        ev = np.ones(10)
        score = baseline.predict(ev)
        assert score == pytest.approx(1.0)

    def test_predict_all_zeros(self) -> None:
        baseline = FixedWeightedScoreBaseline()
        ev = np.zeros(10)
        score = baseline.predict(ev)
        assert score == pytest.approx(0.0)

    def test_predict_batch(self) -> None:
        baseline = FixedWeightedScoreBaseline()
        matrix = np.random.default_rng(42).random((20, 10))
        scores = baseline.predict_batch(matrix)
        assert scores.shape == (20,)
        assert np.all(scores >= 0.0)
        assert np.all(scores <= 1.0)
