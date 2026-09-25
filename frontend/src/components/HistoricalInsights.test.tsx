import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { previousRuns } from "../lib/labels";
import { makeApi, makeReport } from "../test/fixtures";
import { makeHistory } from "../test/historyFixtures";
import { ExecutionSection } from "./ExecutionSection";
import { ReportView } from "./ReportView";

afterEach(() => window.localStorage.clear());

describe("HistoricalInsights", () => {
  it("shows measured history under the report", () => {
    render(<ReportView report={makeReport({ historicalInsights: makeHistory() })} htmlUrl="#" />);
    const section = screen.getByRole("region", { name: "Historical insights" });
    expect(section).toHaveTextContent("2 live run(s) and 3 earlier analysis(es)");
    expect(section).toHaveTextContent("1 dry run(s) are counted but not measured");
    const row = within(section).getByRole("row", { name: /^2 / });
    expect(row).toHaveTextContent("18 min (estimate 10 min) (over estimate)");
    expect(section).toHaveTextContent(
      "2026-09-24 10:00 UTC: COMPLETED in 42 min (over the 30 min RTO)",
    );
    expect(section).toHaveTextContent("payments-db: down or unreachable in 2 of 3 analyses");
    expect(section).not.toHaveTextContent("internal-dns");
  });

  it("is absent without history and brief without details", () => {
    const { unmount } = render(<ReportView report={makeReport()} htmlUrl="#" />);
    expect(screen.queryByRole("region", { name: "Historical insights" })).not.toBeInTheDocument();
    unmount();
    const empty = makeHistory({ steps: [], executions: [], dependencies: [], liveRuns: 0 });
    render(<ReportView report={makeReport({ historicalInsights: empty })} htmlUrl="#" />);
    const section = screen.getByRole("region", { name: "Historical insights" });
    expect(within(section).queryByRole("table")).not.toBeInTheDocument();
    expect(within(section).queryByRole("list")).not.toBeInTheDocument();
  });

  it("puts previous runs on the execution step cards", async () => {
    const report = makeReport({ historicalInsights: makeHistory() });
    render(<ExecutionSection api={makeApi()} jobId="job-1" report={report} pollIntervalMs={0} />);
    await userEvent.type(await screen.findByLabelText("Your name"), "Ann");
    await userEvent.click(screen.getByRole("button", { name: "Create dry run" }));
    const step2 = await screen.findByRole("article", { name: "Step 2" });
    expect(step2).toHaveTextContent(
      "Previous live runs: 2, failed 1, rolled back 1, median 18 min",
    );
    const step1 = screen.getByRole("article", { name: "Step 1" });
    expect(step1).not.toHaveTextContent("Previous live runs");
  });

  it("formats a step without measured time", () => {
    const [step] = makeHistory().steps ?? [];
    if (!step) throw new Error("fixture has a step");
    expect(previousRuns({ ...step, medianActiveMinutes: null })).toBe(
      "Previous live runs: 2, failed 1, rolled back 1",
    );
  });
});
