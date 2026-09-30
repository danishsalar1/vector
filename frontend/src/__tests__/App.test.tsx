import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { DemoDiagnosticProvider } from "../providers/DemoDiagnosticProvider";

describe("App", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders VECTOR header and service subtitle in default LIVE mode", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "VECTOR" })
    ).toBeInTheDocument();
    expect(screen.getByText("Local Diagnostic Service")).toBeInTheDocument();
    expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: LIVE");
  });

  it("renders with injected DemoDiagnosticProvider cleanly", async () => {
    render(<App provider={new DemoDiagnosticProvider()} />);

    expect(
      screen.getByRole("heading", { level: 1, name: "VECTOR" })
    ).toBeInTheDocument();
    expect(screen.getByText("Demo Diagnostic Environment")).toBeInTheDocument();
    expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: DEMO");

    await waitFor(() => {
      expect(screen.getByTestId("status-badge")).toHaveTextContent("DEMO READY");
    });
  });
});
