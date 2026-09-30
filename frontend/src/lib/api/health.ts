import {
  type HealthCheckResult,
  type HealthResponse,
  isHealthResponse,
} from "./types";
import { safeFetchJson } from "./request";

export interface FetchHealthOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const HEALTH_ENDPOINT = "/api/v1/health";
export const DEFAULT_TIMEOUT_MS = 5000;

export const OFFLINE_MESSAGE =
  "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again.";
export const TIMEOUT_HEALTH_MESSAGE =
  "Connection check timed out. Ensure the VECTOR local service is responding.";

/**
 * Performs a health check request to the local VECTOR API.
 * Uses a relative URL (/api/v1/health) so that the Vite dev proxy
 * routes it to http://127.0.0.1:8742 in development.
 */
export async function checkHealth(
  options: FetchHealthOptions = {}
): Promise<HealthCheckResult> {
  const { signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const result = await safeFetchJson<HealthResponse>(
    HEALTH_ENDPOINT,
    isHealthResponse,
    {
      signal,
      timeoutMs,
      fallbackErrorMessage: OFFLINE_MESSAGE,
      timeoutErrorMessage: TIMEOUT_HEALTH_MESSAGE,
    }
  );

  if (result.ok) {
    return {
      state: "ONLINE",
      data: result.data,
      errorMessage: null,
    };
  }

  return {
    state: "OFFLINE",
    data: null,
    errorMessage:
      result.error.kind === "TIMEOUT" ? OFFLINE_MESSAGE : result.error.message,
    error: result.error,
  };
}
