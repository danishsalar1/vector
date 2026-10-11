import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectedDevice } from "../api/devices";
import type { DiagnosticProvider } from "../../providers/DiagnosticProvider";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";

export type DeviceListState = "CHECKING" | "COMPLETE" | "ERROR";

export interface UseDeviceListResult {
  mode: DiagnosticProvider["mode"];
  state: DeviceListState;
  devices: readonly ConnectedDevice[];
  errorMessage: string | null;
  refresh: () => void;
}

/**
 * Lists devices from the active provider. Discovers once on mount and again on
 * explicit refresh; there is no background polling and no fallback data source.
 */
export function useDeviceList(
  providerOverride?: DiagnosticProvider
): UseDeviceListResult {
  const contextProvider = useDiagnosticProvider();
  const provider = providerOverride ?? contextProvider;

  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<DeviceListState>("CHECKING");
  const [devices, setDevices] = useState<readonly ConnectedDevice[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const thisAttempt = ++attemptRef.current;

    provider
      .listDevices({ signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted || thisAttempt !== attemptRef.current) return;
        if (result.state === "COMPLETE" && result.data) {
          setDevices(result.data.devices);
          setErrorMessage(null);
          setState("COMPLETE");
        } else {
          setDevices([]);
          setErrorMessage(result.errorMessage ?? "Device discovery failed.");
          setState("ERROR");
        }
      })
      .catch((error: unknown) => {
        if (
          controller.signal.aborted ||
          thisAttempt !== attemptRef.current ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          return;
        }
        setDevices([]);
        setErrorMessage("Device discovery failed unexpectedly.");
        setState("ERROR");
      });

    return () => controller.abort();
  }, [provider, attempt]);

  const refresh = useCallback(() => {
    setState("CHECKING");
    setErrorMessage(null);
    setAttempt((n) => n + 1);
  }, []);

  return { mode: provider.mode, state, devices, errorMessage, refresh };
}
