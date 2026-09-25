import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { makeApi } from "../../test/fixtures";
import { makeDetail, makeSummary } from "../../test/historyFixtures";
import { HistoryView } from "./HistoryView";

const ROW = /Open Payment Gateway analysis from 2026-09-25 09:00 UTC/;

describe("HistoryView", () => {
  it("lists stored analyses and opens one with its report", async () => {
    const api = makeApi();
    render(<HistoryView api={api} />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Not feasible")).toBeInTheDocument();
    expect(within(table).getByText("72 High")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: ROW }));
    expect(await screen.findByRole("heading", { name: "Payment Gateway" })).toBeInTheDocument();
    expect(screen.getByText(/mistral-small-latest/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download runbook" })).toHaveAttribute(
      "href",
      "http://api.test/api/v1/analyses/job-1/runbook",
    );
    expect(screen.getByRole("link", { name: "Export HTML" })).toHaveAttribute(
      "href",
      "http://api.test/api/v1/analyses/job-1/report.html",
    );
    expect(api.getAnalysis).toHaveBeenCalledWith("job-1");
  });

  it("shows past executions read-only instead of offering to execute", async () => {
    const api = makeApi();
    render(<HistoryView api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: ROW }));
    const section = await screen.findByRole("region", { name: "Executions of this analysis" });
    expect(screen.queryByRole("button", { name: "Execute this runbook…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create (dry|live) run/ })).not.toBeInTheDocument();
    const runs = await within(section).findByRole("region", { name: "Runs of this analysis" });
    expect(runs).toHaveTextContent("payment-gateway.md · live · Olivia");
    await userEvent.click(within(runs).getByRole("button", { name: "exec-1" }));
    const details = await screen.findByLabelText("Execution details");
    expect(api.analysisExecution).toHaveBeenCalledWith("job-1", "exec-1");
    expect(within(details).getByText("LIVE")).toBeInTheDocument();
    expect(within(details).getByRole("article", { name: "Step 2" })).toBeInTheDocument();
    expect(within(details).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(within(details).getByText(/Hash chain verified: 1 events/)).toBeInTheDocument();
    await userEvent.click(within(details).getByRole("button", { name: "Refresh and verify" }));
    expect(api.analysisExecution).toHaveBeenCalledTimes(2);
    await userEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(screen.queryByLabelText("Execution details")).not.toBeInTheDocument();
  });

  it("explains when past executions cannot be listed", async () => {
    const analysisExecutions = vi.fn().mockRejectedValue(new ApiError("down", "INTERNAL", 500));
    render(<HistoryView api={makeApi({ analysisExecutions })} />);
    await userEvent.click(await screen.findByRole("button", { name: ROW }));
    const section = await screen.findByRole("region", { name: "Executions of this analysis" });
    expect(await within(section).findByRole("alert")).toHaveTextContent("down");
  });

  it("goes back to the list and refreshes it", async () => {
    const api = makeApi();
    render(<HistoryView api={api} />);
    await userEvent.click(await screen.findByRole("button", { name: ROW }));
    await userEvent.click(await screen.findByRole("button", { name: "← Back to history" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(api.listAnalyses).toHaveBeenCalledTimes(2);
  });

  it("filters by risk level and service", async () => {
    const api = makeApi();
    render(<HistoryView api={api} />);
    await screen.findByRole("table");
    await userEvent.selectOptions(screen.getByLabelText("Risk level"), "HIGH");
    await userEvent.type(await screen.findByLabelText("Service"), "Payment Gateway");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    await screen.findByRole("table");
    expect(api.listAnalyses).toHaveBeenLastCalledWith({
      service: "Payment Gateway",
      riskLevel: "HIGH",
      limit: 20,
      before: undefined,
    });
  });

  it("loads more pages", async () => {
    const listAnalyses = vi
      .fn()
      .mockResolvedValueOnce({ items: [makeSummary()], nextBefore: "2026-09-25T09:00:00Z" })
      .mockResolvedValueOnce({
        items: [makeSummary({ id: "job-0", completedAt: "2026-09-24T09:00:00Z" })],
        nextBefore: null,
      });
    render(<HistoryView api={makeApi({ listAnalyses })} />);
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByText("2026-09-24 09:00 UTC")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(listAnalyses).toHaveBeenLastCalledWith(
      expect.objectContaining({ before: "2026-09-25T09:00:00Z" }),
    );
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("explains an empty, disabled or failing history", async () => {
    const empty = vi.fn(async () => ({ items: [], nextBefore: null }));
    const { unmount } = render(<HistoryView api={makeApi({ listAnalyses: empty })} />);
    expect(await screen.findByText(/No stored analyses match/)).toBeInTheDocument();
    unmount();
    const off = vi.fn().mockRejectedValue(new ApiError("off", "HISTORY_DISABLED", 403));
    const second = render(<HistoryView api={makeApi({ listAnalyses: off })} />);
    expect(await screen.findByText(/turned off on this server/)).toBeInTheDocument();
    second.unmount();
    const broken = vi.fn().mockRejectedValue(new ApiError("boom", "INTERNAL_ERROR", 500));
    render(<HistoryView api={makeApi({ listAnalyses: broken })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("History unavailable: boom");
  });

  it("warns about stale analyses and shows load errors", async () => {
    const getAnalysis = vi
      .fn()
      .mockResolvedValueOnce(makeDetail({ stale: true }))
      .mockRejectedValueOnce(new ApiError("gone", "NOT_FOUND", 404));
    render(<HistoryView api={makeApi({ getAnalysis })} />);
    await userEvent.click(await screen.findByRole("button", { name: ROW }));
    expect(await screen.findByText(/Dependency health may have changed/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "← Back to history" }));
    await userEvent.click(await screen.findByRole("button", { name: ROW }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not open the analysis");
  });
});
