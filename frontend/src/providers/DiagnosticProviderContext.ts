import { createContext, useContext } from "react";
import type { DiagnosticProvider } from "./DiagnosticProvider";
import { createDiagnosticProvider } from "./createDiagnosticProvider";

export const DiagnosticProviderContext =
  createContext<DiagnosticProvider | null>(null);

let cachedDefaultProvider: DiagnosticProvider | null = null;

/**
 * Returns a stable singleton of the default diagnostic provider.
 */
export function getDefaultDiagnosticProvider(): DiagnosticProvider {
  if (!cachedDefaultProvider) {
    cachedDefaultProvider = createDiagnosticProvider();
  }
  return cachedDefaultProvider;
}

/**
 * Resets the cached default provider. Useful in tests when switching environment modes.
 */
export function resetDefaultDiagnosticProvider(): void {
  cachedDefaultProvider = null;
}

/**
 * Hook to access the active DiagnosticProvider.
 * Falls back to the stable default configured provider if rendered outside a context provider.
 */
export function useDiagnosticProvider(): DiagnosticProvider {
  const context = useContext(DiagnosticProviderContext);
  return context ?? getDefaultDiagnosticProvider();
}
