"""DRReadinessReport -> pretty-printed JSON."""

from __future__ import annotations

import json

from dr_agent.models.report import DRReadinessReport


def format_json(report: DRReadinessReport) -> str:
    return json.dumps(report.to_json_dict(), indent=2)
