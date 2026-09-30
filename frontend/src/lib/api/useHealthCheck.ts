import { useCallback, useEffect, useRef, useState } from "react";
import { checkHealth } from "./health";
import type { ConnectionState, HealthResponse } from "./types";

export interface UseHealthCheckReturn {
  state: ConnectionState;
  data: HealthResponse | null;
  errorMessage: string | null;
  retry: () => void;
}

export function useHealthCheck(timeoutMs?: number): UseHealthCheckReturn {
  const [state, setState] = useState<ConnectionState>("CHECKING");
  const [data, setData] = useState<HealthResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const runCheck = useCallback(
    (controller: AbortController) => {
      checkHealth({ signal: controller.signal, timeoutMs })
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
    [timeoutMs]
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
    state,
    data,
    errorMessage,
    retry,
  };
}
