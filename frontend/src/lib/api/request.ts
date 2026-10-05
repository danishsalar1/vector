import type { ApiError } from "./types";

export interface SafeFetchOptions {
  method?: string;
  body?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  fallbackErrorMessage?: string;
  timeoutErrorMessage?: string;
}

export interface FetchSuccess<T> {
  ok: true;
  data: T;
}

export interface FetchFailure {
  ok: false;
  error: ApiError;
}

export type SafeFetchResult<T> = FetchSuccess<T> | FetchFailure;

/**
 * Executes an HTTP fetch request with bounded timeout, external cancellation propagation,
 * response validation, and structured error categorization.
 */
export async function safeFetchJson<T>(
  url: string,
  validator: (data: unknown) => data is T,
  options: SafeFetchOptions = {}
): Promise<SafeFetchResult<T>> {
  const {
    method = "GET",
    body,
    signal: externalSignal,
    timeoutMs = 5000,
    headers = {},
    fallbackErrorMessage = "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again.",
    timeoutErrorMessage = "Request timed out while contacting VECTOR Local Agent. Try again.",
  } = options;

  if (externalSignal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError");
  }

  const internalController = new AbortController();
  let timedOut = false;

  const timeoutId = setTimeout(() => {
    timedOut = true;
    internalController.abort();
  }, timeoutMs);

  const onExternalAbort = () => {
    internalController.abort();
  };

  if (externalSignal) {
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  try {
    const response = await fetch(url, {
      method,
      body,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      signal: internalController.signal,
    });

    if (!response.ok) {
      return {
        ok: false,
        error: {
          kind: "HTTP",
          statusCode: response.status,
          message: `VECTOR Local Agent returned HTTP ${response.status}.`,
        },
      };
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return {
        ok: false,
        error: {
          kind: "INVALID_RESPONSE",
          message: "Received an invalid response format from VECTOR Local Agent.",
        },
      };
    }

    if (!validator(payload)) {
      return {
        ok: false,
        error: {
          kind: "INVALID_RESPONSE",
          message: "Received an unexpected schema from VECTOR Local Agent.",
        },
      };
    }

    return {
      ok: true,
      data: payload,
    };
  } catch (err: unknown) {
    if (externalSignal?.aborted) {
      throw err;
    }

    if (timedOut) {
      return {
        ok: false,
        error: {
          kind: "TIMEOUT",
          message: timeoutErrorMessage,
        },
      };
    }

    return {
      ok: false,
      error: {
        kind: "NETWORK",
        message: fallbackErrorMessage,
      },
    };
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}
