import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InputPanel } from "./InputPanel";

const samples = {
  runbooks: ["runbooks/auth-service.md"],
  inventories: ["inventories/healthy.json"],
};

function setup(overrides: Partial<Parameters<typeof InputPanel>[0]> = {}) {
  const onAnalyze = vi.fn();
  const loadSample = vi.fn(async (path: string) =>
    path.endsWith(".json") ? '{"services": []}' : "# Auth Service\n",
  );
  render(
    <InputPanel
      samples={samples}
      samplesError={null}
      loadSample={loadSample}
      busy={false}
      onAnalyze={onAnalyze}
      {...overrides}
    />,
  );
  return { onAnalyze, loadSample };
}

const analyzeButton = () => screen.getByRole("button", { name: "Analyze runbook" });

describe("InputPanel", () => {
  it("loads samples into the editors and submits them", async () => {
    const { onAnalyze } = setup();
    await userEvent.selectOptions(
      screen.getByLabelText("Sample runbook"),
      "runbooks/auth-service.md",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Sample inventory"),
      "inventories/healthy.json",
    );
    expect(screen.getByLabelText("Runbook (Markdown)")).toHaveValue("# Auth Service\n");
    expect(screen.getByLabelText("Sample runbook")).toHaveValue("runbooks/auth-service.md");

    await userEvent.click(analyzeButton());
    expect(onAnalyze).toHaveBeenCalledWith({
      runbookMarkdown: "# Auth Service\n",
      inventory: { services: [] },
      runbookName: "auth-service.md",
    });
  });

  it("requires a runbook", async () => {
    const { onAnalyze } = setup();
    await userEvent.click(analyzeButton());
    expect(screen.getByRole("alert")).toHaveTextContent("Paste, upload or pick a runbook first.");
    expect(onAnalyze).not.toHaveBeenCalled();
  });

  it("rejects an inventory that is not JSON", async () => {
    const { onAnalyze } = setup();
    await userEvent.type(screen.getByLabelText("Runbook (Markdown)"), "# Svc");
    await userEvent.type(screen.getByLabelText("Inventory (JSON, optional)"), "not json");
    await userEvent.click(analyzeButton());
    expect(screen.getByRole("alert")).toHaveTextContent("The inventory is not valid JSON.");
    expect(onAnalyze).not.toHaveBeenCalled();
  });

  it("submits a pasted runbook without inventory or name", async () => {
    const { onAnalyze } = setup();
    await userEvent.type(screen.getByLabelText("Runbook (Markdown)"), "# Svc");
    await userEvent.click(analyzeButton());
    expect(onAnalyze).toHaveBeenCalledWith({
      runbookMarkdown: "# Svc",
      inventory: null,
      runbookName: null,
    });
  });

  it("reads an uploaded file into the editor", async () => {
    setup();
    const file = new File(["# Uploaded\n"], "up.md", { type: "text/markdown" });
    await userEvent.upload(screen.getByLabelText("Upload runbook (markdown) file"), file);
    expect(await screen.findByDisplayValue("# Uploaded")).toBeInTheDocument();
  });

  it("reports a sample that fails to load", async () => {
    setup({ loadSample: vi.fn().mockRejectedValue(new Error("gone")) });
    await userEvent.selectOptions(
      screen.getByLabelText("Sample runbook"),
      "runbooks/auth-service.md",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("gone");
  });

  it("disables input while busy and shows sample errors", () => {
    setup({ busy: true, samplesError: "offline" });
    expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
    expect(screen.getByText("Samples unavailable: offline")).toBeInTheDocument();
  });
});
