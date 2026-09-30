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

export interface HealthCheckResult {
  state: ConnectionState;
  data: HealthResponse | null;
  errorMessage: string | null;
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
