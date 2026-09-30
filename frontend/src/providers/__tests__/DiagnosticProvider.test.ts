import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { LiveDiagnosticProvider } from "../LiveDiagnosticProvider";
import { DemoDiagnosticProvider } from "../DemoDiagnosticProvider";
import {
  createDiagnosticProvider,
  resolveProviderMode,
} from "../createDiagnosticProvider";
import { DEMO_HEALTH_FIXTURE } from "../demo/fixtures";
import type { HealthResponse } from "../../lib/api/types";

describe("DiagnosticProvider Abstraction (Phase 1B)", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("LiveDiagnosticProvider", () => {
    it("identifies as mode 'live'", () => {
      const provider = new LiveDiagnosticProvider();
      expect(provider.mode).toBe("live");
    });

    it("1. delegates to real health API and returns successful ONLINE state", async () => {
      const mockHealth: HealthResponse = {
        status: "OK",
        timestamp: "2026-09-30T12:00:00Z",
        version: "0.1.0",
        mode: "LIVE",
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockHealth,
      });
      globalThis.fetch = mockFetch;

      const provider = new LiveDiagnosticProvider();
      const result = await provider.checkHealth();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/v1/health",
        expect.objectContaining({ method: "GET" })
      );
      expect(result).toEqual({
        state: "ONLINE",
        data: mockHealth,
        errorMessage: null,
      });
    });

    it("2. propagates connection failures as OFFLINE", async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Connection refused"));

      const provider = new LiveDiagnosticProvider();
      const result = await provider.checkHealth();

      expect(result.state).toBe("OFFLINE");
      expect(result.data).toBeNull();
      expect(result.errorMessage).toBe(
        "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again."
      );
    });

    it("3. propagates HTTP non-success as OFFLINE", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
      });

      const provider = new LiveDiagnosticProvider();
      const result = await provider.checkHealth();

      expect(result.state).toBe("OFFLINE");
      expect(result.data).toBeNull();
      expect(result.errorMessage).toContain("503");
    });
  });

  describe("DemoDiagnosticProvider", () => {
    it("identifies as mode 'demo'", () => {
      const provider = new DemoDiagnosticProvider();
      expect(provider.mode).toBe("demo");
    });

    it("4. does NOT call fetch or any network API", async () => {
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch;

      const provider = new DemoDiagnosticProvider();
      await provider.checkHealth();

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("5. returns deterministic demo readiness state with demo fixture", async () => {
      const provider = new DemoDiagnosticProvider();
      const result = await provider.checkHealth();

      expect(result.state).toBe("DEMO_READY");
      expect(result.data).toEqual(DEMO_HEALTH_FIXTURE);
      expect(result.data?.mode).toBe("DEMO");
      expect(result.data?.status).toBe("DEMO");
      expect(result.errorMessage).toBeNull();
    });

    it("respects abort signal when already aborted", async () => {
      const controller = new AbortController();
      controller.abort();

      const provider = new DemoDiagnosticProvider();
      await expect(
        provider.checkHealth({ signal: controller.signal })
      ).rejects.toThrow("The operation was aborted.");
    });
  });

  describe("Provider Selection & Mode Resolution", () => {
    it("6. resolves 'live' mode explicitly", () => {
      expect(resolveProviderMode("live")).toBe("live");
      expect(resolveProviderMode("LIVE")).toBe("live");
      expect(resolveProviderMode("  Live  ")).toBe("live");
    });

    it("7. resolves 'demo' mode explicitly", () => {
      expect(resolveProviderMode("demo")).toBe("demo");
      expect(resolveProviderMode("DEMO")).toBe("demo");
      expect(resolveProviderMode(" Demo ")).toBe("demo");
    });

    it("defaults to 'live' when unconfigured or empty", () => {
      expect(resolveProviderMode(undefined)).toBe("live");
      expect(resolveProviderMode("")).toBe("live");
      expect(resolveProviderMode("   ")).toBe("live");
    });

    it("8. fails fast on invalid mode configuration with descriptive error", () => {
      expect(() => resolveProviderMode("banana")).toThrow(
        'Invalid VECTOR provider mode: "banana". Expected "live" or "demo".'
      );
      expect(() => resolveProviderMode("staging")).toThrow(
        'Invalid VECTOR provider mode: "staging". Expected "live" or "demo".'
      );
    });

    it("creates LiveDiagnosticProvider when configured for live", () => {
      const provider = createDiagnosticProvider({ mode: "live" });
      expect(provider).toBeInstanceOf(LiveDiagnosticProvider);
      expect(provider.mode).toBe("live");
    });

    it("creates DemoDiagnosticProvider when configured for demo", () => {
      const provider = createDiagnosticProvider({ mode: "demo" });
      expect(provider).toBeInstanceOf(DemoDiagnosticProvider);
      expect(provider.mode).toBe("demo");
    });

    it("defaults to LiveDiagnosticProvider when mode config is omitted", () => {
      const provider = createDiagnosticProvider({});
      expect(provider).toBeInstanceOf(LiveDiagnosticProvider);
      expect(provider.mode).toBe("live");
    });
  });
});
