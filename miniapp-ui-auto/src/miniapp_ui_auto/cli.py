from __future__ import annotations

import argparse
from pathlib import Path

from miniapp_ui_auto.case_loader import load_cases
from miniapp_ui_auto.drivers.registry import create_driver
from miniapp_ui_auto.filtering import CaseFilter, filter_cases
from miniapp_ui_auto.models import RunContext
from miniapp_ui_auto.runner import run_cases


def main() -> int:
    parser = argparse.ArgumentParser(prog="miniapp-ui-auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run miniapp UI automation cases")
    run_parser.add_argument("--cases", default="cases")
    run_parser.add_argument("--schema", default="schemas/case.schema.json")
    run_parser.add_argument("--driver", default="dry-run", choices=("dry-run", "minium"))
    run_parser.add_argument("--tag", action="append", default=[])
    run_parser.add_argument("--priority", action="append", default=[])
    run_parser.add_argument("--module", action="append", default=[])
    run_parser.add_argument("--env", default="test")
    run_parser.add_argument("--branch", default="")
    run_parser.add_argument("--commit", default="")
    run_parser.add_argument("--report-dir", default="reports/summary")

    args = parser.parse_args()
    if args.command == "run":
        return _run(args)
    return 2


def _run(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases), Path(args.schema))
    selected = filter_cases(
        cases,
        CaseFilter(
            tags=tuple(args.tag),
            priorities=tuple(args.priority),
            modules=tuple(args.module),
            drivers=(args.driver,),
        ),
    )
    summary = run_cases(
        cases=selected,
        driver=create_driver(args.driver),
        context=RunContext(env=args.env, trigger="cli", branch=args.branch, commit=args.commit),
        report_dir=Path(args.report_dir),
    )
    print(f"total={summary.total} passed={summary.passed} failed={summary.failed} skipped={summary.skipped}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
