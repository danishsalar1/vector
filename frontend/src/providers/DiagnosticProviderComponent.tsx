import { useMemo, type FC, type ReactNode } from "react";
import type { DiagnosticProvider } from "./DiagnosticProvider";
import {
  DiagnosticProviderContext,
  getDefaultDiagnosticProvider,
} from "./DiagnosticProviderContext";

export interface DiagnosticProviderComponentProps {
  provider?: DiagnosticProvider;
  children: ReactNode;
}

/**
 * Context provider to inject a DiagnosticProvider implementation into the React component tree.
 */
export const DiagnosticProviderComponent: FC<
  DiagnosticProviderComponentProps
> = ({ provider, children }) => {
  const activeProvider = useMemo(
    () => provider ?? getDefaultDiagnosticProvider(),
    [provider]
  );

  return (
    <DiagnosticProviderContext.Provider value={activeProvider}>
      {children}
    </DiagnosticProviderContext.Provider>
  );
};
