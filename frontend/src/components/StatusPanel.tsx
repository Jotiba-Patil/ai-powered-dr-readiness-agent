import { useEffect, useState } from "react";
import type { ApiError } from "../api/client";

/** Shown while a job runs: a local model on CPU takes minutes, so show elapsed time. */
export function LoadingPanel({ jobId }: { jobId: string | null }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div role="status" aria-live="polite" className="card overflow-hidden bg-ink-900 text-white">
      <div aria-hidden="true" className="h-1 overflow-hidden bg-white/10">
        <div className="h-full w-1/3 animate-pulse bg-gradient-to-r from-signal-400 to-signal-600" />
      </div>
      <div className="space-y-3 p-5">
        <p className="flex items-center gap-2 text-lg font-semibold">
          <span
            aria-hidden="true"
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-signal-400 border-t-transparent"
          />
          {jobId ? "Analyzing runbook…" : "Submitting…"} ({seconds} s)
        </p>
        <ul className="grid gap-2 text-sm text-slate-300 sm:grid-cols-3">
          <li>① Parse the steps, owners and estimates</li>
          <li>② Check every dependency against the inventory</li>
          <li>③ AI review: gaps, single points of failure, plan</li>
        </ul>
        <p className="text-xs text-slate-400">
          Parsing and health checks are instant; the local LLM can take a few minutes on CPU.
          {jobId && ` Job ${jobId}.`}
        </p>
      </div>
    </div>
  );
}

export function ErrorPanel({
  error,
  onDismiss,
  title = "Analysis failed",
}: {
  error: ApiError;
  onDismiss: () => void;
  title?: string;
}) {
  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900">
      <p className="font-semibold">
        <span aria-hidden="true">✖ </span>
        {title}
      </p>
      <p>{error.message}</p>
      <p className="text-sm text-red-700">
        Code: {error.code}
        {error.status > 0 && ` · HTTP ${error.status}`}
      </p>
      <button type="button" onClick={onDismiss} className="mt-2 text-sm underline">
        Dismiss
      </button>
    </div>
  );
}
