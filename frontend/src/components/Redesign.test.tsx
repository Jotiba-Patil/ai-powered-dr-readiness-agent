import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { runProgress } from "../lib/runProgress";
import { kpis, verdict } from "../lib/verdict";
import { makeExecution, makeStep } from "../test/executionFixtures";
import { makeApi, makeJob, makeReport } from "../test/fixtures";
import { makeHistory } from "../test/historyFixtures";

describe("verdict and key figures", () => {
  it("leads with the RTO when it is missed, then with risk", () => {
    expect(verdict(makeReport())).toEqual({
      headline: "Not ready: recovery takes 45 min, the RTO is 30 min.",
      mood: "bad",
    });
    const fits = makeReport({
      rtoAnalysis: { ...makeReport().rtoAnalysis, feasible: true, bufferMinutes: 10 },
    });
    expect(verdict({ ...fits, riskLevel: "MEDIUM" }).mood).toBe("watch");
    expect(verdict({ ...fits, riskLevel: "LOW" }).headline).toMatch(/^Ready/);
    expect(verdict({ ...fits, riskLevel: "HIGH" }).mood).toBe("bad");
  });

  it("summarises timing, dependencies, gaps, SPOFs and history", () => {
    const tiles = kpis(makeReport({ historicalInsights: makeHistory() }));
    expect(tiles.map((t) => [t.label, t.value, t.detail])).toEqual([
      ["Recovery time", "45 min / 30 min", "15 min over the RTO"],
      ["Dependencies", "1 of 3 up", "2 not confirmed up"],
      ["Gaps", "3", "1 high severity"],
      ["Single points of failure", "1", "people or systems with no backup"],
      ["Track record", "2 live runs", "3 earlier analysis(es)"],
    ]);
    expect(tiles[0]?.anchor).toBe("sec-rto-feasibility");
  });

  it("groups run progress the way people read it", () => {
    const run = makeExecution({
      steps: [
        makeStep({ state: "SUCCEEDED" }),
        makeStep({ stepNumber: 2, state: "AWAITING_MANUAL" }),
        makeStep({ stepNumber: 3, state: "RUNNING" }),
        makeStep({ stepNumber: 4, state: "ROLLED_BACK" }),
        makeStep({ stepNumber: 5, state: "APPROVED" }),
        makeStep({ stepNumber: 6, state: "VERIFYING", verify: null }),
      ],
    });
    expect(runProgress(run)).toEqual({
      done: 1,
      needsYou: 2,
      running: 1,
      failed: 1,
      ready: 1,
      total: 6,
    });
  });
});

describe("app shell and flow", () => {
  it("shows what the server allows in the header", async () => {
    render(<App api={makeApi()} pollIntervalMs={0} />);
    const status = screen.getByLabelText("Server status");
    expect(await within(status).findByText("API online · v0.1.0")).toBeInTheDocument();
    expect(await within(status).findByText("Live runs enabled")).toBeInTheDocument();
  });

  it("reports an unreachable API and a server without execution", async () => {
    const api = makeApi({
      health: vi.fn().mockRejectedValue(new Error("down")),
      executionSettings: vi.fn(async () => ({
        enabled: false,
        allowLive: false,
        approvalTimeoutMinutes: 30,
        maxToolCalls: 50,
        approvalsByRisk: {},
        identityVerified: false as const,
      })),
    });
    render(<App api={api} pollIntervalMs={0} />);
    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
    expect(await screen.findByText("Execution off")).toBeInTheDocument();
  });

  it("walks the journey, folds the input, and starts over from scratch", async () => {
    const pasted = makeReport({
      meta: { ...makeReport().meta, runbookFile: "request-body.md", inventoryFile: "(none)" },
    });
    const api = makeApi({
      pollJob: vi.fn(async () => makeJob({ status: "succeeded", report: pasted })),
    });
    render(<App api={api} pollIntervalMs={0} />);
    const steps = screen.getByRole("list", { name: "Progress" });
    expect(within(steps).getAllByRole("listitem")[0]).toHaveAttribute("aria-current", "step");
    await userEvent.type(screen.getByLabelText("Runbook (Markdown)"), "# Svc");
    await userEvent.click(screen.getByRole("button", { name: "Analyze runbook" }));
    await screen.findByLabelText("Readiness report");
    expect(within(steps).getAllByRole("listitem")[2]).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/Report for/)).toHaveTextContent(
      "Report for pasted runbook without an inventory",
    );
    expect(screen.getByRole("form", { name: "Analysis input", hidden: true })).not.toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Analyze another runbook" }));
    // A fresh start: step 1, empty editors, no report and no execution section.
    expect(screen.getByRole("form", { name: "Analysis input" })).toBeVisible();
    expect(screen.getByLabelText("Runbook (Markdown)")).toHaveValue("");
    expect(screen.queryByLabelText("Readiness report")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Execute this runbook…" })).not.toBeInTheDocument();
    expect(within(steps).getAllByRole("listitem")[0]).toHaveAttribute("aria-current", "step");
  });

  it("ticks the execution step once a run of this analysis has completed", async () => {
    const completed = {
      id: "exec-9",
      analysisJobId: "job-1",
      state: "COMPLETED" as const,
      mode: "live" as const,
      runbookLabel: "payment-gateway.md",
      startedBy: "Ann",
      createdAt: "2026-09-25T09:00:00Z",
      updatedAt: "2026-09-25T09:30:00Z",
      steps: 3,
    };
    const api = makeApi({ listExecutions: vi.fn(async () => [completed]) });
    render(<App api={api} pollIntervalMs={0} />);
    await userEvent.type(screen.getByLabelText("Runbook (Markdown)"), "# Svc");
    await userEvent.click(screen.getByRole("button", { name: "Analyze runbook" }));
    const steps = screen.getByRole("list", { name: "Progress" });
    const execution = () => within(steps).getAllByRole("listitem")[2];
    await userEvent.click(await screen.findByRole("button", { name: "Execute this runbook…" }));
    await screen.findByText("Live run completed.");
    await waitFor(() => expect(execution()).toHaveTextContent("ExecutionDone"));
    expect(execution()).not.toHaveAttribute("aria-current");
  });

  it("says a run is in progress before any run completes", async () => {
    render(<App api={makeApi()} pollIntervalMs={0} />);
    await userEvent.type(screen.getByLabelText("Runbook (Markdown)"), "# Svc");
    await userEvent.click(screen.getByRole("button", { name: "Analyze runbook" }));
    await userEvent.click(await screen.findByRole("button", { name: "Execute this runbook…" }));
    const steps = screen.getByRole("list", { name: "Progress" });
    expect(await within(steps).findByText("Run in progress")).toBeInTheDocument();
  });
});
