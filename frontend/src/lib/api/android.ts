/**
 * API client for Android device discovery and battery telemetry.
 *
 * All functions use safeFetchJson<T> with type guards.
 * No raw ADB commands are accepted from the frontend.
 */

import { safeFetchJson } from "./request";
import type { SafeFetchOptions } from "./request";
import {
  isAndroidDeviceListResponse,
  isBatteryTelemetryResponse,
  type AndroidDeviceListResponse,
  type AndroidDiscoveryResult,
  type BatteryTelemetryResponse,
  type BatteryTelemetryResult,
} from "./types";

const ANDROID_DISCOVERY_TIMEOUT_MS = 12_000;
const BATTERY_TIMEOUT_MS = 20_000;

/**
 * Discover connected Android devices.
 * Corresponds to GET /api/v1/devices/android.
 */
export async function fetchAndroidDevices(
  options: SafeFetchOptions = {}
): Promise<AndroidDiscoveryResult> {
  const result = await safeFetchJson<AndroidDeviceListResponse>(
    "/api/v1/devices/android",
    isAndroidDeviceListResponse,
    {
      timeoutMs: ANDROID_DISCOVERY_TIMEOUT_MS,
      fallbackErrorMessage:
        "Cannot reach VECTOR Local Agent. Ensure the agent is running.",
      timeoutErrorMessage:
        "Android device discovery timed out. The ADB command may be slow to respond.",
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

/**
 * Collect battery telemetry from an authorized Android device.
 * Corresponds to GET /api/v1/devices/android/{deviceId}/battery.
 *
 * The deviceId is an opaque registry identifier — never an ADB serial.
 */
export async function fetchAndroidBatteryTelemetry(
  deviceId: string,
  options: SafeFetchOptions = {}
): Promise<BatteryTelemetryResult> {
  const result = await safeFetchJson<BatteryTelemetryResponse>(
    `/api/v1/devices/android/${encodeURIComponent(deviceId)}/battery`,
    isBatteryTelemetryResponse,
    {
      timeoutMs: BATTERY_TIMEOUT_MS,
      fallbackErrorMessage:
        "Cannot reach VECTOR Local Agent. Ensure the agent is running.",
      timeoutErrorMessage:
        "Battery telemetry collection timed out. The device may have disconnected.",
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
