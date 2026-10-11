import { describe, expect, it } from "vitest";
import type { CapabilityEvidenceRecord } from "../../api/types";
import {
  evidenceNotes,
  formatEvidenceValue,
  rawEvidenceText,
  tidyEvidenceLabel,
} from "../evidenceFormat";

function rec(
  raw_value: string | null,
  unit: string | null,
  extra: Partial<CapabilityEvidenceRecord> = {}
): CapabilityEvidenceRecord {
  return {
    evidence_id: "ev",
    diagnostic_id: "d",
    device_id: "android-testdev0001",
    source_type: "ADB_SHELL",
    source_name: "src",
    collection_method: "adb shell x",
    timestamp: "2026-10-11T00:00:00Z",
    raw_value,
    unit,
    ...extra,
  };
}

describe("bytes -> decimal GB (1 GB = 1,000,000,000 bytes, 2 decimals)", () => {
  // Values captured from the connected Redmi Note 8 Pro.
  it.each([
    ["117694799872", "117.69 GB"], // storage total (/data)
    ["64023437312", "64.02 GB"], // storage used
    ["53520367616", "53.52 GB"], // storage available
    ["5909782528", "5.91 GB"], // RAM total
    ["3390156800", "3.39 GB"], // RAM available
    ["255619072", "0.26 GB"], // RAM free
  ])("%s bytes -> %s", (raw, expected) => {
    const out = formatEvidenceValue(rec(raw, "bytes"));
    expect(out.display).toBe(expected);
    expect(out.formatted).toBe(true);
  });

  it("uses decimal GB, not binary GiB", () => {
    expect(formatEvidenceValue(rec("1000000000", "bytes")).display).toBe("1.00 GB");
    expect(formatEvidenceValue(rec("1073741824", "bytes")).display).toBe("1.07 GB");
  });

  it("preserves the raw value and original unit and flags that it differs", () => {
    const out = formatEvidenceValue(rec("117694799872", "bytes"));
    expect(out.raw).toBe("117694799872 bytes");
    expect(out.showRaw).toBe(true);
  });

  it("handles zero", () => {
    expect(formatEvidenceValue(rec("0", "bytes")).display).toBe("0.00 GB");
  });

  it("never shows a non-zero size as 0.00 GB", () => {
    const out = formatEvidenceValue(rec("5000", "bytes"));
    expect(out.display).toBe("5000 bytes");
    expect(out.formatted).toBe(false);
  });

  it.each([
    ["negative", "-5"],
    ["fractional", "1.5"],
    ["non-numeric", "N/A"],
    ["empty", ""],
    ["thousands separators", "1,000,000"],
    ["exponent", "1e9"],
    ["beyond safe integer range", "99999999999999999999"],
  ])("does not convert malformed bytes (%s)", (_name, raw) => {
    const out = formatEvidenceValue(rec(raw, "bytes"));
    expect(out.formatted).toBe(false);
    expect(out.display).toBe(rawEvidenceText(rec(raw, "bytes")));
    expect(out.display).not.toMatch(/GB/);
  });
});

describe("temperature", () => {
  it("tenths_celsius 344 -> 34.4°C, raw preserved", () => {
    const out = formatEvidenceValue(rec("344", "tenths_celsius"));
    expect(out.display).toBe("34.4°C");
    expect(out.raw).toBe("344 tenths_celsius");
    expect(out.showRaw).toBe(true);
  });

  it("real battery reading 341 tenths_celsius -> 34.1°C", () => {
    expect(formatEvidenceValue(rec("341", "tenths_celsius")).display).toBe("34.1°C");
  });

  it("handles zero and sub-zero tenths", () => {
    expect(formatEvidenceValue(rec("0", "tenths_celsius")).display).toBe("0.0°C");
    expect(formatEvidenceValue(rec("-55", "tenths_celsius")).display).toBe("-5.5°C");
  });

  it("does not convert tenths_celsius that is not a whole number or is below absolute zero", () => {
    expect(formatEvidenceValue(rec("34.4", "tenths_celsius")).formatted).toBe(false);
    expect(formatEvidenceValue(rec("-3000", "tenths_celsius")).formatted).toBe(false);
    expect(formatEvidenceValue(rec("abc", "tenths_celsius")).display).toBe("abc tenths_celsius");
  });

  it("formats celsius to one decimal and shows raw only when digits were rounded", () => {
    const rounded = formatEvidenceValue(rec("36.13", "celsius"));
    expect(rounded.display).toBe("36.1°C");
    expect(rounded.showRaw).toBe(true);
    expect(rounded.raw).toBe("36.13 celsius");

    const exact = formatEvidenceValue(rec("34.6", "celsius"));
    expect(exact.display).toBe("34.6°C");
    expect(exact.showRaw).toBe(false);
  });

  it("does not convert implausible celsius", () => {
    expect(formatEvidenceValue(rec("-300", "celsius")).formatted).toBe(false);
  });
});

