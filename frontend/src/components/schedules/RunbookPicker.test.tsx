import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { makeApi } from "../../test/fixtures";
import { ScheduleForm } from "./ScheduleForm";

function setup(overrides = {}) {
  const api = makeApi(overrides);
  const onCreate = vi.fn(async () => true);
  render(<ScheduleForm api={api} createdBy="Bob" disabled={false} onCreate={onCreate} />);
  return { api, onCreate };
}

const file = (name: string, text: string) => new File([text], name, { type: "text/markdown" });

describe("RunbookPicker (in the schedule form)", () => {
  it("uploads a runbook, reloads the list and selects it", async () => {
    const before = { runbooks: ["runbooks/auth-service.md"], inventories: [] };
    const after = { runbooks: ["runbooks/auth-service.md", "uploads/drill.md"], inventories: [] };
    const listSamples = vi.fn().mockResolvedValueOnce(before).mockResolvedValue(after);
    const { api, onCreate } = setup({ listSamples });
    await screen.findByRole("option", { name: "runbooks/auth-service.md" });
    await userEvent.upload(screen.getByLabelText("Upload runbook…"), file("drill.md", "# Drill"));
    expect(api.uploadRunbook).toHaveBeenCalledWith("drill.md", "# Drill");
    expect(await screen.findByText("Saved as uploads/drill.md (Uploaded Service)")).toBeVisible();
    expect(screen.getByLabelText("Runbook")).toHaveValue("uploads/drill.md");
    expect(api.listSamples).toHaveBeenCalledTimes(2);
    await userEvent.type(screen.getByLabelText("Name"), "Drill");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ runbookPath: "uploads/drill.md" }),
    );
    // The reset also clears the upload note, and the uploaded runbook stays in the list.
    expect(screen.queryByText(/Saved as uploads\/drill.md/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Runbook")).toHaveValue("");
    expect(screen.getByRole("option", { name: "uploads/drill.md" })).toBeInTheDocument();
  });

  it("explains an upload the server refused and keeps the selection", async () => {
    const refused = vi
      .fn()
      .mockRejectedValue(new ApiError("no recovery steps", "PARSE_ERROR", 422));
    const { api } = setup({ uploadRunbook: refused });
    await userEvent.upload(screen.getByLabelText("Upload runbook…"), file("notes.md", "hi"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not saved: no recovery steps");
    expect(screen.getByLabelText("Runbook")).toHaveValue("");
    expect(api.listSamples).toHaveBeenCalledTimes(1);
  });

  it("offers monthly schedules on a day or the last day", async () => {
    const { onCreate } = setup();
    await userEvent.type(screen.getByLabelText("Name"), "Monthly");
    await userEvent.selectOptions(
      await screen.findByLabelText("Runbook"),
      "runbooks/auth-service.md",
    );
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "monthly");
    expect(screen.getByRole("option", { name: "31 (or the last day)" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Day of month"), "31");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenLastCalledWith(
      expect.objectContaining({ cadence: { kind: "monthly", day: 31, time: "06:00" } }),
    );
    // The form was reset by the first create: pick the runbook and "monthly" again.
    await userEvent.type(screen.getByLabelText("Name"), "Last day");
    await userEvent.selectOptions(screen.getByLabelText("Runbook"), "runbooks/auth-service.md");
    await userEvent.selectOptions(screen.getByLabelText("Repeat"), "monthly");
    await userEvent.selectOptions(screen.getByLabelText("Day of month"), "last");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(onCreate).toHaveBeenLastCalledWith(
      expect.objectContaining({ cadence: { kind: "monthly", day: "last", time: "06:00" } }),
    );
  });
});
