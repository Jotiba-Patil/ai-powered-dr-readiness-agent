import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { SampleList } from "../api/types";

const EMPTY: SampleList = { runbooks: [], inventories: [] };

/**
 * Lists the server's sample runbooks/inventories (uploaded runbooks included); `load` fetches one
 * file's text and `reload` refreshes the list, e.g. after an upload.
 */
export function useSamples(api: Api) {
  const [samples, setSamples] = useState<SampleList>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let active = true;
    api.listSamples().then(
      (list) => {
        if (active) setSamples(list);
      },
      (err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load samples");
      },
    );
    return () => {
      active = false;
    };
  }, [api, reloads]);

  const load = useCallback((path: string) => api.getSample(path), [api]);
  const reload = useCallback(() => setReloads((n) => n + 1), []);

  return { samples, error, load, reload };
}
