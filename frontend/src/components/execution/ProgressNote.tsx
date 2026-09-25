import { useEffect, useState } from "react";

/** Tells the user the server is working (buttons are disabled meanwhile), with elapsed time. */
export function ProgressNote({ label, hint }: { label: string; hint?: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-signal-400/40 bg-signal-500/10 p-3 text-ink-900"
    >
      <p className="flex items-center gap-2 font-semibold">
        <span
          aria-hidden="true"
          className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-signal-600 border-t-transparent"
        />
        {label} ({seconds} s)
      </p>
      {hint && <p className="text-sm text-slate-700">{hint}</p>}
    </div>
  );
}
