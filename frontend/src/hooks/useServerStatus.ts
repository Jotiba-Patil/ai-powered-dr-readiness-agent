import { useEffect, useState } from "react";
import type { Api } from "../api/client";
import type { ExecutionSettings } from "../api/types";

export interface ServerStatus {
  online: boolean | null; // null while checking
  version: string | null;
  execution: ExecutionSettings | null;
}

/** What the header shows about the server: reachable, version, and what execution allows. */
export function useServerStatus(api: Api): ServerStatus {
  const [status, setStatus] = useState<ServerStatus>({
    online: null,
    version: null,
    execution: null,
  });
  useEffect(() => {
    let active = true;
    api.health().then(
      (health) => {
        if (active) setStatus((s) => ({ ...s, online: true, version: health.version }));
      },
      () => {
        if (active) setStatus((s) => ({ ...s, online: false }));
      },
    );
    api.executionSettings().then(
      (execution) => {
        if (active) setStatus((s) => ({ ...s, execution }));
      },
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, [api]);
  return status;
}
