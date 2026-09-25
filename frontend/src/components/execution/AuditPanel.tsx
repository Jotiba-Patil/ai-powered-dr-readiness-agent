import type { AuditView } from "../../api/types";
import { shortHash } from "../../lib/executionLabels";

/** The audit log and whether its hash chain verifies. Payloads are shown as text only. */
export function AuditPanel({
  audit,
  error,
  onLoad,
}: {
  audit: AuditView | null;
  error: string | null;
  onLoad: () => void;
}) {
  const verification = audit?.verification;
  return (
    <section aria-label="Audit log" className="card space-y-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-ink-900">Audit log</h3>
        <button type="button" onClick={onLoad} className="btn-ghost">
          {audit ? "Refresh and verify" : "Load and verify"}
        </button>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {verification && (
        <p className={verification.valid ? "text-emerald-800" : "font-semibold text-red-800"}>
          <span aria-hidden="true">{verification.valid ? "✔ " : "✖ "}</span>
          {verification.valid
            ? `Hash chain verified: ${verification.events} events, head ${shortHash(verification.head)}`
            : `Hash chain broken at event ${verification.brokenAtSeq ?? "?"}`}
        </p>
      )}
      {audit && (
        <ol className="max-h-96 divide-y divide-slate-100 overflow-y-auto rounded-xl bg-slate-50 text-xs ring-1 ring-slate-200">
          {audit.events.map((event) => (
            <li key={event.seq} className="grid gap-1 px-3 py-2 sm:grid-cols-[9rem_1fr]">
              <span className="tabular text-slate-500">
                #{event.seq} {event.createdAt.slice(11, 19)}
              </span>
              <span>
                <span className="font-semibold text-ink-900">{event.type}</span> by {event.actor}{" "}
                <span className="block font-mono break-all text-slate-500">
                  {JSON.stringify(event.payload ?? {})}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
