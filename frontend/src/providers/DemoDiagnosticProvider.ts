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
import {
  DEMO_HEALTH_FIXTURE,
  DEMO_PREFLIGHT_FIXTURE,
} from "./demo/fixtures";

/**
 * Demo diagnostic provider for public web presentation.
 * Returns deterministic demonstration datasets without contacting any local hardware or service.
 */
export class DemoDiagnosticProvider implements DiagnosticProvider {
  readonly mode: ProviderMode = "demo";

  async checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult> {
    if (options?.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    return {
      state: "DEMO_READY",
      data: DEMO_HEALTH_FIXTURE,
      errorMessage: null,
    };
  }

  async getPreflight(
    options?: CheckPreflightOptions
  ): Promise<PreflightResult> {
    if (options?.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    return {
      state: "COMPLETE",
      data: DEMO_PREFLIGHT_FIXTURE,
      errorMessage: null,
    };
  }

  /**
   * Demo stub: returns a clearly synthetic NO_DEVICE state.
   * Demo mode never contacts real hardware.
   */
  async discoverAndroidDevices(
    options?: DiscoverAndroidOptions
  ): Promise<AndroidDiscoveryResult> {
    if (options?.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    return {
      state: "COMPLETE",
      data: {
        devices: [],
        count: 0,
        state: "NO_DEVICE",
        message:
          "[DEMO] Android device discovery is not available in Demo mode. Connect a real device in Live mode.",
        adb_available: false,
      },
      errorMessage: null,
    };
  }

  /**
   * Demo stub: returns a synthetic INCONCLUSIVE result.
   * Demo mode never executes real ADB commands.
   */
  async getAndroidBatteryTelemetry(
    _deviceId: string,
    options?: GetBatteryOptions
  ): Promise<BatteryTelemetryResult> {
    if (options?.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    return {
      state: "ERROR",
      data: null,
      errorMessage:
        "[DEMO] Battery telemetry is not available in Demo mode. Switch to Live mode with a connected device.",
    };
  }
}
