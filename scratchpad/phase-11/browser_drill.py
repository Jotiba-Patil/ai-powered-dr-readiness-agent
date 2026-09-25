"""Phase 11 exit drill in a real browser (Microsoft Edge via Playwright).

Prerequisites (see SUMMARY.md): the mock MCP server over HTTP with the
smoke-fails-once scenario, the API with EXECUTION_ENABLED/ALLOW_LIVE, and the
Vite UI on http://localhost:5173 (LLM_PROVIDER=none keeps the analysis instant).
Execution is started from under the finished analysis report. Run with:

    uv run --with playwright python scratchpad/phase-11/browser_drill.py

Playwright is used as a throwaway tool here, not a project dependency.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

UI = "http://localhost:5173"
API = "http://127.0.0.1:8000/api/v1"
SAMPLE = "runbooks/estimate-service-executable.md"
OUT = Path(__file__).parent / "results"
TIMEOUT = 20_000


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print(f"  screenshot {name}.png")


def as_person(page: Page, name: str) -> None:
    page.get_by_label("Your name").fill(name)


def step(page: Page, number: int):  # type: ignore[no-untyped-def]  # Playwright locator
    return page.get_by_role("article", name=f"Step {number}")


def click_in_step(page: Page, number: int, button: str) -> None:
    step(page, number).get_by_role("button", name=button, exact=True).click()
    page.wait_for_load_state("networkidle")


def approve_all(page: Page) -> None:
    as_person(page, "Ann")
    for number in (1, 2, 3, 4, 5):
        click_in_step(page, number, "Approve")
    as_person(page, "Ben")  # destructive steps need a second, different person
    for number in (3, 5):
        click_in_step(page, number, "Approve")
    for number in (1, 2, 3, 4, 5):
        expect(step(page, number)).to_contain_text("Approved", timeout=TIMEOUT)


def create(page: Page, label: str) -> None:
    as_person(page, "Olivia")
    page.get_by_role("button", name=label).click()
    page.wait_for_load_state("networkidle")


def start_and_confirm_step_1(page: Page) -> None:
    start = page.get_by_role("button", name="Start run")
    expect(start).to_be_enabled()  # every step is approved
    start.click()
    expect(step(page, 1)).to_contain_text("Verifying", timeout=TIMEOUT)
    click_in_step(page, 1, "Confirm it worked")


def audit_verifies(execution_id: str) -> bool:
    with urllib.request.urlopen(f"{API}/executions/{execution_id}/audit?verify=true") as response:
        return bool(json.load(response)["verification"]["valid"])


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.set_default_timeout(TIMEOUT)
        page.goto(UI)
        print("0. analysis first (execution is only offered under a finished report)")
        expect(page.get_by_role("tab")).to_have_count(0)
        page.get_by_label("Sample runbook").select_option(SAMPLE)
        runbook_box = page.get_by_role("textbox", name="Runbook (Markdown)")
        expect(runbook_box).to_have_value(re.compile("drsim/"))
        page.get_by_role("button", name="Analyze runbook").click()
        expect(page.get_by_label("Readiness report")).to_be_visible(timeout=TIMEOUT)
        page.get_by_role("button", name="Execute this runbook…").click()
        expect(page.get_by_text("Identity not verified")).to_be_visible()
        shot(page, "0-report-then-execute")

        print("1. dry run")
        create(page, "Create dry run")
        expect(page.get_by_text("DRY RUN", exact=True)).to_be_visible()
        approve_all(page)
        start_and_confirm_step_1(page)
        expect(page.get_by_label("Execution", exact=True)).to_contain_text("Completed", timeout=TIMEOUT)
        expect(step(page, 5)).to_contain_text("Simulated")
        shot(page, "1-dry-run-completed")

        expect(page.get_by_role("button", name="Create dry run")).to_be_disabled()  # done once
        print("2. live run: two-person rule")
        create(page, "Create live run")
        expect(page.get_by_role("button", name="Start run")).to_be_disabled()  # nothing approved
        expect(page.get_by_role("button", name="Abort run")).to_be_disabled()  # not started
        expect(page.get_by_text("LIVE", exact=True)).to_be_visible()
        click_in_step(page, 3, "Approve")  # Olivia started the run: refused for destructive
        alert = page.get_by_role("alert")
        expect(alert).to_contain_text("POLICY_VIOLATION")
        shot(page, "2-starter-cannot-approve-destructive")
        page.get_by_role("button", name="Dismiss").click()
        approve_all(page)
        expect(step(page, 3)).to_contain_text("Approvals 2/2 (Ann, Ben)")
        shot(page, "3-live-two-approvers")

        print("3. live run: injected failure and rollback")
        start_and_confirm_step_1(page)
        expect(page.get_by_text("Paused: step 5 failed")).to_be_visible(timeout=TIMEOUT)
        expect(step(page, 5)).to_contain_text("checkout returns HTTP 500")
        expect(step(page, 3)).to_contain_text("Succeeded")
        shot(page, "4-live-injected-failure")
        for person in ("Ann", "Ben"):  # the rollback switches DNS: destructive, two people
            as_person(page, person)
            click_in_step(page, 5, "Approve rollback")
        click_in_step(page, 5, "Roll back")
        expect(step(page, 5)).to_contain_text("Rolled back", timeout=TIMEOUT)
        shot(page, "5-live-rolled-back")

        print("4. abort and audit")
        page.get_by_label("Reason", exact=True).fill("drill over: failover abandoned")
        page.get_by_role("button", name="Abort run").click()
        expect(page.get_by_label("Execution", exact=True)).to_contain_text("Aborted", timeout=TIMEOUT)
        page.get_by_role("button", name="Load and verify").click()
        expect(page.get_by_text("Hash chain verified")).to_be_visible(timeout=TIMEOUT)
        shot(page, "6-aborted-audit-verified")

        executions = json.load(urllib.request.urlopen(f"{API}/executions"))
        for item in executions:
            print(f"  {item['id']} {item['mode']} {item['state']} audit valid: {audit_verifies(item['id'])}")
        browser.close()
    print("drill passed")


if __name__ == "__main__":
    main()
