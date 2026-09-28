import { useId, useState } from "react";
import { localInputToIso } from "../../lib/scheduleLabels";

/** Pause now, optionally until a date (resumes by itself then); the server checks the limit. */
export function PauseForm({
  label,
  maxDays,
  disabled,
  onPause,
  onCancel,
}: {
  label: string;
  maxDays: number;
  disabled: boolean;
  onPause: (until?: string) => void;
  onCancel: () => void;
}) {
  const untilId = useId();
  const [until, setUntil] = useState("");
  return (
    <form
      aria-label={label}
      className="flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200"
      onSubmit={(event) => {
        event.preventDefault();
        onPause(localInputToIso(until));
      }}
    >
      <label htmlFor={untilId} className="text-sm">
        <span className="block text-slate-700">Pause until (optional, your local time)</span>
        <input
          id={untilId}
          type="datetime-local"
          value={until}
          onChange={(event) => setUntil(event.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1"
        />
      </label>
      <p className="basis-full text-xs text-slate-500">
        Empty pauses until someone resumes. A date resumes by itself (at most {maxDays} days ahead);
        missed slots are skipped.
      </p>
      <button type="submit" className="btn-primary" disabled={disabled}>
        {until ? "Pause until then" : "Pause"}
      </button>
      <button type="button" className="btn-ghost" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}
