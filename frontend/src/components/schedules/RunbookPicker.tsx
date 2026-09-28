import { useId, useState } from "react";
import type { Api } from "../../api/client";
import { FIELD } from "./fieldStyles";

const INPUT = `w-full ${FIELD}`;

/**
 * Pick a runbook from the server's folder, or upload one: the server checks that it parses,
 * saves it under `uploads/` without overwriting anything, and it is selected here.
 */
export function RunbookPicker({
  api,
  runbooks,
  value,
  onChange,
  onUploaded,
}: {
  api: Api;
  runbooks: string[];
  value: string;
  onChange: (path: string) => void;
  onUploaded: () => void;
}) {
  const selectId = useId();
  const fileId = useId();
  const statusId = useId();
  const [status, setStatus] = useState<{ text: string; error: boolean } | null>(null);

  const upload = async (file: File) => {
    setStatus({ text: `Uploading ${file.name}…`, error: false });
    try {
      const saved = await api.uploadRunbook(file.name, await file.text());
      onUploaded();
      onChange(saved.path);
      setStatus({ text: `Saved as ${saved.path} (${saved.serviceName})`, error: false });
    } catch (err: unknown) {
      const reason = err instanceof Error ? err.message : "upload failed";
      setStatus({ text: `Not saved: ${reason}`, error: true });
    }
  };

  const options = value && !runbooks.includes(value) ? [...runbooks, value] : runbooks;
  return (
    <div className="text-sm">
      <label htmlFor={selectId} className="block font-medium text-slate-700">
        Runbook
      </label>
      <select
        id={selectId}
        required
        value={value}
        aria-describedby={status ? statusId : undefined}
        onChange={(event) => onChange(event.target.value)}
        className={INPUT}
      >
        <option value="">Choose a runbook…</option>
        {options.map((path) => (
          <option key={path} value={path}>
            {path}
          </option>
        ))}
      </select>
      <label
        htmlFor={fileId}
        className="mt-1 inline-block cursor-pointer text-signal-700 underline"
      >
        Upload runbook…
      </label>
      <input
        id={fileId}
        type="file"
        accept=".md,.markdown,text/markdown"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = ""; // the same file can be chosen again
          if (file) void upload(file);
        }}
      />
      {status && (
        <p
          id={statusId}
          role={status.error ? "alert" : "status"}
          className={status.error ? "text-red-700" : "text-slate-600"}
        >
          {status.text}
        </p>
      )}
    </div>
  );
}
