import { describe, expect, it } from "vitest";
import type { ConnectedDevice } from "../../api/devices";
import type {
  DiagnosticApplicability,
  DiagnosticEvent,
  DiagnosticResult,
  ScanPlan,
} from "../../api/types";
import {
  buildDiagnosticRows,
  computeProgress,
  describeScanError,
  describeVerificationLevel,
  getDeviceEligibility,
  humanizeDiagnosticId,
  isTerminalScanState,
  parseDiagnosticResults,
  splitPlan,
  summarizeSkipped,
} from "../quickScanModel";

function device(overrides: Partial<ConnectedDevice> = {}): ConnectedDevice {
  return {
    device_id: "android-test0001",
    platform: "ANDROID",
    connection_state: "CONNECTED",
    authorization_state: "AUTHORIZED",
    identity: null,
    ...overrides,
  };
}

const PLAN: ScanPlan = {
  plan_id: "p1",
  device_id: "android-test0001",
  platform: "ANDROID",
  mode: "FULL_VERIFICATION",
  diagnostics_requested: ["a_one", "b_two", "c_three"],
  diagnostics_planned: ["a_one", "b_two"],
  diagnostics_skipped: ["c_three"],
  skip_reasons: { c_three: "Not supported." },
  planned_items: [
    { diagnostic_id: "a_one", applicability: "APPLICABLE", verification_level: "RUNTIME_DETECTION" },
    { diagnostic_id: "b_two", applicability: "APPLICABLE" },
    { diagnostic_id: "c_three", applicability: "NOT_APPLICABLE", reason: "Not supported." },
  ],
  registry_diagnostic_ids: ["a_one", "b_two", "c_three"],
  created_at: "2026-10-11T00:00:00Z",
};

function result(id: string, status: string): DiagnosticResult {
  return {
    diagnostic_id: id,
    diagnostic_name: `Name of ${id}`,
    category: "x",
    status,
    evidence: [],
  };
}

function event(type: DiagnosticEvent["event_type"], diagnostic_id?: string): DiagnosticEvent {
  return {
    event_id: `${type}-${diagnostic_id ?? "scan"}`,
    scan_id: "s1",
    device_id: "android-test0001",
    event_type: type,
    timestamp: "2026-10-11T00:00:00Z",
    diagnostic_id,
  };
}

describe("getDeviceEligibility", () => {
  it("allows only connected + authorized devices", () => {
    expect(getDeviceEligibility(device()).eligible).toBe(true);
  });

  it.each([
    ["AUTHORIZATION_REQUIRED", /Allow USB debugging/],
    ["RESTRICTED", /restricts access/],
    ["UNKNOWN", /not reported/],
    [undefined, /not reported/],
  ])("blocks authorization state %s", (authorization_state, reason) => {
    const e = getDeviceEligibility(
      device({ authorization_state: authorization_state as ConnectedDevice["authorization_state"] })
    );
    expect(e.eligible).toBe(false);
    expect(e.reason).toMatch(reason);
  });

  it("blocks a device that is not CONNECTED even if previously authorized", () => {
    const e = getDeviceEligibility(device({ connection_state: "OFFLINE" }));
    expect(e.eligible).toBe(false);
    expect(e.reason).toMatch(/offline/);
  });
});

describe("describeVerificationLevel", () => {
  it("labels RUNTIME_DETECTION as not a functional test", () => {
    const info = describeVerificationLevel("RUNTIME_DETECTION");
    expect(info.badge).toBe("RUNTIME_DETECTION");
    expect(info.meaning).toMatch(/does not test that the component works/);
  });

  it.each([null, undefined])("never promotes an unreported level (%s)", (level) => {
    const info = describeVerificationLevel(level);
    expect(info.badge).toBe("LEVEL NOT REPORTED");
    expect(info.meaning).toMatch(/not functional/);
  });
});

describe("describeScanError", () => {
  it.each([
    [403, /not authorized USB debugging/],
    [404, /no longer knows/],
    [400, /not connected/],
    [409, /already running/],
  ])("maps HTTP %s to actionable wording", (statusCode, expected) => {
    expect(describeScanError({ kind: "HTTP", statusCode, message: "x" }, "Failed")).toMatch(
      expected
    );
  });

  it("passes transport errors through", () => {
    expect(describeScanError({ kind: "NETWORK", message: "Agent offline." }, "Failed")).toBe(
      "Failed: Agent offline."
    );
  });
});

