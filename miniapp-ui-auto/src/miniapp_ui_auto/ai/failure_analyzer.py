from __future__ import annotations

from miniapp_ui_auto.models import CaseResult


def summarize_run(case_results: list[CaseResult]) -> str:
    total = len(case_results)
    failed = sum(1 for item in case_results if item.status == "failed")
    passed = sum(1 for item in case_results if item.status == "passed")
    if failed == 0:
        return f"本次回归共执行 {total} 条，通过 {passed} 条，未发现失败用例。"

    failed_cases = ", ".join(item.case_id for item in case_results if item.status == "failed")
    return f"本次回归共执行 {total} 条，通过 {passed} 条，失败 {failed} 条。优先查看失败用例：{failed_cases}。"


def classify_failure(messages: list[str]) -> tuple[str, str]:
    combined = " ".join(messages)
    if "ConnectionResetError" in combined or "Connection broken" in combined or "10054" in combined:
        return (
            "设备/Poco连接问题",
            "Airtest/Poco 与手机端服务连接被断开，请检查手机亮屏、USB 连接、PocoService 状态，或将动作描述改成明确控件/图片/滑动步骤。",
        )
    if "not installed" in combined or "environment" in combined:
        return "环境问题", "执行环境或依赖未准备完成。"
    if "assert" in combined.lower():
        return "功能缺陷", "断言未满足，需要结合截图和接口日志确认业务行为。"
    return "脚本问题", "执行步骤失败，需要检查用例步骤、元素定位或 Driver 映射。"
