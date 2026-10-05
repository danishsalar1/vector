import { safeFetchJson, type SafeFetchOptions, type SafeFetchResult } from "./request";
import {
  isScanEventsResponse,
  isScanPlan,
  isScanSummary,
  type ScanEventsResponse,
  type ScanMode,
  type ScanPlan,
  type ScanStartResponse,
  type ScanSummary,
} from "./types";

export interface ScanApiRequest {
  device_id: string;
  mode?: ScanMode;
  category?: string | null;
  diagnostic_ids?: string[];
}

function isScanStartResponse(data: unknown): data is ScanStartResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return typeof d.scan_id === "string" && typeof d.state === "string";
}

/**
 * Request an immutable ScanPlan from the backend without executing.
 */
export async function fetchScanPlan(
  request: ScanApiRequest,
  options: SafeFetchOptions = {}
): Promise<SafeFetchResult<ScanPlan>> {
  return safeFetchJson<ScanPlan>("/api/v1/scans/plan", isScanPlan, {
    method: "POST",
    body: JSON.stringify(request),
    timeoutErrorMessage: "Scan planning timed out.",
    ...options,
  });
}

/**
 * Initiate a scan on the target device.
 */
export async function startScan(
  request: ScanApiRequest,
  sync: boolean = false,
  options: SafeFetchOptions = {}
): Promise<SafeFetchResult<ScanStartResponse>> {
  const url = sync ? "/api/v1/scans?sync=true" : "/api/v1/scans";
  return safeFetchJson<ScanStartResponse>(url, isScanStartResponse, {
    method: "POST",
    body: JSON.stringify(request),
    timeoutErrorMessage: "Starting scan timed out.",
    ...options,
  });
}

/**
 * Fetch scan summary / status by scan_id.
 */
export async function fetchScanSummary(
  scanId: string,
  options: SafeFetchOptions = {}
): Promise<SafeFetchResult<ScanSummary>> {
  return safeFetchJson<ScanSummary>(`/api/v1/scans/${encodeURIComponent(scanId)}`, isScanSummary, {
    timeoutErrorMessage: "Fetching scan summary timed out.",
    ...options,
  });
}

/**
 * Fetch scan event log by scan_id.
 */
export async function fetchScanEvents(
  scanId: string,
  options: SafeFetchOptions = {}
): Promise<SafeFetchResult<ScanEventsResponse>> {
  return safeFetchJson<ScanEventsResponse>(
    `/api/v1/scans/${encodeURIComponent(scanId)}/events`,
    isScanEventsResponse,
    {
      timeoutErrorMessage: "Fetching scan events timed out.",
      ...options,
    }
  );
}
