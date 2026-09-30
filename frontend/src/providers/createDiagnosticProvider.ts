import type { DiagnosticProvider, ProviderMode } from "./DiagnosticProvider";
import { LiveDiagnosticProvider } from "./LiveDiagnosticProvider";
import { DemoDiagnosticProvider } from "./DemoDiagnosticProvider";

export interface ProviderConfig {
  mode?: string;
}

/**
 * Validates and resolves the provider mode string.
 * Defaults to "live" when unconfigured or empty.
 * Throws a clear error on unrecognized modes to prevent accidental fallback.
 */
export function resolveProviderMode(rawMode?: string): ProviderMode {
  if (rawMode === undefined || rawMode === null || rawMode.trim() === "") {
    return "live";
  }

  const normalized = rawMode.trim().toLowerCase();
  if (normalized === "live") {
    return "live";
  }
  if (normalized === "demo") {
    return "demo";
  }

  throw new Error(
    `Invalid VECTOR provider mode: "${rawMode}". Expected "live" or "demo".`
  );
}

/**
 * Factory to create the designated DiagnosticProvider instance.
 * Reads mode from config argument or Vite environment variable VITE_VECTOR_MODE.
 */
export function createDiagnosticProvider(
  config?: ProviderConfig
): DiagnosticProvider {
  const rawMode =
    config?.mode ??
    (typeof import.meta !== "undefined" && import.meta.env
      ? import.meta.env.VITE_VECTOR_MODE
      : undefined);

  const mode = resolveProviderMode(rawMode);

  switch (mode) {
    case "live":
      return new LiveDiagnosticProvider();
    case "demo":
      return new DemoDiagnosticProvider();
  }
}
