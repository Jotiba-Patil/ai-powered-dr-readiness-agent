import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeApi } from "../../test/fixtures";
import { ScheduleForm } from "./ScheduleForm";

function setup(createdBy = "Bob") {
  const api = makeApi();
  const onCreate = vi.fn(async () => true);
  render(<ScheduleForm api={api} createdBy={createdBy} disabled={false} onCreate={onCreate} />);
  return { api, onCreate };
}

describe("ScheduleForm", () => {
  it("creates a weekly schedule with a recipient override and shows the preview", async () => {
    const { api, onCreate } = setup();
    expect(screen.getByLabelText("Email recipients")).toHaveTextContent("Pick a runbook");
    await userEvent.type(screen.getByLabelText("Name"), "Payment weekly");
    await userEvent.selectOptions(
      await screen.findByLabelText("Runbook"),
      "runbooks/payment-gateway.md",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Inventory (optional)"),
      "inventories/healthy.json",
    );
    expect(await screen.findByText("Email goes to: alice.chen@example.com")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "weekly");
    await userEvent.selectOptions(screen.getByLabelText("Day"), "fri");
    expect(screen.getByLabelText("Schedule preview")).toHaveTextContent(
      "Payment weekly · Every Friday at 06:00 (UTC) · checks",
    );
    expect(screen.getByLabelText("Timezone")).toHaveTextContent("UTC (from your browser)");
    expect(screen.queryByRole("textbox", { name: /Timezone/ })).not.toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText(/Email instead of the runbook owner/),
      "ops@example.com, x@example.com",
    );
    expect(api.previewRecipients).toHaveBeenLastCalledWith("runbooks/payment-gateway.md", [
      "ops@example.com",
      "x@example.com",
    ]);
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenCalledWith({
      name: "Payment weekly",
      runbookPath: "runbooks/payment-gateway.md",
      inventoryPath: "inventories/healthy.json",
      cadence: { kind: "weekly", weekday: "fri", time: "06:00" },
      timezone: "UTC",
      recipients: ["ops@example.com", "x@example.com"],
      createdBy: "Bob",
    });
    // After a successful create every field starts over.
    expect(await screen.findByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Runbook")).toHaveValue("");
    expect(screen.getByLabelText("Inventory (optional)")).toHaveValue("");
    expect(screen.getByLabelText("Repeat")).toHaveValue("daily");
    expect(screen.queryByLabelText("Day")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Time")).toHaveValue("06:00");
    expect(screen.getByLabelText(/Email instead of the runbook owner/)).toHaveValue("");
    expect(screen.getByLabelText("Email recipients")).toHaveTextContent("Pick a runbook");
  });

  it("keeps everything when the create fails, so nothing has to be typed again", async () => {
    const api = makeApi();
    const onCreate = vi.fn(async () => false);
    render(<ScheduleForm api={api} createdBy="Bob" disabled={false} onCreate={onCreate} />);
    await userEvent.type(screen.getByLabelText("Name"), "Kept");
    await userEvent.selectOptions(
      await screen.findByLabelText("Runbook"),
      "runbooks/auth-service.md",
    );
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "weekly");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Name")).toHaveValue("Kept");
    expect(screen.getByLabelText("Runbook")).toHaveValue("runbooks/auth-service.md");
    expect(screen.getByLabelText("Repeat")).toHaveValue("weekly");
  });

  it("switches to hourly and explains when nobody would be emailed", async () => {
    const { api, onCreate } = setup();
    vi.mocked(api.previewRecipients).mockResolvedValue({
      addresses: [],
      source: "none",
      ownerFound: false,
      dropped: 1,
    });
    await userEvent.type(screen.getByLabelText("Name"), "Hourly");
    await userEvent.selectOptions(
      await screen.findByLabelText("Runbook"),
      "runbooks/auth-service.md",
    );
    expect(await screen.findByText(/Nobody would get an email/)).toHaveTextContent(
      "(1 address(es) not in an allowed domain)",
    );
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "hourly");
    const minute = screen.getByLabelText("Minute past the hour");
    await userEvent.clear(minute);
    await userEvent.type(minute, "15");
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "daily");
    expect(screen.getByLabelText("Time")).toHaveValue("06:00");
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "hourly");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        cadence: { kind: "hourly", minute: 0 },
        recipients: null,
        inventoryPath: null,
      }),
    );
  });

  it("cannot be sent without a name", () => {
    setup("  ");
    expect(screen.getByRole("button", { name: "Create schedule" })).toBeDisabled();
  });
});
