import json
from pathlib import Path

from miniapp_ui_auto.case_loader import load_cases
from miniapp_ui_auto.drivers.registry import create_driver
from miniapp_ui_auto.models import RunContext
from miniapp_ui_auto.runner import run_cases


def test_run_cases_with_dry_run_driver_writes_summary(tmp_path):
    cases = load_cases(Path("cases"), Path("schemas/case.schema.json"))
    result = run_cases(
        cases=cases,
        driver=create_driver("dry-run"),
        context=RunContext(env="test", trigger="pytest", branch="local", commit="dev"),
        report_dir=tmp_path,
    )

    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result.total == len(cases)
    assert result.passed == len(cases)
    assert summary["total"] == len(cases)
    assert summary["passed"] == len(cases)
    assert summary["cases"][0]["case_id"] == cases[0].id
    assert summary["cases"][0]["status"] == "passed"
    assert f"本次回归共执行 {len(cases)} 条" in summary["ai_summary"]
