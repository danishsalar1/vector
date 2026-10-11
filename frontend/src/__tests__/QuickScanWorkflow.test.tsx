import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "../App";
import { DemoDiagnosticProvider } from "../providers/DemoDiagnosticProvider";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";
import type { ConnectedDevice } from "../lib/api/devices";
import type {
  DiagnosticEvent,
  ScanPlan,
  ScanSummary,
} from "../lib/api/types";
import type { SafeFetchResult } from "../lib/api/request";

// All identifiers below are fabricated test fixtures.

const REDMI: ConnectedDevice = {
  device_id: "android-testdev0001",
  platform: "ANDROID",
  connection_state: "CONNECTED",
  authorization_state: "AUTHORIZED",
  identity: {
    platform: "ANDROID",
    manufacturer: "Xiaomi",
    model: "Redmi Test Phone",
    marketing_name: null,
    android_version: "11",
    android_sdk_level: 30,
    build_fingerprint: null,
    brand: "Redmi",
    device_codename: "testcodename",
    ios_version: null,
    product_type: null,
    serial: null,
    udid: null,
    discovered_at: "2026-10-11T00:00:00Z",
  },
};

const PLAN: ScanPlan = {
  plan_id: "plan-1",
  device_id: REDMI.device_id,
  platform: "ANDROID",
  mode: "FULL_VERIFICATION",
  diagnostics_requested: ["battery_telemetry", "storage_telemetry", "other_thing"],
  diagnostics_planned: ["battery_telemetry", "storage_telemetry"],
  diagnostics_skipped: ["other_thing"],
  skip_reasons: { other_thing: "Platform ANDROID is not supported by 'other_thing'." },
  planned_items: [
    {
      diagnostic_id: "battery_telemetry",
      applicability: "APPLICABLE",
      verification_level: "RUNTIME_DETECTION",
      requires_probe: false,
    },
    {
      diagnostic_id: "storage_telemetry",
      applicability: "APPLICABLE",
      verification_level: "RUNTIME_DETECTION",
      requires_probe: false,
    },
    {
      diagnostic_id: "other_thing",
      applicability: "NOT_APPLICABLE",
      reason: "Platform ANDROID is not supported by 'other_thing'.",
      verification_level: "RUNTIME_DETECTION",
    },
  ],
  registry_diagnostic_ids: ["battery_telemetry", "storage_telemetry", "other_thing"],
  created_at: "2026-10-11T00:00:00Z",
};

const BATTERY_RESULT = {
  diagnostic_id: "battery_telemetry",
  diagnostic_name: "Battery Telemetry",
  category: "battery",
  status: "PASS",
  automation_level: "AUTOMATIC",
  summary: "PASS confirms successful battery telemetry collection. It does not represent full battery-health assessment.",
  duration_seconds: 0.5,
  evidence: [
    {
      evidence_id: "ev-1",
      diagnostic_id: "battery_telemetry",
      device_id: REDMI.device_id,
      source_type: "ADB_DUMPSYS",
      source_name: "ADB / dumpsys battery",
      collection_method: "adb shell dumpsys battery",
      timestamp: "2026-10-11T00:00:01Z",
      raw_value: "97",
      unit: "percent",
      reliability: null,
      metadata: { field: "battery_level" },
      redacted: false,
      error: null,
    },
  ],
};

const STORAGE_RESULT = {
  diagnostic_id: "storage_telemetry",
  diagnostic_name: "Storage Telemetry",
  category: "storage",
  status: "INCONCLUSIVE",
  automation_level: "AUTOMATIC",
  summary: "Storage telemetry was partially collected or unparseable.",
  duration_seconds: 0.2,
  evidence: [],
};

function summary(overrides: Partial<ScanSummary> = {}): ScanSummary {
  return {
    scan_id: "scan-1",
    device_id: REDMI.device_id,
    state: "COMPLETED",
    created_at: "2026-10-11T00:00:00Z",
    plan: PLAN,
    diagnostic_results: [BATTERY_RESULT, STORAGE_RESULT],
    trust_engine_status: "NOT_READY",
    trust_score: null,
    trust_confidence: null,
    error: null,
    ...overrides,
  };
}

function ev(
  id: string,
  event_type: DiagnosticEvent["event_type"],
  diagnostic_id?: string
): DiagnosticEvent {
  return {
    event_id: id,
    scan_id: "scan-1",
    device_id: REDMI.device_id,
    event_type,
    timestamp: "2026-10-11T00:00:00Z",
    diagnostic_id,
  };
}

