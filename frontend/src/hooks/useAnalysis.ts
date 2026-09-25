import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type Api } from "../api/client";
import type { AnalyzeRequest, Report } from "../api/types";

export type AnalysisState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "running"; jobId: string }
  | {
      phase: "done";
      jobId: string;
      report: Report;
      /** Stored in the history? null while history is off on the server. */
      historySaved: boolean | null;
    }
  | { phase: "error"; error: ApiError };

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function asApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError("Unexpected error while analyzing", "CLIENT_ERROR", 0);
}

/**
 * Submits an analysis job and long-polls it until it finishes.
 * Starting a new run or calling `reset` abandons the previous run's results.
 */
export function useAnalysis(api: Api, pollIntervalMs = 1000) {
  const [state, setState] = useState<AnalysisState>({ phase: "idle" });
  const runId = useRef(0);

  useEffect(
    () => () => {
      runId.current += 1; // unmount: ignore any in-flight results
    },
    [],
  );

  const analyze = useCallback(
    async (request: AnalyzeRequest) => {
      const id = ++runId.current;
      const current = () => id === runId.current;
      setState({ phase: "submitting" });
      try {
        let job = await api.submitAnalysis(request);
        while (current() && (job.status === "pending" || job.status === "running")) {
          setState({ phase: "running", jobId: job.jobId });
          job = await api.pollJob(job.jobId);
          if (job.status === "pending" || job.status === "running") await sleep(pollIntervalMs);
        }
        if (!current()) return;
        if (job.status === "succeeded" && job.report) {
          setState({
            phase: "done",
            jobId: job.jobId,
            report: job.report,
            historySaved: job.historySaved ?? null,
          });
        } else {
          const error = job.error ?? { error: "Analysis failed", code: "ANALYSIS_FAILED" };
          setState({ phase: "error", error: new ApiError(error.error, error.code, 200) });
        }
      } catch (err) {
        if (current()) setState({ phase: "error", error: asApiError(err) });
      }
    },
    [api, pollIntervalMs],
  );

  const reset = useCallback(() => {
    runId.current += 1;
    setState({ phase: "idle" });
  }, []);

  return { state, analyze, reset };
}
