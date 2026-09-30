import type { FC } from "react";
import { usePreflight } from "../lib/api/usePreflight";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";
import type { PreflightCheckStatus } from "../lib/api/types";

export interface PreflightStatusProps {
  timeoutMs?: number;
  provider?: DiagnosticProvider;
  autoRun?: boolean;
}

function formatStatusText(status: PreflightCheckStatus): string {
  switch (status) {
    case "PASS":
      return "PASS";
    case "WARN":
      return "WARN";
    case "FAIL":
      return "FAIL";
    case "NOT_INSTALLED":
      return "NOT INSTALLED";
    case "NOT_APPLICABLE":
      return "NOT APPLICABLE";
    default:
      return status;
  }
}

export const PreflightStatus: FC<PreflightStatusProps> = ({
  timeoutMs,
  provider,
  autoRun = true,
}) => {
  const { mode, state, data, errorMessage, runCheck } = usePreflight({
    timeoutMs,
    provider,
    autoRun,
  });

  const isDemo = mode === "demo";
  const overall = data?.overall ?? data?.overall_status;

  const getOverallDisplay = () => {
    if (state === "CHECKING") return "CHECKING";
    if (state === "ERROR") return "UNAVAILABLE";
    if (state === "IDLE") return "IDLE";
    return overall ?? "UNKNOWN";
  };

  const overallText = getOverallDisplay();
  const overallBadgeClass = overallText.toLowerCase().replace("_", "-");

  return (
    <section
      className="preflight-card"
      aria-labelledby="preflight-heading"
      data-testid="preflight-section"
    >
      <div className="preflight-header">
        <div className="brand-row">
          <h2 id="preflight-heading" className="preflight-title">
            Environment Readiness
          </h2>
          <span
            className={`mode-badge mode-${mode}`}
            data-testid="preflight-mode-badge"
          >
            Mode: {mode.toUpperCase()}
          </span>
        </div>
        <p className="service-subtitle">
          {isDemo
            ? "Demo Environment Readiness"
            : "Local Host Environment"}
        </p>
      </div>

      <div
        className="status-section"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <div className="status-indicator-row">
          <span className="status-label">Overall Readiness:</span>
          <span
            className={`status-badge status-${overallBadgeClass}`}
            data-testid="overall-status-badge"
          >
            {overallText}
          </span>
        </div>

        {state === "CHECKING" && (
          <div className="preflight-loading" data-testid="preflight-checking">
            <p>Inspecting local host environment and tooling...</p>
          </div>
        )}

        {state === "ERROR" && (
          <div className="offline-message" data-testid="preflight-error">
            <p>
              {errorMessage ||
                "VECTOR could not complete the system check. Ensure the VECTOR local service is running and try again."}
            </p>
          </div>
        )}

        {state === "COMPLETE" && data && (
          <div className="preflight-content" data-testid="preflight-content">
            {isDemo && (
              <p className="demo-note" data-testid="demo-preflight-banner">
                Demo Environment: Simulated tooling checks only. Real device verification requires Local Hardware Mode.
              </p>
            )}

            <ul
              className="checks-list"
              data-testid="preflight-checks-list"
              aria-label="Preflight checks list"
            >
              {data.checks.map((check) => {
                const statusBadgeClass = check.status
                  .toLowerCase()
                  .replace("_", "-");
                return (
                  <li
                    key={check.id}
                    className="check-item"
                    data-testid={`preflight-check-${check.id}`}
                  >
                    <div className="check-header-row">
                      <span className="check-title">{check.name}</span>
                      <span
                        className={`status-badge status-${statusBadgeClass}`}
                        data-testid={`check-status-${check.id}`}
                      >
                        {formatStatusText(check.status)}
                      </span>
                    </div>
                    <p className="check-message">{check.message}</p>
                    {check.details && (
                      <span className="check-detail-text">
                        {check.details}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      <div className="action-row">
        <button
          type="button"
          className="retry-button"
          onClick={runCheck}
          disabled={state === "CHECKING"}
          aria-label={
            state === "CHECKING"
              ? "Checking environment..."
              : isDemo
                ? "Recheck Demo Environment"
                : "Check Again"
          }
        >
          {state === "CHECKING"
            ? "Checking..."
            : isDemo
              ? "Recheck Demo"
              : "Check Again"}
        </button>
      </div>
    </section>
  );
};
