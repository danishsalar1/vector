import { useCallback, useEffect, useRef, useState } from "react";
import type {
  DiagnosticProvider,
  ProviderMode,
} from "../../providers/DiagnosticProvider";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";
import type { ConnectionState, HealthResponse } from "./types";

export interface UseHealthCheckOptions {
  timeoutMs?: number;
  provider?: DiagnosticProvider;
}

export interface UseHealthCheckReturn {
  mode: ProviderMode;
  state: ConnectionState;
  data: HealthResponse | null;
  errorMessage: string | null;
  retry: () => void;
}

export function useHealthCheck(
  optionsOrTimeout?: number | UseHealthCheckOptions
): UseHealthCheckReturn {
  const contextProvider = useDiagnosticProvider();

  const options: UseHealthCheckOptions =
    typeof optionsOrTimeout === "number"
      ? { timeoutMs: optionsOrTimeout }
      : (optionsOrTimeout ?? {});

  const provider = options.provider ?? contextProvider;
  const timeoutMs = options.timeoutMs;

  const [state, setState] = useState<ConnectionState>("CHECKING");
  const [data, setData] = useState<HealthResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const runCheck = useCallback(
    (controller: AbortController) => {
      provider
        .checkHealth({ signal: controller.signal, timeoutMs })
        .then((result) => {
          if (!isMountedRef.current || controller.signal.aborted) {
            return;
          }
          setState(result.state);
          setData(result.data);
          setErrorMessage(result.errorMessage);
        })
        .catch(() => {
          if (!isMountedRef.current || controller.signal.aborted) {
            return;
          }
          setState("OFFLINE");
          setData(null);
          setErrorMessage(
            "VECTOR Local Agent is offline. Start the VECTOR local service on this laptop and try again."
          );
        });
    },
    [provider, timeoutMs]
  );

  const retry = useCallback(() => {
    if (activeControllerRef.current) {
      activeControllerRef.current.abort();
    }
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setState("CHECKING");
    setErrorMessage(null);
    runCheck(controller);
  }, [runCheck]);

  useEffect(() => {
    isMountedRef.current = true;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    runCheck(controller);

    return () => {
      isMountedRef.current = false;
      if (activeControllerRef.current) {
        activeControllerRef.current.abort();
      }
    };
  }, [runCheck]);

  return {
    mode: provider.mode,
    state,
    data,
    errorMessage,
    retry,
  };
}
