import type { Cadence } from "../../api/types";
import { cadenceSentence } from "../../lib/scheduleLabels";
import { Icon } from "../ui/Icon";

/** The schedule in one sentence before it is created, plus the submit button. */
export function ScheduleSummary({
  name,
  runbook,
  cadence,
  timezone,
  disabled,
}: {
  name: string;
  runbook: string;
  cadence: Cadence;
  timezone: string;
  disabled: boolean;
}) {
  const ready = name.trim() !== "" && runbook !== "";
  return (
    <div className="grid items-center gap-3 rounded-xl bg-ink-900 p-4 text-slate-200 md:grid-cols-[1fr_auto]">
      <div className="min-w-0 space-y-1">
        <p role="status" aria-label="Schedule preview" className="flex items-start gap-2">
          <Icon name="sparkles" className="mt-0.5 h-4 w-4 text-signal-300" />
          {ready ? (
            <span>
              <strong className="text-white">{name.trim()}</strong> ·{" "}
              {cadenceSentence(cadence, timezone)} · checks{" "}
              <code className="font-mono text-sm text-signal-300">{runbook}</code>
            </span>
          ) : (
            <span className="text-slate-400">
              Give the schedule a name and pick a runbook to see a preview.
            </span>
          )}
        </p>
        <p className="pl-6 text-xs text-slate-400">
          Scheduled runs only analyze and email; running the recovery always needs a person.
        </p>
      </div>
      <button
        type="submit"
        className="inline-flex items-center gap-1.5 rounded-lg bg-signal-500 px-4 py-2 font-semibold text-ink-950 transition hover:bg-signal-400 disabled:cursor-not-allowed disabled:opacity-45"
        disabled={disabled}
      >
        <Icon name="plus" />
        Create schedule
      </button>
    </div>
  );
}
