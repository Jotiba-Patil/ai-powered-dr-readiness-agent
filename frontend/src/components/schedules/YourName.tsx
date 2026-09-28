import { useId } from "react";

/** The name recorded with schedule changes; remembered in this browser, never verified. */
export function YourName({ name, onName }: { name: string; onName: (name: string) => void }) {
  const id = useId();
  const hintId = useId();
  return (
    <p className="text-sm">
      <label htmlFor={id} className="text-slate-700">
        Your name
      </label>{" "}
      <input
        id={id}
        value={name}
        aria-describedby={hintId}
        onChange={(event) => onName(event.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1"
      />
      <span id={hintId} className="ml-2 text-xs text-slate-500">
        {name.trim()
          ? "Recorded with every change (not verified)."
          : "Enter your name to make changes."}
      </span>
    </p>
  );
}
