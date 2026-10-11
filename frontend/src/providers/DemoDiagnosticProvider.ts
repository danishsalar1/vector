import type {
  CheckHealthOptions,
  CheckPreflightOptions,
  DiagnosticProvider,
  DiscoverAndroidOptions,
  GetBatteryOptions,
  ProviderMode,
  ProviderRequestOptions,
} from "./DiagnosticProvider";
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
import type { SafeFetchResult } from "../lib/api/request";
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

  /**
   * Demo never contacts hardware and never simulates a device list.
   */
  async listDevices(
    options?: ProviderRequestOptions
  ): Promise<DeviceDiscoveryResult> {
    throwIfAborted(options);
    return { state: "COMPLETE", data: { devices: [], count: 0 }, errorMessage: null };
  }

  async planScan(
    _request: unknown,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanPlan>> {
    return demoScanUnavailable(options);
  }

  async startScan(
    _request: unknown,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanStartResponse>> {
    return demoScanUnavailable(options);
  }

  async getScanSummary(
    _scanId: string,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanSummary>> {
    return demoScanUnavailable(options);
  }

  async getScanEvents(
    _scanId: string,
    options?: ProviderRequestOptions
  ): Promise<SafeFetchResult<ScanEventsResponse>> {
    return demoScanUnavailable(options);
  }
}

function throwIfAborted(options?: ProviderRequestOptions): void {
  if (options?.signal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError");
  }
}

function demoScanUnavailable<T>(
  options?: ProviderRequestOptions
): SafeFetchResult<T> {
  throwIfAborted(options);
  return {
    ok: false,
    error: {
      kind: "CONFIGURATION",
      message:
        "[DEMO] Scans are not available in Demo mode. No scan data is simulated. Switch to Live mode with a connected device.",
    },
  };
}
