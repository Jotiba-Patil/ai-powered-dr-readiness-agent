"""End-to-end pipeline test against the estimate-service golden report.

Parse -> health-check -> analyze -> JSON format, with a scripted FakeProvider
and a fixed clock/timer so the whole pipeline is deterministic. The second
golden report adds a fixed service history (Phase 14,
`backend/tests/fixtures/history/estimate-service.json`). Regenerate
`mock-data/expected-reports/estimate-service*.json` deliberately (see
`docs/IMPLEMENTATION_PLAN.md` Phase 4) if a change intentionally alters the
pipeline's output.
"""

import json
import random
from datetime import UTC, datetime
from pathlib import Path

from dr_agent import __version__
from dr_agent.core.analyzer import run_analysis
from dr_agent.core.parser import parse_runbook
from dr_agent.formatters.format_json import format_json
from dr_agent.health.dependency_check import check_dependencies
from dr_agent.health.mock import MockHealthChecker
from dr_agent.llm.fake import FakeProvider
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.inventory import SystemInventory

ROOT = Path(__file__).resolve().parents[3]
_FAKE_RESPONSE = json.dumps(
    {
        "stepDependencies": [{"stepNumber": 5, "dependsOn": [2, 4]}],
        "singlePointsOfFailure": [
            {
                "description": (
                    "Alice Chen is the only owner who can confirm the outage and flip traffic."
                ),
                "affectedSteps": [1, 5],
                "mitigationSuggestion": (
                    "Train a secondary on-call owner for the confirm and cutover steps."
                ),
            }
        ],
        "gapAnalysis": [
            {
                "type": "VAGUE_INSTRUCTION",
                "description": (
                    "Step 1's 'confirm the outage scope' has no explicit pass/fail threshold."
                ),
                "severity": "LOW",
                "recommendation": "Define what dashboard state counts as confirmed.",
            }
        ],
        "suggestions": [
            {
                "priority": 1,
                "title": "Rehearse the rollback path",
                "detail": "Run the DNS revert quarterly so it is proven, not just documented.",
            }
        ],
        "summary": (
            "Estimate Service's runbook is well structured: every step has a named "
            "owner, a time estimate and a validation command, and the recovery plan "
            "fits inside the 60-minute RTO with a 5-minute buffer. The main residual "
            "risk is that Alice Chen is the sole approver for two critical steps, "
            "creating a single point of failure if she is unavailable during an "
            "incident. Addressing that ownership gap and rehearsing the rollback "
            "path would make this runbook close to ideal."
        ),
        "riskScore": 15,
    }
)


async def _report(provider: FakeProvider, history: ServiceHistory | None = None) -> str:
    runbook_path = ROOT / "mock-data" / "runbooks" / "estimate-service.md"
    inventory_path = ROOT / "mock-data" / "inventories" / "healthy.json"
    runbook = parse_runbook(runbook_path.read_text(encoding="utf-8"))
    inventory = SystemInventory.model_validate(json.loads(inventory_path.read_text()))
    dependency_health = await check_dependencies(
        runbook, inventory, MockHealthChecker(random.Random(42))
    )
    report = await run_analysis(
        runbook,
        dependency_health,
        provider,
        runbook_file="mock-data/runbooks/estimate-service.md",
        inventory_file="mock-data/inventories/healthy.json",
        agent_version=__version__,
        clock=lambda: datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC),
        timer=lambda: 0.0,
        history=history,
    )
    return format_json(report) + "\n"


async def test_estimate_service_matches_the_golden_report() -> None:
    expected_path = ROOT / "mock-data" / "expected-reports" / "estimate-service.json"
    provider = FakeProvider([_FAKE_RESPONSE])
    assert await _report(provider) == expected_path.read_text(encoding="utf-8")
    assert "<history>" not in provider.calls[0][1]


async def test_estimate_service_with_history_matches_its_golden_report() -> None:
    fixture = ROOT / "backend" / "tests" / "fixtures" / "history" / "estimate-service.json"
    expected_path = ROOT / "mock-data" / "expected-reports" / "estimate-service-history.json"
    history = ServiceHistory.model_validate_json(fixture.read_text(encoding="utf-8"))
    provider = FakeProvider([_FAKE_RESPONSE])
    assert await _report(provider, history) == expected_path.read_text(encoding="utf-8")
    prompt = provider.calls[0][1]
    assert "\n<history>\n" in prompt
    assert '"rolledBack": 1' in prompt
    assert "run-4" not in prompt  # execution ids are not prompt facts
