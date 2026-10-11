import type { FC } from "react";
import {
  displayDiagnosticName,
  statusTone,
  type DiagnosticRow,
  type ScanProgress as ScanProgressCounts,
} from "../../lib/scan/quickScanModel";

export interface ScanProgressProps {
  rows: readonly DiagnosticRow[];
  progress: ScanProgressCounts;
  scanState: string;
  finished: boolean;
}

/**
 * Per-diagnostic steps driven only by returned results and events.
 * There is no percentage, no timer and no animation that advances on its own.
 */
export const ScanProgress: FC<ScanProgressProps> = ({ rows, progress, scanState, finished }) => (
  <div className="vx-progress" data-testid="scan-lifecycle">
    <div className="vx-progress-head">
      <span className="qs-label">Scan state</span>
      <span className={`qs-chip tone-${statusTone(scanState)}`} data-testid="scan-state">
        {scanState}
      </span>
      <span className="vx-muted" data-testid="scan-progress-text">
        {progress.finished} of {progress.total} diagnostics reported
        {progress.totalEvents > 0 &&
          ` · ${progress.evidenceEvents} evidence events · ${progress.totalEvents} events`}
      </span>
    </div>
    <ol
      className="vx-steps"
      aria-label={`${progress.finished} of ${progress.total} diagnostics have reported a result`}
    >
      {rows.map((row) => {
        const state = row.result ? "done" : row.status === "RUNNING" ? "active" : "waiting";
        const label = row.result
          ? row.status
          : row.status === "RUNNING"
            ? "RUNNING"
            : finished
              ? "NO RESULT"
              : "WAITING";
        return (
          <li
            key={row.id}
            className={`vx-step is-${state}${row.result ? ` tone-step-${statusTone(row.status)}` : ""}`}
          >
            <span className="vx-step-bar" aria-hidden="true" />
            <span className="vx-step-name">{displayDiagnosticName(row.name)}</span>
            <span className="vx-step-state">{label}</span>
          </li>
        );
      })}
    </ol>
  </div>
);
