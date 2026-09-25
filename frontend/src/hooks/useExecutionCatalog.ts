import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { ExecutionSettings, ExecutionSummary } from "../api/types";

/** Whether execution is available on this server, and the executions it has (newest first). */
export function useExecutionCatalog(api: Api) {
  const [settings, setSettings] = useState<ExecutionSettings | null>(null);
  const [executions, setExecutions] = useState<ExecutionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setExecutions(await api.listExecutions());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not list executions");
    }
  }, [api]);

  useEffect(() => {
    let active = true;
    api.executionSettings().then(
      (loaded) => {
        if (!active) return;
        setSettings(loaded);
        if (loaded.enabled) void refresh();
      },
      (err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load settings");
      },
    );
    return () => {
      active = false;
    };
  }, [api, refresh]);

  return { settings, executions, error, refresh };
}
