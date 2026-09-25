import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeCall, makeExecution } from "../../test/executionFixtures";
import { AuditPanel } from "./AuditPanel";
import { CallEditor } from "./CallEditor";
import { ExecutionControls } from "./ExecutionControls";
import { ExecutionHeader } from "./ExecutionHeader";

const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

describe("CallEditor", () => {
  it.each([
    ["[]", 'Expected {"server", "tool", "arguments"}.'],
    ['{"server": 1, "tool": "t"}', "server and tool must be strings."],
    ['{"server": "s", "tool": "t", "arguments": [1]}', "arguments must be a JSON object."],
  ])("rejects %s", async (text, problem) => {
    render(<CallEditor call={null} onSave={vi.fn()} onCancel={vi.fn()} />);
    const box = screen.getByLabelText(/Call \(JSON\)/);
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste(text);
    await click("Save call");
    expect(screen.getByRole("alert")).toHaveTextContent(problem);
  });

  it("saves a valid call", async () => {
    const onSave = vi.fn();
    render(<CallEditor call={makeCall()} onSave={onSave} onCancel={vi.fn()} />);
    await click("Save call");
    expect(onSave).toHaveBeenCalledWith({
      server: "drsim",
      tool: "cache_ping",
      arguments: { cache: "pricing-cache" },
    });
  });
});

describe("ExecutionHeader", () => {
  it("shows mode, state and the pause reason", () => {
    const { rerender } = render(<ExecutionHeader execution={makeExecution()} maxToolCalls={50} />);
    expect(screen.getByText("DRY RUN")).toBeInTheDocument();
    rerender(
      <ExecutionHeader
        execution={makeExecution({ state: "PAUSED", mode: "live", pauseReason: "step 2 failed" })}
        maxToolCalls={50}
      />,
    );
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("Paused: step 2 failed")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument(); // controls live below the steps
  });
});

describe("ExecutionControls", () => {
  const approved = makeExecution({
    steps: makeExecution().steps.map((step) =>
      step.state === "AWAITING_APPROVAL" ? { ...step, state: "APPROVED" as const } : step,
    ),
  });

  it("keeps Start disabled until every step is approved, and Abort until started", () => {
    render(
      <ExecutionControls execution={makeExecution()} disabled={false} onLifecycle={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Abort run" })).toBeDisabled();
    expect(screen.getByText(/2 still waiting \(step 1, 2\)/)).toBeInTheDocument();
  });

  it("starts once all steps are approved (manual steps need no approval)", async () => {
    const onLifecycle = vi.fn();
    render(<ExecutionControls execution={approved} disabled={false} onLifecycle={onLifecycle} />);
    expect(
      screen.getByText("All steps are approved. Start the run when ready."),
    ).toBeInTheDocument();
    await click("Start run");
    expect(onLifecycle).toHaveBeenCalledWith("start", "");
  });

  it("offers pause, close and abort with a reason once started, and resume when paused", async () => {
    const onLifecycle = vi.fn();
    const { rerender } = render(
      <ExecutionControls
        execution={makeExecution({ state: "RUNNING" })}
        disabled={false}
        onLifecycle={onLifecycle}
      />,
    );
    expect(screen.queryByRole("button", { name: "Start run" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Reason"), "drill over");
    await click("Abort run");
    expect(onLifecycle).toHaveBeenCalledWith("abort", "drill over");
    await click("Pause");
    rerender(
      <ExecutionControls
        execution={makeExecution({ state: "PAUSED" })}
        disabled={false}
        onLifecycle={onLifecycle}
      />,
    );
    await click("Resume");
    await click("Close as failed");
    expect(onLifecycle.mock.calls.map(([action]) => action)).toEqual([
      "abort",
      "pause",
      "resume",
      "close",
    ]);
  });

  it("shows the final state instead of buttons when the run is over", () => {
    render(
      <ExecutionControls
        execution={makeExecution({ state: "COMPLETED" })}
        disabled={false}
        onLifecycle={vi.fn()}
      />,
    );
    expect(screen.getByText(/This run is finished/)).toHaveTextContent("Completed");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("AuditPanel", () => {
  it("shows a verified and a broken chain", () => {
    const events = [
      {
        seq: 1,
        executionId: "e",
        type: "approval",
        actor: "Ann",
        payload: { step: 1 },
        prevHash: "0",
        hash: "1",
        createdAt: "2026-09-24T09:00:00Z",
      },
    ];
    const { rerender } = render(
      <AuditPanel
        audit={{ events, verification: { valid: true, head: "abc", events: 1 } }}
        error={null}
        onLoad={vi.fn()}
      />,
    );
    const panel = screen.getByRole("region", { name: "Audit log" });
    expect(within(panel).getByText(/Hash chain verified: 1 events/)).toBeInTheDocument();
    expect(panel).toHaveTextContent("approval by Ann");
    rerender(
      <AuditPanel
        audit={{ events, verification: { valid: false, head: "x", events: 1, brokenAtSeq: 1 } }}
        error="late"
        onLoad={vi.fn()}
      />,
    );
    expect(screen.getByText("Hash chain broken at event 1")).toBeInTheDocument();
    expect(screen.getByText("late")).toBeInTheDocument();
  });
});