describe("rows and progress", () => {
  it("splits planned from skipped", () => {
    const { planned, skipped } = splitPlan(PLAN);
    expect(planned.map((p) => p.diagnostic_id)).toEqual(["a_one", "b_two"]);
    expect(skipped.map((p) => p.diagnostic_id)).toEqual(["c_three"]);
  });

  it("derives WAITING / RUNNING / result status only from results and events", () => {
    const rows = buildDiagnosticRows(
      PLAN,
      [result("a_one", "PASS")],
      [event("diagnostic.started", "a_one"), event("diagnostic.started", "b_two")]
    );
    expect(rows.map((r) => r.status)).toEqual(["PASS", "RUNNING"]);
    expect(rows[0].name).toBe("Name of a_one");
    expect(rows[1].name).toBe("B Two");
  });

  it("never shows RUNNING once the scan is terminal, even if a start event exists", () => {
    const rows = buildDiagnosticRows(
      PLAN,
      [],
      [event("diagnostic.started", "a_one")],
      true
    );
    expect(rows.map((r) => r.status)).toEqual(["WAITING", "WAITING"]);
  });

  it("never invents a status: no result and no started event is WAITING", () => {
    const rows = buildDiagnosticRows(PLAN, [], []);
    expect(rows.map((r) => r.status)).toEqual(["WAITING", "WAITING"]);
  });

  it("keeps results the plan did not list, with no verification level", () => {
    const rows = buildDiagnosticRows(PLAN, [result("z_extra", "FAIL")], []);
    const extra = rows.find((r) => r.id === "z_extra");
    expect(extra?.status).toBe("FAIL");
    expect(extra?.verificationLevel).toBeUndefined();
  });

  it("reports progress as counts of real results and events, never a percentage", () => {
    const rows = buildDiagnosticRows(PLAN, [result("a_one", "PASS")], []);
    const progress = computeProgress(rows, [
      event("scan.started"),
      event("diagnostic.evidence", "a_one"),
    ]);
    expect(progress).toEqual({ finished: 1, total: 2, evidenceEvents: 1, totalEvents: 2 });
    expect(Object.keys(progress)).not.toContain("percent");
  });
});

describe("parseDiagnosticResults", () => {
  it("surfaces unreadable entries instead of dropping them silently", () => {
    const parsed = parseDiagnosticResults([result("a_one", "PASS"), { nonsense: true }, null]);
    expect(parsed.results).toHaveLength(1);
    expect(parsed.unreadable).toBe(2);
  });
});

describe("misc", () => {
  it("humanizes ids generically", () => {
    expect(humanizeDiagnosticId("camera_inventory")).toBe("Camera Inventory");
  });

  it("recognises only terminal lifecycle states", () => {
    expect(["COMPLETED", "FAILED", "CANCELLED"].every(isTerminalScanState)).toBe(true);
    expect(["CREATED", "PLANNED", "RUNNING"].some(isTerminalScanState)).toBe(false);
  });
});

describe("summarizeSkipped", () => {
  function skipped(...kinds: DiagnosticApplicability[]) {
    return kinds.map((applicability, i) => ({ diagnostic_id: `d${i}`, applicability }));
  }

  it("says 'not applicable to Android' only when every exclusion is a platform exclusion", () => {
    const six = skipped(...Array<DiagnosticApplicability>(6).fill("NOT_APPLICABLE"));
    expect(summarizeSkipped(six, "ANDROID")).toBe("6 diagnostics not applicable to Android");
  });

  it("uses singular wording for one and names the right platform", () => {
    expect(summarizeSkipped(skipped("NOT_APPLICABLE"), "ANDROID")).toBe(
      "1 diagnostic not applicable to Android"
    );
    expect(summarizeSkipped(skipped("NOT_APPLICABLE", "NOT_APPLICABLE"), "IOS")).toBe(
      "2 diagnostics not applicable to iOS"
    );
  });

  it.each([
    ["UNSUPPORTED", "1 diagnostic not run: 1 unsupported on this device"],
    ["UNAVAILABLE", "1 diagnostic not run: 1 unavailable"],
    ["RESTRICTED", "1 diagnostic not run: 1 restricted"],
    ["BLOCKED_BY_PREREQUISITE", "1 diagnostic not run: 1 blocked by a prerequisite"],
    ["UNKNOWN", "1 diagnostic not run: 1 of unknown applicability"],
  ] as const)("never calls a %s exclusion a platform mismatch", (status, expected) => {
    const text = summarizeSkipped(skipped(status), "ANDROID");
    expect(text).toBe(expected);
    expect(text).not.toMatch(/not applicable/);
  });

  it("keeps each reason accurate when exclusions are mixed", () => {
    const text = summarizeSkipped(
      skipped("NOT_APPLICABLE", "NOT_APPLICABLE", "UNAVAILABLE", "RESTRICTED"),
      "ANDROID"
    );
    expect(text).toBe(
      "4 diagnostics not run: 2 not applicable to Android, 1 unavailable, 1 restricted"
    );
  });

  it("falls back to the raw status for a status it does not know", () => {
    expect(
      summarizeSkipped(
        [{ diagnostic_id: "x", applicability: "NEW_STATUS" as DiagnosticApplicability }],
        "ANDROID"
      )
    ).toBe("1 diagnostic not run: 1 new status");
  });
});
