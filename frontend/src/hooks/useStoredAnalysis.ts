import { useEffect, useState } from "react";
import { ApiError, type Api } from "../api/client";
import type { AnalysisDetail } from "../api/types";

export type StoredAnalysisState =
  | { phase: "loading" }
  | { phase: "done"; detail: AnalysisDetail }
  | { phase: "error"; error: ApiError };

/** One stored analysis: its report, how it was produced and whether it is stale.
 * Mount it with `key={analysisId}`, so a different analysis starts from "loading". */
export function useStoredAnalysis(api: Api, analysisId: string) {
  const [state, setState] = useState<StoredAnalysisState>({ phase: "loading" });

  useEffect(() => {
    let active = true;
    api.getAnalysis(analysisId).then(
      (detail) => {
        if (active) setState({ phase: "done", detail });
      },
      (err: unknown) => {
        if (!active) return;
        const error =
          err instanceof ApiError
            ? err
            : new ApiError("Could not load the analysis", "CLIENT_ERROR", 0);
        setState({ phase: "error", error });
      },
    );
    return () => {
      active = false;
    };
  }, [api, analysisId]);

  return state;
}
