"""The scheduler's runs: analysis outcomes and email outcomes."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from history_support import golden_report
from scheduling_support import INVENTORY, RUNBOOK, body, due_run, hourly, make_rig

from dr_agent.scheduling.models import EmailState, RunState
from dr_agent.utils.errors import CapacityError, NotificationError


async def test_a_due_slot_is_analyzed_stored_and_emailed(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    assert await rig.scheduler.tick() == []
    run = await due_run(rig)
    report = golden_report()
    assert run.state is RunState.SUCCEEDED
    assert (run.job_id, run.analysis_id) == ("job1", "job1")
    assert (run.risk_score, run.risk_level) == (report.risk_score, report.risk_level)
    assert run.rto_feasible is report.rto_analysis.feasible
    assert (run.email_state, run.email_to) == (EmailState.SENT, ["alice.chen@example.com"])
    [loaded] = rig.analyze.calls
    assert (loaded.runbook_label, loaded.inventory_label) == (RUNBOOK, INVENTORY)
    assert loaded.inventory is not None
    [message] = rig.notifier.sent
    assert message["To"] == "alice.chen@example.com"
    assert message["From"] == "dr-agent@example.com"
    assert message["Subject"].startswith("[DR readiness] Estimate-Service: ")
    text = body(message)
    assert "Owner: Alice Chen" in text
    assert f"Risk: {report.risk_level.value} ({report.risk_score}/100)" in text
    assert f"http://localhost:8080/#/schedules/s1/runs/{run.id}" in text


async def test_email_carries_no_runbook_or_model_text(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await due_run(rig)
    report = golden_report()
    everything = rig.notifier.sent[0].as_string()
    assert report.summary[:40] not in everything
    for gap in report.gap_analysis:
        assert gap.description[:40] not in everything
    for suggestion in report.suggestions:
        assert suggestion.detail[:40] not in everything


async def test_unstored_analysis_is_flagged(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite", ui_base_url=None)
    rig.analyze.store_it = False
    run = await due_run(rig)
    assert (run.state, run.job_id, run.analysis_id) == (RunState.SUCCEEDED, "job1", None)
    text = body(rig.notifier.sent[0])
    assert "cannot be executed later" in text
    assert "http" not in text  # no UI_BASE_URL, no link


async def test_failed_analysis_sends_a_failure_email(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    rig.analyze.error = CapacityError("too many unfinished analysis jobs")
    run = await due_run(rig)
    assert (run.state, run.error_code, run.analysis_id) == (
        RunState.FAILED,
        "CAPACITY_EXCEEDED",
        None,
    )
    assert run.error == "too many unfinished analysis jobs"
    [message] = rig.notifier.sent
    assert message["Subject"].endswith("scheduled analysis failed")
    assert "the next slot will try again" in body(message)


async def test_unparsable_runbook_fails_the_run_and_mails_the_default(tmp_path: Path) -> None:
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "bad.md").write_text("no structure here", encoding="utf-8")
    rig = await make_rig(tmp_path / "db.sqlite", base_dir=tmp_path)
    spec = hourly(inventory_path=None, runbook_path="runbooks/bad.md")
    await rig.service.create(spec, created_by="Alice")
    run = await rig.scheduler.run_now("s1")
    await rig.scheduler.wait_idle()
    run = await rig.store.get_run(run.id)
    assert (run.state, run.error_code) == (RunState.FAILED, "PARSE_ERROR")
    assert run.email_to == ["dr-team@example.com"]
    text = body(rig.notifier.sent[0])
    assert "could not be matched" in text
    assert "Owner: not found in the directory" in text
    assert rig.analyze.calls == []


async def test_missing_file_fails_the_run(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")
    await rig.service.create(hourly(), created_by="Alice")
    schedule = await rig.store.get("s1")
    await rig.store.update(schedule.model_copy(update={"runbook_path": "runbooks/gone.md"}))
    run = await rig.scheduler.run_now("s1")
    await rig.scheduler.wait_idle()
    assert (await rig.store.get_run(run.id)).error_code == "NOT_FOUND"


async def test_crash_in_analysis_is_recorded(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite")

    async def boom(_: object) -> None:
        raise RuntimeError("bug")

    rig.scheduler._analyze = boom  # type: ignore[assignment]  # replace the stub for one test
    run = await due_run(rig)
    assert (run.state, run.error_code) == (RunState.FAILED, "INTERNAL_ERROR")


class FailingNotifier:
    async def send(self, message: EmailMessage) -> None:
        raise NotificationError("smtp down")


async def test_email_failure_does_not_fail_the_run(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite", notifier=FailingNotifier())
    run = await due_run(rig)
    assert (run.state, run.email_state) == (RunState.SUCCEEDED, EmailState.FAILED)


async def test_nobody_to_mail_is_skipped(tmp_path: Path) -> None:
    rig = await make_rig(tmp_path / "db.sqlite", default_email=None)
    await rig.service.create(hourly(recipients=["x@other.org"]), created_by="Alice")
    run = await rig.scheduler.run_now("s1")
    await rig.scheduler.wait_idle()
    run = await rig.store.get_run(run.id)
    assert (run.state, run.email_state) == (RunState.SUCCEEDED, EmailState.SKIPPED)
    assert run.email_to == []
    assert not rig.notifier.sent
