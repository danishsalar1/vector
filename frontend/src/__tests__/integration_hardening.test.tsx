import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, renderHook, act } from "@testing-library/react";
import { useHealthCheck } from "../lib/api/useHealthCheck";
import { usePreflight } from "../lib/api/usePreflight";
import { HealthStatus } from "../components/HealthStatus";
import { PreflightStatus } from "../components/PreflightStatus";
import { LiveDiagnosticProvider } from "../providers/LiveDiagnosticProvider";
import { DemoDiagnosticProvider } from "../providers/DemoDiagnosticProvider";
import { DiagnosticProviderComponent } from "../providers";
import type { HealthResponse, PreflightResponse } from "../lib/api/types";

const mockHealthSuccess: HealthResponse = {
  status: "OK",
  timestamp: "2026-09-30T12:00:00Z",
  version: "0.1.0",
  mode: "LIVE",
};

const mockPreflightSuccess: PreflightResponse = {
  overall: "READY",
  overall_status: "READY",
  checks: [
    {
      id: "platform_os",
      name: "Operating System",
      category: "platform",
      status: "PASS",
      message: "Windows 11 detected.",
      required: false,
      details: "Windows 11",
    },
  ],
  timestamp: "2026-09-30T12:00:00Z",
};

describe("Phase 1D Integration Hardening & Resilience", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("Race Condition Protection (Latest Request Wins)", () => {
    it("1. useHealthCheck: slower older request A cannot overwrite newer faster request B", async () => {
      let resolveA!: (val: unknown) => void;
      let resolveB!: (val: unknown) => void;

      let callCount = 0;
      globalThis.fetch = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          // Request A (slow)
          return new Promise((resolve) => {
            resolveA = resolve;
          });
        }
        // Request B (fast)
        return new Promise((resolve) => {
          resolveB = resolve;
        });
      });

      const { result } = renderHook(() =>
        useHealthCheck({ provider: new LiveDiagnosticProvider() })
      );

      expect(result.current.state).toBe("CHECKING");

      // Trigger Request B while Request A is pending
      act(() => {
        result.current.retry();
      });

      expect(callCount).toBe(2);

      // Settle Request B first with success
      await act(async () => {
        resolveB({
          ok: true,
          status: 200,
          json: async () => ({
            ...mockHealthSuccess,
            version: "0.2.0-from-B",
          }),
        });
      });

      expect(result.current.state).toBe("ONLINE");
      expect(result.current.data?.version).toBe("0.2.0-from-B");

      // Now settle older Request A with an outdated response
      await act(async () => {
        resolveA({
          ok: true,
          status: 200,
          json: async () => ({
            ...mockHealthSuccess,
            version: "0.1.0-from-A",
          }),
        });
      });

      // Assert Request A DID NOT overwrite Request B
      expect(result.current.state).toBe("ONLINE");
      expect(result.current.data?.version).toBe("0.2.0-from-B");
    });

    it("2. usePreflight: slower older request A cannot overwrite newer faster request B", async () => {
      let resolveA!: (val: unknown) => void;
      let resolveB!: (val: unknown) => void;

      let callCount = 0;
      globalThis.fetch = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return new Promise((resolve) => {
            resolveA = resolve;
          });
        }
        return new Promise((resolve) => {
          resolveB = resolve;
        });
      });

      const { result } = renderHook(() =>
        usePreflight({ provider: new LiveDiagnosticProvider() })
      );

      expect(result.current.state).toBe("CHECKING");

      // Trigger Request B while Request A is pending
      act(() => {
        result.current.runCheck();
      });

      expect(callCount).toBe(2);

      // Settle Request B first
      await act(async () => {
        resolveB({
          ok: true,
          status: 200,
          json: async () => ({
            ...mockPreflightSuccess,
            overall: "READY",
          }),
        });
      });

      expect(result.current.state).toBe("COMPLETE");
      expect(result.current.data?.overall).toBe("READY");

      // Settle Request A with older PARTIAL response
      await act(async () => {
        resolveA({
          ok: true,
          status: 200,
          json: async () => ({
            ...mockPreflightSuccess,
            overall: "PARTIAL",
          }),
        });
      });

      // Older Request A must not overwrite Request B
      expect(result.current.state).toBe("COMPLETE");
      expect(result.current.data?.overall).toBe("READY");
    });
  });

  describe("Stale State Prevention on Retry / Recheck", () => {
    it("3. HealthStatus clears previous data immediately upon retry so old data is not displayed", async () => {
      let shouldFail = false;
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        if (shouldFail) {
          throw new TypeError("Failed to fetch");
        }
        return {
          ok: true,
          status: 200,
          json: async () => mockHealthSuccess,
        };
      });

      render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <HealthStatus />
        </DiagnosticProviderComponent>
      );

      // Initial check succeeds
      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("ONLINE");
      });
      expect(screen.getByTestId("online-details")).toBeInTheDocument();

      // Configure second call to fail
      shouldFail = true;
      const retryButton = screen.getByRole("button", { name: "Retry connection check" });
      fireEvent.click(retryButton);

      // Old details must be removed and offline message displayed
      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });
      expect(screen.queryByTestId("online-details")).not.toBeInTheDocument();
      expect(screen.getByTestId("offline-message")).toBeInTheDocument();
    });

    it("4. PreflightStatus clears previous checks immediately upon recheck so old checks are not displayed", async () => {
      let shouldFail = false;
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        if (shouldFail) {
          throw new TypeError("Failed to fetch");
        }
        return {
          ok: true,
          status: 200,
          json: async () => mockPreflightSuccess,
        };
      });

      render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <PreflightStatus />
        </DiagnosticProviderComponent>
      );

      // Initial check succeeds
      await waitFor(() => {
        expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("READY");
      });
      expect(screen.getByTestId("preflight-checks-list")).toBeInTheDocument();

      // Configure second call to fail
      shouldFail = true;
      const recheckButton = screen.getByRole("button", { name: "Check Again" });
      fireEvent.click(recheckButton);

      // Old check list must be cleared and error message displayed
      await waitFor(() => {
        expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("UNAVAILABLE");
      });
      expect(screen.queryByTestId("preflight-checks-list")).not.toBeInTheDocument();
      expect(screen.getByTestId("preflight-error")).toBeInTheDocument();
    });
  });

  describe("Cancellation on Unmount", () => {
    it("5. unmounting component while health request is in flight cleanly aborts without error", () => {
      let aborted = false;
      globalThis.fetch = vi.fn().mockImplementation(
        (_url, options: { signal: AbortSignal }) => {
          options.signal.addEventListener("abort", () => {
            aborted = true;
          });
          return new Promise(() => {});
        }
      );

      const { unmount } = render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <HealthStatus />
        </DiagnosticProviderComponent>
      );

      unmount();
      expect(aborted).toBe(true);
    });

    it("6. unmounting component while preflight request is in flight cleanly aborts without error", () => {
      let aborted = false;
      globalThis.fetch = vi.fn().mockImplementation(
        (_url, options: { signal: AbortSignal }) => {
          options.signal.addEventListener("abort", () => {
            aborted = true;
          });
          return new Promise(() => {});
        }
      );

      const { unmount } = render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <PreflightStatus />
        </DiagnosticProviderComponent>
      );

      unmount();
      expect(aborted).toBe(true);
    });
  });

  describe("Timeout and Categorized Error Display", () => {
    it("7. PreflightStatus displays timeout error message when request times out", async () => {
      globalThis.fetch = vi.fn().mockImplementation(
        (_url, options: { signal: AbortSignal }) =>
          new Promise((_, reject) => {
            options.signal.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          })
      );

      render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <PreflightStatus timeoutMs={20} />
        </DiagnosticProviderComponent>
      );

      await waitFor(() => {
        expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("UNAVAILABLE");
      });
      expect(
        screen.getByText(/System check timed out. Ensure the VECTOR local service is responding and try again./)
      ).toBeInTheDocument();
    });

    it("8. HealthStatus displays OFFLINE state when connection times out", async () => {
      globalThis.fetch = vi.fn().mockImplementation(
        (_url, options: { signal: AbortSignal }) =>
          new Promise((_, reject) => {
            options.signal.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          })
      );

      render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <HealthStatus timeoutMs={20} />
        </DiagnosticProviderComponent>
      );

      await waitFor(() => {
        expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      });
      expect(screen.getByTestId("offline-message")).toBeInTheDocument();
      expect(
        screen.getByText(/VECTOR Local Agent is offline/)
      ).toBeInTheDocument();
    });
  });

  describe("Mode Isolation (No Silent Fallback to Demo)", () => {
    it("9. Live mode failure NEVER silently falls back to Demo mode", async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Connection refused"));

      render(
        <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
          <div>
            <HealthStatus />
            <PreflightStatus />
          </div>
        </DiagnosticProviderComponent>
      );

      await waitFor(() => {
        expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: LIVE");
        expect(screen.getByTestId("preflight-mode-badge")).toHaveTextContent("Mode: LIVE");
      });

      expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("UNAVAILABLE");

      // Verify no demo indicators appeared
      expect(screen.queryByTestId("demo-details")).not.toBeInTheDocument();
      expect(screen.queryByTestId("demo-preflight-banner")).not.toBeInTheDocument();
      expect(screen.queryByText(/DEMO DATASET/)).not.toBeInTheDocument();
    });

    it("10. Demo mode NEVER makes any HTTP fetch call", async () => {
      const mockFetch = vi.fn();
      globalThis.fetch = mockFetch;

      render(
        <DiagnosticProviderComponent provider={new DemoDiagnosticProvider()}>
          <div>
            <HealthStatus />
            <PreflightStatus />
          </div>
        </DiagnosticProviderComponent>
      );

      await waitFor(() => {
        expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: DEMO");
        expect(screen.getByTestId("preflight-mode-badge")).toHaveTextContent("Mode: DEMO");
      });

      expect(mockFetch).not.toHaveBeenCalled();
      expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("PARTIAL");
    });
  });
});
