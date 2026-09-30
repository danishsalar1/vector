import type {
  CheckHealthOptions,
  DiagnosticProvider,
  ProviderMode,
} from "./DiagnosticProvider";
import type { HealthCheckResult } from "../lib/api/types";
import { checkHealth } from "../lib/api/health";

/**
 * Live hardware diagnostic provider.
 * Communicates with the local VECTOR FastAPI agent running on localhost:8742 via the /api proxy.
 */
export class LiveDiagnosticProvider implements DiagnosticProvider {
  readonly mode: ProviderMode = "live";

  async checkHealth(options?: CheckHealthOptions): Promise<HealthCheckResult> {
    return checkHealth(options);
  }
}
