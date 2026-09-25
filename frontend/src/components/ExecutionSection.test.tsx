import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { App } from "../App";
import { executionApiStubs, makeExecution } from "../test/executionFixtures";
import { makeApi, makeReport } from "../test/fixtures";
import { ExecutionSection } from "./ExecutionSection";

afterEach(() => window.localStorage.clear());

const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));
/** The first step's Approve button (every step awaiting approval has one). */
const firstApprove = async () => {
  const [button] = await screen.findAllByRole("button", { name: "Approve" });
  if (!button) throw new Error("no Approve button");
  return button;
};

async function analyzeSample(api = makeApi()) {
  render(<App api={api} pollIntervalMs={0} />);
  await userEvent.selectOptions(
    await screen.findByLabelText("Sample runbook"),
    "runbooks/payment-gateway.md",
  );
  await click("Analyze runbook");
  await screen.findByLabelText("Readiness report");
  return api;
}

describe("execution after analysis", () => {
  it("is offered only under a finished report, with no separate tab", async () => {
    render(<App api={makeApi()} pollIntervalMs={0} />);
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Execute this runbook…" })).not.toBeInTheDocument();
    await userEvent.selectOptions(
      await screen.findByLabelText("Sample runbook"),
      "runbooks/payment-gateway.md",
    );
    await click("Analyze runbook");
    await click("Execute this runbook…");
    expect(screen.getByRole("region", { name: "Execute this runbook" })).toBeInTheDocument();
  });

  it("creates runs from the analysis job and approves as the typed name", async () => {
    const api = await analyzeSample();
    await click("Execute this runbook…");
    expect(await screen.findByText(/Identity not verified/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("rated this runbook HIGH risk (72)");
    expect(screen.getByRole("button", { name: "Create dry run" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Your name"), "Ann");
    await click("Create dry run");
    expect(api.createExecution).toHaveBeenCalledWith({
      analysisJobId: "job-1",
      mode: "dry_run",
      startedBy: "Ann",
    });
    expect(await screen.findByRole("article", { name: "Step 2" })).toBeInTheDocument();
    await userEvent.click(await firstApprove());
    expect(api.approveStep).toHaveBeenCalledWith("exec-1", 1, {
      approver: "Ann",
      callHash: "a".repeat(64),
      kind: "main",
    });
    // The stub execution still has unapproved steps: the run cannot start yet.
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Abort run" })).toBeDisabled();
    await click("Load and verify");
    expect(await screen.findByText(/Hash chain verified/)).toBeInTheDocument();
    expect(window.localStorage.getItem("dr-agent.approver-name")).toBe("Ann");
  });
});

describe("ExecutionSection", () => {
  const report = makeReport({ riskLevel: "LOW", riskScore: 10 });

  it("explains that execution is off", async () => {
    const api = makeApi({
      executionSettings: vi.fn(async () => ({
        ...(await executionApiStubs().executionSettings()),
        enabled: false,
      })),
    });
    render(<ExecutionSection api={api} jobId="job-1" report={report} />);
    expect(await screen.findByText(/turned off on this server/)).toBeInTheDocument();
  });

  it("reports settings that cannot be loaded", async () => {
    const api = makeApi({ executionSettings: vi.fn().mockRejectedValue(new Error("offline")) });
    render(<ExecutionSection api={api} jobId="job-1" report={report} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  });

  it("lists only this analysis's runs and shows refusals", async () => {
    const approveStep = vi
      .fn()
      .mockRejectedValue(new ApiError("the call changed", "STALE_CALL", 409));
    const api = makeApi({ approveStep });
    render(<ExecutionSection api={api} jobId="job-1" report={report} />);
    expect(screen.queryByRole("note")).not.toBeInTheDocument(); // LOW risk: no warning
    await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
    await userEvent.click(screen.getByRole("button", { name: /exec-1/ }));
    await userEvent.click(await firstApprove());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("STALE_CALL · HTTP 409");
    await click("Dismiss");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    render(<ExecutionSection api={makeApi()} jobId="job-2" report={report} />);
    expect(await screen.findAllByText("None yet.")).toHaveLength(1);
  });

  it("disables live runs the server does not allow and actions without a name", async () => {
    const stubs = executionApiStubs(makeExecution({ state: "RUNNING" }));
    const api = makeApi({
      ...stubs,
      executionSettings: vi.fn(async () => ({
        ...(await stubs.executionSettings()),
        allowLive: false,
      })),
    });
    render(<ExecutionSection api={api} jobId="job-1" report={report} />);
    expect(await screen.findByRole("button", { name: "Create live run" })).toBeDisabled();
    expect(screen.getByText("Live runs are off on this server.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /exec-1/ }));
    expect(await screen.findByRole("button", { name: "Abort run" })).toBeDisabled();
  });

  it("disables the button of a mode whose run already completed", async () => {
    const stubs = executionApiStubs(makeExecution({ state: "COMPLETED", mode: "dry_run" }));
    render(<ExecutionSection api={makeApi(stubs)} jobId="job-1" report={report} />);
    await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
    expect(await screen.findByText("Dry run completed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create dry run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create live run" })).toBeEnabled();
  });

  it.each([
    ["FAILED", true],
    ["ABORTED", true],
    ["COMPLETED", false],
  ] as const)(
    "keeps live runs possible until one completes (last live run %s)",
    async (state, enabled) => {
      const stubs = executionApiStubs(makeExecution({ state, mode: "live" }));
      render(<ExecutionSection api={makeApi(stubs)} jobId="job-1" report={report} />);
      await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
      await screen.findByRole("button", { name: /exec-1/ });
      const live = screen.getByRole("button", { name: "Create live run" });
      if (enabled) {
        expect(live).toBeEnabled();
        expect(screen.queryByText("Live run completed.")).not.toBeInTheDocument();
      } else {
        expect(live).toBeDisabled();
        expect(screen.getByText("Live run completed.")).toBeInTheDocument();
      }
    },
  );
});
