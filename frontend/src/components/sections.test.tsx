import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeReport } from "../test/fixtures";
import { waterfall } from "../lib/waterfall";
import { DependencyTable } from "./DependencyTable";
import { GapList } from "./GapList";
import { RtoTimeline } from "./RtoTimeline";

const report = makeReport();

describe("GapList", () => {
  it("filters gaps by severity", async () => {
    render(<GapList gaps={report.gapAnalysis ?? []} />);
    const region = screen.getByRole("region", { name: "Gap analysis" });
    expect(within(region).getAllByRole("listitem")).toHaveLength(3);

    await userEvent.click(screen.getByRole("button", { name: "Low (1)" }));
    await userEvent.click(screen.getByRole("button", { name: "Medium (1)" }));
    const items = within(region).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("Owner ambiguity");
    expect(screen.getByRole("button", { name: "Low (1)" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await userEvent.click(screen.getByRole("button", { name: "High (1)" }));
    expect(screen.getByText("No gaps match the selected severities.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Low (1)" }));
    expect(within(region).getByText("Step 1 is vague")).toBeInTheDocument();
  });
});

describe("DependencyTable", () => {
  it("shows each status as text, not only color", () => {
    render(<DependencyTable dependencies={report.dependencyHealth ?? []} />);
    const row = screen.getByRole("row", { name: /payments-db/ });
    expect(row).toHaveTextContent("Down");
    expect(screen.getByRole("row", { name: /card-network-gateway/ })).toHaveTextContent(
      "Not in inventory",
    );
    expect(screen.getByText("2 of 3 dependencies are not confirmed up.")).toBeInTheDocument();
  });
});

describe("RtoTimeline", () => {
  it("explains an infeasible RTO and its bottlenecks", () => {
    render(<RtoTimeline rto={report.rtoAnalysis} phases={report.executionPlan ?? []} />);
    expect(
      screen.getByText(/Not feasible: estimated 45 min against a stated RTO of 30 min/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Over the RTO by 15 min\. Bottleneck steps: 3\./)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /timeline against the RTO/ })).toBeInTheDocument();
  });

  it("shows the buffer when feasible and skips the chart without phases", () => {
    const rto = { ...report.rtoAnalysis, feasible: true, bufferMinutes: 7.5, bottleneckSteps: [] };
    render(<RtoTimeline rto={rto} phases={[]} />);
    expect(screen.getByText("Buffer: 7.5 min.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("stacks phases into a waterfall", () => {
    expect(waterfall(report.executionPlan ?? [], 45)).toEqual([
      { name: "Phase 1", start: 0, duration: 20, total: false },
      { name: "Phase 2", start: 20, duration: 25, total: false },
      { name: "Total", start: 0, duration: 45, total: true },
    ]);
  });
});
