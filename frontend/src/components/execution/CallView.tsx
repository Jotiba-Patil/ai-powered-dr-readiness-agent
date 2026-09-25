import type { ToolCall } from "../../api/types";
import { RISK_CLASS_TONES, SOURCE_LABELS, approvalsNeeded } from "../../lib/executionLabels";
import { Badge } from "../Badge";

const KIND_LABELS = { main: "Call", verify: "Verify", rollback: "Rollback" } as const;

/** One tool call exactly as it would run: server, tool, arguments, risk, origin, approvals. */
export function CallView({
  call,
  approvalsByRisk,
}: {
  call: ToolCall;
  approvalsByRisk: Record<string, number>;
}) {
  const needed = approvalsNeeded(call, approvalsByRisk);
  const names = (call.approvals ?? []).map((a) => a.approver).join(", ");
  const result = call.result;
  return (
    <div className="rounded border border-slate-200 bg-slate-50 p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{KIND_LABELS[call.kind]}</span>
        <code className="font-mono">
          {call.server}/{call.tool}
        </code>
        {call.riskClass ? (
          <Badge tone={RISK_CLASS_TONES[call.riskClass]} />
        ) : (
          <span className="text-xs font-semibold text-red-700">Not allowed by policy</span>
        )}
        <span className="rounded bg-white px-1.5 py-0.5 text-xs text-slate-600 ring-1 ring-slate-300">
          {SOURCE_LABELS[call.source]}
        </span>
        {call.kind !== "verify" && needed > 0 && (
          <span className="text-xs text-slate-600">
            Approvals {(call.approvals ?? []).length}/{needed}
            {names && ` (${names})`}
          </span>
        )}
      </div>
      <pre className="mt-1 overflow-x-auto font-mono text-xs">
        {JSON.stringify(call.arguments ?? {}, null, 2)}
      </pre>
      {result && (
        <p className={`mt-1 text-xs ${result.ok ? "text-emerald-800" : "text-red-800"}`}>
          <span aria-hidden="true">{result.ok ? "✔ " : "✖ "}</span>
          {result.simulated ? "Simulated: " : "Result: "}
          <span className="whitespace-pre-wrap">{result.content}</span>
        </p>
      )}
      {call.error && !result && (
        <p className="mt-1 text-xs text-red-800">
          <span aria-hidden="true">✖ </span>
          {call.error}
        </p>
      )}
    </div>
  );
}
