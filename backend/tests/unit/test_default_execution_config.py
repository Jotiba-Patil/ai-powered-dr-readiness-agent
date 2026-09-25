"""The shipped mcp-servers.json and execution-policy.json match the bundled mock server."""

import random
from pathlib import Path

from mcp import Client

from dr_agent.execution.policy import check_call, effective_risk, index_catalog
from dr_agent.execution.policy_file import load_policy
from dr_agent.mock_mcp.environment import DrEnvironment
from dr_agent.mock_mcp.server import build_server
from dr_agent.tools.mcp_executor import McpToolExecutor

REPO = Path(__file__).resolve().parents[3]


async def test_policy_allow_lists_exactly_the_mock_tools_and_hints_agree() -> None:
    policy = load_policy(REPO / "execution-policy.json")
    server = build_server(DrEnvironment())
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as ex:
        specs = await ex.list_tools()
    listed = set(policy.servers["drsim"].tools)
    assert listed == {spec.name for spec in specs}
    for spec in specs:
        risk = policy.servers["drsim"].tools[spec.name].risk
        assert effective_risk(risk, spec) is risk, spec.name  # hints never need to raise it
    assert list(policy.servers) == ["drsim"]


async def test_every_call_in_the_executable_sample_passes_the_default_policy() -> None:
    from dr_agent.core.parser import parse_runbook

    policy = load_policy(REPO / "execution-policy.json")
    server = build_server(DrEnvironment())
    async with McpToolExecutor({"drsim": lambda: Client(server)}, rng=random.Random(0)) as ex:
        catalog = index_catalog(await ex.list_tools())
    runbook = parse_runbook(
        (REPO / "mock-data/runbooks/estimate-service-executable.md").read_text("utf-8")
    )
    calls = [c for s in runbook.steps for c in (s.tool_call, s.verify_call, s.rollback_call) if c]
    assert len(calls) == 11
    for call in calls:
        check_call(policy, catalog, call)
