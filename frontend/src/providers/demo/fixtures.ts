import type {
  HealthResponse,
  PreflightCheckItem,
  PreflightResponse,
} from "../../lib/api/types";

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

const DEMO_CHECKS: readonly PreflightCheckItem[] = Object.freeze([
  {
    id: "platform_os",
    name: "Operating System",
    category: "platform",
    status: "PASS",
    message: "Demo Environment (Simulated Windows Platform).",
    required: false,
    details: "Simulated Windows (Demo Environment)",
  },
  {
    id: "python_runtime",
    name: "Python Runtime",
    category: "runtime",
    status: "PASS",
    message: "Python 3.12 (Demo Simulated Runtime).",
    required: true,
    details: "Simulated Python 3.12 (Demo Environment)",
  },
  {
    id: "vector_agent",
    name: "VECTOR Local Agent",
    category: "agent",
    status: "PASS",
    message: "VECTOR local hardware agent in DEMO mode.",
    required: true,
    details: "Agent version: 0.1.0 | Mode: DEMO",
  },
  {
    id: "android_adb",
    name: "Android Platform Tools",
    category: "android",
    status: "NOT_INSTALLED",
    message:
      "Android Platform Tools are not installed in this demo environment. They will be required before Android device discovery.",
    required: false,
    details: "Simulated environment: adb not configured",
  },
  {
    id: "ios_tools",
    name: "iOS Device Tooling",
    category: "ios",
    status: "NOT_INSTALLED",
    message:
      "iOS device tooling is not installed in this demo environment. It will be required before iPhone discovery.",
    required: false,
    details: "Simulated environment: libimobiledevice utilities not configured",
  },
]);

/**
 * Deterministic demo preflight fixture representing an example demo environment.
 * Clearly labeled as demo/simulated data and free of real machine claims.
 */
export const DEMO_PREFLIGHT_FIXTURE: Readonly<PreflightResponse> = Object.freeze({
  overall: "PARTIAL",
  overall_status: "PARTIAL",
  checks: DEMO_CHECKS,
  timestamp: "2026-09-30T00:00:00.000Z",
});
