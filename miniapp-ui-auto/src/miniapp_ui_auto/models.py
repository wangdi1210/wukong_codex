from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Step:
    action: str
    target: str
    value: Any | None = None
    timeout_ms: int | None = None


@dataclass(frozen=True)
class Assertion:
    type: str
    target: str
    expected: Any


@dataclass(frozen=True)
class TestCase:
    __test__ = False

    id: str
    title: str
    platform: str
    driver: str
    module: str
    priority: str
    tags: tuple[str, ...]
    owner: str
    version: int
    preconditions: tuple[str, ...]
    steps: tuple[Step, ...]
    assertions: tuple[Assertion, ...]
    source_path: str


@dataclass(frozen=True)
class RunContext:
    env: str
    trigger: str
    branch: str = ""
    commit: str = ""


@dataclass(frozen=True)
class StepResult:
    action: str
    target: str
    status: str
    message: str = ""
    artifact_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    title: str
    module: str
    priority: str
    tags: tuple[str, ...]
    status: str
    steps: tuple[StepResult, ...]
    failure_category: str = ""
    failure_summary: str = ""
