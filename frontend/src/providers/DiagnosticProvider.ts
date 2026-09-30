import type {
  AndroidDiscoveryResult,
  BatteryTelemetryResult,
  HealthCheckResult,
  PreflightResult,
} from "../lib/api/types";

export type ProviderMode = "live" | "demo";

export interface CheckHealthOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface CheckPreflightOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface DiscoverAndroidOptions {
  signal?: AbortSignal;
}

export interface GetBatteryOptions {
  signal?: AbortSignal;
}

/**
 * Common abstraction boundary for VECTOR diagnostic data sources.
 * In Live mode, delegates to the local FastAPI hardware agent.
 * In Demo mode, provides deterministic demonstration datasets.
 */
export interface DiagnosticProvider {
  readonly mode: ProviderMode;
  checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult>;
  getPreflight(options?: CheckPreflightOptions): Promise<PreflightResult>;

  // Phase 2A: Android device discovery and battery telemetry
  discoverAndroidDevices(
    options?: DiscoverAndroidOptions
  ): Promise<AndroidDiscoveryResult>;
  getAndroidBatteryTelemetry(
    deviceId: string,
    options?: GetBatteryOptions
  ): Promise<BatteryTelemetryResult>;
}
