import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { checkHealth, HEALTH_ENDPOINT, OFFLINE_MESSAGE } from "../health";
import type { HealthResponse } from "../types";

describe("checkHealth API client", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("calls the relative endpoint /api/v1/health with Accept header", async () => {
    const mockData: HealthResponse = {
      status: "OK",
      timestamp: "2026-09-30T10:00:00Z",
      version: "0.1.0",
      mode: "LIVE",
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockData,
    });
    globalThis.fetch = mockFetch;

    const result = await checkHealth();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      HEALTH_ENDPOINT,
      expect.objectContaining({
        method: "GET",
        headers: { Accept: "application/json" },
      })
    );
    expect(result).toEqual({
      state: "ONLINE",
      data: mockData,
      errorMessage: null,
    });
  });

  it("returns OFFLINE when fetch fails with network error / connection refused", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    const result = await checkHealth();

    expect(result.state).toBe("OFFLINE");
    expect(result.data).toBeNull();
    expect(result.errorMessage).toBe(OFFLINE_MESSAGE);
  });

  it("returns OFFLINE when server responds with HTTP non-success (e.g. 503)", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
    });

    const result = await checkHealth();

    expect(result.state).toBe("OFFLINE");
    expect(result.data).toBeNull();
    expect(result.errorMessage).toContain("503");
  });

  it("returns OFFLINE when response is malformed JSON", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON at position 0");
      },
    });

    const result = await checkHealth();

    expect(result.state).toBe("OFFLINE");
    expect(result.data).toBeNull();
    expect(result.errorMessage).toBe("Received an invalid response format from VECTOR Local Agent.");
  });

  it("returns OFFLINE when response JSON has invalid schema", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ wrong: "data" }),
    });

    const result = await checkHealth();

    expect(result.state).toBe("OFFLINE");
    expect(result.data).toBeNull();
    expect(result.errorMessage).toBe("Received an unexpected schema from VECTOR Local Agent.");
  });

  it("re-throws AbortError if the caller's signal is aborted", async () => {
    const controller = new AbortController();
    globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
      return new Promise((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });

    const promise = checkHealth({ signal: controller.signal });
    controller.abort();

    await expect(promise).rejects.toThrow("The operation was aborted.");
  });

  it("returns OFFLINE if request times out", async () => {
    vi.useFakeTimers();

    globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
      return new Promise((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });

    const checkPromise = checkHealth({ timeoutMs: 100 });
    vi.advanceTimersByTime(150);

    const result = await checkPromise;
    expect(result.state).toBe("OFFLINE");
    expect(result.errorMessage).toBe(OFFLINE_MESSAGE);

    vi.useRealTimers();
  });
});
