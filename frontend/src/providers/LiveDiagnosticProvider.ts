import type {
  CheckHealthOptions,
  CheckPreflightOptions,
  DiagnosticProvider,
  DiscoverAndroidOptions,
  GetBatteryOptions,
  ProviderMode,
} from "./DiagnosticProvider";
import type {
  AndroidDiscoveryResult,
  BatteryTelemetryResult,
  HealthCheckResult,
  PreflightResult,
} from "../lib/api/types";
import { checkHealth } from "../lib/api/health";
import { fetchPreflight } from "../lib/api/preflight";
import {
  fetchAndroidDevices,
  fetchAndroidBatteryTelemetry,
} from "../lib/api/android";

/**
 * Live hardware diagnostic provider.
 * Communicates with the local VECTOR FastAPI agent running on localhost:8742 via the /api proxy.
 */
export class LiveDiagnosticProvider implements DiagnosticProvider {
  readonly mode: ProviderMode = "live";

  async checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult> {
    return checkHealth(options);
  }

  async getPreflight(options?: CheckPreflightOptions): Promise<PreflightResult> {
    return fetchPreflight(options);
  }

  async discoverAndroidDevices(
    options?: DiscoverAndroidOptions
  ): Promise<AndroidDiscoveryResult> {
    return fetchAndroidDevices(options);
  }

  async getAndroidBatteryTelemetry(
    deviceId: string,
    options?: GetBatteryOptions
  ): Promise<BatteryTelemetryResult> {
    return fetchAndroidBatteryTelemetry(deviceId, options);
  }
}
