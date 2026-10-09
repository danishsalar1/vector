import type {
  CheckHealthOptions,
  CheckPreflightOptions,
  DiagnosticProvider,
  DiscoverAndroidOptions,
  GetBatteryOptions,
  ProviderMode,
} from "./DiagnosticProvider";
import type {
  AndroidConnectionState,
  AndroidDevice,
  AndroidDiscoveryResult,
  BatteryTelemetryResult,
  HealthCheckResult,
  PreflightResult,
} from "../lib/api/types";
import { checkHealth } from "../lib/api/health";
import { fetchPreflight } from "../lib/api/preflight";
import { fetchAndroidBatteryTelemetry } from "../lib/api/android";
import { fetchDevices } from "../lib/api/devices";

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
    // In Live mode, device discovery uses the canonical platform-neutral endpoint
    const result = await fetchDevices(options);

    if (result.state === "ERROR" || !result.data) {
      return {
        state: "ERROR",
        data: null,
        errorMessage: result.errorMessage,
        error: result.error,
      };
    }

    // Filter by explicit platform field — never infer from device_id prefix
    const allAndroid = result.data.devices.filter(
      (d) => d.platform.toUpperCase() === "ANDROID"
    );
    const activeAndroid = allAndroid.filter(
      (d) => d.connection_state !== "OFFLINE"
    );

    const targetDevices = activeAndroid.length > 0 ? activeAndroid : allAndroid;

    const mappedDevices: AndroidDevice[] = targetDevices.map((d) => {
      const connState: AndroidConnectionState =
        d.connection_state === "CONNECTED"
          ? "DEVICE"
          : (d.connection_state as AndroidConnectionState);

      return {
        device_id: d.device_id,
        connection_state: connState,
        // The neutral endpoint does not inspect ADB availability; do not synthesize facts
        adb_available: null,
        message: "",
        manufacturer: d.identity?.manufacturer ?? null,
        model: d.identity?.model ?? null,
        device_codename: d.identity?.device_codename ?? null,
        android_version: d.identity?.android_version ?? null,
        sdk_level: d.identity?.android_sdk_level ?? null,
        brand: d.identity?.brand ?? null,
        // Truthful timestamp from identity; do not synthesize current time if identity is absent
        discovered_at: d.identity?.discovered_at ?? null,
      };
    });

    let overallState: AndroidConnectionState = "NO_DEVICE";
    if (activeAndroid.length === 1) {
      overallState = mappedDevices[0].connection_state;
    } else if (activeAndroid.length > 1) {
      overallState = "MULTIPLE_DEVICES";
    } else if (allAndroid.length > 0) {
      overallState = "OFFLINE";
    }

    return {
      state: "COMPLETE",
      data: {
        devices: mappedDevices,
        count: mappedDevices.length,
        state: overallState,
        message: "",
        adb_available: null,
      },
      errorMessage: null,
    };
  }

  async getAndroidBatteryTelemetry(
    deviceId: string,
    options?: GetBatteryOptions
  ): Promise<BatteryTelemetryResult> {
    return fetchAndroidBatteryTelemetry(deviceId, options);
  }
}