describe("percent and voltage", () => {
  it("formats percent consistently without altering the number", () => {
    expect(formatEvidenceValue(rec("100", "percent")).display).toBe("100%");
    expect(formatEvidenceValue(rec("55.0", "percent")).display).toBe("55%");
    expect(formatEvidenceValue(rec("55.5", "percent")).display).toBe("55.5%");
    expect(formatEvidenceValue(rec("0", "percent")).display).toBe("0%");
    expect(formatEvidenceValue(rec("55.0", "percent")).showRaw).toBe(false);
  });

  it("flags raw when percent had to be rounded", () => {
    const out = formatEvidenceValue(rec("12.34", "percent"));
    expect(out.display).toBe("12.3%");
    expect(out.showRaw).toBe(true);
  });

  it("does not convert out-of-range or malformed percent", () => {
    expect(formatEvidenceValue(rec("140", "percent")).display).toBe("140 percent");
    expect(formatEvidenceValue(rec("-1", "percent")).display).toBe("-1 percent");
    expect(formatEvidenceValue(rec("high", "percent")).display).toBe("high percent");
  });

  it("mV -> V with two decimals, raw preserved", () => {
    const out = formatEvidenceValue(rec("4282", "mV"));
    expect(out.display).toBe("4.28 V");
    expect(out.raw).toBe("4282 mV");
    expect(out.showRaw).toBe(true);
    expect(formatEvidenceValue(rec("0", "mV")).display).toBe("0.00 V");
    expect(formatEvidenceValue(rec("-4", "mV")).formatted).toBe(false);
  });
});

describe("unknown, missing and unrecognised data is never guessed", () => {
  it.each([
    ["unknown unit", rec("12", "furlongs"), "12 furlongs"],
    ["case variant of a known unit", rec("5909782528", "Bytes"), "5909782528 Bytes"],
    ["no unit", rec("Good", null), "Good"],
    ["count unit passes through", rec("6", "count"), "6 count"],
    ["dpi unit passes through", rec("440", "dpi"), "440 dpi"],
    ["non-numeric value with a recognised unit", rec("Full", "percent"), "Full percent"],
  ])("%s is shown exactly as received", (_n, record, expected) => {
    const out = formatEvidenceValue(record);
    expect(out.display).toBe(expected);
    expect(out.formatted).toBe(false);
    expect(out.showRaw).toBe(false);
  });

  it("falls back to normalized_value only when raw_value is absent", () => {
    const out = formatEvidenceValue(rec(null, "bytes", { normalized_value: 5909782528 }));
    expect(out.display).toBe("5.91 GB");
    expect(out.raw).toBe("5909782528 bytes");
  });

  it("does not override a non-numeric raw_value with normalized_value", () => {
    const out = formatEvidenceValue(rec("N/A", "bytes", { normalized_value: 5909782528 }));
    expect(out.formatted).toBe(false);
    expect(out.display).toBe("N/A bytes");
  });

  it("shows an em dash when there is no value at all", () => {
    expect(formatEvidenceValue(rec(null, "bytes")).display).toBe("—");
    expect(formatEvidenceValue(rec(null, null, { normalized_value: null })).display).toBe("—");
    expect(formatEvidenceValue(rec(null, "bytes", { normalized_value: Number.NaN })).display).toBe(
      "—"
    );
  });

  it("never reveals a redacted value", () => {
    const out = formatEvidenceValue(rec("117694799872", "bytes", { redacted: true }));
    expect(out.display).toBe("Redacted");
    expect(out.raw).not.toMatch(/117694799872/);
  });

  it("does not mutate the evidence record", () => {
    const record = rec("117694799872", "bytes", { normalized_value: 117694799872 });
    const snapshot = JSON.stringify(record);
    formatEvidenceValue(record);
    expect(JSON.stringify(record)).toBe(snapshot);
  });
});

describe("labels and notes", () => {
  it("drops a redundant trailing unit word only once the value is formatted", () => {
    const bytes = rec("1", "bytes");
    expect(tidyEvidenceLabel("Storage Total Bytes", bytes, true)).toBe("Storage Total");
    expect(tidyEvidenceLabel("Storage Total Bytes", bytes, false)).toBe("Storage Total Bytes");
    expect(tidyEvidenceLabel("Storage Utilization Percent", rec("55", "percent"), true)).toBe(
      "Storage Utilization"
    );
    expect(tidyEvidenceLabel("Battery Temperature", rec("341", "tenths_celsius"), true)).toBe(
      "Battery Temperature"
    );
  });

  it("adds the /data filesystem note only when the evidence reports a storage target", () => {
    const target = rec("/data", null, { metadata: { field: "storage_logical_target" } });
    expect(evidenceNotes([rec("1", "bytes"), target])).toEqual([
      "Storage values describe the /data filesystem, not necessarily the phone's full advertised capacity.",
    ]);
    expect(evidenceNotes([rec("5909782528", "bytes")])).toEqual([]);
  });
});
