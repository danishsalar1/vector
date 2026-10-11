import type {
  AndroidDiscoveryResult,
  BatteryTelemetryResult,
  HealthCheckResult,
  PreflightResult,
  ScanEventsResponse,
  ScanPlan,
  ScanStartResponse,
  ScanSummary,
} from "../lib/api/types";
import type { DeviceDiscoveryResult } from "../lib/api/devices";
import type { ScanApiRequest } from "../lib/api/scans";
import type { SafeFetchResult } from "../lib/api/request";

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

export interface ProviderRequestOptions {
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

  // Phase 8F: platform-neutral device listing and Quick Scan workflow.
  // Unlike discoverAndroidDevices, listDevices preserves authorization_state.
  listDevices(options?: ProviderRequestOptions): Promise<DeviceDiscoveryResult>;
  planScan(
    request: ScanApiRequest,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanPlan>>;
  startScan(
    request: ScanApiRequest,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanStartResponse>>;
  getScanSummary(
    scanId: string,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanSummary>>;
  getScanEvents(
    scanId: string,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanEventsResponse>>;
}
