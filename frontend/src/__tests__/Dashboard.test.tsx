import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "../App";
import { DiagnosticCard } from "../components/scan/DiagnosticCard";
import type { DiagnosticProvider } from "../providers/DiagnosticProvider";
import type { ConnectedDevice } from "../lib/api/devices";
import type { CapabilityEvidenceRecord, ScanPlan, ScanSummary } from "../lib/api/types";
import type { SafeFetchResult } from "../lib/api/request";
import type { DiagnosticRow } from "../lib/scan/quickScanModel";

// Fabricated ids; measurement values are from a real Redmi Note 8 Pro scan.
function ev(field: string, raw_value: string, unit: string | null, diagnostic_id: string): CapabilityEvidenceRecord {
  return {
    evidence_id: `ev-${diagnostic_id}-${field}`,
    diagnostic_id,
    device_id: "android-testdev0001",
    source_type: "ADB_SHELL",
    source_name: "ADB / test",
    collection_method: "adb shell test",
    timestamp: "2026-10-11T00:00:01Z",
    raw_value,
    unit,
    reliability: null,
    metadata: { field },
    redacted: false,
    error: null,
  };
}

const MEMORY = {
  diagnostic_id: "memory_telemetry",
  diagnostic_name: "Memory Telemetry Verification",
  category: "memory",
  status: "PASS",
  summary: "PASS confirms successful memory telemetry collection. It does not represent RAM chip hardware integrity or defect absence.",
  duration_seconds: 0.06,
  evidence: [
    ev("mem_total_bytes", "5909782528", "bytes", "memory_telemetry"),
    ev("mem_free_bytes", "255619072", "bytes", "memory_telemetry"),
    ev("mem_available_bytes", "3390156800", "bytes", "memory_telemetry"),
  ],
};

const STORAGE = {
  diagnostic_id: "storage_telemetry",
  diagnostic_name: "Storage Telemetry Verification",
  category: "storage",
  status: "PASS",
  summary: "PASS confirms successful storage telemetry collection. It does not represent storage chip hardware health or lifetime.",
  duration_seconds: 0.08,
  evidence: [
    ev("storage_total_bytes", "117694799872", "bytes", "storage_telemetry"),
    ev("storage_used_bytes", "64023437312", "bytes", "storage_telemetry"),
    ev("storage_available_bytes", "53520367616", "bytes", "storage_telemetry"),
    ev("storage_utilization_percent", "55.0", "percent", "storage_telemetry"),
    ev("storage_logical_target", "/data", null, "storage_telemetry"),
  ],
};

const BATTERY = {
  diagnostic_id: "battery_telemetry",
  diagnostic_name: "Battery Telemetry Verification",
  category: "battery",
  status: "PASS",
  summary: "PASS confirms successful battery telemetry collection. It does not represent full battery-health assessment.",
  duration_seconds: 0.08,
  evidence: [
    ev("battery_level", "100", "percent", "battery_telemetry"),
    ev("battery_temperature", "341", "tenths_celsius", "battery_telemetry"),
  ],
};

const INCONCLUSIVE = {
  diagnostic_id: "camera_inventory",
  diagnostic_name: "Camera Inventory Verification",
  category: "camera",
  status: "INCONCLUSIVE",
  summary: "Camera inventory was partially collected or unparseable.",
  duration_seconds: 0.1,
  evidence: [],
};

function row(
  result: typeof MEMORY | typeof INCONCLUSIVE | null,
  overrides: Partial<DiagnosticRow> = {}
): DiagnosticRow {
  return {
    id: result?.diagnostic_id ?? "memory_telemetry",
    name: result?.diagnostic_name ?? "Memory Telemetry Verification",
    status: result ? result.status : "WAITING",
    result,
    verificationLevel: "RUNTIME_DETECTION",
    requiresProbe: false,
    ...overrides,
  };
}

function card(r: DiagnosticRow, props: { expanded?: boolean; scanStarted?: boolean; finished?: boolean } = {}) {
  render(
    <ul>
      <DiagnosticCard
        row={r}
        scanStarted={props.scanStarted ?? true}
        finished={props.finished ?? true}
        expanded={props.expanded ?? false}
        onToggle={() => {}}
      />
    </ul>
  );
  return screen.getByTestId("diagnostic-row");
}

