import type { FC } from "react";
import { useHealthCheck } from "../lib/api/useHealthCheck";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";

export interface HealthStatusProps {
  timeoutMs?: number;
  provider?: DiagnosticProvider;
}

export const HealthStatus: FC<HealthStatusProps> = ({ timeoutMs, provider }) => {
  const { mode, state, data, errorMessage, retry } = useHealthCheck({
    timeoutMs,
    provider,
  });

  const isDemo = mode === "demo";
  const subtitle = isDemo
    ? "Demo Diagnostic Environment"
    : "Local Diagnostic Service";

  return (
    <section className="health-card" aria-labelledby="service-heading">
      <div className="health-header">
        <div className="brand-row">
          <h1 id="service-heading" className="brand-title">
            VECTOR
          </h1>
          <span
            className={`mode-badge mode-${mode}`}
            data-testid="mode-badge"
          >
            Mode: {mode.toUpperCase()}
          </span>
        </div>
        <p className="service-subtitle">{subtitle}</p>
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
            className={`status-badge status-${state.toLowerCase().replace("_", "-")}`}
            data-testid="status-badge"
          >
            {state === "DEMO_READY" ? "DEMO READY" : state}
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

        {state === "DEMO_READY" && data && (
          <div className="demo-details" data-testid="demo-details">
            <div className="detail-row">
              <span className="detail-label">Version:</span>
              <span className="detail-value">{data.version}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Dataset:</span>
              <span className="detail-value">DEMO DATASET</span>
            </div>
            <p className="demo-note" data-testid="demo-note">
              Demo environment ready. Real USB hardware diagnostics require Local Hardware Mode.
            </p>
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
          aria-label={isDemo ? "Refresh demo environment" : "Retry connection check"}
        >
          {state === "CHECKING" ? "Checking..." : isDemo ? "Refresh Demo" : "Retry"}
        </button>
      </div>
    </section>
  );
};
