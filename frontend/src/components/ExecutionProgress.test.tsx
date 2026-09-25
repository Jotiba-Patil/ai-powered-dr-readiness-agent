import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Execution } from "../api/types";
import { callingTools } from "../lib/executionLabels";
import { executionApiStubs, makeExecution, makeStep } from "../test/executionFixtures";
import { makeApi, makeReport } from "../test/fixtures";
import { ExecutionSection } from "./ExecutionSection";

afterEach(() => window.localStorage.clear());

/** A request that stays pending until the test calls `finish`. */
function pending() {
  let finish: (execution: Execution) => void = () => undefined;
  const promise = new Promise<Execution>((resolve) => {
    finish = resolve;
  });
  return { call: vi.fn(() => promise), finish };
}

async function renderSection(overrides = {}) {
  const api = makeApi({ ...executionApiStubs(), ...overrides });
  render(<ExecutionSection api={api} jobId="job-1" report={makeReport()} pollIntervalMs={10} />);
  await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
  return api;
}

describe("execution progress", () => {
  it("says a run is being created while the buttons are disabled", async () => {
    const create = pending();
    await renderSection({ createExecution: create.call });
    await userEvent.click(screen.getByRole("button", { name: "Create live run" }));
    const note = await screen.findByText(/Creating the live run… \(\d+ s\)/);
    expect(note.closest("[role=status]")).toHaveTextContent(/proposed by the AI/);
    expect(screen.getByRole("button", { name: "Create dry run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create live run" })).toBeDisabled();
    create.finish(makeExecution());
    expect(await screen.findByRole("article", { name: "Step 1" })).toBeInTheDocument();
    expect(screen.queryByText(/Creating the live run/)).not.toBeInTheDocument();
  });

  it("clears the previous run while a new one is being created", async () => {
    const create = pending();
    const finished = makeExecution({ id: "exec-live", state: "COMPLETED", mode: "live" });
    const api = await renderSection({ getExecution: vi.fn(async () => finished) });
    await userEvent.click(await screen.findByRole("button", { name: /exec-1/ }));
    expect(await screen.findByRole("article", { name: "Step 1" })).toBeInTheDocument();
    api.createExecution = create.call;
    await userEvent.click(screen.getByRole("button", { name: "Create dry run" }));
    expect(await screen.findByText(/Creating the dry run/)).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Step 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Runs of this analysis" })).toBeInTheDocument();
    create.finish(makeExecution({ id: "exec-dry" }));
    expect(await screen.findByRole("article", { name: "Step 1" })).toBeInTheDocument();
  });

  it("says which decision is being sent", async () => {
    const approve = pending();
    await renderSection({ approveStep: approve.call });
    await userEvent.click(screen.getByRole("button", { name: "Create dry run" }));
    const [button] = await screen.findAllByRole("button", { name: "Approve" });
    if (!button) throw new Error("no Approve button");
    await userEvent.click(button);
    expect(await screen.findByText(/Recording your approval of step 1…/)).toBeInTheDocument();
    approve.finish(makeExecution());
    await screen.findByRole("article", { name: "Step 1" });
    expect(screen.queryByText(/Recording your approval/)).not.toBeInTheDocument();
  });

  it("says tool calls are running in the background", async () => {
    const running = makeExecution({ state: "RUNNING", steps: [makeStep({ state: "RUNNING" })] });
    const stubs = executionApiStubs(running);
    await renderSection(stubs);
    await userEvent.click(screen.getByRole("button", { name: "Create dry run" }));
    expect(await screen.findByText(/Run in progress: tool calls are running/)).toBeInTheDocument();
  });

  it("knows when the server is calling tools and when it waits for a person", () => {
    const waiting = makeExecution({
      state: "RUNNING",
      steps: [
        makeStep({ state: "AWAITING_MANUAL" }),
        makeStep({ stepNumber: 2, state: "VERIFYING", verify: null }),
      ],
    });
    expect(callingTools(waiting)).toBe(false);
    const step = makeStep({ state: "VERIFYING" });
    const verifying = makeExecution({ state: "RUNNING", steps: [{ ...step, verify: step.call }] });
    expect(callingTools(verifying)).toBe(true);
    expect(
      callingTools(makeExecution({ state: "PAUSED", steps: [makeStep({ state: "RUNNING" })] })),
    ).toBe(false);
  });
});
