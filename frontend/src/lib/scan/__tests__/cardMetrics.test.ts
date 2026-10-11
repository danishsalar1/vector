import { describe, expect, it } from "vitest";
import type { CapabilityEvidenceRecord, DiagnosticResult } from "../../api/types";
import { buildCardModel } from "../cardMetrics";

// Fabricated ids; measurement values are from a real Redmi Note 8 Pro scan.
function ev(field: string, raw_value: string | null, unit: string | null): CapabilityEvidenceRecord {
  return {
    evidence_id: `ev-${field}`,
    diagnostic_id: "d",
    device_id: "android-testdev0001",
    source_type: "ADB_SHELL",
    source_name: "src",
    collection_method: "adb shell x",
    timestamp: "2026-10-11T00:00:00Z",
    raw_value,
    unit,
    metadata: { field },
  };
}

function result(diagnostic_id: string, evidence: CapabilityEvidenceRecord[]): DiagnosticResult {
  return {
    diagnostic_id,
    diagnostic_name: diagnostic_id,
    category: "x",
    status: "PASS",
    evidence,
  };
}

function metricsOf(model: ReturnType<typeof buildCardModel>): Record<string, string> {
  return Object.fromEntries(model.metrics.map((m) => [m.label, m.value]));
}

describe("memory card", () => {
  const model = buildCardModel(
    result("memory_telemetry", [
      ev("mem_total_bytes", "5909782528", "bytes"),
      ev("mem_free_bytes", "255619072", "bytes"),
      ev("mem_available_bytes", "3390156800", "bytes"),
    ])
  );

  it("labels the readings System RAM and Estimated available RAM", () => {
    expect(metricsOf(model)).toEqual({
      "System RAM": "5.91 GB",
      "Estimated available RAM": "3.39 GB",
    });
  });

  it("derives the available share from the two real readings", () => {
    expect(model.meter?.caption).toBe("57% of System RAM");
    expect(model.meter?.fraction).toBeCloseTo(3390156800 / 5909782528, 5);
  });

  it("explains the source and does not claim to match Recent Apps", () => {
    expect(model.note).toMatch(/\/proc\/meminfo/);
    expect(model.note).toMatch(/Recent Apps .* different estimate/);
  });

  it("keeps the raw value reachable on each converted metric", () => {
    expect(model.metrics[0].raw).toBe("5909782528 bytes");
  });

  it("draws no gauge when the readings are inconsistent or unreadable", () => {
    const inconsistent = buildCardModel(
      result("memory_telemetry", [
        ev("mem_total_bytes", "1000", "bytes"),
        ev("mem_available_bytes", "5000", "bytes"),
      ])
    );
    expect(inconsistent.meter).toBeNull();
    const unreadable = buildCardModel(
      result("memory_telemetry", [
        ev("mem_total_bytes", "N/A", "bytes"),
        ev("mem_available_bytes", "3390156800", "bytes"),
      ])
    );
    expect(unreadable.meter).toBeNull();
    // Malformed total is not converted or guessed.
    expect(metricsOf(unreadable)["System RAM"]).toBe("N/A bytes");
  });
});

describe("storage card", () => {
  const model = buildCardModel(
    result("storage_telemetry", [
      ev("storage_total_bytes", "117694799872", "bytes"),
      ev("storage_used_bytes", "64023437312", "bytes"),
      ev("storage_available_bytes", "53520367616", "bytes"),
      ev("storage_utilization_percent", "55.0", "percent"),
      ev("storage_logical_target", "/data", null),
    ])
  );

  it("describes the data filesystem, not total physical capacity", () => {
    expect(metricsOf(model)).toEqual({
      "Data filesystem capacity": "117.69 GB",
      "Data filesystem used": "64.02 GB",
      "Data filesystem available": "53.52 GB",
    });
    expect(Object.keys(metricsOf(model)).join(" ")).not.toMatch(/Total storage|Physical/i);
  });

  it("uses the reported utilization for the gauge", () => {
    expect(model.meter?.caption).toBe("55% used");
    expect(model.meter?.fraction).toBeCloseTo(0.55, 5);
  });

  it("warns that advertised storage and Settings usage may differ", () => {
    expect(model.note).toMatch(/\/data filesystem, not the phone’s total physical capacity/);
    expect(model.note).toMatch(/Advertised storage and Settings → Storage usage can differ/);
  });

  it("falls back to used/total when no utilization is reported, and to nothing when unreadable", () => {
    const computed = buildCardModel(
      result("storage_telemetry", [
        ev("storage_total_bytes", "1000000000", "bytes"),
        ev("storage_used_bytes", "250000000", "bytes"),
      ])
    );
    expect(computed.meter?.caption).toBe("25% used");
    const none = buildCardModel(
      result("storage_telemetry", [ev("storage_total_bytes", "N/A", "bytes")])
    );
    expect(none.meter).toBeNull();
  });
});

