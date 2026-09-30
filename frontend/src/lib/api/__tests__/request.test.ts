import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { safeFetchJson } from "../request";

interface TestPayload {
  key: string;
}

function isTestPayload(val: unknown): val is TestPayload {
  return (
    typeof val === "object" &&
    val !== null &&
    typeof (val as Record<string, unknown>).key === "string"
  );
}

describe("safeFetchJson Request Layer (Phase 1D)", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("1. successfully parses and validates response on HTTP 200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ key: "value" }),
    });

    const result = await safeFetchJson("/test", isTestPayload);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual({ key: "value" });
    }
  });

  it("2. returns categorized TIMEOUT error when timeout expires", async () => {
    globalThis.fetch = vi.fn().mockImplementation(
      (_url, options: { signal: AbortSignal }) =>
        new Promise((_, reject) => {
          options.signal.addEventListener("abort", () => {
            const err = new DOMException("The operation was aborted.", "AbortError");
            reject(err);
          });
        })
    );

    const result = await safeFetchJson("/test", isTestPayload, {
      timeoutMs: 20,
      timeoutErrorMessage: "Custom timeout",
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("TIMEOUT");
      expect(result.error.message).toBe("Custom timeout");
    }
  });

  it("3. returns categorized NETWORK error on fetch rejection", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    const result = await safeFetchJson("/test", isTestPayload, {
      fallbackErrorMessage: "Custom network error",
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("NETWORK");
      expect(result.error.message).toBe("Custom network error");
    }
  });

  it("4. returns categorized HTTP error on non-2xx response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
    });

    const result = await safeFetchJson("/test", isTestPayload);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("HTTP");
      expect(result.error.statusCode).toBe(503);
      expect(result.error.message).toContain("503");
    }
  });

  it("5. returns categorized INVALID_RESPONSE error on malformed JSON", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON");
      },
    });

    const result = await safeFetchJson("/test", isTestPayload);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("INVALID_RESPONSE");
      expect(result.error.message).toContain("invalid response format");
    }
  });

  it("6. returns categorized INVALID_RESPONSE error on schema validator failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ wrong: 123 }),
    });

    const result = await safeFetchJson("/test", isTestPayload);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.kind).toBe("INVALID_RESPONSE");
      expect(result.error.message).toContain("unexpected schema");
    }
  });

  it("7. propagates external abort as DOMException", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      safeFetchJson("/test", isTestPayload, { signal: controller.signal })
    ).rejects.toThrow("The operation was aborted.");
  });
});
