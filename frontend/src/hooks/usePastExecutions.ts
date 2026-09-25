import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { ExecutionSettings, ExecutionSummary, StoredExecution } from "../api/types";

const message = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

/** Runs of one stored analysis and, on request, one of them with its steps and audit log. */
export function usePastExecutions(api: Api, analysisId: string) {
  const [runs, setRuns] = useState<ExecutionSummary[] | null>(null);
  const [settings, setSettings] = useState<ExecutionSettings | null>(null);
  const [selected, setSelected] = useState<StoredExecution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let active = true;
    api.analysisExecutions(analysisId).then(
      (loaded) => {
        if (active) setRuns(loaded);
      },
      (err: unknown) => {
        if (active) setError(message(err, "Could not list the executions"));
      },
    );
    // Only for approval counts and the tool-call limit; answers even while execution is off.
    api.executionSettings().then(
      (loaded) => {
        if (active) setSettings(loaded);
      },
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, [api, analysisId, reloads]);

  const open = useCallback(
    (executionId: string) => {
      setError(null);
      api
        .analysisExecution(analysisId, executionId)
        .then(setSelected, (err: unknown) =>
          setError(message(err, "Could not load the execution")),
        );
    },
    [api, analysisId],
  );

  const refresh = useCallback(() => {
    setReloads((count) => count + 1);
    if (selected) open(selected.execution.id);
  }, [open, selected]);

  return { runs, settings, selected, error, open, refresh, close: () => setSelected(null) };
}
