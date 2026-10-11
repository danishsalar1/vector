import { useState, type FC } from "react";
import type { ConnectedDevice } from "../../lib/api/devices";
import {
  buildDiagnosticRows,
  computeProgress,
  describeDevice,
  describeVerificationLevel,
  parseDiagnosticResults,
  splitPlan,
  statusTone,
  formatDuration,
  type DiagnosticRow,
  type RowStatus,
} from "../../lib/scan/quickScanModel";
import type { UseQuickScanResult } from "../../lib/scan/useQuickScan";
import { EvidenceTable } from "./EvidenceTable";
import { EventLog } from "./EventLog";
import { TrustEnginePanel } from "./TrustEnginePanel";

export interface ScanPanelProps {
  device: ConnectedDevice;
  session: UseQuickScanResult;
}

const START_LABELS: Partial<Record<UseQuickScanResult["phase"], string>> = {
  PLAN_READY: "Start Quick Scan",
  START_ERROR: "Try again",
  FINISHED: "Run scan again",
  PLANNING: "Preparing plan…",
  STARTING: "Starting…",
  RUNNING: "Scan in progress…",
};

function rowStatusLabel(status: RowStatus, scanStarted: boolean, finished: boolean): string {
  if (status === "WAITING") {
    if (!scanStarted) return "NOT RUN";
    return finished ? "NO RESULT" : "WAITING";
  }
  return status;
}

const DiagnosticItem: FC<{
  row: DiagnosticRow;
  scanStarted: boolean;
  finished: boolean;
  expanded: boolean;
  onToggle: () => void;
}> = ({ row, scanStarted, finished, expanded, onToggle }) => {
  const level = describeVerificationLevel(row.verificationLevel);
  const label = rowStatusLabel(row.status, scanStarted, finished);
  const evidenceCount = row.result?.evidence.length ?? 0;
  const panelId = `evidence-${row.id}`;
  return (
    <li className="qs-diag" data-testid="diagnostic-row" data-diagnostic-id={row.id}>
      <div className="qs-diag-main">
        <div className="qs-diag-head">
          <h3 className="qs-diag-name">{row.name}</h3>
          <span
            className={`qs-chip tone-${statusTone(row.status)}`}
            data-testid="diagnostic-status"
          >
            {label}
          </span>
        </div>
        <p className="qs-chips">
          <span className="qs-chip tone-neutral qs-mono" title={level.meaning}>
            {level.badge}
          </span>
          {row.requiresProbe === true && (
            <span className="qs-chip tone-warn">Requires VECTOR Probe</span>
          )}
        </p>
        {row.result?.summary && (
          <p className="qs-diag-summary" data-testid="diagnostic-summary">
            {row.result.summary}
          </p>
        )}
        {row.result && (
          <div className="qs-diag-foot">
            <button
              type="button"
              className="qs-button qs-button-quiet"
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={onToggle}
              data-testid="evidence-toggle"
            >
              {expanded ? "Hide evidence" : `Show evidence (${evidenceCount})`}
            </button>
            <span className="qs-muted">{formatDuration(row.result.duration_seconds)}</span>
          </div>
        )}
      </div>
      {row.result && expanded && (
        <div id={panelId} className="qs-diag-evidence">
          <EvidenceTable evidence={row.result.evidence} />
        </div>
      )}
    </li>
  );
};

