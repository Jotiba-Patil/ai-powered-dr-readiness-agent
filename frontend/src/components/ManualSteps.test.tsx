import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { executionApiStubs, makeExecution, makeStep } from "../test/executionFixtures";
import { makeApi, makeReport } from "../test/fixtures";
import { ExecutionSection } from "./ExecutionSection";

afterEach(() => window.localStorage.clear());

// Like an order-service run: the AI found no tool, so every step waits for manual work.
const manualRun = makeExecution({
  state: "CREATED",
  mode: "live",
  steps: [
    makeStep({ state: "AWAITING_MANUAL", call: null }),
    makeStep({ stepNumber: 2, phase: 2, state: "AWAITING_MANUAL", call: null, dependsOn: [1] }),
  ],
});

async function createRun() {
  const api = makeApi(executionApiStubs(manualRun));
  render(<ExecutionSection api={api} jobId="job-1" report={makeReport()} />);
  await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
  await userEvent.click(screen.getByRole("button", { name: "Create live run" }));
  return { api, step1: await screen.findByRole("article", { name: "Step 1" }) };
}

describe("manual steps of a new run", () => {
  it("can be marked done or skipped as soon as the run is created", async () => {
    const { api, step1 } = await createRun();
    const markDone = within(step1).getByRole("button", { name: "Mark done" });
    expect(markDone).toBeEnabled();
    expect(within(step1).getByRole("button", { name: "Skip" })).toBeEnabled();
    await userEvent.type(within(step1).getByLabelText("Reason / note"), "declared in #inc-42");
    await userEvent.click(markDone);
    expect(api.decideStep).toHaveBeenCalledWith("exec-1", 1, "mark-done", {
      actor: "Ann",
      reason: "declared in #inc-42",
      succeeded: null,
    });
  });

  it("explains why the buttons are disabled without a name", async () => {
    const { step1 } = await createRun();
    await userEvent.clear(screen.getByLabelText("Your name"));
    expect(within(step1).getByRole("button", { name: "Mark done" })).toBeDisabled();
    expect(
      screen.getByText(/Enter your name above to approve, complete or skip steps/),
    ).toBeInTheDocument();
  });
});
