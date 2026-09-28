import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { ScheduleRun } from "../api/types";

/** Runs of one schedule, newest first; polls while a run is still going. */
export function useScheduleRuns(api: Api, scheduleId: string, pollIntervalMs = 3000) {
  const [runs, setRuns] = useState<ScheduleRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let active = true;
    api.listScheduleRuns(scheduleId).then(
      (page) => {
        if (!active) return;
        setRuns(page.items);
        setError(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Could not load the runs");
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [api, scheduleId, reloads]);

  const running = runs.some((run) => run.state === "running");
  useEffect(() => {
    if (!running || pollIntervalMs <= 0) return;
    const timer = window.setTimeout(() => setReloads((n) => n + 1), pollIntervalMs);
    return () => window.clearTimeout(timer);
  }, [running, runs, pollIntervalMs]);

  const refresh = useCallback(() => setReloads((n) => n + 1), []);
  return { runs, loading, error, refresh };
}
