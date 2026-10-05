import { safeFetchJson, type SafeFetchOptions } from "./request";
import type { ApiError } from "./types";

export interface DeviceIdentity {
  platform: string;
  manufacturer: string | null;
  model: string | null;
  marketing_name: string | null;
  android_version: string | null;
  android_sdk_level: number | null;
  build_fingerprint: string | null;
  brand: string | null;
  device_codename: string | null;
  ios_version: string | null;
  product_type: string | null;
  serial: string | null;
  udid: string | null;
  discovered_at: string;
}

export interface ConnectedDevice {
  device_id: string;
  platform: string;
  connection_state: string;
  identity: DeviceIdentity | null;
}

export interface DeviceListResponse {
  devices: ConnectedDevice[];
  count: number;
}

export type DeviceDiscoveryState = "IDLE" | "CHECKING" | "COMPLETE" | "ERROR";

export interface DeviceDiscoveryResult {
  state: DeviceDiscoveryState;
  data: DeviceListResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

export function isDeviceListResponse(data: unknown): data is DeviceListResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return typeof d.count === "number" && Array.isArray(d.devices);
}

const DISCOVERY_TIMEOUT_MS = 15_000;

export async function fetchDevices(
  options: SafeFetchOptions = {}
): Promise<DeviceDiscoveryResult> {
  const result = await safeFetchJson<DeviceListResponse>(
    "/api/v1/devices",
    isDeviceListResponse,
    {
      timeoutMs: DISCOVERY_TIMEOUT_MS,
      fallbackErrorMessage: "Cannot reach VECTOR Local Agent.",
      timeoutErrorMessage: "Device discovery timed out.",
      ...options,
    }
  );

  if (result.ok) {
    return { state: "COMPLETE", data: result.data, errorMessage: null };
  }

  return {
    state: "ERROR",
    data: null,
    errorMessage: result.error.message,
    error: result.error,
  };
}
