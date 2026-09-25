import { useState } from "react";
import type { SampleList } from "../api/types";

interface Props {
  samples: SampleList;
  error: string | null;
  disabled: boolean;
  onPick: (kind: "runbook" | "inventory", path: string) => void;
}

const fileName = (path: string) => path.split("/").pop() ?? path;

/** Two selects that load a server-side sample runbook or inventory into the editors. */
export function SamplePicker({ samples, error, disabled, onPick }: Props) {
  const [chosen, setChosen] = useState({ runbook: "", inventory: "" });
  if (error) {
    return <p className="text-sm text-slate-500">Samples unavailable: {error}</p>;
  }
  const select = (kind: "runbook" | "inventory", label: string, options: string[]) => (
    <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
      {label}
      <select
        value={chosen[kind]}
        disabled={disabled || options.length === 0}
        onChange={(event) => {
          const path = event.target.value;
          setChosen((prev) => ({ ...prev, [kind]: path }));
          onPick(kind, path);
        }}
        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-normal shadow-sm focus:border-signal-500"
      >
        <option value="">Choose…</option>
        {options.map((path) => (
          <option key={path} value={path}>
            {fileName(path)}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <div className="flex flex-wrap gap-4 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
      {select("runbook", "Sample runbook", samples.runbooks)}
      {select("inventory", "Sample inventory", samples.inventories)}
    </div>
  );
}