describe("DiagnosticCard", () => {
  it("drops the 'Verification' suffix from telemetry titles", () => {
    const el = card(row(MEMORY));
    expect(within(el).getByRole("heading", { name: "Memory Telemetry" })).toBeInTheDocument();
    expect(el.textContent).not.toMatch(/Telemetry Verification/);
  });

  it("shows System RAM and Estimated available RAM in GB with the gauge", () => {
    const el = card(row(MEMORY));
    const metrics = within(el).getAllByTestId("metric").map((m) => m.textContent);
    expect(metrics[0]).toContain("System RAM");
    expect(metrics[0]).toContain("5.91 GB");
    expect(metrics[1]).toContain("Estimated available RAM");
    expect(metrics[1]).toContain("3.39 GB");
    expect(within(el).getByTestId("card-meter")).toHaveTextContent("57% of System RAM");
  });

  it("separates data collected from a functional test", () => {
    const el = card(row(MEMORY));
    expect(within(el).getByText("RUNTIME_DETECTION")).toBeInTheDocument();
    expect(el).toHaveTextContent(/data was read from the phone\. The component was not functionally tested/);
    expect(within(el).getByTestId("diagnostic-status")).toHaveTextContent("PASS");
  });

  it("treats an unreported level as not functional", () => {
    const el = card(row(MEMORY, { verificationLevel: undefined }));
    expect(within(el).getByText("LEVEL NOT REPORTED")).toBeInTheDocument();
    expect(el).toHaveTextContent(/not treated as a functional result/);
    expect(within(el).queryByText("RUNTIME_DETECTION")).not.toBeInTheDocument();
  });

  it("keeps technical evidence collapsed until expanded, with raw values reachable", () => {
    const collapsed = card(row(MEMORY));
    const toggle = within(collapsed).getByTestId("evidence-toggle");
    expect(toggle).toHaveTextContent("Technical evidence (3)");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(collapsed).queryByTestId("evidence-table")).not.toBeInTheDocument();
  });

  it("renders the evidence table with the exact raw value when expanded", () => {
    const el = card(row(MEMORY), { expanded: true });
    const table = within(el).getByTestId("evidence-table");
    expect(within(table).getByText("5.91 GB")).toBeInTheDocument();
    expect(within(table).getByText("Raw: 5909782528 bytes")).toBeInTheDocument();
  });

  it("an inconclusive result shows no metrics, its status and its backend summary", () => {
    const el = card(row(INCONCLUSIVE));
    expect(within(el).getByTestId("diagnostic-status")).toHaveTextContent("INCONCLUSIVE");
    expect(within(el).queryByTestId("card-metrics")).not.toBeInTheDocument();
    expect(within(el).getByTestId("diagnostic-summary")).toHaveTextContent("partially collected");
    expect(within(el).getByTestId("evidence-toggle")).toHaveTextContent("(0)");
  });

  it("before a scan the card says it has not run and shows no numbers", () => {
    const el = card(row(null), { scanStarted: false, finished: false });
    expect(within(el).getByTestId("diagnostic-status")).toHaveTextContent("NOT RUN");
    expect(el).toHaveTextContent("Runs when you start the scan.");
    expect(within(el).queryByTestId("metric")).not.toBeInTheDocument();
    expect(within(el).queryByTestId("evidence-toggle")).not.toBeInTheDocument();
  });

  it("after a finished scan a diagnostic without a result says so, never PASS", () => {
    const el = card(row(null), { scanStarted: true, finished: true });
    expect(within(el).getByTestId("diagnostic-status")).toHaveTextContent("NO RESULT");
    expect(el).toHaveTextContent("did not report a result");
  });
});

// ---- Full dashboard through App ----

