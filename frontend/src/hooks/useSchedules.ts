import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type Api } from "../api/client";
import type { SchedulerView, ScheduleView } from "../api/types";

export type SchedulesStatus = "loading" | "ready" | "disabled" | "error";

interface Loaded {
  scheduler: SchedulerView | null;
  schedules: ScheduleView[];
  status: SchedulesStatus;
  error: string | null;
}

const LOADING: Loaded = { scheduler: null, schedules: [], status: "loading", error: null };

async function load(api: Api): Promise<Loaded> {
  try {
    const [scheduler, schedules] = await Promise.all([api.schedulerState(), api.listSchedules()]);
    return { scheduler, schedules, status: "ready", error: null };
  } catch (err: unknown) {
    if (err instanceof ApiError && err.code === "SCHEDULER_DISABLED") {
      return { ...LOADING, status: "disabled" };
    }
    const error = err instanceof Error ? err.message : "Could not load the schedules";
    return { ...LOADING, status: "error", error };
  }
}

/** Schedules plus the global pause state; `act` runs a change and reloads both. */
export function useSchedules(api: Api) {
  const [loaded, setLoaded] = useState<Loaded>(LOADING);
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const request = useRef(0); // answers to older requests are ignored

  useEffect(() => {
    const id = ++request.current;
    load(api).then((next) => id === request.current && setLoaded(next));
    return () => {
      request.current += 1;
    };
  }, [api]);

  const refresh = useCallback(async () => {
    const id = ++request.current;
    const next = await load(api);
    if (id === request.current) setLoaded(next);
  }, [api]);

  /** Runs one change (`label` explains the wait); errors are shown, never thrown. */
  const act = useCallback(
    async (label: string, change: () => Promise<unknown>): Promise<boolean> => {
      setPending(label);
      setActionError(null);
      try {
        await change();
        await refresh();
        return true;
      } catch (err: unknown) {
        setActionError(err instanceof Error ? err.message : "The change failed");
        return false;
      } finally {
        setPending(null);
      }
    },
    [refresh],
  );

  return { ...loaded, pending, actionError, refresh, act };
}
