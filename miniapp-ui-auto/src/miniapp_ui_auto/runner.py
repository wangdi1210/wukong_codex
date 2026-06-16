from __future__ import annotations

from pathlib import Path

from miniapp_ui_auto.ai.failure_analyzer import classify_failure
from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import CaseResult, RunContext, Step, StepResult, TestCase
from miniapp_ui_auto.reporter import RunSummary, write_summary


def run_cases(
    cases: list[TestCase],
    driver: AutomationDriver,
    context: RunContext,
    report_dir: Path,
) -> RunSummary:
    case_results: list[CaseResult] = []
    driver.setup(context)
    try:
        for case in cases:
            case_results.append(_run_case(case, driver))
    finally:
        driver.teardown()
    return write_summary(report_dir, context, case_results)


def _run_case(case: TestCase, driver: AutomationDriver) -> CaseResult:
    step_results: list[StepResult] = []
    for step in case.steps:
        result = driver.execute_step(step)
        step_results.append(result)
        if result.status == "failed":
            break
    if not any(item.status == "failed" for item in step_results):
        for assertion in case.assertions:
            result = driver.execute_step(
                Step(action=f"assert_{assertion.type}", target=assertion.target, value=assertion.expected)
            )
            step_results.append(result)
            if result.status == "failed":
                break

    failed_messages = [item.message for item in step_results if item.status == "failed"]
    if failed_messages:
        category, summary = classify_failure(failed_messages)
        status = "failed"
    else:
        category = ""
        summary = ""
        status = "passed"

    return CaseResult(
        case_id=case.id,
        title=case.title,
        module=case.module,
        priority=case.priority,
        tags=case.tags,
        depends_on_previous=case.depends_on_previous,
        status=status,
        steps=tuple(step_results),
        failure_category=category,
        failure_summary=summary,
    )
