import { DiagnosticProviderComponent } from "./providers";
import { HealthStatus } from "./components/HealthStatus";
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
      </main>
    </DiagnosticProviderComponent>
  );
}

export default App;
