import type { FC } from "react";
import { useHealthCheck } from "../lib/api/useHealthCheck";

export interface HealthStatusProps {
  timeoutMs?: number;
}

export const HealthStatus: FC<HealthStatusProps> = ({ timeoutMs }) => {
  const { state, data, errorMessage, retry } = useHealthCheck(timeoutMs);

  return (
    <section className="health-card" aria-labelledby="service-heading">
      <div className="health-header">
        <h1 id="service-heading" className="brand-title">
          VECTOR
        </h1>
        <p className="service-subtitle">Local Diagnostic Service</p>
      </div>

      <div
        className="status-section"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <div className="status-indicator-row">
          <span className="status-label">Status:</span>
          <span
            className={`status-badge status-${state.toLowerCase()}`}
            data-testid="status-badge"
          >
            {state}
          </span>
        </div>

        {state === "ONLINE" && data && (
          <div className="online-details" data-testid="online-details">
            <div className="detail-row">
              <span className="detail-label">Version:</span>
              <span className="detail-value">{data.version}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Mode:</span>
              <span className="detail-value">{data.mode}</span>
            </div>
          </div>
        )}

        {state === "OFFLINE" && (
          <div className="offline-message" data-testid="offline-message">
            <p>
              {errorMessage ||
                "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again."}
            </p>
          </div>
        )}
      </div>

      <div className="action-row">
        <button
          type="button"
          className="retry-button"
          onClick={retry}
          disabled={state === "CHECKING"}
          aria-label="Retry connection check"
        >
          {state === "CHECKING" ? "Checking..." : "Retry"}
        </button>
      </div>
    </section>
  );
};
