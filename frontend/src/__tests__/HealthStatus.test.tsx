import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HealthStatus } from "../components/HealthStatus";
import type { HealthResponse } from "../lib/api/types";

describe("HealthStatus Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("1. initial state shows CHECKING", () => {
    // Hang fetch so it stays in CHECKING during initial render
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

  it("6. Retry performs another request", async () => {
    const user = userEvent.setup();

    // First attempt fails
    globalThis.fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network error"));

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-badge")).toHaveTextContent("OFFLINE");
    });

    const retryBtn = screen.getByRole("button", { name: /retry/i });
    expect(retryBtn).not.toBeDisabled();

    // Second attempt succeeds
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

    // Unmount while fetch is in flight
    unmount();

    // Resolve after unmount
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

    // Give microtasks time to run
    await new Promise((r) => setTimeout(r, 50));

    // Ensure no React unmounted state update errors were logged
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });
});
