import type { Execution } from "../../api/types";
import { BUCKET_BAR, BUCKET_LABEL, runProgress, type Bucket } from "../../lib/runProgress";

const ORDER: Bucket[] = ["done", "running", "needsYou", "failed", "ready"];

/** A segmented bar plus the same counts as text, so progress never relies on colour alone. */
export function RunProgress({ execution }: { execution: Execution }) {
  const progress = runProgress(execution);
  const shown = ORDER.filter((bucket) => progress[bucket] > 0);
  return (
    <div className="space-y-2" aria-label="Run progress">
      <p className="tabular text-sm text-slate-700">
        <strong className="text-ink-900">
          {progress.done} of {progress.total} steps done
        </strong>
        {progress.needsYou > 0 && (
          <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
            {progress.needsYou} waiting for a person
          </span>
        )}
      </p>
      <div aria-hidden="true" className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
        {ORDER.map((bucket) =>
          progress[bucket] ? (
            <div
              key={bucket}
              className={`${BUCKET_BAR[bucket]} transition-all`}
              style={{ width: `${(progress[bucket] / progress.total) * 100}%` }}
            />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {shown.map((bucket) => (
          <li key={bucket} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${BUCKET_BAR[bucket]}`} />
            {progress[bucket]} {BUCKET_LABEL[bucket]}
          </li>
        ))}
      </ul>
    </div>
  );
}
