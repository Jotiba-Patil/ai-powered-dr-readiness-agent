import json

from dr_agent.formatters.format_json import format_json
from dr_agent.models.report import DRReadinessReport


def test_output_is_valid_json_with_camel_case_keys(sample_report: DRReadinessReport) -> None:
    parsed = json.loads(format_json(sample_report))
    assert parsed["riskScore"] == sample_report.risk_score
    assert parsed["serviceSummary"]["name"] == sample_report.service_summary.name


def test_output_round_trips_through_the_model(sample_report: DRReadinessReport) -> None:
    parsed = json.loads(format_json(sample_report))
    assert DRReadinessReport.model_validate(parsed) == sample_report
