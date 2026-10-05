/**
 * Shape of the response returned by GET /api/v1/health.
 * Matches FastAPI HealthResponse model in local-agent/src/vector_agent/api/health.py.
 */
export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
  mode: string;
}

/**
 * Explicit connection state for the health handshake and provider availability.
 */
export type ConnectionState = "CHECKING" | "ONLINE" | "OFFLINE" | "DEMO_READY";

/**
 * Normalized category of client/network error.
 */
export type ApiErrorKind =
  | "NETWORK"
  | "TIMEOUT"
  | "HTTP"
  | "INVALID_RESPONSE"
  | "ABORTED"
  | "CONFIGURATION"
  | "UNKNOWN";

/**
 * Structured client error carrying category, user message, and optional HTTP status code.
 */
export interface ApiError {
  kind: ApiErrorKind;
  message: string;
  statusCode?: number;
}

export interface HealthCheckResult {
  state: ConnectionState;
  data: HealthResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

/**
 * Type guard to validate whether an unknown object adheres to HealthResponse.
 */
export function isHealthResponse(data: unknown): data is HealthResponse {
  if (typeof data !== "object" || data === null) {
    return false;
  }
  const candidate = data as Record<string, unknown>;
  return (
    typeof candidate.status === "string" &&
    typeof candidate.timestamp === "string" &&
    typeof candidate.version === "string" &&
    typeof candidate.mode === "string"
  );
}

/**
 * Status of an individual preflight environment check.
 * Aligned with backend PreflightStatus enum in local-agent/src/vector_agent/models/preflight.py.
 */
export type PreflightCheckStatus =
  | "PASS"
  | "WARN"
  | "FAIL"
  | "NOT_INSTALLED"
  | "NOT_APPLICABLE";

/**
 * Overall environment readiness state.
 * Aligned with backend PreflightOverall enum.
 */
export type PreflightOverallStatus = "READY" | "PARTIAL" | "BLOCKED";

/**
 * Individual check result returned by the backend preflight endpoint.
 */
export interface PreflightCheckItem {
  id: string;
  name: string;
  category: string;
  status: PreflightCheckStatus;
  message: string;
  required: boolean;
  details: string | null;
  detail?: string | null;
}

/**
 * Preflight response payload from GET /api/v1/system/preflight.
 */
export interface PreflightResponse {
  overall: PreflightOverallStatus;
  overall_status: PreflightOverallStatus;
  checks: readonly PreflightCheckItem[];
  items?: readonly PreflightCheckItem[];
  timestamp: string;
}

/**
 * Explicit state of the preflight inspection cycle.
 */
export type PreflightState = "IDLE" | "CHECKING" | "COMPLETE" | "ERROR";

/**
 * Result structure returned by provider.getPreflight().
 */
export interface PreflightResult {
  state: PreflightState;
  data: PreflightResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

/**
 * Type guard to validate whether an unknown object adheres to PreflightResponse.
 */
export function isPreflightResponse(data: unknown): data is PreflightResponse {
  if (typeof data !== "object" || data === null) {
    return false;
  }
  const candidate = data as Record<string, unknown>;
  const overall = candidate.overall ?? candidate.overall_status;
  const checks = candidate.checks ?? candidate.items;

  if (
    typeof overall !== "string" ||
    !["READY", "PARTIAL", "BLOCKED"].includes(overall) ||
    !Array.isArray(checks) ||
    typeof candidate.timestamp !== "string"
  ) {
    return false;
  }

  return checks.every((check) => {
    if (typeof check !== "object" || check === null) {
      return false;
    }
    const c = check as Record<string, unknown>;
    return (
      typeof c.id === "string" &&
      typeof c.name === "string" &&
      typeof c.category === "string" &&
      typeof c.status === "string" &&
      typeof c.message === "string" &&
      typeof c.required === "boolean"
    );
  });
}

// ============================================================
// Android device types (Phase 2A)
// ============================================================

/**
 * ADB connection state returned by the discovery endpoint.
 */
export type AndroidConnectionState =
  | "DEVICE"
  | "UNAUTHORIZED"
  | "OFFLINE"
  | "NO_DEVICE"
  | "MULTIPLE_DEVICES"
  | "ERROR";

/**
 * A single Android device entry from the discovery response.
 */
export interface AndroidDevice {
  device_id: string;
  connection_state: AndroidConnectionState;
  adb_available?: boolean | null;
  message?: string;

  // Identity — only present when state is DEVICE
  manufacturer: string | null;
  model: string | null;
  device_codename: string | null;
  android_version: string | null;
  sdk_level: number | null;
  brand: string | null;

  discovered_at?: string | null;
}

/**
 * Response from GET /api/v1/devices/android or adapted from platform-neutral API.
 */
export interface AndroidDeviceListResponse {
  devices: AndroidDevice[];
  count: number;
  state: AndroidConnectionState;
  message: string;
  adb_available?: boolean | null;
}

/**
 * Battery telemetry diagnostic status.
 * PASS = telemetry collected successfully. NOT a battery health assessment.
 */
export type BatteryDiagnosticStatus = "PASS" | "INCONCLUSIVE" | "ERROR";

/**
 * Response from GET /api/v1/devices/android/{device_id}/battery.
 */
export interface BatteryTelemetryResponse {
  device_id: string;
  status: BatteryDiagnosticStatus;
  status_note: string; // Explicitly disclaims battery health
  confidence: number;

  level_pct: number | null;
  charging_state: string | null;
  health_state: string | null;
  plugged: string | null;
  voltage_v: number | null;
  temperature_c: number | null;
  technology: string | null;
  present: boolean | null;

  evidence_source: string;
  collection_method: string;
  collected_at: string;

  error: string | null;
}

/**
 * State of the Android device discovery cycle.
 */
export type AndroidDiscoveryState = "IDLE" | "CHECKING" | "COMPLETE" | "ERROR";

/**
 * Result returned by provider.discoverAndroidDevices().
 */
export interface AndroidDiscoveryResult {
  state: AndroidDiscoveryState;
  data: AndroidDeviceListResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

/**
 * State of the battery telemetry collection cycle.
 */
export type BatteryState = "IDLE" | "RUNNING" | "COMPLETE" | "ERROR";

/**
 * Result returned by provider.getAndroidBatteryTelemetry().
 */
export interface BatteryTelemetryResult {
  state: BatteryState;
  data: BatteryTelemetryResponse | null;
  errorMessage: string | null;
  error?: ApiError | null;
}

/**
 * Type guard for AndroidDeviceListResponse.
 */
export function isAndroidDeviceListResponse(
  data: unknown
): data is AndroidDeviceListResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.state === "string" &&
    typeof d.adb_available === "boolean" &&
    typeof d.message === "string" &&
    Array.isArray(d.devices)
  );
}

/**
 * Type guard for BatteryTelemetryResponse.
 */
export function isBatteryTelemetryResponse(
  data: unknown
): data is BatteryTelemetryResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.device_id === "string" &&
    typeof d.status === "string" &&
    typeof d.status_note === "string" &&
    typeof d.confidence === "number" &&
    typeof d.evidence_source === "string"
  );
}
