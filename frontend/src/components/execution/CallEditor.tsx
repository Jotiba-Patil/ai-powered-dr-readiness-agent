import { useId, useState, type FormEvent } from "react";
import type { PlannedToolCall, ToolCall } from "../../api/types";

function draftOf(call: ToolCall | null | undefined): string {
  const planned = call
    ? { server: call.server, tool: call.tool, arguments: call.arguments ?? {} }
    : { server: "", tool: "", arguments: {} };
  return JSON.stringify(planned, null, 2);
}

function parse(text: string): PlannedToolCall | string {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return "Not valid JSON.";
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return 'Expected {"server", "tool", "arguments"}.';
  }
  const { server, tool, arguments: args } = value as Record<string, unknown>;
  if (typeof server !== "string" || typeof tool !== "string") {
    return "server and tool must be strings.";
  }
  if (args !== undefined && (typeof args !== "object" || args === null || Array.isArray(args))) {
    return "arguments must be a JSON object.";
  }
  return { server, tool, arguments: (args ?? {}) as PlannedToolCall["arguments"] };
}

/** Edits a call as JSON. The server checks it against the allow-list, schema and policy. */
export function CallEditor({
  call,
  onSave,
  onCancel,
}: {
  call: ToolCall | null | undefined;
  onSave: (call: PlannedToolCall) => void;
  onCancel: () => void;
}) {
  const id = useId();
  const [text, setText] = useState(() => draftOf(call));
  const [problem, setProblem] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parse(text);
    if (typeof parsed === "string") {
      setProblem(parsed);
      return;
    }
    setProblem(null);
    onSave(parsed);
  };

  return (
    <form onSubmit={submit} className="space-y-1" aria-label="Edit call">
      <label htmlFor={id} className="text-sm font-medium">
        Call (JSON). Saving clears all approvals.
      </label>
      <textarea
        id={id}
        value={text}
        rows={6}
        spellCheck={false}
        onChange={(event) => setText(event.target.value)}
        className="w-full rounded border border-slate-300 p-2 font-mono text-xs"
      />
      {problem && (
        <p role="alert" className="text-sm text-red-700">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary px-3 py-1 text-sm">
          Save call
        </button>
        <button type="button" onClick={onCancel} className="rounded px-3 py-1 text-sm underline">
          Cancel
        </button>
      </div>
    </form>
  );
}
