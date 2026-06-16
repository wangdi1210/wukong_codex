import json
from pathlib import Path

from miniapp_ui_auto.case_loader import load_cases
from miniapp_ui_auto.drivers.registry import create_driver
from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult
from miniapp_ui_auto.runner import run_cases


class FailingAssertionDriver(AutomationDriver):
    name = "failing-assertion"

    def setup(self, context):
        pass

    def execute_step(self, step: Step) -> StepResult:
        if step.action.startswith("assert_"):
            return StepResult(action=step.action, target=step.target, status="failed", message="assertion failed")
        return StepResult(action=step.action, target=step.target, status="passed", message="step passed")

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        pass


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
    assert any(step["action"].startswith("assert_") for step in summary["cases"][0]["steps"])
    assert f"本次回归共执行 {len(cases)} 条" in summary["ai_summary"]


def test_run_cases_marks_case_failed_when_assertion_fails(tmp_path):
    cases = load_cases(Path("cases"), Path("schemas/case.schema.json"))[:1]

    result = run_cases(
        cases=cases,
        driver=FailingAssertionDriver(),
        context=RunContext(env="test", trigger="pytest"),
        report_dir=tmp_path,
    )
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))

    assert result.failed == 1
    assert summary["cases"][0]["status"] == "failed"
    assert summary["cases"][0]["steps"][-1]["action"] == "assert_text"
    assert summary["cases"][0]["steps"][-1]["message"] == "assertion failed"
