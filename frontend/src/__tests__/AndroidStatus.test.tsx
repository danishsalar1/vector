/**
 * Tests for AndroidStatus component — Phase 2A.
 *
 * Requirements covered:
 * 1. Detect Android Device action
 * 2. no-device state
 * 3. unauthorized state
 * 4. authorized device presentation
 * 5. exact real-data response renders
 * 6. Run Battery Test enabled only for authorized device
 * 7. battery evidence displayed
 * 8. evidence source displayed
 * 9. PASS explanation does NOT say battery is healthy
 * 10. API failure state
 * 11. disconnect state (ERROR after authorized discovery)
 * 12. no Demo fallback
 * 13. mode remains LIVE
 * 14. loading states
 * 15. retry detection
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AndroidStatus } from "../components/AndroidStatus";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";
import type {
  AndroidDiscoveryResult,
  BatteryTelemetryResult,
  HealthCheckResult,
  PreflightResult,
} from "../lib/api/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeProvider(
  discoveryResult: AndroidDiscoveryResult,
  batteryResult: BatteryTelemetryResult
): DiagnosticProvider {
  return {
    mode: "live",
    checkHealth: vi.fn<() => Promise<HealthCheckResult>>(),
    getPreflight: vi.fn<() => Promise<PreflightResult>>(),
    discoverAndroidDevices: vi.fn().mockResolvedValue(discoveryResult),
    getAndroidBatteryTelemetry: vi.fn().mockResolvedValue(batteryResult),
  };
}

const NO_DEVICE_RESULT: AndroidDiscoveryResult = {
  state: "COMPLETE",
  data: {
    devices: [],
    count: 0,
    state: "NO_DEVICE",
    message: "No Android devices detected.",
    adb_available: true,
  },
  errorMessage: null,
};

const UNAUTHORIZED_RESULT: AndroidDiscoveryResult = {
  state: "COMPLETE",
  data: {
    devices: [
      {
        device_id: "android-aabbcc001122",
        connection_state: "UNAUTHORIZED",
        adb_available: true,
        message: "Device not authorized.",
        manufacturer: null,
        model: null,
        device_codename: null,
        android_version: null,
        sdk_level: null,
        brand: null,
        discovered_at: "2026-09-30T00:00:00Z",
      },
    ],
    count: 1,
    state: "UNAUTHORIZED",
    message: "Android device detected but not authorized.",
    adb_available: true,
  },
  errorMessage: null,
};

const AUTHORIZED_RESULT: AndroidDiscoveryResult = {
  state: "COMPLETE",
  data: {
    devices: [
      {
        device_id: "android-aabbcc001122",
        connection_state: "DEVICE",
        adb_available: true,
        message: "Android device connected and authorized.",
        manufacturer: "Xiaomi",
        model: "23117RA66G",
        device_codename: "spes",
        android_version: "15",
        sdk_level: 35,
        brand: "Xiaomi",
        discovered_at: "2026-09-30T00:00:00Z",
      },
    ],
    count: 1,
    state: "DEVICE",
    message: "Android device connected and authorized.",
    adb_available: true,
  },
  errorMessage: null,
};

const ERROR_DISCOVERY_RESULT: AndroidDiscoveryResult = {
  state: "ERROR",
  data: null,
  errorMessage: "Cannot reach VECTOR Local Agent.",
};

const BATTERY_PASS_RESULT: BatteryTelemetryResult = {
  state: "COMPLETE",
  data: {
    device_id: "android-aabbcc001122",
    status: "PASS",
    status_note:
      "PASS confirms successful battery telemetry collection. It does not represent full battery-health assessment.",
    confidence: 0.95,
    level_pct: 83,
    charging_state: "Charging",
    health_state: "Good",
    plugged: "USB",
    voltage_v: 4.127,
    temperature_c: 31.4,
    technology: "Li-ion",
    present: true,
    evidence_source: "ADB / dumpsys battery",
    collection_method: "adb shell dumpsys battery",
    collected_at: "2026-09-30T10:00:00Z",
    error: null,
  },
  errorMessage: null,
};

const BATTERY_ERROR_RESULT: BatteryTelemetryResult = {
  state: "ERROR",
  data: null,
  errorMessage: "Device disconnected during test.",
};

const DUMMY_BATTERY: BatteryTelemetryResult = {
  state: "IDLE",
  data: null,
  errorMessage: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AndroidStatus", () => {
  it("shows detect button on initial idle state", () => {
    const provider = makeProvider(NO_DEVICE_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    expect(
      screen.getByTestId("detect-android-btn")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("detect-android-btn")
    ).not.toBeDisabled();
  });

  it("calls discoverAndroidDevices when detect button clicked (test 1)", async () => {
    const provider = makeProvider(NO_DEVICE_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(provider.discoverAndroidDevices).toHaveBeenCalledTimes(1);
    });
  });

  it("shows no-device state (test 2)", async () => {
    const provider = makeProvider(NO_DEVICE_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("android-no-device")).toBeInTheDocument();
    });
  });

  it("shows unauthorized state with guidance (test 3)", async () => {
    const provider = makeProvider(UNAUTHORIZED_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("android-unauthorized")).toBeInTheDocument();
      expect(
        screen.getByTestId("android-unauthorized").textContent
      ).toMatch(/not authorized|unauthorized/i);
    });
  });

  it("shows authorized device identity (test 4)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("android-device-details")).toBeInTheDocument();
    });
    expect(screen.getByTestId("android-manufacturer").textContent).toBe(
      "Xiaomi"
    );
    expect(screen.getByTestId("android-model").textContent).toBe("23117RA66G");
    expect(screen.getByTestId("android-version").textContent).toBe("15");
    expect(screen.getByTestId("android-adb-status").textContent).toBe(
      "AUTHORIZED"
    );
  });

  it("renders exact real-data model and version values (test 5)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("android-model").textContent).toBe(
        "23117RA66G"
      );
    });
  });

  it("Run Battery Test button disabled before authorized device (test 6)", () => {
    const provider = makeProvider(NO_DEVICE_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    // battery test button should not even be in the DOM for no-device state
    expect(
      screen.queryByTestId("run-battery-test-btn")
    ).not.toBeInTheDocument();
  });

  it("Run Battery Test button enabled only after authorized device detected (test 6)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(
        screen.getByTestId("run-battery-test-btn")
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("run-battery-test-btn")
      ).not.toBeDisabled();
    });
  });

  it("shows battery telemetry values after running test (test 7)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, BATTERY_PASS_RESULT);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("run-battery-test-btn")).toBeInTheDocument()
    );
    fireEvent.click(screen.getByTestId("run-battery-test-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("battery-results")).toBeInTheDocument();
    });
    expect(screen.getByTestId("battery-level").textContent).toBe("83%");
    expect(screen.getByTestId("battery-temperature").textContent).toMatch(
      /31\.4/
    );
    expect(screen.getByTestId("battery-voltage").textContent).toMatch(/4\.13|4\.12/);
  });

  it("shows evidence source in battery results (test 8)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, BATTERY_PASS_RESULT);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() =>
      screen.getByTestId("run-battery-test-btn")
    );
    fireEvent.click(screen.getByTestId("run-battery-test-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("battery-evidence-source")).toBeInTheDocument()
    );
    expect(screen.getByTestId("battery-evidence-source").textContent).toBe(
      "ADB / dumpsys battery"
    );
  });

  it("PASS status note does not claim battery is healthy (test 9)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, BATTERY_PASS_RESULT);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => screen.getByTestId("run-battery-test-btn"));
    fireEvent.click(screen.getByTestId("run-battery-test-btn"));
    await waitFor(() => screen.getByTestId("battery-pass-note"));
    const noteText = screen.getByTestId("battery-pass-note").textContent ?? "";
    // Must disclaim health assessment
    expect(noteText.toLowerCase()).toMatch(/not represent|does not|no.*health/);
  });

  it("shows API failure state when discovery errors (test 10)", async () => {
    const provider = makeProvider(ERROR_DISCOVERY_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("android-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("android-error").textContent).toMatch(
      /Cannot reach|unavailable/i
    );
  });

  it("shows battery error when device disconnects during test (test 11)", async () => {
    const provider = makeProvider(AUTHORIZED_RESULT, BATTERY_ERROR_RESULT);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => screen.getByTestId("run-battery-test-btn"));
    fireEvent.click(screen.getByTestId("run-battery-test-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("battery-error")).toBeInTheDocument();
    });
  });

  it("demo mode does not call real discovery (test 12, 13)", async () => {
    const demoProvider: DiagnosticProvider = {
      mode: "demo",
      checkHealth: vi.fn(),
      getPreflight: vi.fn(),
      discoverAndroidDevices: vi.fn().mockResolvedValue({
        state: "COMPLETE",
        data: {
          devices: [],
          count: 0,
          state: "NO_DEVICE",
          message: "[DEMO] Not available.",
          adb_available: false,
        },
        errorMessage: null,
      }),
      getAndroidBatteryTelemetry: vi.fn().mockResolvedValue({
        state: "ERROR",
        data: null,
        errorMessage: "[DEMO] Not available.",
      }),
    };
    render(<AndroidStatus provider={demoProvider} />);
    // In demo mode, detect button is NOT rendered
    expect(
      screen.queryByTestId("detect-android-btn")
    ).not.toBeInTheDocument();
    // Demo banner shown
    expect(screen.getByTestId("android-demo-banner")).toBeInTheDocument();
    // No live API calls
    expect(demoProvider.discoverAndroidDevices).not.toHaveBeenCalled();
  });

  it("shows loading state while detecting (test 14)", async () => {
    let resolveDiscovery!: (v: AndroidDiscoveryResult) => void;
    const pendingDiscovery = new Promise<AndroidDiscoveryResult>(
      (r) => (resolveDiscovery = r)
    );
    const provider: DiagnosticProvider = {
      mode: "live",
      checkHealth: vi.fn(),
      getPreflight: vi.fn(),
      discoverAndroidDevices: vi.fn().mockReturnValue(pendingDiscovery),
      getAndroidBatteryTelemetry: vi.fn(),
    };
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    // Should show checking indicator
    expect(screen.getByTestId("android-checking")).toBeInTheDocument();
    expect(
      screen.getByTestId("detect-android-btn")
    ).toBeDisabled();
    // Resolve
    resolveDiscovery(NO_DEVICE_RESULT);
    await waitFor(() => {
      expect(
        screen.queryByTestId("android-checking")
      ).not.toBeInTheDocument();
    });
  });

  it("retry detection button available after first check (test 15)", async () => {
    const provider = makeProvider(NO_DEVICE_RESULT, DUMMY_BATTERY);
    render(<AndroidStatus provider={provider} />);
    fireEvent.click(screen.getByTestId("detect-android-btn"));
    await waitFor(() => screen.getByTestId("android-no-device"));
    // After detection completes, button says Retry Detection
    expect(screen.getByTestId("detect-android-btn").textContent).toMatch(
      /retry/i
    );
  });
});
