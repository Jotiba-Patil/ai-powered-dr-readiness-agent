import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { makeApi } from "../../test/fixtures";
import { makeRun, makeScheduler, makeSchedule } from "../../test/scheduleFixtures";
import { SchedulesView } from "./SchedulesView";

async function signIn() {
  await userEvent.type(await screen.findByLabelText("Your name"), "Bob");
}

describe("SchedulesView", () => {
  beforeEach(() => window.localStorage.clear());

  it("lists schedules with their cadence, next run, last run and state", async () => {
    render(<SchedulesView api={makeApi()} pollIntervalMs={0} />);
    const table = await screen.findByRole("table");
    const row = within(table).getByRole("row", { name: /Payment daily/ });
    expect(row).toHaveTextContent("Payment daily");
    expect(row).toHaveTextContent("runbooks/payment-gateway.md");
    expect(row).toHaveTextContent("Daily 06:00 UTC");
    expect(row).toHaveTextContent("28 Sep 2026, 06:00 UTC");
    expect(row).toHaveTextContent("Succeeded");
    expect(row).toHaveTextContent("72 High");
    expect(row).toHaveTextContent("RTO not feasible");
    expect(row).toHaveTextContent("Active");
    expect(screen.getByText(/they never execute. Emails are sent over SMTP./)).toBeInTheDocument();
    const overview = screen.getByRole("list", { name: "Schedule overview" });
    expect(overview).toHaveTextContent("Active schedules1 of 1");
    expect(overview).toHaveTextContent("Needs attention1");
    expect(overview).toHaveTextContent("EmailsSMTP");
  });

  it("explains a disabled scheduler and load errors", async () => {
    const off = vi.fn().mockRejectedValue(new ApiError("off", "SCHEDULER_DISABLED", 403));
    render(<SchedulesView api={makeApi({ schedulerState: off })} />);
    expect(await screen.findByRole("status")).toHaveTextContent("SCHEDULER_ENABLED=false");
    const down = vi.fn().mockRejectedValue(new ApiError("down", "INTERNAL", 500));
    render(<SchedulesView api={makeApi({ listSchedules: down })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Schedules unavailable: down");
  });

  it("needs a name before changing anything", async () => {
    render(<SchedulesView api={makeApi()} />);
    const runNow = await screen.findByRole("button", { name: "Run Payment daily now" });
    expect(runNow).toBeDisabled();
    expect(screen.getByText("Enter your name to make changes.")).toBeInTheDocument();
    await signIn();
    expect(runNow).toBeEnabled();
    expect(window.localStorage.getItem("dr-agent.approver-name")).toBe("Bob");
  });

  it("runs now, shows the runs and opens a run's report with execution", async () => {
    const api = makeApi();
    render(<SchedulesView api={api} pollIntervalMs={0} />);
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Run Payment daily now" }));
    expect(api.runScheduleNow).toHaveBeenCalledWith("sched-1");
    const runs = await screen.findByRole("region", { name: "Runs of Payment daily" });
    expect(await within(runs).findByText("Emailed alice.chen@example.com")).toBeInTheDocument();
    await userEvent.click(within(runs).getByRole("button", { name: "Open report" }));
    expect(await screen.findByLabelText("Scheduled readiness report")).toBeInTheDocument();
    expect(api.getAnalysis).toHaveBeenCalledWith("job-1");
    expect(screen.getByText(/Scheduled run of/)).toHaveTextContent("Payment daily");
    expect(screen.getByRole("button", { name: "Execute this runbook…" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "← Back to schedules" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("pauses a schedule until a date and resumes a paused one", async () => {
    const paused = makeSchedule({ id: "sched-2", name: "Auth weekly", enabled: false });
    const api = makeApi({ listSchedules: vi.fn(async () => [makeSchedule(), paused]) });
    render(<SchedulesView api={api} />);
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Pause Payment daily" }));
    const form = screen.getByRole("form", { name: "Pause Payment daily" });
    await userEvent.type(within(form).getByLabelText(/Pause until/), "2026-09-30T08:00");
    await userEvent.click(within(form).getByRole("button", { name: "Pause until then" }));
    expect(api.pauseSchedule).toHaveBeenCalledWith(
      "sched-1",
      "Bob",
      new Date("2026-09-30T08:00").toISOString(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Resume Auth weekly" }));
    expect(api.resumeSchedule).toHaveBeenCalledWith("sched-2", "Bob");
  });

  it("offers quick pause lengths and toggles a schedule's runs", async () => {
    const api = makeApi();
    render(<SchedulesView api={api} pollIntervalMs={0} />);
    await signIn();
    const name = screen.getByRole("button", { name: "Payment daily" });
    await userEvent.click(name);
    expect(name).toHaveAttribute("aria-expanded", "true");
    expect(
      await screen.findByRole("region", { name: "Runs of Payment daily" }),
    ).toBeInTheDocument();
    await userEvent.click(name);
    expect(screen.queryByRole("region", { name: "Runs of Payment daily" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Pause Payment daily" }));
    const form = screen.getByRole("form", { name: "Pause Payment daily" });
    await userEvent.click(within(form).getByRole("button", { name: "1 day" }));
    expect(within(form).getByLabelText(/Pause until/)).not.toHaveValue("");
    await userEvent.click(within(form).getByRole("button", { name: "Pause until then" }));
    const until = vi.mocked(api.pauseSchedule).mock.calls[0]?.[2] ?? "";
    const hours = (Date.parse(until) - Date.now()) / 3_600_000;
    expect(hours).toBeGreaterThan(23);
    expect(hours).toBeLessThan(25);
  });

  it("shows an empty state", async () => {
    render(<SchedulesView api={makeApi({ listSchedules: vi.fn(async () => []) })} />);
    expect(await screen.findByText("No schedules yet. Create one below.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Schedule overview" })).toHaveTextContent(
      "None planned",
    );
  });

  it("pauses and resumes everything", async () => {
    const api = makeApi();
    render(<SchedulesView api={api} />);
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Pause all…" }));
    const form = screen.getByRole("form", { name: "Pause all schedules" });
    await userEvent.click(within(form).getByRole("button", { name: "Pause" }));
    expect(api.pauseAll).toHaveBeenCalledWith("Bob", undefined);
    vi.mocked(api.schedulerState).mockResolvedValue(
      makeScheduler({ paused: true, pausedBy: "Bob", pauseUntil: "2026-09-30T06:00:00Z" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(
      await screen.findByText(/All schedules are paused until 30 Sep 2026, 06:00 UTC by Bob/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Resume all" }));
    expect(api.resumeAll).toHaveBeenCalledWith("Bob");
  });

  it("deletes after confirmation and shows failed changes", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValue(true);
    const api = makeApi({
      resumeSchedule: vi.fn().mockRejectedValue(new ApiError("nope", "CONFLICT", 409)),
    });
    render(<SchedulesView api={api} />);
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Delete Payment daily" }));
    expect(api.deleteSchedule).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete Payment daily" }));
    expect(api.deleteSchedule).toHaveBeenCalledWith("sched-1");
    expect(confirm).toHaveBeenCalledTimes(2);
    confirm.mockRestore();
  });

  it("cancels a running run", async () => {
    const running = makeRun({
      state: "running",
      analysisId: null,
      emailState: null,
      riskScore: null,
      riskLevel: null,
    });
    const api = makeApi({
      listScheduleRuns: vi.fn(async () => ({ items: [running], nextBefore: null })),
    });
    render(<SchedulesView api={api} pollIntervalMs={0} />);
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Payment daily" }));
    const runs = await screen.findByRole("region", { name: "Runs of Payment daily" });
    expect(await within(runs).findByText("Analyzing…")).toBeInTheDocument();
    await userEvent.click(within(runs).getByRole("button", { name: "Cancel run" }));
    expect(api.cancelScheduleRun).toHaveBeenCalledWith("run-1");
    expect(within(runs).getByText("Scheduled")).toBeInTheDocument();
    await userEvent.click(within(runs).getByRole("button", { name: "Close runs" }));
    expect(screen.queryByRole("region", { name: "Runs of Payment daily" })).not.toBeInTheDocument();
  });

  it("opens the run from an email link", async () => {
    const api = makeApi();
    render(<SchedulesView api={api} link={{ scheduleId: "sched-1", runId: "run-1" }} />);
    expect(await screen.findByLabelText("Scheduled readiness report")).toBeInTheDocument();
    expect(api.getScheduleRun).toHaveBeenCalledWith("run-1");
    expect(await screen.findByText(/Scheduled run of/)).toHaveTextContent("Payment daily");
    window.location.hash = "#/schedules/sched-1/runs/run-1";
    await userEvent.click(screen.getByRole("button", { name: "← Back to schedules" }));
    expect(window.location.hash).toBe("");
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });
});
