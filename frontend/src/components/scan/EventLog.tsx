import type { FC } from "react";
import type { DiagnosticEvent } from "../../lib/api/types";
import {
  describeEventType,
  formatTime,
  humanizeDiagnosticId,
} from "../../lib/scan/quickScanModel";

/** The raw lifecycle log exactly as returned by /scans/{id}/events. */
export const EventLog: FC<{ events: readonly DiagnosticEvent[] }> = ({ events }) => {
  if (events.length === 0) return null;
  const evidenceCount = events.filter((e) => e.event_type === "diagnostic.evidence").length;
  return (
    <details className="qs-details" data-testid="event-log">
      <summary>
        Scan event log ({events.length} events, {evidenceCount} evidence)
      </summary>
      <ol className="qs-events">
        {events.map((event) => (
          <li key={event.event_id}>
            <span className="qs-mono qs-event-time">{formatTime(event.timestamp)}</span>
            <span className="qs-event-type">{describeEventType(event.event_type)}</span>
            {event.diagnostic_id && (
              <span className="qs-muted">{humanizeDiagnosticId(event.diagnostic_id)}</span>
            )}
            {event.message && <span className="qs-event-message">{event.message}</span>}
          </li>
        ))}
      </ol>
    </details>
  );
};
