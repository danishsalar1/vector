import {
  type HealthCheckResult,
  isHealthResponse,
} from "./types";

export interface FetchHealthOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const HEALTH_ENDPOINT = "/api/v1/health";
export const DEFAULT_TIMEOUT_MS = 5000;

export const OFFLINE_MESSAGE =
  "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again.";

/**
 * Performs a health check request to the local VECTOR API.
 * Uses a relative URL (/api/v1/health) so that the Vite dev proxy
 * routes it to http://127.0.0.1:8742 in development.
 */
export async function checkHealth(
  options: FetchHealthOptions = {}
): Promise<HealthCheckResult> {
  const { signal: externalSignal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  if (externalSignal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError");
  }

  const internalController = new AbortController();

  const timeoutId = setTimeout(() => {
    internalController.abort();
  }, timeoutMs);

  const onExternalAbort = () => {
    internalController.abort();
  };

  if (externalSignal) {
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  try {
    const response = await fetch(HEALTH_ENDPOINT, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal: internalController.signal,
    });

    if (!response.ok) {
      return {
        state: "OFFLINE",
        data: null,
        errorMessage: `VECTOR Local Agent returned HTTP ${response.status}.`,
      };
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return {
        state: "OFFLINE",
        data: null,
        errorMessage: "Received an invalid response format from VECTOR Local Agent.",
      };
    }

    if (!isHealthResponse(payload)) {
      return {
        state: "OFFLINE",
        data: null,
        errorMessage: "Received an unexpected schema from VECTOR Local Agent.",
      };
    }

    return {
      state: "ONLINE",
      data: payload,
      errorMessage: null,
    };
  } catch (error: unknown) {
    if (externalSignal?.aborted) {
      throw error;
    }

    return {
      state: "OFFLINE",
      data: null,
      errorMessage: OFFLINE_MESSAGE,
    };
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}
