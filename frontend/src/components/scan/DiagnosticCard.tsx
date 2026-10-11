import type { FC } from "react";
import { buildCardModel } from "../../lib/scan/cardMetrics";
import { NARROW_QUERY, useMediaQuery } from "../../lib/scan/useMediaQuery";
import {
  describeVerificationLevel,
  displayDiagnosticName,
  formatDuration,
  statusTone,
  type DiagnosticRow,
  type RowStatus,
} from "../../lib/scan/quickScanModel";
import { EvidenceTable } from "./EvidenceTable";

export interface DiagnosticCardProps {
  row: DiagnosticRow;
  scanStarted: boolean;
  finished: boolean;
  expanded: boolean;
  onToggle: () => void;
}

function statusLabel(status: RowStatus, scanStarted: boolean, finished: boolean): string {
  if (status === "WAITING") {
    if (!scanStarted) return "NOT RUN";
    return finished ? "NO RESULT" : "WAITING";
  }
  return status;
}

/** One sentence separating "data was collected" from "the hardware was tested". */
function collectionLine(row: DiagnosticRow): string | null {
  if (!row.result) return null;
  switch (row.verificationLevel) {
    case "RUNTIME_DETECTION":
      return "Runtime detection: data was read from the phone. The component was not functionally tested.";
    case "FUNCTIONAL_VERIFICATION":
      return "Functional verification: the component was exercised.";
    case "REFERENCE_COMPARISON":
      return "Reference comparison against model reference data.";
    default:
      return "Verification level not reported, so this is not treated as a functional result.";
  }
}

export const DiagnosticCard: FC<DiagnosticCardProps> = ({
  row,
  scanStarted,
  finished,
  expanded,
  onToggle,
}) => {
  const level = describeVerificationLevel(row.verificationLevel);
  const model = buildCardModel(row.result);
  const evidenceCount = row.result?.evidence.length ?? 0;
  const panelId = `evidence-${row.id}`;
  const tone = statusTone(row.status);
  const line = collectionLine(row);
  // On a phone the limitation text is collapsed behind a disclosure; elsewhere it stays open.
  const narrow = useMediaQuery(NARROW_QUERY);
  const hasLimits = Boolean(model.note || row.result?.summary || line);

  return (
    <li
      className={`vx-card tone-edge-${tone}${expanded ? " is-expanded" : ""}`}
      data-testid="diagnostic-row"
      data-diagnostic-id={row.id}
    >
      <header className="vx-card-head">
        <h3 className="vx-card-title">{displayDiagnosticName(row.name)}</h3>
        <span className={`qs-chip tone-${tone}`} data-testid="diagnostic-status">
          {statusLabel(row.status, scanStarted, finished)}
        </span>
      </header>

      {model.metrics.length > 0 && (
        <dl className="vx-metrics" data-testid="card-metrics">
          {model.metrics.map((m) => (
            <div
              key={m.key}
              className={`vx-metric${m.quiet ? " is-quiet" : ""}`}
              title={m.raw ? `Raw value: ${m.raw}` : undefined}
              data-testid="metric"
            >
              <dt>{m.label}</dt>
              <dd className="vx-metric-value">{m.value}</dd>
              {m.hint && <dd className="vx-metric-hint">{m.hint}</dd>}
            </div>
          ))}
        </dl>
      )}

      {model.meter && (
        <div className="vx-gauge" data-testid="card-meter">
          <div
            className="vx-gauge-track"
            role="img"
            aria-label={`${model.meter.label}: ${model.meter.caption}`}
          >
            <span
              className="vx-gauge-fill"
              style={{ width: `${Math.round(Math.min(1, Math.max(0, model.meter.fraction)) * 100)}%` }}
            />
          </div>
          <span className="vx-gauge-caption">{model.meter.caption}</span>
        </div>
      )}

      {model.chips.length > 0 && (
        <ul className="vx-sensors" aria-label="Sensor readings" data-testid="card-sensors">
          {model.chips.map((chip) => (
            <li key={chip.label}>
              <span className="vx-sensor-name">{chip.label}</span>
              <span className="vx-sensor-value">{chip.value}</span>
            </li>
          ))}
        </ul>
      )}

      {hasLimits && (
        <details key={String(narrow)} className="vx-limits" open={!narrow}>
          <summary>Limitations: data collected, not hardware tested</summary>
          {model.note && <p className="vx-note">{model.note}</p>}
          {row.result?.summary && (
            <p className="vx-summary" data-testid="diagnostic-summary">
              {row.result.summary}
            </p>
          )}
          {line && <p className="vx-collection">{line}</p>}
        </details>
      )}

      {!row.result && (
        <p className="vx-muted">
          {scanStarted && !finished
            ? "Waiting for this diagnostic to report."
            : finished
              ? "This diagnostic did not report a result."
              : "Runs when you start the scan."}
        </p>
      )}

      <footer className="vx-card-foot">
        <div className="qs-chips">
          <span className="qs-chip tone-neutral qs-mono" title={level.meaning}>
            {level.badge}
          </span>
          {row.requiresProbe === true && (
            <span className="qs-chip tone-warn">Requires VECTOR Probe</span>
          )}
        </div>
        {row.result && (
          <div className="vx-card-actions">
            <button
              type="button"
              className="qs-button qs-button-quiet"
              aria-expanded={expanded}
              aria-controls={panelId}
              onClick={onToggle}
              data-testid="evidence-toggle"
            >
              Technical evidence ({evidenceCount})
              <span className="vx-chevron" aria-hidden="true" />
            </button>
            <span className="vx-muted">{formatDuration(row.result.duration_seconds)}</span>
          </div>
        )}
      </footer>

      {row.result && expanded && (
        <div id={panelId} className="vx-card-evidence">
          <EvidenceTable evidence={row.result.evidence} />
        </div>
      )}
    </li>
  );
};
