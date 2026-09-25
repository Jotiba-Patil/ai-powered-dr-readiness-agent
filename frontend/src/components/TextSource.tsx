import { useId } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  accept: string;
  placeholder: string;
  rows?: number;
}

/** A labeled text area that can also be filled from a local file (read in the browser). */
export function TextSource({ label, value, onChange, accept, placeholder, rows = 10 }: Props) {
  const id = useId();
  const onFile = async (files: FileList | null) => {
    const file = files?.[0];
    if (file) onChange(await file.text());
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-sm font-semibold text-slate-700">
          {label}
        </label>
        <label className="btn-ghost cursor-pointer py-1 text-xs">
          Upload file
          <input
            type="file"
            accept={accept}
            className="sr-only"
            aria-label={`Upload ${label.toLowerCase()} file`}
            onChange={(event) => void onFile(event.target.files)}
          />
        </label>
      </div>
      <textarea
        id={id}
        value={value}
        rows={rows}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-xl border border-ink-800 bg-ink-950 p-3 font-mono text-xs leading-relaxed text-slate-100 placeholder:text-slate-500"
      />
    </div>
  );
}
