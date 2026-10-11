/**
 * Presentation model for a diagnostic card: which evidence to surface as headline metrics.
 *
 * Everything shown is taken from the diagnostic's own evidence records and formatted with
 * evidenceFormat (display plus raw). Nothing is invented: a metric appears only when its
 * evidence exists and is readable. A diagnostic with no known presenter still renders as a
 * generic card (name, status, summary, evidence).
 */

import type { CapabilityEvidenceRecord, DiagnosticResult } from "../api/types";
import { formatEvidenceValue } from "./evidenceFormat";

export interface CardMetric {
  key: string;
  label: string;
  value: string;
  hint?: string;
  /** Original backend value and unit when the displayed value was converted or rounded. */
  raw?: string;
  /** Visually de-emphasised: a qualitative value reported by the OS, not a VECTOR measurement. */
  quiet?: boolean;
}

export interface CardChip {
  label: string;
  value: string;
}

export interface CardMeter {
  label: string;
  /** 0..1, derived from real evidence values. */
  fraction: number;
  caption: string;
}

export interface CardModel {
  metrics: CardMetric[];
  chips: CardChip[];
  meter: CardMeter | null;
  note: string | null;
}

const DECIMAL = /^-?\d+(\.\d+)?$/;

function index(evidence: readonly CapabilityEvidenceRecord[]): Map<string, CapabilityEvidenceRecord> {
  const byField = new Map<string, CapabilityEvidenceRecord>();
  for (const record of evidence) {
    const field = record.metadata?.field;
    if (typeof field === "string" && field && !byField.has(field)) byField.set(field, record);
  }
  return byField;
}

function numeric(record: CapabilityEvidenceRecord | undefined): number | null {
  if (!record || record.redacted || typeof record.raw_value !== "string") return null;
  const text = record.raw_value.trim();
  return DECIMAL.test(text) ? Number(text) : null;
}

function metric(
  key: string,
  label: string,
  record: CapabilityEvidenceRecord | undefined,
  hint?: string
): CardMetric | null {
  if (!record) return null;
  const out = formatEvidenceValue(record);
  if (out.display === "—") return null;
  // A bare count reads better without its unit word ("6", not "6 count").
  const value = record.unit === "count" && typeof record.raw_value === "string" ? record.raw_value : out.display;
  return { key, label, value, hint, raw: out.showRaw ? out.raw : undefined };
}

function quiet(m: CardMetric | null): CardMetric | null {
  return m && { ...m, quiet: true };
}

function compact(items: (CardMetric | null)[]): CardMetric[] {
  return items.filter((m): m is CardMetric => m !== null);
}

const EMPTY: CardModel = { metrics: [], chips: [], meter: null, note: null };

function battery(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  return {
    ...EMPTY,
    metrics: compact([
      metric("level", "Charge level", f.get("battery_level")),
      metric("voltage", "Voltage", f.get("battery_voltage")),
      metric("temperature", "Temperature", f.get("battery_temperature")),
      metric("charging", "Charging state", f.get("battery_charging_status")),
      quiet(
        metric(
          "android-state",
          "Android battery state",
          f.get("battery_health_classification"),
          "As reported by Android. VECTOR has not measured capacity or wear."
        )
      ),
    ]),
  };
}

function memory(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  const total = numeric(f.get("mem_total_bytes"));
  const available = numeric(f.get("mem_available_bytes"));
  const meter =
    total !== null && available !== null && total > 0 && available >= 0 && available <= total
      ? {
          label: "Estimated available RAM",
          fraction: available / total,
          caption: `${Math.round((available / total) * 100)}% of System RAM`,
        }
      : null;
  return {
    ...EMPTY,
    metrics: compact([
      metric("system-ram", "System RAM", f.get("mem_total_bytes"), "MemTotal from /proc/meminfo"),
      metric(
        "available-ram",
        "Estimated available RAM",
        f.get("mem_available_bytes"),
        "MemAvailable from /proc/meminfo"
      ),
    ]),
    meter,
    note: "Read from /proc/meminfo at scan time. Android’s Recent Apps screen uses a different estimate, so the two can disagree.",
  };
}

