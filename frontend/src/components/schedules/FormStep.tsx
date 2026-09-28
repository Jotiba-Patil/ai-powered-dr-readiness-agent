import type { ReactNode } from "react";

/** One numbered step of the new-schedule form. */
export function FormStep({
  step,
  title,
  hint,
  children,
}: {
  step: number;
  title: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="space-y-3 rounded-xl bg-slate-50/60 p-4 ring-1 ring-slate-200">
      <legend className="sr-only">{title}</legend>
      <div aria-hidden="true" className="flex items-center gap-2">
        <span className="tabular grid h-6 w-6 place-items-center rounded-full bg-ink-900 text-xs font-semibold text-signal-300">
          {step}
        </span>
        <span className="font-semibold text-ink-900">{title}</span>
      </div>
      <p className="-mt-1 text-xs text-slate-500">{hint}</p>
      {children}
    </fieldset>
  );
}