const REDMI: ConnectedDevice = {
  device_id: "android-testdev0001",
  platform: "ANDROID",
  connection_state: "CONNECTED",
  authorization_state: "AUTHORIZED",
  identity: {
    platform: "ANDROID",
    manufacturer: "Xiaomi",
    model: "Redmi Note 8 Pro",
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
  diagnostics_requested: ["battery_telemetry", "storage_telemetry", "memory_telemetry"],
  diagnostics_planned: ["battery_telemetry", "storage_telemetry", "memory_telemetry"],
  diagnostics_skipped: [],
  skip_reasons: {},
  planned_items: ["battery_telemetry", "storage_telemetry", "memory_telemetry"].map((id) => ({
    diagnostic_id: id,
    applicability: "APPLICABLE" as const,
    verification_level: "RUNTIME_DETECTION" as const,
    requires_probe: false,
  })),
  registry_diagnostic_ids: ["battery_telemetry", "storage_telemetry", "memory_telemetry"],
  created_at: "2026-10-11T00:00:00Z",
};

function ok<T>(data: T): SafeFetchResult<T> {
  return { ok: true, data };
}

function provider(): DiagnosticProvider {
  const summary: ScanSummary = {
    scan_id: "scan-1",
    device_id: REDMI.device_id,
    state: "COMPLETED",
    created_at: "2026-10-11T00:00:00Z",
    plan: PLAN,
    diagnostic_results: [BATTERY, STORAGE, MEMORY],
    trust_engine_status: "NOT_READY",
    trust_score: null,
    trust_confidence: null,
    error: null,
  };
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
    startScan: vi.fn().mockResolvedValue(ok({ scan_id: "scan-1", state: "RUNNING", plan: PLAN })),
    getScanSummary: vi.fn().mockResolvedValue(ok(summary)),
    getScanEvents: vi.fn().mockResolvedValue(ok({ scan_id: "scan-1", events: [] })),
  };
}

describe("Dashboard (App)", () => {
  it("shows the phone's identity, Android version and status in the overview", async () => {
    render(<App provider={provider()} scanOptions={{ pollIntervalMs: 5 }} />);
    const heading = await screen.findByRole("heading", { level: 2, name: "Xiaomi Redmi Note 8 Pro" });
    const overview = heading.closest("section") as HTMLElement;
    expect(overview).toHaveTextContent("Android 11 · SDK 30 · testcodename");
    expect(within(overview).getByTestId("device-connection")).toHaveTextContent("CONNECTED");
    expect(within(overview).getByTestId("device-authorization")).toHaveTextContent("Authorized");
    expect(within(overview).getByTestId("start-scan")).toBeInTheDocument();
  });

  it("presents a finished scan as readable cards with the requested labels", async () => {
    render(<App provider={provider()} scanOptions={{ pollIntervalMs: 5 }} />);
    const start = await screen.findByTestId("start-scan");
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));

    const cards = screen.getAllByTestId("diagnostic-row");
    expect(cards).toHaveLength(3);
    const byId = (id: string) => cards.find((c) => c.dataset.diagnosticId === id) as HTMLElement;

    const storage = byId("storage_telemetry");
    expect(storage).toHaveTextContent("Data filesystem capacity");
    expect(storage).toHaveTextContent("117.69 GB");
    expect(storage).toHaveTextContent("Data filesystem used");
    expect(storage).toHaveTextContent("64.02 GB");
    expect(storage).toHaveTextContent(/Advertised storage and Settings → Storage usage can differ/);
    expect(storage.textContent).not.toMatch(/Total storage/i);

    const memory = byId("memory_telemetry");
    expect(memory).toHaveTextContent("System RAM");
    expect(memory).toHaveTextContent("Estimated available RAM");
    expect(memory).toHaveTextContent("3.39 GB");

    expect(byId("battery_telemetry")).toHaveTextContent("34.1°C");

    // No card or step uses the overstated "Verification" wording for telemetry.
    expect(screen.getByTestId("diagnostic-list").textContent).not.toMatch(/Telemetry Verification/);
    expect(screen.getByTestId("verification-explainer")).toHaveTextContent(
      "Data collected is not hardware tested."
    );
    // Trust Engine is reported exactly as returned.
    expect(screen.getByTestId("trust-status")).toHaveTextContent("NOT_READY");
    expect(screen.getByTestId("trust-no-score")).toBeInTheDocument();
  });

  it("progress steps show real per-diagnostic results, with no percentage", async () => {
    render(<App provider={provider()} scanOptions={{ pollIntervalMs: 5 }} />);
    const start = await screen.findByTestId("start-scan");
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    await waitFor(() => expect(screen.getByTestId("scan-state")).toHaveTextContent("COMPLETED"));

    const lifecycle = screen.getByTestId("scan-lifecycle");
    expect(lifecycle).toHaveTextContent("3 of 3 diagnostics reported");
    expect(within(lifecycle).getAllByRole("listitem")).toHaveLength(3);
    expect(lifecycle.textContent).not.toMatch(/%/);
  });
});
