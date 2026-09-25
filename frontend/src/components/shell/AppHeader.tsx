import type { ServerStatus } from "../../hooks/useServerStatus";
import { Icon, type IconName } from "../ui/Icon";

export type View = "analyze" | "history";

const TABS: { view: View; label: string; icon: IconName; hint: string }[] = [
  { view: "analyze", label: "Analyze", icon: "pulse", hint: "Check a runbook and run it" },
  { view: "history", label: "History", icon: "history", hint: "Past reports and runs" },
];

function Chip({ tone, children }: { tone: "ok" | "warn" | "off" | "wait"; children: string }) {
  const styles = {
    ok: "bg-emerald-400/15 text-emerald-200 ring-emerald-300/30",
    warn: "bg-amber-400/15 text-amber-100 ring-amber-300/30",
    off: "bg-white/5 text-slate-300 ring-white/15",
    wait: "bg-white/5 text-slate-400 ring-white/10",
  }[tone];
  const dot = {
    ok: "bg-emerald-400",
    warn: "bg-amber-400",
    off: "bg-slate-500",
    wait: "bg-slate-600",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${styles}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${dot[tone]}`} />
      {children}
    </span>
  );
}

function executionChip(status: ServerStatus) {
  const exec = status.execution;
  if (!exec) return <Chip tone="wait">Execution: checking…</Chip>;
  if (!exec.enabled) return <Chip tone="off">Execution off</Chip>;
  return exec.allowLive ? (
    <Chip tone="warn">Live runs enabled</Chip>
  ) : (
    <Chip tone="ok">Dry runs only</Chip>
  );
}

/** Command bar: product mark, the two views, and what this server allows right now. */
export function AppHeader({
  view,
  onView,
  status,
}: {
  view: View;
  onView: (view: View) => void;
  status: ServerStatus;
}) {
  const api =
    status.online === null ? (
      <Chip tone="wait">API: checking…</Chip>
    ) : status.online ? (
      <Chip tone="ok">{`API online${status.version ? ` · v${status.version}` : ""}`}</Chip>
    ) : (
      <Chip tone="off">API unreachable</Chip>
    );
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-ink-950/95 text-white backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-signal-400 to-signal-700 shadow-lg shadow-signal-500/20">
            <Icon name="shield" className="h-5 w-5 text-white" />
          </span>
          <div>
            <h1 className="text-lg leading-tight font-semibold">DR Readiness Agent</h1>
            <p className="text-xs text-slate-400">
              Will this runbook bring the service back in time?
            </p>
          </div>
        </div>
        <nav aria-label="Views" className="flex gap-1 rounded-lg bg-white/5 p-1">
          {TABS.map((tab) => {
            const current = view === tab.view;
            return (
              <button
                key={tab.view}
                type="button"
                title={tab.hint}
                aria-current={current ? "page" : undefined}
                onClick={() => onView(tab.view)}
                className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  current ? "bg-white text-ink-900 shadow" : "text-slate-300 hover:bg-white/10"
                }`}
              >
                <Icon name={tab.icon} />
                {tab.label}
              </button>
            );
          })}
        </nav>
        <div className="ml-auto flex flex-wrap items-center gap-2" aria-label="Server status">
          {api}
          {executionChip(status)}
        </div>
      </div>
    </header>
  );
}