export const ScanPanel: FC<ScanPanelProps> = ({ device, session }) => {
  const { phase, plan, summary, events, error, pollWarning, start, retryPlan, resumePolling } =
    session;
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(new Set());
  const { title } = describeDevice(device);

  const scanStarted = phase === "RUNNING" || phase === "FINISHED" || phase === "POLL_LOST";
  const finished = phase === "FINISHED";
  const { results, unreadable } = parseDiagnosticResults(summary?.diagnostic_results ?? []);
  const rows = plan ? buildDiagnosticRows(plan, results, events, finished) : [];
  const progress = computeProgress(rows, events);
  const skipped = plan ? splitPlan(plan).skipped : [];

  const tallies = new Map<string, number>();
  for (const r of results) tallies.set(r.status, (tallies.get(r.status) ?? 0) + 1);

  const toggle = (id: string) =>
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const canStart = phase === "PLAN_READY" || phase === "START_ERROR" || phase === "FINISHED";

  return (
    <>
      <section className="qs-panel" aria-labelledby="scan-heading" data-testid="scan-panel">
        <div className="qs-panel-head">
          <div>
            <h2 id="scan-heading" className="qs-panel-title">
              Quick Scan
            </h2>
            <p className="qs-muted">{title}</p>
          </div>
          <button
            type="button"
            className="qs-button qs-button-primary"
            onClick={start}
            disabled={!canStart}
            data-testid="start-scan"
          >
            {START_LABELS[phase] ?? "Start Quick Scan"}
          </button>
        </div>

        {phase === "PLANNING" && (
          <p className="qs-muted" role="status" data-testid="plan-loading">
            Asking the agent which diagnostics apply to this phone…
          </p>
        )}

        {phase === "PLAN_ERROR" && (
          <div className="qs-alert" role="alert" data-testid="plan-error">
            <p>{error}</p>
            <button type="button" className="qs-button" onClick={retryPlan}>
              Retry planning
            </button>
          </div>
        )}

        {phase === "START_ERROR" && (
          <div className="qs-alert" role="alert" data-testid="start-error">
            <p>{error}</p>
          </div>
        )}

        {plan && (
          <p className="qs-notice" data-testid="verification-explainer">
            <strong>How to read this scan.</strong> Diagnostics labelled{" "}
            <span className="qs-mono">RUNTIME_DETECTION</span> confirm that VECTOR could
            read data from the phone. A PASS there means the collection succeeded. It does
            not prove the component works or is healthy; for example, battery percentage is
            not battery health.
          </p>
        )}

        {scanStarted && (
          <div className="qs-lifecycle" data-testid="scan-lifecycle">
            <div className="qs-lifecycle-row">
              <span className="qs-label">Scan state</span>
              <span
                className={`qs-chip tone-${statusTone(summary?.state ?? "RUNNING")}`}
                data-testid="scan-state"
              >
                {summary?.state ?? "STARTING"}
              </span>
              <span className="qs-muted" data-testid="scan-progress-text">
                {progress.finished} of {progress.total} diagnostics reported
                {progress.totalEvents > 0 &&
                  ` · ${progress.evidenceEvents} evidence events · ${progress.totalEvents} events`}
              </span>
            </div>
            <div
              className="qs-meter"
              role="img"
              aria-label={`${progress.finished} of ${progress.total} diagnostics have reported a result`}
            >
              {rows.map((row) => (
                <span
                  key={row.id}
                  className={`qs-meter-seg${
                    row.result ? ` tone-${statusTone(row.status)} is-done` : ""
                  }${row.status === "RUNNING" ? " is-active" : ""}`}
                />
              ))}
            </div>
            {finished && tallies.size > 0 && (
              <p className="qs-tallies" data-testid="scan-tallies">
                {[...tallies.entries()].map(([status, count]) => (
                  <span key={status} className={`qs-chip tone-${statusTone(status)}`}>
                    {count} {status}
                  </span>
                ))}
              </p>
            )}
            {summary?.error && (
              <p className="qs-alert" role="alert" data-testid="scan-error">
                Scan {summary.state.toLowerCase()}: {summary.error}
              </p>
            )}
            {pollWarning && (
              <p className="qs-warning" role="status" data-testid="poll-warning">
                {pollWarning} Retrying…
              </p>
            )}
            {phase === "POLL_LOST" && (
              <div className="qs-alert" role="alert" data-testid="poll-lost">
                <p>{error}</p>
                <p className="qs-muted">
                  The scan may still be running on the agent. Results shown below are the
                  last ones received.
                </p>
                <button type="button" className="qs-button" onClick={resumePolling}>
                  Check scan status again
                </button>
              </div>
            )}
          </div>
        )}

        {plan && rows.length === 0 && (
          <div className="qs-empty" data-testid="plan-empty">
            <p className="qs-empty-title">No diagnostics apply to this device</p>
            <p className="qs-muted">The agent planned zero runnable diagnostics for this phone.</p>
          </div>
        )}

        {rows.length > 0 && (
          <ul className="qs-diag-list" aria-label="Diagnostics" data-testid="diagnostic-list">
            {rows.map((row) => (
              <DiagnosticItem
                key={row.id}
                row={row}
                scanStarted={scanStarted}
                finished={finished}
                expanded={expandedIds.has(row.id)}
                onToggle={() => toggle(row.id)}
              />
            ))}
          </ul>
        )}

        {unreadable > 0 && (
          <p className="qs-alert" role="alert" data-testid="unreadable-results">
            {unreadable} result {unreadable === 1 ? "entry" : "entries"} from the agent could
            not be read and {unreadable === 1 ? "is" : "are"} not shown.
          </p>
        )}

        {skipped.length > 0 && (
          <details className="qs-details" data-testid="skipped-list">
            <summary>{skipped.length} diagnostics not run on this device</summary>
            <ul className="qs-skipped">
              {skipped.map((item) => (
                <li key={item.diagnostic_id}>
                  <span className="qs-mono">{item.diagnostic_id}</span>
                  <span className="qs-chip tone-neutral">{item.applicability}</span>
                  <span className="qs-muted">{item.reason ?? "No reason reported."}</span>
                </li>
              ))}
            </ul>
          </details>
        )}

        <EventLog events={events} />
      </section>

      {scanStarted && <TrustEnginePanel summary={summary} />}
    </>
  );
};
