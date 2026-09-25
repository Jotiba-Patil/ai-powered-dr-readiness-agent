import { useCallback, useEffect, useState } from "react";
import { ApiError, type Api } from "../api/client";
import type { Execution } from "../api/types";

/** What the server is doing while a request is pending (shown as a progress note). */
export interface Progress {
  label: string;
  hint?: string;
}

export type RunAction = (action: () => Promise<Execution>, progress?: Progress) => Promise<void>;

function asApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError("Unexpected error", "CLIENT_ERROR", 0);
}

/**
 * The execution being viewed. Every action goes through `run`, which shows the server's answer
 * (the updated execution) or its error. While the execution is RUNNING, tool calls happen in the
 * background on the server, so the hook polls it, like `useAnalysis` polls a job.
 * `progress` says what a pending request is doing, so the UI can explain disabled buttons.
 */
export function useExecution(api: Api, pollIntervalMs = 1000) {
  const [execution, setExecution] = useState<Execution | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);

  const running = execution?.state === "RUNNING";
  const executionId = execution?.id;
  const updatedAt = execution?.updatedAt;

  useEffect(() => {
    if (!running || !executionId) return;
    let active = true;
    const timer = setTimeout(() => {
      api.getExecution(executionId).then(
        (latest) => {
          if (active) setExecution(latest);
        },
        (err: unknown) => {
          if (active) setError(asApiError(err));
        },
      );
    }, pollIntervalMs);
    return () => {
      active = false;
      clearTimeout(timer);
    };
    // updatedAt re-arms the timer after each poll while the execution keeps running
  }, [api, running, executionId, updatedAt, pollIntervalMs]);

  const run: RunAction = useCallback(async (action, next = { label: "Sending your request…" }) => {
    setProgress(next);
    setError(null);
    try {
      setExecution(await action());
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setProgress(null);
    }
  }, []);

  const open = useCallback(
    (id: string) => run(() => api.getExecution(id), { label: "Loading the run…" }),
    [api, run],
  );
  const clear = useCallback(() => setExecution(null), []);
  const dismissError = useCallback(() => setError(null), []);

  const busy = progress !== null;
  return { execution, error, busy, progress, run, open, clear, dismissError };
}