const ALL_EVENTS: DiagnosticEvent[] = [
  ev("e1", "scan.started"),
  ev("e2", "diagnostic.started", "battery_telemetry"),
  ev("e3", "diagnostic.evidence", "battery_telemetry"),
  ev("e4", "diagnostic.completed", "battery_telemetry"),
  ev("e5", "diagnostic.started", "storage_telemetry"),
  ev("e6", "diagnostic.inconclusive", "storage_telemetry"),
  ev("e7", "scan.completed"),
];

function ok<T>(data: T): SafeFetchResult<T> {
  return { ok: true, data };
}

function httpError(statusCode: number): SafeFetchResult<never> {
  return { ok: false, error: { kind: "HTTP", statusCode, message: `HTTP ${statusCode}` } };
}

function makeProvider(overrides: Partial<DiagnosticProvider> = {}): DiagnosticProvider {
  return {
    mode: "live",
    checkHealth: vi.fn().mockResolvedValue({
      state: "ONLINE",
      data: { status: "OK", timestamp: "2026-10-11T00:00:00Z", version: "0.1.0", mode: "LIVE" },
      errorMessage: null,
    }),
    getPreflight: vi.fn().mockReturnValue(new Promise(() => {})),
    discoverAndroidDevices: vi.fn(),
    getAndroidBatteryTelemetry: vi.fn(),
    listDevices: vi
      .fn()
      .mockResolvedValue({ state: "COMPLETE", data: { devices: [REDMI], count: 1 }, errorMessage: null }),
    planScan: vi.fn().mockResolvedValue(ok(PLAN)),
    startScan: vi
      .fn()
      .mockResolvedValue(ok({ scan_id: "scan-1", state: "RUNNING", plan: PLAN })),
    getScanSummary: vi.fn().mockResolvedValue(ok(summary())),
    getScanEvents: vi.fn().mockResolvedValue(ok({ scan_id: "scan-1", events: ALL_EVENTS })),
    ...overrides,
  };
}

const FAST = { pollIntervalMs: 5, maxPollFailures: 2 };

function renderApp(provider: DiagnosticProvider) {
  return render(<App provider={provider} scanOptions={FAST} />);
}

