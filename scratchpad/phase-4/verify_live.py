"""Phase 4 exit-criteria check: run the real pipeline against a live local Ollama model.

Not part of the test suite (tests never touch a real LLM, per testing.md) -- this is
the same kind of throwaway verification script as scratchpad/phase-0/spike_structured_output.py,
but it exercises the actual production code path (parser -> health checker -> analyzer ->
formatters) instead of a standalone re-implementation, to prove "end-to-end analyze works
on all 3 runbooks with local model" (docs/IMPLEMENTATION_PLAN.md Phase 4 exit criterion).

Run with (from repo root):
  uv run python scratchpad/phase-4/verify_live.py <model> [runbook,inventory ...]

Writes one JSON result file per model to scratchpad/phase-4/results/<model>.json
and the full JSON report for the first runbook to scratchpad/phase-4/results/<model>_<runbook>.json.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from dr_agent import __version__  # noqa: E402
from dr_agent.core.analyzer import run_analysis  # noqa: E402
from dr_agent.core.parser import parse_runbook  # noqa: E402
from dr_agent.formatters.format_json import format_json  # noqa: E402
from dr_agent.health.dependency_check import check_dependencies  # noqa: E402
from dr_agent.health.mock import MockHealthChecker  # noqa: E402
from dr_agent.llm.ollama import OllamaProvider  # noqa: E402
from dr_agent.models.inventory import SystemInventory  # noqa: E402
from dr_agent.utils.errors import AnalysisError  # noqa: E402

CASES = [
    ("estimate-service.md", "healthy.json"),
    ("payment-gateway.md", "partial-outage.json"),
    ("auth-service.md", "major-outage.json"),
]


async def run_one(model: str, runbook_name: str, inventory_name: str) -> dict[str, object]:
    runbook_md = (ROOT / "mock-data" / "runbooks" / runbook_name).read_text(encoding="utf-8")
    runbook = parse_runbook(runbook_md)
    inventory = SystemInventory.model_validate(
        json.loads((ROOT / "mock-data" / "inventories" / inventory_name).read_text())
    )
    dependency_health = await check_dependencies(
        runbook, inventory, MockHealthChecker(random.Random(42))
    )

    async with httpx.AsyncClient() as client:
        llm = OllamaProvider(
            client,
            base_url="http://localhost:11434",
            model=model,
            max_tokens=2048,
            rng=random.Random(1),
            timeout_seconds=600.0,
        )
        started = time.perf_counter()
        try:
            report = await run_analysis(
                runbook,
                dependency_health,
                llm,
                runbook_file=f"mock-data/runbooks/{runbook_name}",
                inventory_file=f"mock-data/inventories/{inventory_name}",
                agent_version=__version__,
            )
        except AnalysisError as exc:
            return {
                "runbook": runbook_name,
                "inventory": inventory_name,
                "wall_seconds": round(time.perf_counter() - started, 1),
                "ai_analysis_available": False,
                "error": str(exc),
            }

    return {
        "runbook": runbook_name,
        "inventory": inventory_name,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "ai_analysis_available": report.ai_analysis_available,
        "ai_note": report.ai_note,
        "risk_score": report.risk_score,
        "risk_level": report.risk_level.value,
        "rto_feasible": report.rto_analysis.feasible,
        "gap_types": sorted({g.type.value for g in report.gap_analysis}),
        "spof_count": len(report.single_points_of_failure),
        "suggestion_count": len(report.suggestions),
        "execution_phases": len(report.execution_plan),
        "_report": report,
    }


async def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:3b-instruct"
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)

    rows: list[dict[str, object]] = []
    for runbook_name, inventory_name in CASES:
        print(f"[{model}] {runbook_name} + {inventory_name} ...", flush=True)
        row = await run_one(model, runbook_name, inventory_name)
        report = row.pop("_report", None)
        if report is not None:
            safe_name = runbook_name.replace(".md", "")
            (out_dir / f"{model.replace(':', '_')}_{safe_name}.json").write_text(
                format_json(report), encoding="utf-8"
            )
        rows.append(row)
        print(json.dumps(row, indent=2, default=str), flush=True)

    (out_dir / f"{model.replace(':', '_')}.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
