/**
 * Presentation-only formatting for evidence values.
 *
 * Nothing here changes the evidence: the backend record is never mutated and the
 * original value and unit are always returned alongside the formatted text.
 * A value is converted only when its unit is explicitly recognised AND the raw value
 * is a clean number that is plausible for that unit. Anything else is shown as received.
 */

import type { CapabilityEvidenceRecord } from "../api/types";

export interface FormattedEvidence {
  /** Text for the Value column. */
  display: string;
  /** Exactly what the backend sent: raw value plus its original unit. */
  raw: string;
  /** True when `display` carries a different number or unit than `raw`. */
  showRaw: boolean;
  /** True when a recognised unit was formatted (not just passed through). */
  formatted: boolean;
}

const DECIMAL_NUMBER = /^-?\d+(\.\d+)?$/;
const BYTES_PER_GB = 1_000_000_000;
const ABSOLUTE_ZERO_C = -273.15;

/** The number to format, or null. Never falls back to normalized_value when raw_value exists. */
function sourceNumber(record: CapabilityEvidenceRecord): number | null {
  const raw = record.raw_value;
  if (typeof raw === "string") {
    const text = raw.trim();
    return DECIMAL_NUMBER.test(text) ? Number(text) : null;
  }
  if (typeof record.normalized_value === "number" && Number.isFinite(record.normalized_value)) {
    return record.normalized_value;
  }
  return null;
}

/** The unmodified evidence as text, e.g. "341 tenths_celsius", or "—" when absent. */
export function rawEvidenceText(record: CapabilityEvidenceRecord): string {
  const value =
    record.raw_value ??
    (typeof record.normalized_value === "number" && Number.isFinite(record.normalized_value)
      ? String(record.normalized_value)
      : null);
  if (value === null) return "—";
  return record.unit ? `${value} ${record.unit}` : value;
}

function celsius(value: number): { text: string; changed: boolean } | null {
  if (!Number.isFinite(value) || value < ABSOLUTE_ZERO_C) return null;
  const rounded = Number(value.toFixed(1));
  return { text: `${value.toFixed(1)}°C`, changed: rounded !== value };
}

/** Returns formatted text for a recognised, valid measurement; null means "leave as received". */
function convert(
  record: CapabilityEvidenceRecord
): { text: string; changed: boolean } | null {
  const n = sourceNumber(record);
  if (n === null) return null;

  switch (record.unit) {
    case "bytes": {
      if (!Number.isSafeInteger(n) || n < 0) return null;
      const text = (n / BYTES_PER_GB).toFixed(2);
      // Never present a non-zero size as 0.00 GB.
      if (n !== 0 && Number(text) === 0) return null;
      return { text: `${text} GB`, changed: true };
    }
    case "tenths_celsius": {
      // Tenths are whole numbers by definition; a fraction means the unit is not what it claims.
      if (!Number.isInteger(n)) return null;
      const c = celsius(n / 10);
      return c && { text: c.text, changed: true };
    }
    case "celsius":
      return celsius(n);
    case "percent": {
      if (n < 0 || n > 100) return null;
      const rounded = Number(n.toFixed(1));
      return { text: `${rounded}%`, changed: rounded !== n };
    }
    case "mV":
      return n >= 0 ? { text: `${(n / 1000).toFixed(2)} V`, changed: true } : null;
    default:
      return null;
  }
}

export function formatEvidenceValue(record: CapabilityEvidenceRecord): FormattedEvidence {
  if (record.redacted) {
    return { display: "Redacted", raw: "Redacted", showRaw: false, formatted: false };
  }
  const raw = rawEvidenceText(record);
  const converted = convert(record);
  if (!converted) {
    return { display: raw, raw, showRaw: false, formatted: false };
  }
  return { display: converted.text, raw, showRaw: converted.changed, formatted: true };
}

/** Drops a trailing unit word from a label once the value carries its own unit ("Total Bytes" -> "Total"). */
export function tidyEvidenceLabel(label: string, record: CapabilityEvidenceRecord, formatted: boolean): string {
  if (!formatted) return label;
  const suffix = record.unit === "bytes" ? /\s+Bytes$/i : record.unit === "percent" ? /\s+Percent$/i : null;
  const tidy = suffix ? label.replace(suffix, "") : label;
  return tidy || label;
}

/** Context notes that stop a correct number from being misread. Driven only by the evidence itself. */
export function evidenceNotes(evidence: readonly CapabilityEvidenceRecord[]): string[] {
  const notes: string[] = [];
  const target = evidence.find((e) => e.metadata?.field === "storage_logical_target");
  if (target && typeof target.raw_value === "string" && target.raw_value) {
    notes.push(
      `Storage values describe the ${target.raw_value} filesystem, not necessarily the phone's full advertised capacity.`
    );
  }
  return notes;
}
