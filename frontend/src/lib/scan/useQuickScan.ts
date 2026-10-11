import { useCallback, useEffect, useRef, useState } from "react";
import type { DiagnosticEvent, ScanPlan, ScanSummary } from "../api/types";
import type { DiagnosticProvider } from "../../providers/DiagnosticProvider";
import { useDiagnosticProvider } from "../../providers/DiagnosticProviderContext";
import {
  describeScanError,
  isTerminalScanState,
  QUICK_SCAN_MODE,
} from "./quickScanModel";

export type QuickScanPhase =
  | "IDLE" // device not eligible; nothing requested
  | "PLANNING"
  | "PLAN_READY"
  | "PLAN_ERROR"
  | "STARTING"
  | "START_ERROR"
  | "RUNNING"
  | "POLL_LOST" // agent stopped answering while a scan may still be running
  | "FINISHED"; // backend reported a terminal scan state

export interface UseQuickScanOptions {
  provider?: DiagnosticProvider;
  /** Delay between status polls. Cadence only; it never produces progress by itself. */
  pollIntervalMs?: number;
  /** Consecutive failed polls tolerated before giving up and asking the user. */
  maxPollFailures?: number;
}

export interface UseQuickScanResult {
  phase: QuickScanPhase;
  plan: ScanPlan | null;
  summary: ScanSummary | null;
  events: readonly DiagnosticEvent[];
  error: string | null;
  /** Transient poll problem while still retrying. */
  pollWarning: string | null;
  start: () => void;
  retryPlan: () => void;
  resumePolling: () => void;
}

const DEFAULT_POLL_MS = 1000;
const DEFAULT_MAX_FAILURES = 5;

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/**
 * Drives one device's Quick Scan: plan (non-executing) -> start -> poll.
 * Everything exposed is returned by the backend. Mount it with `key={deviceId}`
 * so switching device discards the previous device's plan and results.
 */
export function useQuickScan(
  deviceId: string,
  eligible: boolean,
  options: UseQuickScanOptions = {}
): UseQuickScanResult {
  const contextProvider = useDiagnosticProvider();
  const provider = options.provider ?? contextProvider;
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;
  const maxPollFailures = options.maxPollFailures ?? DEFAULT_MAX_FAILURES;

  const [phase, setPhase] = useState<QuickScanPhase>(eligible ? "PLANNING" : "IDLE");
  const [planAttempt, setPlanAttempt] = useState(0);
  const [plan, setPlan] = useState<ScanPlan | null>(null);
  const [scanId, setScanId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [events, setEvents] = useState<readonly DiagnosticEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);

  const startControllerRef = useRef<AbortController | null>(null);

  // Plan (read-only on the backend; nothing is executed on the phone).
  useEffect(() => {
    if (!eligible) return;
    const controller = new AbortController();

    provider
      .planScan({ device_id: deviceId, mode: QUICK_SCAN_MODE }, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.ok) {
          setPlan(result.data);
          setError(null);
          setPhase("PLAN_READY");
        } else {
          setError(describeScanError(result.error, "Could not plan the scan"));
          setPhase("PLAN_ERROR");
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbort(err)) return;
        setError("Could not plan the scan: unexpected failure.");
        setPhase("PLAN_ERROR");
      });

    return () => controller.abort();
  }, [provider, deviceId, eligible, planAttempt]);

  // Poll summary then events. Summary first: events fetched afterwards are a
  // superset, so a terminal summary is always paired with the complete event log.
  useEffect(() => {
    if (phase !== "RUNNING" || !scanId) return;
    const controller = new AbortController();
    const { signal } = controller;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const tick = async () => {
      let failure: string | null = null;
      try {
        const summaryResult = await provider.getScanSummary(scanId, { signal });
        if (signal.aborted) return;
        if (summaryResult.ok) {
          setSummary(summaryResult.data);
          const eventsResult = await provider.getScanEvents(scanId, { signal });
          if (signal.aborted) return;
          if (eventsResult.ok) {
            setEvents(eventsResult.data.events);
          } else {
            failure = describeScanError(eventsResult.error, "Could not read scan events");
          }
          if (!failure && isTerminalScanState(summaryResult.data.state)) {
            setPollWarning(null);
            setPhase("FINISHED");
            return;
          }
        } else {
          failure = describeScanError(summaryResult.error, "Could not read scan status");
        }
      } catch (err: unknown) {
        if (signal.aborted || isAbort(err)) return;
        failure = "Could not read scan status: unexpected failure.";
      }

      if (failure) {
        failures += 1;
        if (failures >= maxPollFailures) {
          setError(failure);
          setPollWarning(null);
          setPhase("POLL_LOST");
          return;
        }
        setPollWarning(failure);
      } else {
        failures = 0;
        setPollWarning(null);
      }
      timer = setTimeout(() => void tick(), pollIntervalMs);
    };

    void tick();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [provider, phase, scanId, pollIntervalMs, maxPollFailures]);

  useEffect(() => () => startControllerRef.current?.abort(), []);

  const start = useCallback(() => {
    if (
      !eligible ||
      (phase !== "PLAN_READY" && phase !== "START_ERROR" && phase !== "FINISHED")
    ) {
      return;
    }
    startControllerRef.current?.abort();
    const controller = new AbortController();
    startControllerRef.current = controller;

    setPhase("STARTING");
    setError(null);
    setPollWarning(null);
    setSummary(null);
    setEvents([]);
    setScanId(null);

    provider
      .startScan({ device_id: deviceId, mode: QUICK_SCAN_MODE }, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.ok) {
          if (result.data.plan) setPlan(result.data.plan);
          setScanId(result.data.scan_id);
          setPhase("RUNNING");
        } else {
          setError(describeScanError(result.error, "Could not start the scan"));
          setPhase("START_ERROR");
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbort(err)) return;
        setError("Could not start the scan: unexpected failure.");
        setPhase("START_ERROR");
      });
  }, [eligible, phase, provider, deviceId]);

  const retryPlan = useCallback(() => {
    setError(null);
    setPhase("PLANNING");
    setPlanAttempt((n) => n + 1);
  }, []);

  const resumePolling = useCallback(() => {
    if (!scanId) return;
    setError(null);
    setPhase("RUNNING");
  }, [scanId]);

  return { phase, plan, summary, events, error, pollWarning, start, retryPlan, resumePolling };
}
