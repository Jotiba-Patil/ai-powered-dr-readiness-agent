import { useId, useState } from "react";
import { localInputToIso } from "../../lib/scheduleLabels";
import { FIELD } from "./fieldStyles";

const PRESETS = [
  { label: "1 hour", hours: 1 },
  { label: "1 day", hours: 24 },
  { label: "1 week", hours: 24 * 7 },
] as const;

/** A `datetime-local` value (browser time) `hours` from now. */
function localInputIn(hours: number): string {
  const date = new Date(Date.now() + hours * 3_600_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

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
      className="flex flex-wrap items-end gap-2 rounded-xl bg-amber-50/50 p-3 text-left ring-1 ring-amber-200"
      onSubmit={(event) => {
        event.preventDefault();
        onPause(localInputToIso(until));
      }}
    >
      <label htmlFor={untilId} className="text-sm">
        <span className="block font-medium text-slate-700">
          Pause until (optional, your local time)
        </span>
        <input
          id={untilId}
          type="datetime-local"
          value={until}
          onChange={(event) => setUntil(event.target.value)}
          className={FIELD}
        />
      </label>
      <span className="flex gap-1" role="group" aria-label="Quick pause lengths">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-amber-100"
            onClick={() => setUntil(localInputIn(preset.hours))}
          >
            {preset.label}
          </button>
        ))}
      </span>
      <p className="basis-full text-xs text-slate-500">
        Empty pauses until someone resumes. A date resumes by itself (at most {maxDays} days ahead);
        missed slots are skipped.
      </p>
      <button type="submit" className="btn-primary py-1.5 text-sm" disabled={disabled}>
        {until ? "Pause until then" : "Pause"}
      </button>
      <button type="button" className="btn-ghost" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}
