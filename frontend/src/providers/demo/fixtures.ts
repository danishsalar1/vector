import type { HealthResponse } from "../../lib/api/types";

/**
 * Deterministic demo health fixture for public evaluation and offline demonstration.
 * Free of random generation or live hardware dependencies.
 */
export const DEMO_HEALTH_FIXTURE: Readonly<HealthResponse> = Object.freeze({
  status: "DEMO",
  timestamp: "2026-09-30T00:00:00.000Z",
  version: "0.1.0",
  mode: "DEMO",
});
