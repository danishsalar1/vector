import type {
  CheckHealthOptions,
  DiagnosticProvider,
  ProviderMode,
} from "./DiagnosticProvider";
import type { HealthCheckResult } from "../lib/api/types";
import { DEMO_HEALTH_FIXTURE } from "./demo/fixtures";

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
}
