import type { FC } from "react";
import type { CapabilityEvidenceRecord } from "../../lib/api/types";
import { formatTime, humanizeDiagnosticId } from "../../lib/scan/quickScanModel";

function evidenceLabel(record: CapabilityEvidenceRecord): string {
  const field = record.metadata?.field;
  return typeof field === "string" && field ? humanizeDiagnosticId(field) : record.source_name;
}

function evidenceValue(record: CapabilityEvidenceRecord): string {
  if (record.redacted) return "Redacted";
  const value =
    record.raw_value ??
    (record.normalized_value != null ? String(record.normalized_value) : null);
  if (value === null) return "—";
  return record.unit ? `${value} ${record.unit}` : value;
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
  return (
    <div className="qs-table-wrap">
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
          {evidence.map((record) => (
            <tr key={record.evidence_id}>
              <th scope="row">{evidenceLabel(record)}</th>
              <td className="qs-mono">
                {evidenceValue(record)}
                {record.error && <span className="qs-evidence-error"> · {record.error}</span>}
              </td>
              <td>
                <span className="qs-mono">{record.collection_method}</span>
                <span className="qs-muted"> ({record.source_type})</span>
              </td>
              <td>{formatScore(record.reliability)}</td>
              <td>{formatTime(record.timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
