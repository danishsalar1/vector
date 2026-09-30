import { DiagnosticProviderComponent } from "./providers";
import { HealthStatus } from "./components/HealthStatus";
import { PreflightStatus } from "./components/PreflightStatus";
import type { DiagnosticProvider } from "./providers";
import "./App.css";

export interface AppProps {
  provider?: DiagnosticProvider;
}

function App({ provider }: AppProps) {
  return (
    <DiagnosticProviderComponent provider={provider}>
      <main id="app-container">
        <HealthStatus />
        <PreflightStatus />
      </main>
    </DiagnosticProviderComponent>
  );
}

export default App;
