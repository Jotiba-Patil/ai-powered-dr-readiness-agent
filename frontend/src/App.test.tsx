import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api/client";
import { App } from "./App";
import { ErrorPanel, LoadingPanel } from "./components/StatusPanel";
import { makeApi, makeJob, makeReport } from "./test/fixtures";

async function runSample(api = makeApi()) {
  render(<App api={api} pollIntervalMs={0} />);
  await userEvent.selectOptions(
    await screen.findByLabelText("Sample runbook"),
    "runbooks/payment-gateway.md",
  );
  await userEvent.click(screen.getByRole("button", { name: "Analyze runbook" }));
  return api;
}

describe("App", () => {
  it("runs the demo path: sample -> job -> report", async () => {
    const api = await runSample();
    const report = await screen.findByLabelText("Readiness report");
    expect(report).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Payment Gateway" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export HTML" })).toHaveAttribute(
      "href",
      "http://api.test/api/v1/dr/jobs/job-1/report.html",
    );
    expect(api.submitAnalysis).toHaveBeenCalledOnce();
  });

  it("says whether the report was saved to history", async () => {
    const saved = makeJob({ status: "succeeded", report: makeReport(), historySaved: true });
    await runSample(makeApi({ pollJob: vi.fn(async () => saved) }));
    expect(await screen.findByText("Saved to history.")).toBeInTheDocument();
  });

  it("warns when the report could not be saved", async () => {
    const unsaved = makeJob({ status: "succeeded", report: makeReport(), historySaved: false });
    await runSample(makeApi({ pollJob: vi.fn(async () => unsaved) }));
    expect(await screen.findByText(/Not saved to history/)).toBeInTheDocument();
  });

  it("switches to the history and back without losing the report", async () => {
    await runSample();
    await screen.findByLabelText("Readiness report");
    await userEvent.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByRole("heading", { name: "Stored analyses" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "History" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(screen.getByLabelText("Readiness report")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Stored analyses" })).not.toBeInTheDocument();
  });

  it("shows the rule-based-only state when AI is unavailable", async () => {
    const report = makeReport({ aiAnalysisAvailable: false, aiNote: "model offline" });
    await runSample(
      makeApi({ pollJob: vi.fn(async () => makeJob({ status: "succeeded", report })) }),
    );
    expect(await screen.findByText(/AI analysis unavailable/)).toBeInTheDocument();
  });

  it("shows an error and lets the user dismiss it", async () => {
    const submitAnalysis = vi.fn().mockRejectedValue(new ApiError("bad", "PARSE_ERROR", 422));
    await runSample(makeApi({ submitAnalysis }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("PARSE_ERROR · HTTP 422");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("StatusPanel", () => {
  it("counts elapsed seconds while a job runs", () => {
    vi.useFakeTimers();
    try {
      render(<LoadingPanel jobId="job-9" />);
      act(() => vi.advanceTimersByTime(3000));
      expect(screen.getByRole("status")).toHaveTextContent("Analyzing runbook… (3 s)");
      expect(screen.getByRole("status")).toHaveTextContent("Job job-9.");
    } finally {
      vi.useRealTimers();
    }
  });

  it("says submitting before a job exists and hides status 0 on errors", () => {
    render(<LoadingPanel jobId={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Submitting…");
    render(<ErrorPanel error={new ApiError("down", "NETWORK_ERROR", 0)} onDismiss={() => {}} />);
    expect(screen.getByRole("alert")).not.toHaveTextContent("HTTP");
  });
});