function storage(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  const reported = numeric(f.get("storage_utilization_percent"));
  const used = numeric(f.get("storage_used_bytes"));
  const total = numeric(f.get("storage_total_bytes"));
  const percent =
    reported !== null && reported >= 0 && reported <= 100
      ? reported
      : used !== null && total !== null && total > 0 && used <= total
        ? (used / total) * 100
        : null;
  const target = f.get("storage_logical_target")?.raw_value;
  return {
    ...EMPTY,
    metrics: compact([
      metric("capacity", "Data filesystem capacity", f.get("storage_total_bytes")),
      metric("used", "Data filesystem used", f.get("storage_used_bytes")),
      metric("available", "Data filesystem available", f.get("storage_available_bytes")),
    ]),
    meter:
      percent !== null
        ? {
            label: "Data filesystem used",
            fraction: percent / 100,
            caption: `${Number(percent.toFixed(1))}% used`,
          }
        : null,
    note: `These figures describe the ${typeof target === "string" && target ? target : "data"} filesystem, not the phone’s total physical capacity. Advertised storage and Settings → Storage usage can differ.`,
  };
}

function thermal(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  const sensors = [...f.entries()].filter(
    ([field, record]) => field.startsWith("sensor_") && record.unit === "celsius"
  );
  const chips: CardChip[] = sensors.map(([field, record]) => ({
    label: field.slice("sensor_".length).replace(/_/g, " "),
    value: formatEvidenceValue(record).display,
  }));
  const readings = sensors
    .map(([field, record]) => ({ field, record, n: numeric(record) }))
    .filter((s): s is { field: string; record: CapabilityEvidenceRecord; n: number } => s.n !== null);
  const hottest = readings.length ? readings.reduce((a, b) => (b.n > a.n ? b : a)) : null;
  return {
    ...EMPTY,
    metrics: compact([
      metric("sensors", "Sensors reported", f.get("thermal_sensor_count")),
      hottest
        ? metric(
            "highest",
            "Highest reading",
            hottest.record,
            `${hottest.field.slice("sensor_".length).replace(/_/g, " ")} sensor`
          )
        : null,
    ]),
    chips,
  };
}

function display(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  const resolution = f.get("display_physical_resolution");
  const dims =
    resolution && typeof resolution.raw_value === "string"
      ? /^(\d+)x(\d+)$/i.exec(resolution.raw_value.trim())
      : null;
  return {
    ...EMPTY,
    metrics: compact([
      dims && resolution
        ? { key: "resolution", label: "Resolution", value: `${dims[1]} × ${dims[2]}`, raw: resolution.raw_value ?? undefined }
        : metric("resolution", "Resolution", resolution),
      metric("density", "Density", f.get("display_physical_density_dpi")),
    ]),
  };
}

function camera(f: Map<string, CapabilityEvidenceRecord>): CardModel {
  return {
    ...EMPTY,
    metrics: compact([metric("count", "Camera devices reported", f.get("camera_device_count"))]),
  };
}

const PRESENTERS: Record<string, (f: Map<string, CapabilityEvidenceRecord>) => CardModel> = {
  battery_telemetry: battery,
  memory_telemetry: memory,
  storage_telemetry: storage,
  thermal_telemetry: thermal,
  display_metrics: display,
  camera_inventory: camera,
};

/** Metrics for a finished diagnostic. Unknown diagnostics and missing results yield an empty model. */
export function buildCardModel(result: DiagnosticResult | null): CardModel {
  if (!result || result.evidence.length === 0) return EMPTY;
  const present = PRESENTERS[result.diagnostic_id];
  return present ? present(index(result.evidence)) : EMPTY;
}
