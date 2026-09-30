import type { HealthCheckResult } from "../lib/api/types";

export type ProviderMode = "live" | "demo";

export interface CheckHealthOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Common abstraction boundary for VECTOR diagnostic data sources.
 * In Live mode, delegates to the local FastAPI hardware agent.
 * In Demo mode, provides deterministic demonstration datasets.
 */
export interface DiagnosticProvider {
  readonly mode: ProviderMode;
  checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult>;
}
