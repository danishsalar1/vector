import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HealthStatus } from "../components/HealthStatus";
import {
  DemoDiagnosticProvider,
  LiveDiagnosticProvider,
  DiagnosticProviderComponent,
} from "../providers";
import type { HealthResponse } from "../lib/api/types";
import type { DiagnosticProvider } from "../providers";

describe("HealthStatus Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("Phase 1A Baseline Behaviors (LIVE Mode)", () => {
    it("1. initial state shows CHECKING", () => {
      globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

      render(<HealthStatus />);

      const badge = screen.getByTestId("status-badge");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("CHECKING");
      expect(screen.getByRole("button", { name: /retry/i })).toBeDisabled();
    });

    it("2. valid health response results in ONLINE", async () => {
      const mockHealth: HealthResponse = {
        status: "OK",
        timestamp: "2026-09-30T12:00:00Z",
        version: "0.1.0",
        mode: "LIVE",
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockHealth,
      });

      render(<HealthStatus />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("ONLINE");
      });

      expect(screen.getByTestId("online-details")).toBeInTheDocument();
      expect(screen.getByText("0.1.0")).toBeInTheDocument();
      expect(screen.getByText("LIVE")).toBeInTheDocument();
    });

    it("3. connection failure results in OFFLINE with clear message", async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

      render(<HealthStatus />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });

      const offlineMsg = screen.getByTestId("offline-message");
      expect(offlineMsg).toBeInTheDocument();
      expect(offlineMsg).toHaveTextContent(
        "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again."
      );
    });

    it("4. HTTP non-success results in OFFLINE", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
      });

      render(<HealthStatus />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });

      expect(screen.getByTestId("offline-message")).toHaveTextContent(
        "VECTOR Local Agent returned HTTP 500."
      );
    });

    it("5. malformed health response does not crash the application", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ unexpected: 123 }),
      });

      render(<HealthStatus />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });

      expect(screen.getByTestId("offline-message")).toHaveTextContent(
        "Received an unexpected schema from VECTOR Local Agent."
      );
    });

    it("6. Retry performs another request in LIVE mode", async () => {
      const user = userEvent.setup();

      globalThis.fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network error"));

      render(<HealthStatus />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });

      const retryBtn = screen.getByRole("button", { name: /retry/i });
      expect(retryBtn).not.toBeDisabled();

      const mockHealth: HealthResponse = {
        status: "OK",
        timestamp: "2026-09-30T12:05:00Z",
        version: "0.1.0",
        mode: "LIVE",
      };

      globalThis.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockHealth,
      });

      await user.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("ONLINE");
      });
    });

    it("7. component unmount/request cancellation does not generate avoidable state-update errors", async () => {
      const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      let resolveFetch: (value: unknown) => void;
      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        return new Promise((resolve, reject) => {
          resolveFetch = resolve;
          options?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        });
      });

      const { unmount } = render(<HealthStatus />);
      expect(screen.getByTestId("status-badge")).toHaveTextContent("CHECKING");

      unmount();

      resolveFetch!({
        ok: true,
        status: 200,
        json: async () => ({
          status: "OK",
          timestamp: "2026-09-30T12:00:00Z",
          version: "0.1.0",
          mode: "LIVE",
        }),
      });

      await new Promise((r) => setTimeout(r, 50));

      expect(consoleErrorSpy).not.toHaveBeenCalled();
      consoleErrorSpy.mockRestore();
    });
  });

  describe("Phase 1B Provider Abstraction Behaviors", () => {
    it("8. visibly identifies LIVE mode and displays 'Local Diagnostic Service'", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: "OK",
          timestamp: "2026-09-30T12:00:00Z",
          version: "0.1.0",
          mode: "LIVE",
        }),
      });

      render(<HealthStatus provider={new LiveDiagnosticProvider()} />);

      expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: LIVE");
      expect(screen.getByText("Local Diagnostic Service")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("ONLINE");
      });
    });

    it("9. visibly identifies DEMO mode and displays 'Demo Diagnostic Environment'", async () => {
      render(<HealthStatus provider={new DemoDiagnosticProvider()} />);

      expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: DEMO");
      expect(screen.getByText("Demo Diagnostic Environment")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
      });
    });

    it("10. DEMO mode cannot be confused with 'Local Agent Online'", async () => {
      render(<HealthStatus provider={new DemoDiagnosticProvider()} />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
      });

      // Must never claim agent is online or live
      expect(screen.queryByText("ONLINE")).not.toBeInTheDocument();
      expect(screen.queryByText(/local agent online/i)).not.toBeInTheDocument();

      // Must clearly display demo dataset indication and notice
      expect(screen.getByTestId("demo-details")).toBeInTheDocument();
      expect(screen.getByText("DEMO DATASET")).toBeInTheDocument();
      expect(screen.getByTestId("demo-note")).toHaveTextContent(
        "Demo environment ready. Real USB hardware diagnostics require Local Hardware Mode."
      );
    });

    it("11. supports dependency injection via DiagnosticProviderComponent context", async () => {
      const customProvider: DiagnosticProvider = {
        mode: "demo",
        checkHealth: vi.fn().mockResolvedValue({
          state: "DEMO_READY",
          data: {
            status: "DEMO",
            timestamp: "2026-09-30T00:00:00Z",
            version: "0.2.0-test",
            mode: "DEMO",
          },
          errorMessage: null,
        }),
        getPreflight: vi.fn(),
        discoverAndroidDevices: vi.fn(),
        getAndroidBatteryTelemetry: vi.fn(),
      };

      render(
        <DiagnosticProviderComponent provider={customProvider}>
          <HealthStatus />
        </DiagnosticProviderComponent>
      );

      expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: DEMO");

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
      });
      expect(screen.getByText("0.2.0-test")).toBeInTheDocument();
      expect(customProvider.checkHealth).toHaveBeenCalled();
    });

    it("12. Refresh Demo button re-triggers demo health check without calling fetch", async () => {
      const user = userEvent.setup();
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch;

      const demoProvider = new DemoDiagnosticProvider();
      const checkSpy = vi.spyOn(demoProvider, "checkHealth");

      render(<HealthStatus provider={demoProvider} />);

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
      });

      const refreshBtn = screen.getByRole("button", { name: /refresh demo/i });
      await user.click(refreshBtn);

      expect(checkSpy).toHaveBeenCalledTimes(2);
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });
});
