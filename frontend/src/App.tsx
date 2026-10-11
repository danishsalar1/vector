import { DiagnosticProviderComponent } from "./providers";
import { HealthStatus } from "./components/HealthStatus";
import { PreflightStatus } from "./components/PreflightStatus";
import { AndroidStatus } from "./components/AndroidStatus";
import { QuickScanWorkspace } from "./components/scan/QuickScanWorkspace";
import type { QuickScanWorkspaceProps } from "./components/scan/QuickScanWorkspace";
import type { DiagnosticProvider } from "./providers";
import "./App.css";
import "./workspace.css";

export interface AppProps {
  provider?: DiagnosticProvider;
  /** Test seam: polling cadence for the Quick Scan workflow. */
  scanOptions?: QuickScanWorkspaceProps["scanOptions"];
}

function App({ provider, scanOptions }: AppProps) {
  return (
    <DiagnosticProviderComponent provider={provider}>
      <main id="app-container">
        <div className="agent-bar">
          <HealthStatus />
        </div>
        <QuickScanWorkspace scanOptions={scanOptions} />
        <details className="qs-tools">
          <summary>Engineering checks (preflight, battery telemetry)</summary>
          <div className="qs-tools-body">
            <PreflightStatus />
            <AndroidStatus />
          </div>
        </details>
      </main>
    </DiagnosticProviderComponent>
  );
}

export default App;
