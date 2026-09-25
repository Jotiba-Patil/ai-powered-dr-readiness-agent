import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { StepRun } from "../../api/types";
import { makeCall, makeStep } from "../../test/executionFixtures";
import type { StepHandlers } from "./handlers";
import { StepCard } from "./StepCard";

const BY_RISK = { read: 1, write: 1, destructive: 2 };

function renderStep(step: StepRun, locked = false) {
  const handlers: StepHandlers = { approve: vi.fn(), decide: vi.fn(), setCall: vi.fn() };
  render(
    <StepCard
      step={step}
      approvalsByRisk={BY_RISK}
      handlers={handlers}
      disabled={false}
      locked={locked}
    />,
  );
  return handlers;
}

const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

describe("StepCard", () => {
  it("shows the exact call with risk, source and approvals, and approves by hash", async () => {
    const step = makeStep({
      call: makeCall({
        riskClass: "destructive",
        approvals: [{ approver: "Ann", callHash: "a".repeat(64), createdAt: "t" }],
      }),
    });
    const handlers = renderStep(step);
    const card = screen.getByRole("article", { name: "Step 1" });
    expect(card).toHaveTextContent("drsim/cache_ping");
    expect(card).toHaveTextContent('"cache": "pricing-cache"');
    expect(card).toHaveTextContent("Destructive");
    expect(card).toHaveTextContent("Annotated");
    expect(card).toHaveTextContent("Approvals 1/2 (Ann)");
    await click("Approve");
    expect(handlers.approve).toHaveBeenCalledWith(step, "main", "a".repeat(64));
  });

  it("sends the reason with reject and skip", async () => {
    const handlers = renderStep(makeStep());
    await userEvent.type(screen.getByLabelText("Reason / note"), "wrong region");
    await click("Reject");
    await click("Skip");
    expect(handlers.decide).toHaveBeenCalledWith(expect.anything(), "reject", {
      reason: "wrong region",
      succeeded: undefined,
    });
    expect(handlers.decide).toHaveBeenLastCalledWith(expect.anything(), "skip", expect.anything());
  });

  it("offers accept for an AI proposal and shows its rationale as unverified text", async () => {
    const step = makeStep({
      state: "PROPOSED",
      call: makeCall({ source: "ai_proposed" }),
      proposal: { rationale: "<b>trust me</b>", confidence: "high" },
    });
    const handlers = renderStep(step);
    expect(screen.getByText(/AI rationale \(not verified\)/)).toBeInTheDocument();
    expect(screen.getByText(/<b>trust me<\/b>/)).toBeInTheDocument();
    expect(screen.getByText("AI-proposed")).toBeInTheDocument();
    await click("Accept proposal");
    expect(handlers.setCall).toHaveBeenCalledWith(step, "main", null);
    await click("Make manual");
    expect(handlers.decide).toHaveBeenCalledWith(step, "manual", expect.anything());
  });

  it("offers retry and a separately approved rollback for a failed step", async () => {
    const rollback = makeCall({ kind: "rollback", callHash: "c".repeat(64) });
    const step = makeStep({
      state: "FAILED",
      rollback,
      call: makeCall({ error: "crashloop", result: null }),
    });
    const handlers = renderStep(step);
    expect(screen.getByText("crashloop")).toBeInTheDocument();
    await click("Retry");
    await click("Approve rollback");
    await click("Roll back");
    expect(handlers.approve).toHaveBeenCalledWith(step, "rollback", "c".repeat(64));
    expect(handlers.decide).toHaveBeenCalledWith(step, "rollback", expect.anything());
  });

  it("asks a person to confirm steps without a verify tool, and to mark manual steps done", async () => {
    const handlers = renderStep(makeStep({ state: "VERIFYING", verify: null }));
    await click("Report failure");
    expect(handlers.decide).toHaveBeenCalledWith(expect.anything(), "verify", {
      reason: "",
      succeeded: false,
    });
    renderStep(makeStep({ stepNumber: 3, state: "AWAITING_MANUAL", call: null }));
    expect(screen.getByRole("button", { name: "Mark done" })).toBeInTheDocument();
  });

  it("shows results and no actions once finished or when the execution is closed", () => {
    renderStep(
      makeStep({
        state: "SUCCEEDED",
        call: makeCall({ result: { ok: true, content: "pong", simulated: true } }),
      }),
    );
    expect(screen.getByText(/Simulated:/)).toHaveTextContent("pong");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    renderStep(makeStep({ stepNumber: 2 }), true);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("edits a call through the JSON editor", async () => {
    const handlers = renderStep(makeStep());
    await click("Edit call");
    const box = screen.getByLabelText(/Call \(JSON\)/);
    await userEvent.clear(box);
    await userEvent.type(box, "not json");
    await click("Save call");
    expect(screen.getByRole("alert")).toHaveTextContent("Not valid JSON.");
    await click("Cancel");
    expect(handlers.setCall).not.toHaveBeenCalled();
  });
});
