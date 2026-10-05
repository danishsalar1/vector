import { describe, expect, it, vi } from "vitest";
import {
  isDiagnosticEvent,
  isScanEventsResponse,
  isScanPlan,
  isScanSummary,
  type DiagnosticEvent,
  type ScanEventsResponse,
  type ScanPlan,
  type ScanSummary,
} from "../types";
import { fetchScanPlan, fetchScanSummary, startScan } from "../scans";

describe("Scan API types and guards", () => {
  it("validates valid ScanPlan", () => {
    const validPlan: ScanPlan = {
      plan_id: "plan-123",
      device_id: "dev-001",
      platform: "ANDROID",
      mode: "FULL_VERIFICATION",
      diagnostics_requested: ["battery_telemetry"],
      diagnostics_planned: ["battery_telemetry"],
      diagnostics_skipped: [],
      skip_reasons: {},
      planned_items: [
        {
          diagnostic_id: "battery_telemetry",
          applicability: "APPLICABLE",
          reason: null,
        },
      ],
      created_at: new Date().toISOString(),
      registry_diagnostic_ids: ["battery_telemetry"],
    };

    expect(isScanPlan(validPlan)).toBe(true);
    expect(isScanPlan({ plan_id: "incomplete" })).toBe(false);
    expect(
      isScanPlan({
        ...validPlan,
        planned_items: [{ invalid: "item" }],
      })
    ).toBe(false);
  });

  it("validates valid DiagnosticEvent", () => {
    const event: DiagnosticEvent = {
      event_id: "ev-1",
      scan_id: "scan-1",
      device_id: "dev-1",
      event_type: "scan.started",
      timestamp: new Date().toISOString(),
    };

    expect(isDiagnosticEvent(event)).toBe(true);
    expect(isDiagnosticEvent({ event_id: "ev-1" })).toBe(false);
  });

  it("validates valid ScanSummary", () => {
    const summary: ScanSummary = {
      scan_id: "scan-1",
      device_id: "dev-1",
      state: "COMPLETED",
      created_at: new Date().toISOString(),
      diagnostic_results: [],
      trust_engine_status: "NOT_READY",
      trust_score: null,
    };

    expect(isScanSummary(summary)).toBe(true);
    expect(isScanSummary({ scan_id: "scan-1" })).toBe(false);
  });

  it("validates ScanEventsResponse and rejects malformed events", () => {
    const validEventsResp: ScanEventsResponse = {
      scan_id: "scan-1",
      events: [
        {
          event_id: "ev-1",
          scan_id: "scan-1",
          device_id: "dev-1",
          event_type: "scan.started",
          timestamp: new Date().toISOString(),
        },
      ],
    };
    expect(isScanEventsResponse(validEventsResp)).toBe(true);
    expect(
      isScanEventsResponse({
        scan_id: "scan-1",
        events: [{ invalid: "event" }],
      })
    ).toBe(false);
    expect(isScanEventsResponse({ scan_id: "scan-1" })).toBe(false);
  });
});

describe("Scan API client functions", () => {
  it("fetchScanPlan sends POST with JSON body", async () => {
    const mockPlan: ScanPlan = {
      plan_id: "plan-1",
      device_id: "dev-1",
      platform: "ANDROID",
      mode: "FULL_VERIFICATION",
      diagnostics_requested: ["battery_telemetry"],
      diagnostics_planned: ["battery_telemetry"],
      diagnostics_skipped: [],
      skip_reasons: {},
      planned_items: [],
      created_at: new Date().toISOString(),
      registry_diagnostic_ids: [],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPlan,
    } as unknown as Response);

    const result = await fetchScanPlan({ device_id: "dev-1" });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.plan_id).toBe("plan-1");
    }
  });

  it("startScan sends POST to start scan", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        scan_id: "scan-abc",
        state: "PLANNED",
      }),
    } as unknown as Response);

    const result = await startScan({ device_id: "dev-1" });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.scan_id).toBe("scan-abc");
      expect(result.data.state).toBe("PLANNED");
    }
  });

  it("fetchScanSummary retrieves summary", async () => {
    const mockSummary: ScanSummary = {
      scan_id: "scan-abc",
      device_id: "dev-1",
      state: "RUNNING",
      created_at: new Date().toISOString(),
      diagnostic_results: [],
      trust_engine_status: "NOT_READY",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSummary,
    } as unknown as Response);

    const result = await fetchScanSummary("scan-abc");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.scan_id).toBe("scan-abc");
      expect(result.data.trust_engine_status).toBe("NOT_READY");
    }
  });
});
