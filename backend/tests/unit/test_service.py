import json
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.disabled import DisabledProvider
from dr_agent.llm.fake import FakeProvider
from dr_agent.loaders import load_inventory
from dr_agent.models.inventory import DependencyStatus, HealthStatus
from dr_agent.service import (
    NO_INVENTORY_LABEL,
    analyze_runbook,
    parse_markdown,
    validate_inventory,
)
from dr_agent.utils.errors import ParseError

MOCK = Path(__file__).resolve().parents[3] / "mock-data"
FIXED = datetime(2026, 9, 23, tzinfo=UTC)
LLM_JSON = json.dumps({"summary": "Grounded summary.", "riskScore": 91})


async def _no_sleep(_seconds: float) -> None:
    return None


def _checker() -> MockHealthChecker:
    return MockHealthChecker(random.Random(7), sleeper=_no_sleep)


class _Ticker:
    """Fake perf counter: each call advances 0.5 s, so durations are deterministic."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.5
        return self.now


def _markdown(name: str) -> str:
    return (MOCK / "runbooks" / name).read_text(encoding="utf-8")


def test_parse_markdown_returns_runbook() -> None:
    runbook = parse_markdown(_markdown("estimate-service.md"))
    assert runbook.service_name
    assert runbook.steps


def test_parse_markdown_raises_parse_error_on_empty() -> None:
    with pytest.raises(ParseError):
        parse_markdown("   ")


async def test_analyze_runbook_uses_llm_and_inventory() -> None:
    runbook = parse_markdown(_markdown("payment-gateway.md"))
    inventory = load_inventory(MOCK / "inventories" / "partial-outage.json")
    report = await analyze_runbook(
        runbook,
        inventory,
        llm=FakeProvider([LLM_JSON]),
        checker=_checker(),
        runbook_label="payment-gateway.md",
        inventory_label="partial-outage.json",
        clock=lambda: FIXED,
        timer=_Ticker(),
    )
    assert report.ai_analysis_available is True
    assert report.risk_score == 91
    assert report.meta.inventory_file == "partial-outage.json"
    assert report.meta.analyzed_at == FIXED
    statuses = {dep.name: dep.actual_status for dep in report.dependency_health}
    assert statuses["card-network-gateway"] is DependencyStatus.NOT_IN_INVENTORY
    assert DependencyStatus.DOWN in statuses.values()


async def test_analysis_time_covers_the_whole_pipeline() -> None:
    runbook = parse_markdown(_markdown("estimate-service.md"))
    report = await analyze_runbook(
        runbook,
        None,
        llm=FakeProvider([LLM_JSON]),
        checker=_checker(),
        runbook_label="r.md",
        inventory_label=None,
        clock=lambda: FIXED,
        timer=_Ticker(),
    )
    # Ticker reads: total start 0.5, health 1.0-1.5, analyzer 2.0-2.5, total stop 3.0.
    # The analyzer alone would report 500 ms; the report carries the whole pipeline.
    assert report.meta.analysis_time_ms == 2500


async def test_no_inventory_marks_every_dependency_unverified() -> None:
    runbook = parse_markdown(_markdown("estimate-service.md"))
    report = await analyze_runbook(
        runbook,
        None,
        llm=DisabledProvider(),
        checker=_checker(),
        runbook_label="estimate-service.md",
        inventory_label=None,
    )
    assert report.meta.inventory_file == NO_INVENTORY_LABEL
    assert report.ai_analysis_available is False
    assert report.ai_note is not None
    assert "disabled" in report.ai_note
    assert {d.actual_status for d in report.dependency_health} == {
        DependencyStatus.NOT_IN_INVENTORY
    }


async def test_validate_inventory_checks_every_service() -> None:
    inventory = load_inventory(MOCK / "inventories" / "major-outage.json")
    statuses = await validate_inventory(inventory, _checker())
    assert [s.name for s in statuses] == [s.name for s in inventory.services]
    assert sum(s.status is HealthStatus.DOWN for s in statuses) == 4
