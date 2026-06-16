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
        previous_result: CaseResult | None = None
        for case in cases:
            if case.depends_on_previous and previous_result is not None and previous_result.status != "passed":
                result = _skip_dependent_case(case, previous_result)
            else:
                result = _run_case(case, driver)
            case_results.append(result)
            previous_result = result
    finally:
        driver.teardown()
    return write_summary(report_dir, context, case_results)


def _skip_dependent_case(case: TestCase, previous_result: CaseResult) -> CaseResult:
    return CaseResult(
        case_id=case.id,
        title=case.title,
        module=case.module,
        priority=case.priority,
        tags=case.tags,
        depends_on_previous=case.depends_on_previous,
        status="skipped",
        steps=(
            StepResult(
                action="dependency",
                target=previous_result.case_id,
                status="skipped",
                message=f"上一条用例 {previous_result.case_id} 状态为 {previous_result.status}，当前用例配置为依赖上一条，已跳过执行。",
            ),
        ),
        failure_category="依赖跳过",
        failure_summary="上一条用例未通过，当前依赖用例未执行。",
    )


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
