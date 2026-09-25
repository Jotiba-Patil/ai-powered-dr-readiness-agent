import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { SampleList } from "../api/types";

const EMPTY: SampleList = { runbooks: [], inventories: [] };

/** Lists the server's sample runbooks/inventories; `load` fetches one file's text. */
export function useSamples(api: Api) {
  const [samples, setSamples] = useState<SampleList>(EMPTY);
  const [error, setError] = useState<string | null>(null);

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
  }, [api]);

  const load = useCallback((path: string) => api.getSample(path), [api]);

  return { samples, error, load };
}
