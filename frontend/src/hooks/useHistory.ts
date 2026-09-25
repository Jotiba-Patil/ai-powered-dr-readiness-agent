import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type Api } from "../api/client";
import type { AnalysisPage, AnalysisSummary, RiskLevel } from "../api/types";

export interface HistoryFilters {
  service: string;
  riskLevel: RiskLevel | "";
}

export type HistoryStatus = "loading" | "ready" | "disabled" | "error";

const PAGE_SIZE = 20;

/** Stored analyses, newest first, with filters and "load more" (keyset pages). */
export function useHistory(api: Api) {
  const [filters, setFilterState] = useState<HistoryFilters>({ service: "", riskLevel: "" });
  const [reloads, setReloads] = useState(0);
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [status, setStatus] = useState<HistoryStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0); // answers to older requests are ignored

  const fetchPage = useCallback(
    (before?: string) =>
      api.listAnalyses({
        service: filters.service.trim() || undefined,
        riskLevel: filters.riskLevel || undefined,
        limit: PAGE_SIZE,
        before,
      }),
    [api, filters],
  );

  const settle = useCallback((id: number, before?: string) => {
    const done = (page: AnalysisPage) => {
      if (id !== request.current) return;
      setItems((current) => (before ? [...current, ...page.items] : page.items));
      setNext(page.nextBefore ?? null);
      setStatus("ready");
    };
    const failed = (err: unknown) => {
      if (id !== request.current) return;
      if (err instanceof ApiError && err.code === "HISTORY_DISABLED") {
        setStatus("disabled");
        return;
      }
      setError(err instanceof Error ? err.message : "Could not load the history");
      setStatus("error");
    };
    return [done, failed] as const;
  }, []);

  useEffect(() => {
    const id = ++request.current;
    fetchPage().then(...settle(id));
    return () => {
      request.current += 1;
    };
  }, [fetchPage, settle, reloads]);

  const loadMore = useCallback(() => {
    if (!next) return;
    const id = ++request.current;
    fetchPage(next).then(...settle(id, next));
  }, [fetchPage, settle, next]);

  // "loading" is set by the actions that start a fresh first page, never inside the effect.
  const setFilters = useCallback((value: HistoryFilters) => {
    setStatus("loading");
    setFilterState(value);
  }, []);

  const refresh = useCallback(() => {
    setStatus("loading");
    setReloads((count) => count + 1);
  }, []);

  return { items, next, status, error, filters, setFilters, loadMore, refresh };
}
