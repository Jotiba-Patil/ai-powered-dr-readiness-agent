import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeReport } from "../test/fixtures";
import { ReportView } from "./ReportView";

const HTML_URL = "http://api.test/api/v1/dr/jobs/job-1/report.html";

afterEach(() => vi.restoreAllMocks());

describe("ReportView", () => {
  it("renders every report section", () => {
    render(<ReportView report={makeReport()} htmlUrl={HTML_URL} />);
    for (const title of [
      "Executive summary",
      "RTO feasibility",
      "Dependency health",
      "Single points of failure",
      "Gap analysis",
      "Execution plan",
      "Suggestions",
    ]) {
      expect(screen.getByRole("region", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByRole("figure", { name: "Risk score 72 of 100" })).toBeInTheDocument();
    expect(screen.getByText("High risk")).toBeInTheDocument();
    expect(screen.getByText("The runbook cannot meet its RTO.")).toBeInTheDocument();
    expect(screen.getByText("Only Bob can fail over")).toBeInTheDocument();
    expect(screen.queryByText(/AI analysis unavailable/)).not.toBeInTheDocument();
  });

  it("shows the AI-unavailable banner with the note", () => {
    const report = makeReport({ aiAnalysisAvailable: false, aiNote: "Ollama timed out" });
    render(<ReportView report={report} htmlUrl={HTML_URL} />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("AI analysis unavailable");
    expect(banner).toHaveTextContent("Ollama timed out");
  });

  it("orders suggestions by priority and marks parallel phases", () => {
    render(<ReportView report={makeReport()} htmlUrl={HTML_URL} />);
    const items = within(screen.getByRole("region", { name: "Suggestions" })).getAllByRole(
      "listitem",
    );
    expect(items[0]).toHaveTextContent("Rehearse failover");
    const plan = screen.getByRole("region", { name: "Execution plan" });
    expect(within(plan).getByText(/steps 1, 2/)).toHaveTextContent("(in parallel)");
  });

  it("renders empty states for empty lists", () => {
    const report = makeReport({
      dependencyHealth: [],
      singlePointsOfFailure: [],
      gapAnalysis: [],
      executionPlan: [],
      suggestions: [],
    });
    render(<ReportView report={report} htmlUrl={HTML_URL} />);
    expect(screen.getByText("The runbook declares no dependencies.")).toBeInTheDocument();
    expect(screen.getByText("No single points of failure identified.")).toBeInTheDocument();
    expect(screen.getByText("No gaps found.")).toBeInTheDocument();
    expect(screen.getByText("No recovery steps to plan.")).toBeInTheDocument();
    expect(screen.getByText("No suggestions.")).toBeInTheDocument();
  });

  it("exports JSON through a download and links the HTML export", async () => {
    const createObjectURL = vi.fn(() => "blob:report");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ReportView report={makeReport()} htmlUrl={HTML_URL} />);
    await userEvent.click(screen.getByRole("button", { name: "Export JSON" }));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
    expect(screen.getByRole("link", { name: "Export HTML" })).toHaveAttribute("href", HTML_URL);
  });
});
