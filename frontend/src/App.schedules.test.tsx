import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { makeApi } from "./test/fixtures";
import { makeRun } from "./test/scheduleFixtures";

describe("App schedules tab", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("opens the Schedules tab from the header", async () => {
    const api = makeApi();
    render(<App api={api} pollIntervalMs={0} />);
    await userEvent.click(screen.getByRole("button", { name: "Schedules" }));
    expect(screen.getByRole("button", { name: "Schedules" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await screen.findByRole("region", { name: "Schedules" })).toBeInTheDocument();
    expect(api.listSchedules).toHaveBeenCalledOnce();
  });

  it("opens a scheduled run's report from an email link", async () => {
    window.location.hash = "#/schedules/sched-1/runs/run-1";
    const api = makeApi();
    render(<App api={api} pollIntervalMs={0} />);
    expect(screen.getByRole("button", { name: "Schedules" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await screen.findByLabelText("Scheduled readiness report")).toBeInTheDocument();
    expect(api.getScheduleRun).toHaveBeenCalledWith("run-1");
  });

  it("follows a link opened in a tab that is already open", async () => {
    const api = makeApi();
    render(<App api={api} pollIntervalMs={0} />);
    expect(screen.getByRole("button", { name: "Analyze" })).toHaveAttribute("aria-current", "page");
    window.location.hash = "#/schedules/sched-1/runs/run-1";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByLabelText("Scheduled readiness report")).toBeInTheDocument();
    window.location.hash = "#/history";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(screen.getByLabelText("Scheduled readiness report")).toBeInTheDocument();
  });

  it("polls the runs while one is still going", async () => {
    const running = makeRun({ state: "running", riskScore: null, riskLevel: null });
    const listScheduleRuns = vi
      .fn()
      .mockResolvedValueOnce({ items: [running], nextBefore: null })
      .mockResolvedValue({ items: [makeRun()], nextBefore: null });
    window.location.hash = "#/schedules/sched-1";
    render(<App api={makeApi({ listScheduleRuns })} pollIntervalMs={5} />);
    expect(await screen.findByText("Analyzing…")).toBeInTheDocument();
    await waitFor(() => expect(listScheduleRuns).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Emailed alice.chen@example.com")).toBeInTheDocument();
  });
});
