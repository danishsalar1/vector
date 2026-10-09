"""RV-01: a variant-specific performance baseline never yields a definitive verdict while the
device variant is unresolved or ambiguous. All data is fabricated; test-only catalogs."""

from __future__ import annotations

import pytest

from tests.test_phase8e_final_remediation import (
    DEFINITIVE,
    Out,
    PerformanceReferenceManager,
    _perf_manager,
    catalog,
    identity,
)
from vector_agent.models.reference import ResolutionStatus
from vector_agent.reference.resolver import DeviceResolver

IN_RANGE, OUT_OF_RANGE = 1.5, 3.0  # reference_min=1.0, reference_max=2.0 in the shared fixture
DISTRIBUTIONS = {
    "min-max": {},
    "mean-sigma": {
        "reference_min": None,
        "reference_max": None,
        "reference_mean": 1.5,
        "reference_std_dev": 0.25,
    },
}


def manager(distribution: str, **kwargs: object) -> PerformanceReferenceManager:
    return _perf_manager(
        claim_path="performance.baseline", **{**DISTRIBUTIONS[distribution], **kwargs}
    )


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
@pytest.mark.parametrize("variant_id", [None, ""])
@pytest.mark.parametrize("observed", [IN_RANGE, OUT_OF_RANGE, 0.0])
def test_rv01_unresolved_variant_never_gives_a_definitive_verdict(
    distribution: str, variant_id: str | None, observed: float
) -> None:
    result = manager(distribution, applicable_variant_ids=("v-a",)).evaluate_metric(
        "score-a", observed, "acme-one", variant_id
    )
    assert result.outcome == Out.VARIANT_AMBIGUOUS
    assert result.outcome not in DEFINITIVE
    assert result.observed_value == observed  # preserved, not discarded
    assert "Definitive verdict withheld" in result.reason


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_rv01_omitted_variant_argument_is_also_unresolved(distribution: str) -> None:
    result = manager(distribution, applicable_variant_ids=("v-a",)).evaluate_metric(
        "score-a", OUT_OF_RANGE, "acme-one"
    )
    assert result.outcome == Out.VARIANT_AMBIGUOUS


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_rv01_ambiguous_resolution_from_the_resolver_withholds_the_verdict(
    distribution: str,
) -> None:
    perf = manager(distribution, applicable_variant_ids=("v-a",))
    cat = catalog(test_only=True)
    ambiguous = DeviceResolver(cat).resolve(identity(marketing_name="Acme One"))
    assert ambiguous.status == ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT
    assert ambiguous.resolved_variant is None
    variant = ambiguous.resolved_variant.variant_id if ambiguous.resolved_variant else None
    result = perf.evaluate_metric("score-a", OUT_OF_RANGE, "acme-one", variant)
    assert result.outcome == Out.VARIANT_AMBIGUOUS


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_rv01_explicitly_resolved_variant_still_gets_a_verdict(distribution: str) -> None:
    perf = manager(distribution, applicable_variant_ids=("v-a",))
    exact = DeviceResolver(catalog(test_only=True)).resolve(identity("am-a"))
    assert exact.status == ResolutionStatus.EXACT_MATCH and exact.resolved_variant is not None
    variant = exact.resolved_variant.variant_id
    assert variant == "v-a"
    assert (
        perf.evaluate_metric("score-a", IN_RANGE, "acme-one", variant).outcome
        == Out.CONSISTENT_WITH_REFERENCE
    )
    assert (
        perf.evaluate_metric("score-a", OUT_OF_RANGE, "acme-one", variant).outcome
        == Out.DIFFERS_FROM_REFERENCE
    )


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_rv01_resolved_variant_outside_the_baseline_is_still_unavailable(
    distribution: str,
) -> None:
    result = manager(distribution, applicable_variant_ids=("v-a",)).evaluate_metric(
        "score-a", IN_RANGE, "acme-one", "v-b"
    )
    assert result.outcome == Out.REFERENCE_UNAVAILABLE


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
@pytest.mark.parametrize("variant_id", [None, "", "v-a", "v-b"])
def test_rv01_model_wide_baseline_is_unaffected_by_the_variant(
    distribution: str, variant_id: str | None
) -> None:
    perf = manager(distribution)  # no applicable_variant_ids: genuinely model-wide
    assert (
        perf.evaluate_metric("score-a", IN_RANGE, "acme-one", variant_id).outcome
        == Out.CONSISTENT_WITH_REFERENCE
    )
    assert (
        perf.evaluate_metric("score-a", OUT_OF_RANGE, "acme-one", variant_id).outcome
        == Out.DIFFERS_FROM_REFERENCE
    )


def test_rv01_verification_and_model_checks_still_precede_the_variant_check() -> None:
    unverified = _perf_manager(claim_path=None, applicable_variant_ids=("v-a",))
    assert (
        unverified.evaluate_metric("score-a", IN_RANGE, "acme-one", None).outcome
        == Out.REFERENCE_UNAVAILABLE
    )
    wrong_model = manager("min-max", applicable_variant_ids=("v-a",))
    assert (
        wrong_model.evaluate_metric("score-a", IN_RANGE, "other-model", None).outcome
        == Out.REFERENCE_UNAVAILABLE
    )


@pytest.mark.parametrize("observed", [float("nan"), "1.5", True, -1.0])
def test_rv01_malformed_observation_with_unresolved_variant_stays_non_definitive(
    observed: object,
) -> None:
    result = manager("min-max", applicable_variant_ids=("v-a",)).evaluate_metric(
        "score-a",
        observed,  # type: ignore[arg-type]
        "acme-one",
        None,
    )
    assert result.outcome not in DEFINITIVE
    assert result.observed_value is None
