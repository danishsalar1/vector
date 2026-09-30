import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { PreflightStatus } from "../components/PreflightStatus";
import { LiveDiagnosticProvider } from "../providers/LiveDiagnosticProvider";
import { DemoDiagnosticProvider } from "../providers/DemoDiagnosticProvider";
import { DiagnosticProviderComponent } from "../providers";
import type { PreflightResponse } from "../lib/api/types";

const mockSamplePreflight: PreflightResponse = {
  overall: "PARTIAL",
  overall_status: "PARTIAL",
  checks: [
    {
      id: "platform_os",
      name: "Operating System",
      category: "platform",
      status: "PASS",
      message: "Windows 11 detected. Supported platform.",
      required: false,
      details: "Windows 11 (Build 22631)",
    },
    {
      id: "python_runtime",
      name: "Python Runtime",
      category: "runtime",
      status: "PASS",
      message: "Python 3.12.0 operational.",
      required: true,
      details: "3.12.0",
    },
    {
      id: "vector_agent",
      name: "VECTOR Local Agent",
      category: "agent",
      status: "PASS",
      message: "VECTOR local hardware agent service is running.",
      required: true,
      details: "Version 0.1.0",
    },
    {
      id: "android_adb",
      name: "Android Platform Tools",
      category: "android",
      status: "NOT_INSTALLED",
      message:
        "Android Platform Tools are not installed or are not available on PATH. They will be required before Android device discovery.",
      required: false,
      details: "adb not found in PATH",
    },
    {
      id: "ios_tools",
      name: "iOS Device Tooling",
      category: "ios",
      status: "NOT_INSTALLED",
      message:
        "iOS device tooling is not available yet. It will be required before iPhone discovery.",
      required: false,
      details: "ideviceinfo not found in PATH",
    },
  ],
  timestamp: "2026-09-30T12:00:00Z",
};

describe("PreflightStatus Component (Phase 1C)", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("1 & 3. initially shows checking state in LIVE mode and executes preflight fetch", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    expect(screen.getByTestId("preflight-mode-badge")).toHaveTextContent("Mode: LIVE");
    expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("CHECKING");
    expect(screen.getByTestId("preflight-checking")).toBeInTheDocument();
  });

  it("4 & 5. successful check renders overall status and individual check items", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSamplePreflight,
    });

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("PARTIAL");
    });

    expect(screen.getByText("Operating System")).toBeInTheDocument();
    expect(screen.getByText("Python Runtime")).toBeInTheDocument();
    expect(screen.getByText("VECTOR Local Agent")).toBeInTheDocument();
    expect(screen.getByText("Android Platform Tools")).toBeInTheDocument();
    expect(screen.getByText("iOS Device Tooling")).toBeInTheDocument();

    expect(screen.getByTestId("check-status-platform_os")).toHaveTextContent("PASS");
    expect(screen.getByTestId("check-status-python_runtime")).toHaveTextContent("PASS");
    expect(screen.getByTestId("check-status-vector_agent")).toHaveTextContent("PASS");
  });

  it("6. missing Android tooling is visibly flagged as NOT INSTALLED with guidance", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSamplePreflight,
    });

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("check-status-android_adb")).toHaveTextContent("NOT INSTALLED");
    });

    expect(
      screen.getByText(/Android Platform Tools are not installed or are not available on PATH/)
    ).toBeInTheDocument();
  });

  it("7. missing iOS tooling is visibly flagged as NOT INSTALLED with guidance", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSamplePreflight,
    });

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("check-status-ios_tools")).toHaveTextContent("NOT INSTALLED");
    });

    expect(
      screen.getByText(/iOS device tooling is not available yet/)
    ).toBeInTheDocument();
  });

  it("2, 10 & 11. Demo mode returns deterministic demo preflight, labeled DEMO and explicit notice", async () => {
    const mockFetch = vi.fn();
    globalThis.fetch = mockFetch;

    render(
      <DiagnosticProviderComponent provider={new DemoDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.getByTestId("preflight-mode-badge")).toHaveTextContent("Mode: DEMO");

    await waitFor(() => {
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("PARTIAL");
    });

    expect(screen.getByTestId("demo-preflight-banner")).toHaveTextContent(
      "Demo Environment: Simulated tooling checks only. Real device verification requires Local Hardware Mode."
    );
    expect(screen.getByTestId("check-status-android_adb")).toHaveTextContent("NOT INSTALLED");
    expect(screen.getByTestId("check-status-ios_tools")).toHaveTextContent("NOT INSTALLED");
  });

  it("8. recheck allows re-running the system preflight check", async () => {
    let callCount = 0;
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      callCount++;
      return {
        ok: true,
        status: 200,
        json: async () => mockSamplePreflight,
      };
    });

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("PARTIAL");
    });
    expect(callCount).toBe(1);

    const recheckButton = screen.getByRole("button", { name: "Check Again" });
    fireEvent.click(recheckButton);

    await waitFor(() => {
      expect(callCount).toBe(2);
    });
  });

  it("9. API failure displays a user-friendly error message", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Connection refused"));

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("UNAVAILABLE");
    });

    expect(screen.getByTestId("preflight-error")).toBeInTheDocument();
    expect(
      screen.getByText(/VECTOR could not complete the system check/)
    ).toBeInTheDocument();
  });

  it("12. preflight status uses clear readable text for all statuses without relying solely on color", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSamplePreflight,
    });

    render(
      <DiagnosticProviderComponent provider={new LiveDiagnosticProvider()}>
        <PreflightStatus />
      </DiagnosticProviderComponent>
    );

    await waitFor(() => {
      expect(screen.getByTestId("overall-status-badge")).toHaveTextContent("PARTIAL");
    });

    // Check that text content itself conveys status
    const passBadges = screen.getAllByText("PASS");
    expect(passBadges.length).toBeGreaterThanOrEqual(3);

    const notInstalledBadges = screen.getAllByText("NOT INSTALLED");
    expect(notInstalledBadges.length).toBeGreaterThanOrEqual(2);
  });
});
