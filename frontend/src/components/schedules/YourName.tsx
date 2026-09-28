import { useId } from "react";
import { Icon } from "../ui/Icon";
import { FIELD } from "./fieldStyles";

/** The name recorded with schedule changes; remembered in this browser, never verified. */
export function YourName({ name, onName }: { name: string; onName: (name: string) => void }) {
  const id = useId();
  const hintId = useId();
  const named = name.trim() !== "";
  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-xl p-2 pl-3 text-sm ring-1 ${named ? "bg-white ring-slate-200" : "bg-amber-50 ring-amber-200"}`}
    >
      <Icon name="users" className={`h-4 w-4 ${named ? "text-signal-600" : "text-amber-700"}`} />
      <label htmlFor={id} className="font-medium text-slate-700">
        Your name
      </label>
      <input
        id={id}
        value={name}
        placeholder="Who is making changes?"
        aria-describedby={hintId}
        onChange={(event) => onName(event.target.value)}
        className={`${FIELD} w-48`}
      />
      <span id={hintId} className={`text-xs ${named ? "text-slate-500" : "text-amber-800"}`}>
        {named ? "Recorded with every change (not verified)." : "Enter your name to make changes."}
      </span>
    </div>
  );
}
