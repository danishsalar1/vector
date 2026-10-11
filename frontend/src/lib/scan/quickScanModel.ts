/**
 * Pure helpers for the Quick Scan workflow.
 *
 * Everything here is derived from backend payloads. Nothing is invented:
 * - no percentages (progress is a count of diagnostics that have reported a result)
 * - no default "healthy" status (a diagnostic with no result is WAITING or RUNNING)
 * - an unknown verification level is never promoted to a functional claim
 */

import type { ConnectedDevice } from "../api/devices";
import type {
  ApiError,
  DiagnosticEvent,
  DiagnosticResult,
  PlannedDiagnostic,
  ScanLifecycleState,
  ScanMode,
  ScanPlan,
  VerificationLevel,
} from "../api/types";
import { isDiagnosticResult } from "../api/types";

/** The Quick Scan is the backend's default full scan of every eligible runtime diagnostic. */
export const QUICK_SCAN_MODE: ScanMode = "FULL_VERIFICATION";

const TERMINAL_STATES: readonly ScanLifecycleState[] = [
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

export function isTerminalScanState(state: string): boolean {
  return (TERMINAL_STATES as readonly string[]).includes(state);
}

// ------------------------------------------------------------
// Devices
// ------------------------------------------------------------

export interface DeviceEligibility {
  eligible: boolean;
  /** Plain-language reason shown to the user when not eligible. */
  reason: string | null;
}

/**
 * A device can be scanned only when it is connected AND the backend reports it
 * as authorized. Anything else (including "not reported") blocks the scan.
 */
export function getDeviceEligibility(device: ConnectedDevice): DeviceEligibility {
  if (device.connection_state !== "CONNECTED") {
    return {
      eligible: false,
      reason: `Device is ${device.connection_state.toLowerCase()}. Reconnect the USB cable and refresh.`,
    };
  }
  switch (device.authorization_state) {
    case "AUTHORIZED":
      return { eligible: true, reason: null };
    case "AUTHORIZATION_REQUIRED":
      return {
        eligible: false,
        reason:
          "USB debugging is not authorized. Unlock the phone, accept the “Allow USB debugging” prompt, then refresh.",
      };
    case "RESTRICTED":
      return {
        eligible: false,
        reason:
          "This device restricts access. VECTOR does not bypass platform security, so it cannot be scanned.",
      };
    default:
      return {
        eligible: false,
        reason: "Authorization status was not reported, so a scan cannot start safely.",
      };
  }
}

export function formatPlatform(platform: string): string {
  const p = platform.toUpperCase();
  if (p === "ANDROID") return "Android";
  if (p === "IOS") return "iOS";
  return platform;
}

export function describeDevice(device: ConnectedDevice): {
  title: string;
  os: string | null;
} {
  const id = device.identity;
  const name = [id?.manufacturer, id?.model].filter(Boolean).join(" ");
  const version = id?.android_version ?? id?.ios_version ?? null;
  return {
    title: name || "Unidentified device",
    os: version ? `${formatPlatform(device.platform)} ${version}` : null,
  };
}

// ------------------------------------------------------------
// Errors
// ------------------------------------------------------------

/** Turn a transport/HTTP error into a message that tells the user what to do. */
export function describeScanError(error: ApiError, action: string): string {
  if (error.kind === "HTTP") {
    switch (error.statusCode) {
      case 403:
        return `${action}: the phone has not authorized USB debugging. Unlock it and accept the prompt, then refresh.`;
      case 404:
        return `${action}: the agent no longer knows this device or scan. Refresh the device list.`;
      case 400:
        return `${action}: the device is not connected. Reconnect the USB cable and refresh.`;
      case 409:
        return `${action}: a scan is already running on this device.`;
      default:
        return `${action}: ${error.message}`;
    }
  }
  return `${action}: ${error.message}`;
}

// ------------------------------------------------------------
// Labels
// ------------------------------------------------------------

export function humanizeDiagnosticId(id: string): string {
  return id
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export interface VerificationLevelInfo {
  /** Token shown verbatim as the badge, or a neutral placeholder if unreported. */
  badge: string;
  /** What a PASS at this level does and does not establish. */
  meaning: string;
}

export function describeVerificationLevel(
  level: VerificationLevel | null | undefined
): VerificationLevelInfo {
  switch (level) {
    case "RUNTIME_DETECTION":
      return {
        badge: "RUNTIME_DETECTION",
        meaning:
          "VECTOR could read this data from the phone. It does not test that the component works.",
      };
    case "FUNCTIONAL_VERIFICATION":
      return {
        badge: "FUNCTIONAL_VERIFICATION",
        meaning: "The component was exercised and its behavior was checked.",
      };
    case "REFERENCE_COMPARISON":
      return {
        badge: "REFERENCE_COMPARISON",
        meaning: "Observed values were compared against trusted model reference data.",
      };
    default:
      return {
        badge: "LEVEL NOT REPORTED",
        meaning:
          "The backend did not report what this diagnostic verifies, so it is treated as not functional.",
      };
  }
}

const EVENT_LABELS: Record<string, string> = {
  "scan.started": "Scan started",
  "diagnostic.started": "Diagnostic started",
  "diagnostic.progress": "Diagnostic progress",
  "diagnostic.evidence": "Evidence collected",
  "diagnostic.completed": "Diagnostic completed",
  "diagnostic.failed": "Diagnostic failed",
  "diagnostic.inconclusive": "Diagnostic inconclusive",
  "scan.completed": "Scan completed",
  "scan.failed": "Scan failed",
};

export function describeEventType(type: string): string {
  return EVENT_LABELS[type] ?? type;
}

// ------------------------------------------------------------
// Rows (plan + results + events)
// ------------------------------------------------------------

/** Display status before a result exists. Results use the backend's status verbatim. */
export type RowStatus = DiagnosticResult["status"] | "WAITING";

export interface DiagnosticRow {
  id: string;
  name: string;
  status: RowStatus;
  /** Present once the backend has reported a result for this diagnostic. */
  result: DiagnosticResult | null;
  verificationLevel: VerificationLevel | null | undefined;
  requiresProbe: boolean | null | undefined;
}

export interface ParsedResults {
  results: DiagnosticResult[];
  /** Entries that did not match the expected shape. Surfaced, never dropped silently. */
  unreadable: number;
}

export function parseDiagnosticResults(raw: readonly unknown[]): ParsedResults {
  const results: DiagnosticResult[] = [];
  let unreadable = 0;
  for (const entry of raw) {
    if (isDiagnosticResult(entry)) {
      results.push(entry);
    } else {
      unreadable += 1;
    }
  }
  return { results, unreadable };
}

export function splitPlan(plan: ScanPlan): {
  planned: PlannedDiagnostic[];
  skipped: PlannedDiagnostic[];
} {
  const planned: PlannedDiagnostic[] = [];
  const skipped: PlannedDiagnostic[] = [];
  for (const item of plan.planned_items) {
    (item.applicability === "APPLICABLE" ? planned : skipped).push(item);
  }
  return { planned, skipped };
}

/**
 * `scanFinished` means the backend reported a terminal scan state. After that,
 * a diagnostic without a result is never shown as RUNNING.
 */
export function buildDiagnosticRows(
  plan: ScanPlan,
  results: readonly DiagnosticResult[],
  events: readonly DiagnosticEvent[],
  scanFinished = false
): DiagnosticRow[] {
  const resultById = new Map(results.map((r) => [r.diagnostic_id, r]));
  const startedIds = new Set(
    events
      .filter((e) => e.event_type === "diagnostic.started" && e.diagnostic_id)
      .map((e) => e.diagnostic_id as string)
  );

  const { planned } = splitPlan(plan);
  const rows: DiagnosticRow[] = planned.map((item) => {
    const result = resultById.get(item.diagnostic_id) ?? null;
    return {
      id: item.diagnostic_id,
      name: result?.diagnostic_name ?? humanizeDiagnosticId(item.diagnostic_id),
      status: result
        ? result.status
        : startedIds.has(item.diagnostic_id) && !scanFinished
          ? "RUNNING"
          : "WAITING",
      result,
      verificationLevel: item.verification_level,
      requiresProbe: item.requires_probe,
    };
  });

  // A result the plan did not list is still real data: show it, flagged by its missing level.
  const plannedIds = new Set(planned.map((p) => p.diagnostic_id));
  for (const result of results) {
    if (!plannedIds.has(result.diagnostic_id)) {
      rows.push({
        id: result.diagnostic_id,
        name: result.diagnostic_name,
        status: result.status,
        result,
        verificationLevel: undefined,
        requiresProbe: undefined,
      });
    }
  }
  return rows;
}

export interface ScanProgress {
  finished: number;
  total: number;
  evidenceEvents: number;
  totalEvents: number;
}

/** Real counts only. There is deliberately no percentage. */
export function computeProgress(
  rows: readonly DiagnosticRow[],
  events: readonly DiagnosticEvent[]
): ScanProgress {
  return {
    finished: rows.filter((r) => r.result !== null).length,
    total: rows.length,
    evidenceEvents: events.filter((e) => e.event_type === "diagnostic.evidence").length,
    totalEvents: events.length,
  };
}

// ------------------------------------------------------------
// Presentation helpers
// ------------------------------------------------------------

export function statusTone(
  status: string
): "ok" | "warn" | "bad" | "neutral" | "active" {
  switch (status) {
    case "PASS":
    case "COMPLETED":
      return "ok";
    case "INCONCLUSIVE":
    case "DEGRADED":
    case "RESTRICTED":
      return "warn";
    case "FAIL":
    case "ERROR":
    case "FAILED":
      return "bad";
    case "RUNNING":
      return "active";
    default:
      return "neutral";
  }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} s`;
}

export function formatTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString();
}
