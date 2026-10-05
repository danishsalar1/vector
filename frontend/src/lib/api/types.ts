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

// ============================================================
// Platform-neutral capability types (Phase 4)
// ============================================================

export type CapabilityStatus =
  | "PRESENT"
  | "ABSENT"
  | "UNKNOWN"
  | "RESTRICTED"
  | "NOT_REPORTED"
  | "UNSUPPORTED";

export type VerificationLevel =
  | "RUNTIME_DETECTION"
  | "FUNCTIONAL_VERIFICATION"
  | "REFERENCE_COMPARISON";

export interface CapabilityEvidenceRecord {
  evidence_id: string;
  diagnostic_id: string;
  device_id: string;
  source_type: string;
  source_name: string;
  collection_method: string;
  timestamp: string;
  raw_value?: string | null;
  normalized_value?: number | null;
  unit?: string | null;
  reliability: number;
  confidence: number;
  metadata?: Record<string, unknown>;
  redacted?: boolean;
  error?: string | null;
}

export interface CapabilityEntry {
  name: string;
  status: CapabilityStatus;
  verification_level: VerificationLevel | null;
  source?: string | null;
  note?: string | null;
  evidence?: readonly CapabilityEvidenceRecord[];
}

export interface DeviceCapabilityProfile {
  device_id: string;
  platform: "ANDROID" | "IOS" | "UNKNOWN";
  capabilities: Record<string, CapabilityEntry>;
  profiled_at: string;
  profile_complete: boolean;
  evidence?: readonly CapabilityEvidenceRecord[];
  metadata?: Record<string, unknown>;
}

export function isDeviceCapabilityProfile(
  data: unknown
): data is DeviceCapabilityProfile {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.device_id === "string" &&
    typeof d.platform === "string" &&
    typeof d.capabilities === "object" &&
    d.capabilities !== null &&
    typeof d.profiled_at === "string" &&
    typeof d.profile_complete === "boolean"
  );
}

// ============================================================
// Platform-neutral scan orchestration types (Phase 5)
// ============================================================

export type ScanMode =
  | "FULL_VERIFICATION"
  | "CATEGORY_VERIFICATION"
  | "SELECTED_DIAGNOSTICS"
  | "SINGLE_COMPONENT";

export type DiagnosticApplicability =
  | "APPLICABLE"
  | "NOT_APPLICABLE"
  | "UNSUPPORTED"
  | "RESTRICTED"
  | "UNAVAILABLE"
  | "BLOCKED_BY_PREREQUISITE"
  | "UNKNOWN";

export interface PlannedDiagnostic {
  diagnostic_id: string;
  applicability: DiagnosticApplicability;
  reason?: string | null;
}

export interface ScanPlan {
  plan_id: string;
  device_id: string;
  platform: "ANDROID" | "IOS" | "UNKNOWN";
  mode: ScanMode;
  diagnostics_requested: readonly string[];
  diagnostics_planned: readonly string[];
  diagnostics_skipped: readonly string[];
  skip_reasons: Record<string, string>;
  planned_items: readonly PlannedDiagnostic[];
  planning_session_epoch?: number;
  capability_profiled_at?: string | null;
  registry_diagnostic_ids: readonly string[];
  created_at: string;
}

export type ScanLifecycleState =
  | "CREATED"
  | "PLANNED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type DiagnosticEventType =
  | "scan.started"
  | "diagnostic.started"
  | "diagnostic.progress"
  | "diagnostic.evidence"
  | "diagnostic.completed"
  | "diagnostic.failed"
  | "diagnostic.inconclusive"
  | "scan.completed"
  | "scan.failed";

export interface DiagnosticEvent {
  event_id: string;
  scan_id: string;
  device_id: string;
  event_type: DiagnosticEventType;
  timestamp: string;
  diagnostic_id?: string | null;
  progress?: number | null;
  evidence?: CapabilityEvidenceRecord | null;
  result?: Record<string, unknown> | null;
  message?: string | null;
}

export interface ScanStartResponse {
  scan_id: string;
  state: ScanLifecycleState;
  plan?: ScanPlan | null;
}

export interface ScanEventsResponse {
  scan_id: string;
  events: readonly DiagnosticEvent[];
}

export interface ScanSummary {
  scan_id: string;
  device_id: string;
  state: ScanLifecycleState;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  plan?: ScanPlan | null;
  diagnostic_results: readonly Record<string, unknown>[];
  trust_engine_status: string;
  trust_score?: number | null;
  trust_confidence?: number | null;
  error?: string | null;
}

export function isScanPlan(data: unknown): data is ScanPlan {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.plan_id === "string" &&
    typeof d.device_id === "string" &&
    typeof d.platform === "string" &&
    typeof d.mode === "string" &&
    Array.isArray(d.diagnostics_requested) &&
    Array.isArray(d.diagnostics_planned) &&
    Array.isArray(d.diagnostics_skipped) &&
    typeof d.skip_reasons === "object" &&
    d.skip_reasons !== null &&
    Array.isArray(d.planned_items) &&
    d.planned_items.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as Record<string, unknown>).diagnostic_id === "string" &&
        typeof (item as Record<string, unknown>).applicability === "string"
    ) &&
    typeof d.created_at === "string"
  );
}

export function isDiagnosticEvent(data: unknown): data is DiagnosticEvent {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.event_id === "string" &&
    typeof d.scan_id === "string" &&
    typeof d.device_id === "string" &&
    typeof d.event_type === "string" &&
    typeof d.timestamp === "string"
  );
}

export function isScanSummary(data: unknown): data is ScanSummary {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.scan_id === "string" &&
    typeof d.device_id === "string" &&
    typeof d.state === "string" &&
    typeof d.created_at === "string" &&
    Array.isArray(d.diagnostic_results) &&
    typeof d.trust_engine_status === "string"
  );
}

export function isScanEventsResponse(data: unknown): data is ScanEventsResponse {
  if (typeof data !== "object" || data === null) return false;
  const d = data as Record<string, unknown>;
  return (
    typeof d.scan_id === "string" &&
    Array.isArray(d.events) &&
    d.events.every(isDiagnosticEvent)
  );
}
