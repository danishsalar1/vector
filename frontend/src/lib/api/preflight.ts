import {
  type PreflightResponse,
  type PreflightResult,
  isPreflightResponse,
} from "./types";

export interface FetchPreflightOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const PREFLIGHT_ENDPOINT = "/api/v1/system/preflight";
export const DEFAULT_PREFLIGHT_TIMEOUT_MS = 5000;

export const PREFLIGHT_ERROR_MESSAGE =
  "VECTOR could not complete the system check. Ensure the VECTOR local service is running and try again.";

/**
 * Performs a system preflight environment inspection via GET /api/v1/system/preflight.
 * Uses a relative URL routed by the Vite dev proxy to localhost:8742 in development.
 */
export async function fetchPreflight(
  options: FetchPreflightOptions = {}
): Promise<PreflightResult> {
  const { signal: externalSignal, timeoutMs = DEFAULT_PREFLIGHT_TIMEOUT_MS } = options;

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
    const response = await fetch(PREFLIGHT_ENDPOINT, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      signal: internalController.signal,
    });

    if (!response.ok) {
      return {
        state: "ERROR",
        data: null,
        errorMessage: `VECTOR Local Agent returned HTTP ${response.status} during system preflight.`,
      };
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return {
        state: "ERROR",
        data: null,
        errorMessage: "Received an invalid JSON response format during system check.",
      };
    }

    if (!isPreflightResponse(payload)) {
      return {
        state: "ERROR",
        data: null,
        errorMessage: "Received an unexpected schema from VECTOR system preflight endpoint.",
      };
    }

    return {
      state: "COMPLETE",
      data: payload as PreflightResponse,
      errorMessage: null,
    };
  } catch (error: unknown) {
    if (externalSignal?.aborted) {
      throw error;
    }

    return {
      state: "ERROR",
      data: null,
      errorMessage: PREFLIGHT_ERROR_MESSAGE,
    };
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}
