import type { FC } from "react";
import type { ScanSummary } from "../../lib/api/types";

/**
 * Renders exactly what the backend returned for the Trust Engine.
 * No score is shown, estimated or implied unless the API supplied one.
 */
export const TrustEnginePanel: FC<{ summary: ScanSummary | null }> = ({ summary }) => {
  const hasScore = summary?.trust_score != null;
  return (
    <section className="qs-panel" aria-labelledby="trust-heading" data-testid="trust-panel">
      <h2 id="trust-heading" className="qs-panel-title">
        Trust assessment
      </h2>
      {!summary ? (
        <p className="qs-muted">The Trust Engine status is reported once a scan has been read.</p>
      ) : (
        <>
          <div className="qs-trust-row">
            <span className="qs-label">Trust Engine</span>
            <span className="qs-chip tone-neutral" data-testid="trust-status">
              {summary.trust_engine_status}
            </span>
          </div>
          {hasScore ? (
            <p data-testid="trust-score">
              Trust score: <strong>{summary.trust_score}</strong>
              {summary.trust_confidence != null && ` (confidence ${summary.trust_confidence})`}
            </p>
          ) : (
            <p data-testid="trust-no-score">
              <strong>No trust score.</strong>{" "}
              {summary.trust_engine_status === "NOT_READY"
                ? "The Trust Engine is not ready, so VECTOR does not estimate a score. The evidence above is collected data, not a verdict on the phone."
                : "The backend did not return a score, so none is shown."}
            </p>
          )}
        </>
      )}
    </section>
  );
};
