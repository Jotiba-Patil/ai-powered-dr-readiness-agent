import { useCallback, useState } from "react";
import type { Api } from "../api/client";
import type { AuditView } from "../api/types";

/** Loads an execution's audit log with the server's hash-chain verification. */
export function useAudit(api: Api) {
  const [audit, setAudit] = useState<AuditView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (executionId: string) => {
      try {
        setAudit(await api.getAudit(executionId));
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load the audit log");
      }
    },
    [api],
  );

  return { audit, error, load };
}
