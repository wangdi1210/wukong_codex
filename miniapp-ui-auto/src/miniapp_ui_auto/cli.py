from __future__ import annotations

import argparse
from pathlib import Path

from miniapp_ui_auto.case_loader import load_cases
from miniapp_ui_auto.case_generator import generate_case_from_text, write_generated_case
from miniapp_ui_auto.drivers.registry import create_driver
from miniapp_ui_auto.filtering import CaseFilter, filter_cases
from miniapp_ui_auto.models import RunContext
from miniapp_ui_auto.runner import run_cases
from miniapp_ui_auto.web_admin import run_web_admin


def main() -> int:
    parser = argparse.ArgumentParser(prog="miniapp-ui-auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run miniapp UI automation cases")
    run_parser.add_argument("--cases", default="cases")
    run_parser.add_argument("--schema", default="schemas/case.schema.json")
    run_parser.add_argument("--driver", default="dry-run", choices=("dry-run", "airtest", "poco", "minium"))
    run_parser.add_argument("--case-driver", action="append", default=[])
    run_parser.add_argument("--tag", action="append", default=[])
    run_parser.add_argument("--priority", action="append", default=[])
    run_parser.add_argument("--module", action="append", default=[])
    run_parser.add_argument("--env", default="test")
    run_parser.add_argument("--branch", default="")
    run_parser.add_argument("--commit", default="")
    run_parser.add_argument("--report-dir", default="reports/summary")

    generate_parser = subparsers.add_parser("generate", help="Generate a YAML case from natural language")
    generate_parser.add_argument("--text", default="")
    generate_parser.add_argument("--input-file", default="")
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--case-id", required=True)
    generate_parser.add_argument("--title", required=True)
    generate_parser.add_argument("--module", required=True)
    generate_parser.add_argument("--priority", default="P0", choices=("P0", "P1", "P2", "P3"))
    generate_parser.add_argument("--tag", action="append", default=[])
    generate_parser.add_argument("--owner", default="qa")
    generate_parser.add_argument("--driver", default="airtest", choices=("dry-run", "airtest", "poco", "minium"))
    generate_parser.add_argument("--schema", default="schemas/case.schema.json")

    web_parser = subparsers.add_parser("web", help="Start the local web admin")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    if args.command == "run":
        return _run(args)
    if args.command == "generate":
        return _generate(args)
    if args.command == "web":
        run_web_admin(args.host, args.port)
        return 0
    return 2


def _run(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases), Path(args.schema))
    selected = filter_cases(
        cases,
        CaseFilter(
            tags=tuple(args.tag),
            priorities=tuple(args.priority),
            modules=tuple(args.module),
            drivers=tuple(args.case_driver),
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


def _generate(args: argparse.Namespace) -> int:
    text = args.text
    if args.input_file:
        text = Path(args.input_file).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("请通过 --text 或 --input-file 提供自然语言用例内容。")

    generated_case = generate_case_from_text(
        text,
        case_id=args.case_id,
        title=args.title,
        module=args.module,
        priority=args.priority,
        tags=tuple(args.tag) or ("smoke",),
        owner=args.owner,
        driver=args.driver,
    )
    output_path = write_generated_case(generated_case, Path(args.output))
    load_cases(output_path.parent, Path(args.schema))
    print(f"generated={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