describe("battery card", () => {
  const model = buildCardModel(
    result("battery_telemetry", [
      ev("battery_level", "100", "percent"),
      ev("battery_voltage", "4282", "mV"),
      ev("battery_temperature", "341", "tenths_celsius"),
      ev("battery_charging_status", "Full", null),
      ev("battery_health_classification", "Good", null),
    ])
  );

  it("formats readings and never labels charge level as health", () => {
    const m = metricsOf(model);
    expect(m["Charge level"]).toBe("100%");
    expect(m["Voltage"]).toBe("4.28 V");
    expect(m["Temperature"]).toBe("34.1°C");
    expect(m["Charging state"]).toBe("Full");
    expect(Object.keys(m).join(" ")).not.toMatch(/health/i);
  });

  it("qualifies the Android-reported state as not a VECTOR measurement", () => {
    const state = model.metrics.find((x) => x.label === "Android battery state");
    expect(state?.value).toBe("Good");
    expect(state?.hint).toMatch(/not measured capacity or wear/);
  });

  it("keeps the raw temperature reachable", () => {
    expect(model.metrics.find((x) => x.label === "Temperature")?.raw).toBe("341 tenths_celsius");
  });
});

describe("thermal, display and camera cards", () => {
  it("lists sensors with readings and the highest one", () => {
    const model = buildCardModel(
      result("thermal_telemetry", [
        ev("thermal_status_code", "0", null),
        ev("thermal_sensor_count", "6", "count"),
        ev("sensor_CPU", "36.18", "celsius"),
        ev("sensor_SKIN", "34.6", "celsius"),
        ev("sensor_POWER_AMPLIFIER", "34.4", "celsius"),
      ])
    );
    expect(model.chips).toEqual([
      { label: "CPU", value: "36.2°C" },
      { label: "SKIN", value: "34.6°C" },
      { label: "POWER AMPLIFIER", value: "34.4°C" },
    ]);
    expect(metricsOf(model)).toEqual({ "Sensors reported": "6", "Highest reading": "36.2°C" });
  });

  it("shows resolution and density", () => {
    const model = buildCardModel(
      result("display_metrics", [
        ev("display_physical_resolution", "1080x2340", null),
        ev("display_physical_density_dpi", "440", "dpi"),
      ])
    );
    expect(metricsOf(model)).toEqual({ Resolution: "1080 × 2340", Density: "440 dpi" });
  });

  it("does not reformat a resolution that is not WxH", () => {
    const model = buildCardModel(
      result("display_metrics", [ev("display_physical_resolution", "unknown", null)])
    );
    expect(metricsOf(model)).toEqual({ Resolution: "unknown" });
  });

  it("reports the camera device count without a unit word", () => {
    const model = buildCardModel(
      result("camera_inventory", [ev("camera_device_count", "6", "count"), ev("camera_0", "Camera 0", null)])
    );
    expect(metricsOf(model)).toEqual({ "Camera devices reported": "6" });
  });
});

describe("no data, no card metrics", () => {
  it.each([
    ["no result", null],
    ["no evidence", result("storage_telemetry", [])],
    ["unknown diagnostic", result("brand_new_diagnostic", [ev("anything", "1", "bytes")])],
  ])("%s yields an empty model", (_name, input) => {
    const model = buildCardModel(input);
    expect(model.metrics).toEqual([]);
    expect(model.meter).toBeNull();
    expect(model.note).toBeNull();
    expect(model.chips).toEqual([]);
  });

  it("omits a metric whose evidence is missing rather than inventing one", () => {
    const model = buildCardModel(
      result("memory_telemetry", [ev("mem_total_bytes", "5909782528", "bytes")])
    );
    expect(metricsOf(model)).toEqual({ "System RAM": "5.91 GB" });
  });
});
