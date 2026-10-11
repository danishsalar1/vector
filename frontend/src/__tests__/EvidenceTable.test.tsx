import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { EvidenceTable } from "../components/scan/EvidenceTable";
import type { CapabilityEvidenceRecord } from "../lib/api/types";

// Fabricated ids; measurement values are from a real Redmi Note 8 Pro scan.
function rec(
  id: string,
  field: string,
  raw_value: string | null,
  unit: string | null,
  extra: Partial<CapabilityEvidenceRecord> = {}
): CapabilityEvidenceRecord {
  return {
    evidence_id: id,
    diagnostic_id: "d",
    device_id: "android-testdev0001",
    source_type: "ADB_SHELL",
    source_name: "ADB / test",
    collection_method: "adb shell test",
    timestamp: "2026-10-11T00:00:00Z",
    raw_value,
    unit,
    metadata: { field },
    ...extra,
  };
}

function rowFor(label: string): HTMLElement {
  return screen.getByRole("rowheader", { name: label }).closest("tr") as HTMLElement;
}

describe("EvidenceTable formatting", () => {
  it("shows readable GB values while keeping the raw bytes visible", () => {
    render(
      <EvidenceTable
        evidence={[
          rec("1", "storage_total_bytes", "117694799872", "bytes"),
          rec("2", "storage_used_bytes", "64023437312", "bytes"),
          rec("3", "storage_available_bytes", "53520367616", "bytes"),
          rec("4", "mem_total_bytes", "5909782528", "bytes"),
        ]}
      />
    );
    const total = within(rowFor("Storage Total"));
    expect(total.getByText("117.69 GB")).toBeInTheDocument();
    expect(total.getByTestId("evidence-raw")).toHaveTextContent("Raw: 117694799872 bytes");
    expect(within(rowFor("Storage Used")).getByText("64.02 GB")).toBeInTheDocument();
    expect(within(rowFor("Storage Available")).getByText("53.52 GB")).toBeInTheDocument();
    expect(within(rowFor("Mem Total")).getByText("5.91 GB")).toBeInTheDocument();
  });

  it("shows temperature, voltage and percent in consistent units", () => {
    render(
      <EvidenceTable
        evidence={[
          rec("1", "battery_temperature", "344", "tenths_celsius"),
          rec("2", "battery_voltage", "4282", "mV"),
          rec("3", "battery_level", "100", "percent"),
          rec("4", "sensor_CPU", "36.13", "celsius"),
        ]}
      />
    );
    const temp = within(rowFor("Battery Temperature"));
    expect(temp.getByText("34.4°C")).toBeInTheDocument();
    expect(temp.getByTestId("evidence-raw")).toHaveTextContent("Raw: 344 tenths_celsius");
    expect(within(rowFor("Battery Voltage")).getByText("4.28 V")).toBeInTheDocument();
    const level = within(rowFor("Battery Level"));
    expect(level.getByText("100%")).toBeInTheDocument();
    expect(level.queryByTestId("evidence-raw")).not.toBeInTheDocument();
    expect(within(rowFor("Sensor CPU")).getByText("36.1°C")).toBeInTheDocument();
  });

  it("leaves unknown units, text values and missing values exactly as received", () => {
    render(
      <EvidenceTable
        evidence={[
          rec("1", "display_physical_resolution", "1080x2340", null),
          rec("2", "display_physical_density_dpi", "440", "dpi"),
          rec("3", "camera_device_count", "6", "count"),
          rec("4", "battery_health_classification", "Good", null),
          rec("5", "mem_free_bytes", "N/A", "bytes"),
          rec("6", "thermal_status_code", null, null),
        ]}
      />
    );
    expect(within(rowFor("Display Physical Resolution")).getByText("1080x2340")).toBeInTheDocument();
    expect(within(rowFor("Display Physical Density Dpi")).getByText("440 dpi")).toBeInTheDocument();
    expect(within(rowFor("Camera Device Count")).getByText("6 count")).toBeInTheDocument();
    expect(within(rowFor("Battery Health Classification")).getByText("Good")).toBeInTheDocument();
    // Malformed bytes are not converted and keep their full label.
    expect(within(rowFor("Mem Free Bytes")).getByText("N/A bytes")).toBeInTheDocument();
    expect(within(rowFor("Thermal Status Code")).getByText("—")).toBeInTheDocument();
  });

  it("notes that /data values describe that filesystem, only when the evidence says so", () => {
    const { rerender } = render(
      <EvidenceTable
        evidence={[
          rec("1", "storage_total_bytes", "117694799872", "bytes"),
          rec("2", "storage_logical_target", "/data", null),
        ]}
      />
    );
    expect(screen.getByTestId("evidence-note")).toHaveTextContent(
      "Storage values describe the /data filesystem, not necessarily the phone's full advertised capacity."
    );

    rerender(<EvidenceTable evidence={[rec("3", "mem_total_bytes", "5909782528", "bytes")]} />);
    expect(screen.queryByTestId("evidence-note")).not.toBeInTheDocument();
  });

  it("keeps provenance columns (method, source type, time) untouched", () => {
    render(<EvidenceTable evidence={[rec("1", "storage_total_bytes", "117694799872", "bytes")]} />);
    const row = within(rowFor("Storage Total"));
    expect(row.getByText("adb shell test")).toBeInTheDocument();
    expect(row.getByText("(ADB_SHELL)")).toBeInTheDocument();
    expect(row.getByText("not modeled")).toBeInTheDocument();
  });

  it("still shows backend errors alongside the value", () => {
    render(
      <EvidenceTable evidence={[rec("1", "mem_total_bytes", "5909782528", "bytes", { error: "partial read" })]} />
    );
    expect(within(rowFor("Mem Total")).getByText(/partial read/)).toBeInTheDocument();
  });
});
