from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from miniapp_ui_auto.ai.failure_analyzer import summarize_run
from miniapp_ui_auto.models import CaseResult, RunContext


@dataclass(frozen=True)
class RunSummary:
    total: int
    passed: int
    failed: int
    skipped: int


def write_summary(report_dir: Path, context: RunContext, case_results: list[CaseResult]) -> RunSummary:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = RunSummary(
        total=len(case_results),
        passed=sum(1 for item in case_results if item.status == "passed"),
        failed=sum(1 for item in case_results if item.status == "failed"),
        skipped=sum(1 for item in case_results if item.status == "skipped"),
    )
    payload = {
        **asdict(summary),
        "context": asdict(context),
        "ai_summary": summarize_run(case_results),
        "cases": [asdict(item) for item in case_results],
    }
    (report_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
