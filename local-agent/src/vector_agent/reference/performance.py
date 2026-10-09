"""Performance Reference Infrastructure Foundation.

Defines repository and query evaluation for benchmark baselines without
manufacturing synthetic expectations.

Core rules:
- Advertising claims are never converted into benchmark distributions.
- If verified benchmark data is absent, cleanly report REFERENCE_UNAVAILABLE.
- Physical qualification remains NOT RUN.
"""

from __future__ import annotations

import json
import math

from vector_agent.models.reference import (
    ComparisonOutcome,
    PerformanceEvaluationResult,
    PerformanceMetricReference,
)

from .catalog import ReferenceCatalog


class PerformanceReferenceManager:
    """Manages and queries verified performance baseline references."""

    def __init__(self, catalog: ReferenceCatalog | None = None) -> None:
        self.catalog = catalog or ReferenceCatalog()

    def register_metric_reference(self, metric: PerformanceMetricReference) -> None:
        """Register a performance metric reference in the underlying catalog."""
        self.catalog.register_performance_metric(metric)

    def get_metric(self, metric_id: str) -> PerformanceMetricReference | None:
        return self.catalog.get_performance_metric(metric_id)

    def get_metrics_for_model(self, model_id: str) -> tuple[PerformanceMetricReference, ...]:
        with self.catalog._lock:
            return tuple(
                m
                for m in self.catalog._performance_metrics.values()
                if model_id in m.applicable_model_ids
            )

    def evaluate_metric(
        self,
        metric_id: str,
        observed_value: float | None,
        model_id: str,
        variant_id: str | None = None,
    ) -> PerformanceEvaluationResult:
        """Evaluate an observed benchmark result against reference baseline distribution."""
        # Sanitize before any result is built: malformed caller input is never echoed
        # and never raises; it simply becomes a missing observation.
        if observed_value is not None and (
            not isinstance(observed_value, (int, float))
            or isinstance(observed_value, bool)
            or not 0 <= observed_value <= 1e308  # also rejects NaN/inf and huge ints
            or not math.isfinite(observed_value)
        ):
            observed_value = None

        metric = self.get_metric(metric_id)
        if metric is None:
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=observed_value,
                unit="unknown",
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason=f"No verified performance reference baseline registered for metric '{metric_id}'.",
                source_id=None,
            )

        source = self.catalog.get_source(metric.source_id)
        verified = source is not None and (
            self.catalog.test_only
            or (
                not source.is_synthetic
                and any(
                    claim.entity_id == metric.metric_id
                    and claim.property_path == "performance.baseline"
                    and claim.reference_value_json
                    == json.dumps(
                        metric.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                    )
                    for claim in source.verified_claims
                )
            )
        )
        if not verified:
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=observed_value,
                unit=metric.measurement_unit,
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason="Performance baseline lacks verified support for this exact distribution and methodology.",
                source_id=metric.source_id if source is not None else None,
            )

        if model_id not in metric.applicable_model_ids:
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=observed_value,
                unit=metric.measurement_unit,
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason=(
                    f"Performance baseline for '{metric_id}' is not applicable to model '{model_id}' "
                    f"(applies to: {', '.join(metric.applicable_model_ids)})."
                ),
                source_id=metric.source_id,
            )

        if metric.applicable_variant_ids and not variant_id:
            # The baseline is variant-specific but the device variant is unresolved or
            # ambiguous: no definitive verdict may be drawn. The observation is preserved.
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=observed_value,
                unit=metric.measurement_unit,
                outcome=ComparisonOutcome.VARIANT_AMBIGUOUS,
                reason=(
                    f"Performance baseline for '{metric_id}' applies only to specific variants "
                    f"({', '.join(metric.applicable_variant_ids)}) and the device variant is not "
                    "resolved. Definitive verdict withheld."
                ),
                source_id=metric.source_id,
                confidence_limitations=metric.confidence_limitations,
            )

        if (
            variant_id
            and metric.applicable_variant_ids
            and variant_id not in metric.applicable_variant_ids
        ):
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=observed_value,
                unit=metric.measurement_unit,
                outcome=ComparisonOutcome.REFERENCE_UNAVAILABLE,
                reason=(
                    f"Performance baseline for '{metric_id}' does not apply to variant '{variant_id}'."
                ),
                source_id=metric.source_id,
            )

        if observed_value is None:
            return PerformanceEvaluationResult(
                metric_id=metric_id,
                observed_value=None,
                unit=metric.measurement_unit,
                reference_min=metric.reference_min,
                reference_max=metric.reference_max,
                reference_mean=metric.reference_mean,
                outcome=ComparisonOutcome.INSUFFICIENT_EVIDENCE,
                reason="Observed performance benchmark score was not provided.",
                source_id=metric.source_id,
                confidence_limitations=metric.confidence_limitations,
            )

        # Check range
        ref_min = metric.reference_min
        ref_max = metric.reference_max

        if ref_min is not None and ref_max is not None:
            is_consistent = ref_min <= observed_value <= ref_max
            outcome = (
                ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                if is_consistent
                else ComparisonOutcome.DIFFERS_FROM_REFERENCE
            )
            reason = (
                f"Observed benchmark score {observed_value} {metric.measurement_unit} is within "
                f"reference baseline distribution [{ref_min}-{ref_max} {metric.measurement_unit}]."
                if is_consistent
                else (
                    f"Observed benchmark score {observed_value} {metric.measurement_unit} is outside "
                    f"reference baseline distribution [{ref_min}-{ref_max} {metric.measurement_unit}]."
                )
            )
        elif metric.reference_mean is not None and metric.reference_std_dev is not None:
            # 2 standard deviations margin
            lower = metric.reference_mean - (2 * metric.reference_std_dev)
            upper = metric.reference_mean + (2 * metric.reference_std_dev)
            is_consistent = lower <= observed_value <= upper
            outcome = (
                ComparisonOutcome.CONSISTENT_WITH_REFERENCE
                if is_consistent
                else ComparisonOutcome.DIFFERS_FROM_REFERENCE
            )
            reason = (
                f"Observed benchmark score {observed_value} {metric.measurement_unit} is within 2-sigma "
                f"of reference baseline mean ({metric.reference_mean:.1f} ± {2 * metric.reference_std_dev:.1f})."
                if is_consistent
                else (
                    f"Observed benchmark score {observed_value} {metric.measurement_unit} deviates significantly "
                    f"from reference baseline mean ({metric.reference_mean:.1f})."
                )
            )
        else:
            outcome = ComparisonOutcome.NOT_COMPARABLE
            reason = "Reference metric definition lacks valid numeric bounds or distribution."

        return PerformanceEvaluationResult(
            metric_id=metric_id,
            observed_value=observed_value,
            unit=metric.measurement_unit,
            reference_min=ref_min,
            reference_max=ref_max,
            reference_mean=metric.reference_mean,
            outcome=outcome,
            reason=reason,
            source_id=metric.source_id,
            confidence_limitations=metric.confidence_limitations,
            disclaimer=(
                "TEST-ONLY CATALOG: synthetic/unverified performance fixture; not a hardware benchmark. "
                if self.catalog.test_only
                else ""
            )
            + "Performance consistency does not establish component authenticity or hardware calibration.",
        )
