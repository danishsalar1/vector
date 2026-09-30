/**
 * React hook for Android device discovery.
 *
 * - Manual trigger only (no continuous polling).
 * - Request sequencing prevents stale data from overwriting current state.
 * - Unmount cancellation prevents post-unmount state updates.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AndroidDiscoveryResult, AndroidDiscoveryState } from "./types";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";
import type { DiagnosticProvider } from "../../providers/DiagnosticProvider";

export interface UseAndroidDiscoveryOptions {
  provider?: DiagnosticProvider;
}

export interface UseAndroidDiscoveryResult {
  mode: string;
  state: AndroidDiscoveryState;
  data: AndroidDiscoveryResult["data"];
  errorMessage: string | null;
  detect: () => void;
}

export function useAndroidDiscovery(
  options: UseAndroidDiscoveryOptions = {}
): UseAndroidDiscoveryResult {
  const contextProvider = useDiagnosticProvider();
  const provider = options.provider ?? contextProvider;

  const [state, setState] = useState<AndroidDiscoveryState>("IDLE");
  const [data, setData] = useState<AndroidDiscoveryResult["data"]>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const requestIdRef = useRef<number>(0);

  const executeDetect = useCallback(
    (controller: AbortController) => {
      const requestId = ++requestIdRef.current;

      provider
        .discoverAndroidDevices({ signal: controller.signal })
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
          setErrorMessage("Android device detection failed unexpectedly.");
        });
    },
    [provider]
  );

  const detect = useCallback(() => {
    if (activeControllerRef.current) {
      activeControllerRef.current.abort();
    }
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setState("CHECKING");
    setData(null);
    setErrorMessage(null);
    executeDetect(controller);
  }, [executeDetect]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (activeControllerRef.current) {
        activeControllerRef.current.abort();
      }
    };
  }, []);

  return {
    mode: provider.mode,
    state,
    data,
    errorMessage,
    detect,
  };
}