async function startScan() {
  const button = await screen.findByTestId("start-scan");
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

describe("Quick Scan workflow (LIVE)", () => {
  it("shows the discovered device with identity, connection and authorization", async () => {
    renderApp(makeProvider());

    const facts = await screen.findByTestId("device-facts");
    expect(within(facts).getByText("Xiaomi")).toBeInTheDocument();
    expect(within(facts).getByText("Redmi Test Phone")).toBeInTheDocument();
    expect(within(facts).getByText("11")).toBeInTheDocument();
    expect(screen.getByTestId("device-connection")).toHaveTextContent("CONNECTED");
    expect(screen.getByTestId("device-authorization")).toHaveTextContent("Authorized");
    expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: LIVE");
  });

  it("shows the backend plan labelled RUNTIME_DETECTION, not run yet, and lists skipped diagnostics", async () => {
    const provider = makeProvider();
    renderApp(provider);

    const rows = await screen.findAllByTestId("diagnostic-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Battery Telemetry")).toBeInTheDocument();
    expect(within(rows[0]).getByText("RUNTIME_DETECTION")).toBeInTheDocument();
    expect(within(rows[0]).getByTestId("diagnostic-status")).toHaveTextContent("NOT RUN");
    expect(provider.planScan).toHaveBeenCalledWith(
      { device_id: REDMI.device_id, mode: "FULL_VERIFICATION" },
      expect.anything()
    );
    // The plan is read-only: nothing has started a scan.
    expect(provider.startScan).not.toHaveBeenCalled();
    expect(screen.getByTestId("skipped-list")).toHaveTextContent("1 diagnostics not run");
    expect(screen.getByTestId("verification-explainer")).toHaveTextContent(
      /does not prove the component works/
    );
    expect(screen.getByTestId("verification-explainer")).toHaveTextContent(
      /battery percentage is not battery health/
    );
  });

  it("runs a real scan and renders actual PASS and INCONCLUSIVE results with summaries", async () => {
    const provider = makeProvider();
    renderApp(provider);
    await startScan();

    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));
    expect(provider.startScan).toHaveBeenCalledWith(
      { device_id: REDMI.device_id, mode: "FULL_VERIFICATION" },
      expect.anything()
    );
    const statuses = screen.getAllByTestId("diagnostic-status").map((n) => n.textContent);
    expect(statuses).toEqual(["PASS", "INCONCLUSIVE"]);
    expect(screen.getAllByTestId("diagnostic-summary")[0]).toHaveTextContent(
      "does not represent full battery-health assessment"
    );
    expect(screen.getByTestId("scan-tallies")).toHaveTextContent("1 PASS");
    expect(screen.getByTestId("scan-tallies")).toHaveTextContent("1 INCONCLUSIVE");
  });

  it("derives progress from real counts and events, never a percentage", async () => {
    const running = summary({ state: "RUNNING", diagnostic_results: [BATTERY_RESULT] });
    // The second poll is held until released, so the mid-scan state is observed deterministically.
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const provider = makeProvider({
      getScanSummary: vi
        .fn()
        .mockResolvedValueOnce(ok(running))
        .mockImplementation(async () => {
          await gate;
          return ok(summary());
        }),
      getScanEvents: vi
        .fn()
        .mockResolvedValueOnce(ok({ scan_id: "scan-1", events: ALL_EVENTS.slice(0, 5) }))
        .mockImplementation(async () => {
          await gate;
          return ok({ scan_id: "scan-1", events: ALL_EVENTS });
        }),
    });
    renderApp(provider);
    await startScan();

    await waitFor(() =>
      expect(screen.getByTestId("scan-progress-text")).toHaveTextContent(
        "1 of 2 diagnostics reported · 1 evidence events · 5 events"
      )
    );
    const lifecycle = screen.getByTestId("scan-lifecycle");
    expect(lifecycle.textContent).not.toMatch(/%/);
    const statuses = screen.getAllByTestId("diagnostic-status").map((n) => n.textContent);
    expect(statuses).toEqual(["PASS", "RUNNING"]);

    release();
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));
    expect(screen.getByTestId("scan-progress-text")).toHaveTextContent(
      "2 of 2 diagnostics reported · 1 evidence events · 7 events"
    );
  });

  it("lets the user inspect collected evidence and shows an honest empty evidence state", async () => {
    renderApp(makeProvider());
    await startScan();
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));

    const toggles = screen.getAllByTestId("evidence-toggle");
    expect(toggles[0]).toHaveTextContent("Show evidence (1)");
    expect(toggles[0]).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggles[0]);

    const table = await screen.findByTestId("evidence-table");
    expect(within(table).getByText("Battery Level")).toBeInTheDocument();
    // Formatted for readability; the table keeps the exact collection method and provenance.
    expect(within(table).getByText("97%")).toBeInTheDocument();
    expect(within(table).getByText("adb shell dumpsys battery")).toBeInTheDocument();
    expect(within(table).getByText("not modeled")).toBeInTheDocument();

    fireEvent.click(toggles[1]);
    expect(await screen.findByTestId("evidence-empty")).toHaveTextContent(
      "No evidence records were collected"
    );
  });

  it("shows Trust Engine NOT_READY with no score and no estimate", async () => {
    renderApp(makeProvider());
    await startScan();
    await waitFor(() => expect(screen.getByTestId("trust-status")).toHaveTextContent("NOT_READY"));
    expect(screen.getByTestId("trust-no-score")).toHaveTextContent("No trust score.");
    expect(screen.queryByTestId("trust-score")).not.toBeInTheDocument();
  });

  it("renders a returned score only when the API supplies one", async () => {
    renderApp(
      makeProvider({
        getScanSummary: vi
          .fn()
          .mockResolvedValue(
            ok(summary({ trust_engine_status: "READY", trust_score: 81, trust_confidence: 0.7 }))
          ),
      })
    );
    await startScan();
    expect(await screen.findByTestId("trust-score")).toHaveTextContent("81");
    expect(screen.queryByTestId("trust-no-score")).not.toBeInTheDocument();
  });

  it("shows the raw event log from the backend", async () => {
    renderApp(makeProvider());
    await startScan();
    await waitFor(() => expect(screen.getByTestId("event-log")).toBeInTheDocument());
    expect(screen.getByTestId("event-log")).toHaveTextContent("7 events, 1 evidence");
  });

  it("surfaces unreadable result entries instead of dropping them", async () => {
    renderApp(
      makeProvider({
        getScanSummary: vi
          .fn()
          .mockResolvedValue(ok(summary({ diagnostic_results: [BATTERY_RESULT, { junk: 1 }] }))),
      })
    );
    await startScan();
    expect(await screen.findByTestId("unreadable-results")).toHaveTextContent(
      "1 result entry from the agent could not be read"
    );
  });

  it("labels a diagnostic with no reported verification level as not functional", async () => {
    const plan: ScanPlan = {
      ...PLAN,
      planned_items: [{ diagnostic_id: "battery_telemetry", applicability: "APPLICABLE" }],
    };
    renderApp(makeProvider({ planScan: vi.fn().mockResolvedValue(ok(plan)) }));
    const row = await screen.findByTestId("diagnostic-row");
    expect(within(row).getByText("LEVEL NOT REPORTED")).toBeInTheDocument();
    expect(within(row).queryByText("RUNTIME_DETECTION")).not.toBeInTheDocument();
  });
});

