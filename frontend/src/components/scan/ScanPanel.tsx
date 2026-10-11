import { useState, type FC } from "react";
import {
  buildDiagnosticRows,
  computeProgress,
  parseDiagnosticResults,
  splitPlan,
  statusTone,
  summarizeSkipped,
} from "../../lib/scan/quickScanModel";
import { NARROW_QUERY, useMediaQuery } from "../../lib/scan/useMediaQuery";
import type { UseQuickScanResult } from "../../lib/scan/useQuickScan";
import { DiagnosticCard } from "./DiagnosticCard";
import { EventLog } from "./EventLog";
import { ScanProgress } from "./ScanProgress";
import { TrustEnginePanel } from "./TrustEnginePanel";

export interface ScanPanelProps {
  session: UseQuickScanResult;
}

/** Everything below the device overview: progress, diagnostic cards, trust status, event log. */
export const ScanPanel: FC<ScanPanelProps> = ({ session }) => {
  const { phase, plan, summary, events, error, pollWarning, retryPlan, resumePolling } = session;
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(new Set());
  const narrow = useMediaQuery(NARROW_QUERY);

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

  return (
    <div className="vx-scan" data-testid="scan-panel">
      {phase === "PLANNING" && (
        <p className="vx-muted" role="status" data-testid="plan-loading">
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

      {scanStarted && (
        <section className="vx-panel">
          <ScanProgress
            rows={rows}
            progress={progress}
            scanState={summary?.state ?? "STARTING"}
            finished={finished}
          />
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
              <p className="vx-muted">
                The scan may still be running on the agent. Results shown below are the last
                ones received.
              </p>
              <button type="button" className="qs-button" onClick={resumePolling}>
                Check scan status again
              </button>
            </div>
          )}
        </section>
      )}

      {plan && (
        <aside className="vx-explainer" data-testid="verification-explainer">
          <details key={String(narrow)} open={!narrow}>
            <summary>
              <strong>Data collected is not hardware tested.</strong>
            </summary>
            <p>
              Diagnostics labelled <span className="qs-mono">RUNTIME_DETECTION</span> confirm that
              VECTOR could read data from the phone. A PASS there means the collection succeeded.
              It does not prove the component works or is healthy; for example, battery
              percentage is not battery health. Only a diagnostic labelled{" "}
              <span className="qs-mono">FUNCTIONAL_VERIFICATION</span> exercises a component.
            </p>
          </details>
        </aside>
      )}

      {plan && rows.length === 0 && (
        <div className="qs-empty" data-testid="plan-empty">
          <p className="qs-empty-title">No diagnostics apply to this device</p>
          <p className="vx-muted">The agent planned zero runnable diagnostics for this phone.</p>
        </div>
      )}

      {rows.length > 0 && (
        <ul className="vx-grid" aria-label="Diagnostics" data-testid="diagnostic-list">
          {rows.map((row) => (
            <DiagnosticCard
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
          {unreadable} result {unreadable === 1 ? "entry" : "entries"} from the agent could not
          be read and {unreadable === 1 ? "is" : "are"} not shown.
        </p>
      )}

      {scanStarted && <TrustEnginePanel summary={summary} />}

      {skipped.length > 0 && (
        <details className="qs-details" data-testid="skipped-list">
          <summary>{summarizeSkipped(skipped, plan?.platform ?? "")}</summary>
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
    </div>
  );
};
