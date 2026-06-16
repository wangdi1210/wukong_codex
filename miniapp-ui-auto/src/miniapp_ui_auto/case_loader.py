from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from miniapp_ui_auto.models import Assertion, Step, TestCase


class CaseValidationError(ValueError):
    """Raised when a case file does not match the schema."""


def load_cases(case_root: Path, schema_path: Path) -> list[TestCase]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    case_paths = sorted(case_root.rglob("*.yaml"))
    cases: list[TestCase] = []

    for case_path in case_paths:
        raw = yaml.safe_load(case_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CaseValidationError(f"{case_path}: case file must contain a YAML object")
        _validate_case(validator, case_path, raw)
        cases.append(_to_case(raw, case_path))

    return cases


def _validate_case(validator: Draft202012Validator, case_path: Path, raw: dict[str, Any]) -> None:
    errors = sorted(validator.iter_errors(raw), key=lambda item: list(item.path))
    if not errors:
        return

    first = errors[0]
    location = ".".join(str(part) for part in first.path) or "<root>"
    message = _friendly_message(first)
    raise CaseValidationError(f"{case_path}: {location}: {message}")


def _friendly_message(error: ValidationError) -> str:
    if error.validator == "required":
        missing = ", ".join(error.validator_value)
        return f"required property missing: {missing}"
    return error.message


def _to_case(raw: dict[str, Any], source_path: Path) -> TestCase:
    steps = tuple(
        Step(
            action=item["action"],
            target=item["target"],
            value=item.get("value"),
            timeout_ms=item.get("timeout_ms"),
        )
        for item in raw["steps"]
    )
    assertions = tuple(
        Assertion(
            type=item["type"],
            target=item["target"],
            expected=item["expected"],
        )
        for item in raw["assertions"]
    )
    return TestCase(
        id=raw["id"],
        title=raw["title"],
        platform=raw["platform"],
        driver=raw["driver"],
        module=raw["module"],
        priority=raw["priority"],
        tags=tuple(raw["tags"]),
        owner=raw["owner"],
        version=raw["version"],
        preconditions=tuple(raw.get("preconditions", [])),
        depends_on_previous=bool(raw.get("depends_on_previous", False)),
        steps=steps,
        assertions=assertions,
        source_path=str(source_path),
    )
