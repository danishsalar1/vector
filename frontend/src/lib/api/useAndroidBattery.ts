/**
 * React hook for Android battery telemetry collection.
 *
 * - Manual trigger only.
 * - Disabled until a single authorized device is available.
 * - Request sequencing and unmount cancellation.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { BatteryTelemetryResult, BatteryState } from "./types";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";
import type { DiagnosticProvider } from "../../providers/DiagnosticProvider";

export interface UseAndroidBatteryOptions {
  provider?: DiagnosticProvider;
}

export interface UseAndroidBatteryResult {
  state: BatteryState;
  data: BatteryTelemetryResult["data"];
  errorMessage: string | null;
  runTest: (deviceId: string) => void;
}

export function useAndroidBattery(
  options: UseAndroidBatteryOptions = {}
): UseAndroidBatteryResult {
  const contextProvider = useDiagnosticProvider();
  const provider = options.provider ?? contextProvider;

  const [state, setState] = useState<BatteryState>("IDLE");
  const [data, setData] = useState<BatteryTelemetryResult["data"]>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const requestIdRef = useRef<number>(0);

  const executeTest = useCallback(
    (deviceId: string, controller: AbortController) => {
      const requestId = ++requestIdRef.current;

      provider
        .getAndroidBatteryTelemetry(deviceId, { signal: controller.signal })
        .then((result) => {
          if (
            !isMountedRef.current ||
            controller.signal.aborted ||
            requestId !== requestIdRef.current
          ) {
            return;
          }
          setState(result.state);
          setData(result.data);
          setErrorMessage(result.errorMessage);
        })
        .catch((error: unknown) => {
          if (
            !isMountedRef.current ||
            controller.signal.aborted ||
            requestId !== requestIdRef.current ||
            (error instanceof DOMException && error.name === "AbortError")
          ) {
            return;
          }
          setState("ERROR");
          setData(null);
          setErrorMessage("Battery telemetry collection failed unexpectedly.");
        });
    },
    [provider]
  );

  const runTest = useCallback(
    (deviceId: string) => {
      if (!deviceId) return;
      if (activeControllerRef.current) {
        activeControllerRef.current.abort();
      }
      const controller = new AbortController();
      activeControllerRef.current = controller;
      setState("RUNNING");
      setData(null);
      setErrorMessage(null);
      executeTest(deviceId, controller);
    },
    [executeTest]
  );

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (activeControllerRef.current) {
        activeControllerRef.current.abort();
      }
    };
  }, []);

  return { state, data, errorMessage, runTest };
}
