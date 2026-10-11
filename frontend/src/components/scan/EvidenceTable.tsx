import type { FC } from "react";
import type { CapabilityEvidenceRecord } from "../../lib/api/types";
import {
  evidenceNotes,
  formatEvidenceValue,
  tidyEvidenceLabel,
} from "../../lib/scan/evidenceFormat";
import { formatTime, humanizeDiagnosticId } from "../../lib/scan/quickScanModel";

function evidenceLabel(record: CapabilityEvidenceRecord): string {
  const field = record.metadata?.field;
  return typeof field === "string" && field ? humanizeDiagnosticId(field) : record.source_name;
}

function formatScore(n: number | null | undefined): string {
  return n == null ? "not modeled" : n.toFixed(2);
}

export const EvidenceTable: FC<{ evidence: readonly CapabilityEvidenceRecord[] }> = ({
  evidence,
}) => {
  if (evidence.length === 0) {
    return (
      <p className="qs-muted" data-testid="evidence-empty">
        No evidence records were collected for this diagnostic.
      </p>
    );
  }
  const notes = evidenceNotes(evidence);
  return (
    <>
      <p className="qs-scroll-hint" aria-hidden="true">
        Swipe sideways for method, reliability and time.
      </p>
      <div
        className="qs-table-wrap"
        role="region"
        aria-label="Evidence table. Scrolls sideways on small screens."
        tabIndex={0}
      >
        <table className="qs-table" data-testid="evidence-table">
          <caption className="qs-sr-only">Evidence collected from the device</caption>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Value</th>
              <th scope="col">Collected by</th>
              <th scope="col">Reliability</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((record) => {
              const value = formatEvidenceValue(record);
              return (
                <tr key={record.evidence_id}>
                  <th scope="row">
                    {tidyEvidenceLabel(evidenceLabel(record), record, value.formatted)}
                  </th>
                  <td className="qs-mono" data-testid="evidence-value">
                    <span title={value.formatted ? `Raw value: ${value.raw}` : undefined}>
                      {value.display}
                    </span>
                    {value.showRaw && (
                      <span className="qs-raw" data-testid="evidence-raw">
                        Raw: {value.raw}
                      </span>
                    )}
                    {record.error && <span className="qs-evidence-error"> · {record.error}</span>}
                  </td>
                  <td>
                    <span className="qs-mono">{record.collection_method}</span>
                    <span className="qs-muted"> ({record.source_type})</span>
                  </td>
                  <td>{formatScore(record.reliability)}</td>
                  <td>{formatTime(record.timestamp)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {notes.map((note) => (
        <p key={note} className="qs-muted qs-evidence-note" data-testid="evidence-note">
          {note}
        </p>
      ))}
    </>
  );
};