describe("Quick Scan workflow: device and API failure states", () => {
  it("blocks scanning for an unauthorized device and never plans or starts", async () => {
    const unauthorized: ConnectedDevice = {
      ...REDMI,
      authorization_state: "AUTHORIZATION_REQUIRED",
    };
    const provider = makeProvider({
      listDevices: vi
        .fn()
        .mockResolvedValue({ state: "COMPLETE", data: { devices: [unauthorized], count: 1 }, errorMessage: null }),
    });
    renderApp(provider);

    expect(await screen.findByTestId("device-blocked")).toHaveTextContent(/Allow USB debugging/);
    expect(screen.getByTestId("device-authorization")).toHaveTextContent("Authorization required");
    expect(screen.getByTestId("scan-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("start-scan")).not.toBeInTheDocument();
    expect(provider.planScan).not.toHaveBeenCalled();
    expect(provider.startScan).not.toHaveBeenCalled();
  });

  it("blocks scanning for a disconnected (OFFLINE) device", async () => {
    const offline: ConnectedDevice = { ...REDMI, connection_state: "OFFLINE" };
    const provider = makeProvider({
      listDevices: vi
        .fn()
        .mockResolvedValue({ state: "COMPLETE", data: { devices: [offline], count: 1 }, errorMessage: null }),
    });
    renderApp(provider);
    expect(await screen.findByTestId("device-blocked")).toHaveTextContent(/offline/);
    expect(provider.planScan).not.toHaveBeenCalled();
  });

  it("shows a setup checklist when no device is connected", async () => {
    renderApp(
      makeProvider({
        listDevices: vi
          .fn()
          .mockResolvedValue({ state: "COMPLETE", data: { devices: [], count: 0 }, errorMessage: null }),
      })
    );
    expect(await screen.findByTestId("device-empty")).toHaveTextContent("No phone detected");
    expect(screen.getByTestId("scan-idle")).toBeInTheDocument();
  });

  it("shows a loading state while discovering", async () => {
    renderApp(makeProvider({ listDevices: vi.fn().mockReturnValue(new Promise(() => {})) }));
    expect(await screen.findByTestId("device-loading")).toBeInTheDocument();
  });

  it("shows discovery errors as errors and does not fall back to demo data", async () => {
    renderApp(
      makeProvider({
        listDevices: vi.fn().mockResolvedValue({
          state: "ERROR",
          data: null,
          errorMessage: "VECTOR Local Agent is offline.",
        }),
      })
    );
    expect(await screen.findByTestId("device-error")).toHaveTextContent("Local Agent is offline");
    expect(screen.queryByText(/DEMO DATASET/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("device-option")).not.toBeInTheDocument();
    expect(screen.getByTestId("mode-badge")).toHaveTextContent("Mode: LIVE");
  });

  it("refresh re-runs discovery", async () => {
    const provider = makeProvider();
    renderApp(provider);
    await screen.findByTestId("device-facts");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(provider.listDevices).toHaveBeenCalledTimes(2));
  });

  it("requires an explicit choice when several devices are connected", async () => {
    const second: ConnectedDevice = { ...REDMI, device_id: "android-testdev0002" };
    const provider = makeProvider({
      listDevices: vi
        .fn()
        .mockResolvedValue({ state: "COMPLETE", data: { devices: [REDMI, second], count: 2 }, errorMessage: null }),
    });
    renderApp(provider);

    const options = await screen.findAllByTestId("device-option");
    expect(options).toHaveLength(2);
    expect(provider.planScan).not.toHaveBeenCalled();
    expect(screen.getByTestId("scan-idle")).toBeInTheDocument();

    fireEvent.click(options[1]);
    await screen.findAllByTestId("diagnostic-row");
    expect(provider.planScan).toHaveBeenCalledTimes(1);
    expect(provider.planScan).toHaveBeenCalledWith(
      { device_id: "android-testdev0002", mode: "FULL_VERIFICATION" },
      expect.anything()
    );
  });

  it("shows a plan error with retry and keeps the scan disabled", async () => {
    const planScan = vi
      .fn()
      .mockResolvedValueOnce(httpError(403))
      .mockResolvedValue(ok(PLAN));
    renderApp(makeProvider({ planScan }));

    expect(await screen.findByTestId("plan-error")).toHaveTextContent(/not authorized USB debugging/);
    expect(screen.getByTestId("start-scan")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Retry planning" }));
    expect(await screen.findAllByTestId("diagnostic-row")).toHaveLength(2);
    expect(screen.getByTestId("start-scan")).toBeEnabled();
  });

  it("shows an actionable error when the scan cannot start (409 already running)", async () => {
    const provider = makeProvider({ startScan: vi.fn().mockResolvedValue(httpError(409)) });
    renderApp(provider);
    await startScan();

    expect(await screen.findByTestId("start-error")).toHaveTextContent(/already running/);
    expect(screen.queryByTestId("scan-lifecycle")).not.toBeInTheDocument();
    expect(provider.getScanSummary).not.toHaveBeenCalled();
    expect(screen.getByTestId("start-scan")).toHaveTextContent("Try again");
  });

  it("recovers from a transient poll failure without losing the scan", async () => {
    const getScanSummary = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        error: { kind: "NETWORK", message: "VECTOR Local Agent is offline." },
      })
      .mockResolvedValue(ok(summary()));
    renderApp(makeProvider({ getScanSummary }));
    await startScan();
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));
    expect(screen.queryByTestId("poll-lost")).not.toBeInTheDocument();
  });

  it("stops polling after repeated failures and offers to check again", async () => {
    const down = {
      ok: false as const,
      error: { kind: "NETWORK" as const, message: "VECTOR Local Agent is offline." },
    };
    const getScanSummary = vi.fn().mockResolvedValue(down);
    renderApp(makeProvider({ getScanSummary }));
    await startScan();

    const lost = await screen.findByTestId("poll-lost");
    expect(lost).toHaveTextContent("Local Agent is offline");
    expect(lost).toHaveTextContent("may still be running");
    // Bounded: it did not poll forever.
    const callsAtStop = getScanSummary.mock.calls.length;
    await new Promise((r) => setTimeout(r, 40));
    expect(getScanSummary.mock.calls.length).toBe(callsAtStop);

    getScanSummary.mockResolvedValue(ok(summary()));
    fireEvent.click(screen.getByRole("button", { name: "Check scan status again" }));
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));
  });

  it("shows a failed scan as failed, with the backend error", async () => {
    renderApp(
      makeProvider({
        getScanSummary: vi
          .fn()
          .mockResolvedValue(
            ok(summary({ state: "FAILED", diagnostic_results: [], error: "Device disconnected." }))
          ),
      })
    );
    await startScan();
    expect(await screen.findByTestId("scan-error")).toHaveTextContent(
      "Scan failed: Device disconnected."
    );
    expect(screen.getByTestId("scan-state")).toHaveTextContent("FAILED");
    // No result means no invented PASS.
    const statuses = screen.getAllByTestId("diagnostic-status").map((n) => n.textContent);
    expect(statuses).toEqual(["NO RESULT", "NO RESULT"]);
  });

  it("lets the user run the scan again after it finishes", async () => {
    const provider = makeProvider();
    renderApp(provider);
    await startScan();
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));
    expect(screen.getByTestId("start-scan")).toHaveTextContent("Run scan again");
    fireEvent.click(screen.getByTestId("start-scan"));
    await waitFor(() => expect(provider.startScan).toHaveBeenCalledTimes(2));
  });
});

describe("Quick Scan workflow (DEMO)", () => {
  it("labels demo as DEMO DATASET and never lists devices or plans scans", async () => {
    const demo = new DemoDiagnosticProvider();
    const planSpy = vi.spyOn(demo, "planScan");
    render(<App provider={demo} scanOptions={FAST} />);

    expect(await screen.findByTestId("device-demo-banner")).toHaveTextContent("DEMO DATASET");
    expect(screen.queryByTestId("device-option")).not.toBeInTheDocument();
    expect(screen.queryByTestId("start-scan")).not.toBeInTheDocument();
    expect(screen.getByTestId("scan-idle")).toHaveTextContent("unavailable in Demo mode");
    expect(planSpy).not.toHaveBeenCalled();
  });

  it("demo scan methods refuse rather than simulate results", async () => {
    const demo = new DemoDiagnosticProvider();
    const result = await demo.startScan({ device_id: "x" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toMatch(/\[DEMO\].*not available/);
    expect((await demo.listDevices()).data?.devices).toEqual([]);
  });
});
