import { useCallback, useEffect, useRef, useState } from "react";
import type {
  DiagnosticProvider,
  ProviderMode,
} from "../../providers/DiagnosticProvider";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";
import type {
  PreflightResponse,
  PreflightState,
} from "./types";
import { PREFLIGHT_ERROR_MESSAGE } from "./preflight";

export interface UsePreflightOptions {
  timeoutMs?: number;
  provider?: DiagnosticProvider;
  autoRun?: boolean;
}

export interface UsePreflightReturn {
  mode: ProviderMode;
  state: PreflightState;
  data: PreflightResponse | null;
  errorMessage: string | null;
  runCheck: () => void;
}

/**
 * Hook to manage the lifecycle, state, and retry execution of system preflight environment checks.
 */
export function usePreflight(
  optionsOrTimeout?: number | UsePreflightOptions
): UsePreflightReturn {
  const contextProvider = useDiagnosticProvider();

  const options: UsePreflightOptions =
    typeof optionsOrTimeout === "number"
      ? { timeoutMs: optionsOrTimeout }
      : (optionsOrTimeout ?? {});

  const provider = options.provider ?? contextProvider;
  const timeoutMs = options.timeoutMs;
  const autoRun = options.autoRun ?? true;

  const [state, setState] = useState<PreflightState>(autoRun ? "CHECKING" : "IDLE");
  const [data, setData] = useState<PreflightResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const executeCheck = useCallback(
    (controller: AbortController) => {
      provider
        .getPreflight({ signal: controller.signal, timeoutMs })
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
          setState("ERROR");
          setData(null);
          setErrorMessage(PREFLIGHT_ERROR_MESSAGE);
        });
    },
    [provider, timeoutMs]
  );

  const runCheck = useCallback(() => {
    if (activeControllerRef.current) {
      activeControllerRef.current.abort();
    }
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setState("CHECKING");
    setErrorMessage(null);
    executeCheck(controller);
  }, [executeCheck]);

  useEffect(() => {
    isMountedRef.current = true;
    if (autoRun) {
      const controller = new AbortController();
      activeControllerRef.current = controller;
      executeCheck(controller);
    }

    return () => {
      isMountedRef.current = false;
      if (activeControllerRef.current) {
        activeControllerRef.current.abort();
      }
    };
  }, [autoRun, executeCheck]);

  return {
    mode: provider.mode,
    state,
    data,
    errorMessage,
    runCheck,
  };
}
