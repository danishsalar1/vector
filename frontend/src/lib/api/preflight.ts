import {
  type PreflightResponse,
  type PreflightResult,
  isPreflightResponse,
} from "./types";
import { safeFetchJson } from "./request";

export interface FetchPreflightOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const PREFLIGHT_ENDPOINT = "/api/v1/system/preflight";
export const DEFAULT_PREFLIGHT_TIMEOUT_MS = 5000;

export const PREFLIGHT_ERROR_MESSAGE =
  "VECTOR could not complete the system check. Ensure the VECTOR local service is running and try again.";
export const TIMEOUT_PREFLIGHT_MESSAGE =
  "System check timed out. Ensure the VECTOR local service is responding and try again.";

/**
 * Performs a system preflight environment inspection via GET /api/v1/system/preflight.
 * Uses a relative URL routed by the Vite dev proxy to localhost:8742 in development.
 */
export async function fetchPreflight(
  options: FetchPreflightOptions = {}
): Promise<PreflightResult> {
  const { signal, timeoutMs = DEFAULT_PREFLIGHT_TIMEOUT_MS } = options;

  const result = await safeFetchJson<PreflightResponse>(
    PREFLIGHT_ENDPOINT,
    isPreflightResponse,
    {
      signal,
      timeoutMs,
      fallbackErrorMessage: PREFLIGHT_ERROR_MESSAGE,
      timeoutErrorMessage: TIMEOUT_PREFLIGHT_MESSAGE,
    }
  );

  if (result.ok) {
    return {
      state: "COMPLETE",
      data: result.data,
      errorMessage: null,
    };
  }

  return {
    state: "ERROR",
    data: null,
    errorMessage: result.error.message,
    error: result.error,
  };
}
