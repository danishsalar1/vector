import { safeFetchJson, type SafeFetchOptions } from "./request";
import type {
  ApiError,
  DeviceAuthorizationState,
  DevicePairResponse,
} from "./types";
import { isDeviceAuthorizationState, isDevicePairResponse } from "./types";

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
  authorization_state?: DeviceAuthorizationState;
  identity: DeviceIdentity | null;
}

export function isConnectedDevice(data: unknown): data is ConnectedDevice {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  if (
    typeof d.device_id !== "string" ||
    typeof d.platform !== "string" ||
    typeof d.connection_state !== "string"
  ) {
    return false;
  }
  if (
    d.authorization_state !== undefined &&
    !isDeviceAuthorizationState(d.authorization_state)
  ) {
    return false;
  }
  return true;
}

export interface DeviceListResponse {
  devices: ConnectedDevice[];
  count: number;
  provider_statuses?: Record<string, string> | null;
}

export type DeviceDiscoveryState = "IDLE" | "CHECKING" | "COMPLETE" | "ERROR";

export interface DeviceDiscoveryResult {
  state: DeviceDiscoveryState;
  data: DeviceListResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

export interface PairDeviceResult {
  data: DevicePairResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

export function isDeviceListResponse(data: unknown): data is DeviceListResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  if (
    typeof d.count !== "number" ||
    !Array.isArray(d.devices) ||
    !d.devices.every(isConnectedDevice)
  ) {
    return false;
  }
  if (
    d.provider_statuses !== undefined &&
    d.provider_statuses !== null &&
    (typeof d.provider_statuses !== "object" || Array.isArray(d.provider_statuses))
  ) {
    return false;
  }
  return true;
}

const DISCOVERY_TIMEOUT_MS = 15_000;
const PAIRING_TIMEOUT_MS = 20_000;

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

export async function pairDevice(
  deviceId: string,
  options: SafeFetchOptions = {}
): Promise<PairDeviceResult> {
  const result = await safeFetchJson<DevicePairResponse>(
    `/api/v1/devices/${encodeURIComponent(deviceId)}/pair`,
    isDevicePairResponse,
    {
      method: "POST",
      timeoutMs: PAIRING_TIMEOUT_MS,
      fallbackErrorMessage: "Failed to pair device.",
      timeoutErrorMessage: "Pairing operation timed out.",
      ...options,
    }
  );

  if (result.ok) {
    return { data: result.data, errorMessage: null };
  }

  return {
    data: null,
    errorMessage: result.error.message,
    error: result.error,
  };
}
