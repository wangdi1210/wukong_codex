# 小程序 UI 自动化 MVP 实施计划

> **给后续执行者：**执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。每个任务使用复选框跟踪进度。

**目标：**搭建第一版可运行的小程序 UI 自动化工程骨架，支持 YAML 用例、Schema 校验、Driver 抽象、dry-run 执行、Summary JSON 报告和 AI 失败分析入口。

**架构：**工程放在 `miniapp-ui-auto/` 下，核心包名为 `miniapp_ui_auto`。执行链路为：加载 YAML 用例，按 JSON Schema 校验，按标签/优先级/模块过滤，通过 Driver Registry 创建执行驱动，执行标准化步骤，最后写出平台可沉淀的 `summary.json`。第一版先提供可本地验证的 `dry-run` Driver，同时预留 `MiniumDriver` 边界，后续接真实微信开发者工具和 Minium 时不需要重写上层编排。

**技术栈：**Python 3.11+、`pytest`、`pyyaml`、`jsonschema`、标准库 `argparse`、`dataclasses`、`json`，后续真实小程序执行接入 `minium`。

---

## 文件结构

- 新增：`miniapp-ui-auto/pyproject.toml`
  - 定义 Python 包、依赖、测试配置和命令行入口。
- 新增：`miniapp-ui-auto/README.md`
  - 说明安装、用例编写和 dry-run 执行方式。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/__init__.py`
  - 包声明和版本号。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/models.py`
  - 定义用例、步骤、断言、执行结果和运行上下文模型。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/case_loader.py`
  - 加载 YAML 用例、做 Schema 校验，并转换成模型对象。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/filtering.py`
  - 按标签、优先级、模块、平台和 Driver 过滤用例。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/base.py`
  - 定义统一 Driver 接口。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/dry_run.py`
  - 实现无设备 dry-run Driver，用于本地验证平台链路。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/minium_driver.py`
  - 定义 Minium Driver 边界，未安装 Minium 时给出清晰错误。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/registry.py`
  - 根据 Driver 名称创建对应实现。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/ai/failure_analyzer.py`
  - 第一版提供规则化失败归因和报告摘要，后续替换为真实 AI Agent。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/reporter.py`
  - 写出 `summary.json` 报告。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/runner.py`
  - 编排用例执行。
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/cli.py`
  - 提供命令行入口。
- 新增：`miniapp-ui-auto/schemas/case.schema.json`
  - YAML 用例的 JSON Schema。
- 新增：`miniapp-ui-auto/cases/smoke/miniapp_login_001.yaml`
  - 第一条 P0 冒烟示例用例。
- 新增：`miniapp-ui-auto/config/env.yaml`
  - 测试环境配置示例。
- 新增：`miniapp-ui-auto/config/minium.yaml`
  - Minium 配置示例。
- 新增：`miniapp-ui-auto/reports/.gitkeep`
  - 保留报告目录。
- 新增：`miniapp-ui-auto/tests/test_case_loader.py`
  - 覆盖用例加载和 Schema 错误。
- 新增：`miniapp-ui-auto/tests/test_filtering.py`
  - 覆盖用例过滤。
- 新增：`miniapp-ui-auto/tests/test_minium_driver.py`
  - 覆盖 Minium 未安装时的错误提示。
- 新增：`miniapp-ui-auto/tests/test_runner_dry_run.py`
  - 覆盖 dry-run 执行和报告生成。

---

## 任务 1：创建工程骨架和用例 Schema

**涉及文件：**
- 新增：`miniapp-ui-auto/pyproject.toml`
- 新增：`miniapp-ui-auto/README.md`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/__init__.py`
- 新增：`miniapp-ui-auto/schemas/case.schema.json`
- 新增：`miniapp-ui-auto/cases/smoke/miniapp_login_001.yaml`
- 新增：`miniapp-ui-auto/config/env.yaml`
- 新增：`miniapp-ui-auto/config/minium.yaml`
- 新增：`miniapp-ui-auto/reports/.gitkeep`

- [ ] **步骤 1：创建 Python 工程配置**

创建 `miniapp-ui-auto/pyproject.toml`：

```toml
[project]
name = "miniapp-ui-auto"
version = "0.1.0"
description = "Minium-oriented miniapp UI automation MVP"
requires-python = ">=3.11"
dependencies = [
  "pyyaml>=6.0.2",
  "jsonschema>=4.23.0"
]

[project.optional-dependencies]
test = [
  "pytest>=8.2.0"
]

[project.scripts]
miniapp-ui-auto = "miniapp_ui_auto.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **步骤 2：创建包声明文件**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/__init__.py`：

```python
"""Miniapp UI automation MVP package."""

__version__ = "0.1.0"
```

- [ ] **步骤 3：创建 YAML 用例 Schema**

创建 `miniapp-ui-auto/schemas/case.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Miniapp UI Automation Case",
  "type": "object",
  "required": ["id", "title", "platform", "driver", "module", "priority", "tags", "owner", "version", "steps", "assertions"],
  "properties": {
    "id": { "type": "string", "pattern": "^[a-zA-Z0-9_\\-]+$" },
    "title": { "type": "string", "minLength": 1 },
    "platform": { "type": "string", "enum": ["miniapp"] },
    "driver": { "type": "string", "enum": ["dry-run", "minium"] },
    "module": { "type": "string", "minLength": 1 },
    "priority": { "type": "string", "enum": ["P0", "P1", "P2", "P3"] },
    "tags": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 },
      "minItems": 1,
      "uniqueItems": true
    },
    "owner": { "type": "string", "minLength": 1 },
    "version": { "type": "integer", "minimum": 1 },
    "preconditions": {
      "type": "array",
      "items": { "type": "string" },
      "default": []
    },
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["action", "target"],
        "properties": {
          "action": {
            "type": "string",
            "enum": ["open_page", "tap", "input", "wait", "assert_text", "assert_element", "assert_data", "screenshot", "mock", "set_storage"]
          },
          "target": { "type": "string", "minLength": 1 },
          "value": {},
          "timeout_ms": { "type": "integer", "minimum": 0 }
        },
        "additionalProperties": false
      }
    },
    "assertions": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["type", "target", "expected"],
        "properties": {
          "type": { "type": "string", "enum": ["text", "element", "data", "api"] },
          "target": { "type": "string", "minLength": 1 },
          "expected": {}
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

- [ ] **步骤 4：创建示例冒烟用例**

创建 `miniapp-ui-auto/cases/smoke/miniapp_login_001.yaml`：

```yaml
id: miniapp_login_001
title: 手机号验证码登录成功
platform: miniapp
driver: dry-run
module: login
priority: P0
tags:
  - smoke
  - regression
owner: qa
version: 1
preconditions:
  - 已配置测试环境
  - 验证码服务使用固定验证码
steps:
  - action: open_page
    target: pages/index/index
  - action: tap
    target: 我的
  - action: tap
    target: 登录
  - action: input
    target: 手机号输入框
    value: "13800000000"
  - action: input
    target: 验证码输入框
    value: "123456"
  - action: tap
    target: 确认登录
assertions:
  - type: text
    target: 用户昵称
    expected: visible
  - type: api
    target: login
    expected: success
```

- [ ] **步骤 5：创建配置文件和报告目录**

创建 `miniapp-ui-auto/config/env.yaml`：

```yaml
env: test
base_url: ""
miniapp:
  appid: ""
  project_path: ""
accounts:
  default_user:
    phone: "13800000000"
    captcha: "123456"
```

创建 `miniapp-ui-auto/config/minium.yaml`：

```yaml
minium:
  cli_path: ""
  project_path: ""
  platform: ide
  device_desire: {}
```

创建空文件 `miniapp-ui-auto/reports/.gitkeep`。

- [ ] **步骤 6：创建 README**

创建 `miniapp-ui-auto/README.md`：

````markdown
# 小程序 UI 自动化 MVP

这是 UI 自动化平台的小程序首期工程，用于先跑通用例资产、执行编排、Driver 抽象和报告闭环。

## 安装

```bash
python -m pip install -e ".[test]"
```

## 执行 dry-run 冒烟用例

```bash
miniapp-ui-auto run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

## 用例模型

用例使用 YAML 编写，并通过 `schemas/case.schema.json` 校验。执行器消费标准动作，例如 `open_page`、`tap`、`input` 和断言动作。Minium 被封装在 Driver 层，后续 Web/App/API Driver 可以复用同一套编排和报告链路。
````

- [ ] **步骤 7：验证骨架文件**

运行：

```powershell
Get-ChildItem -Recurse miniapp-ui-auto
```

预期：能看到 `pyproject.toml`、`schemas/case.schema.json`、`cases/smoke/miniapp_login_001.yaml`、`config/env.yaml`、`config/minium.yaml` 和 `src/miniapp_ui_auto/__init__.py`。

- [ ] **步骤 8：提交**

```bash
git add miniapp-ui-auto/pyproject.toml miniapp-ui-auto/README.md miniapp-ui-auto/src/miniapp_ui_auto/__init__.py miniapp-ui-auto/schemas/case.schema.json miniapp-ui-auto/cases/smoke/miniapp_login_001.yaml miniapp-ui-auto/config/env.yaml miniapp-ui-auto/config/minium.yaml miniapp-ui-auto/reports/.gitkeep
git commit -m "feat: scaffold miniapp ui automation project"
```

---

## 任务 2：实现用例加载和 Schema 校验

**涉及文件：**
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/models.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/case_loader.py`
- 新增：`miniapp-ui-auto/tests/test_case_loader.py`

- [ ] **步骤 1：先写失败测试**

创建 `miniapp-ui-auto/tests/test_case_loader.py`：

```python
from pathlib import Path

import pytest

from miniapp_ui_auto.case_loader import CaseValidationError, load_cases


def test_load_valid_case_from_directory():
    cases = load_cases(Path("cases"), Path("schemas/case.schema.json"))

    assert len(cases) == 1
    case = cases[0]
    assert case.id == "miniapp_login_001"
    assert case.platform == "miniapp"
    assert case.driver == "dry-run"
    assert case.steps[0].action == "open_page"
    assert case.assertions[0].target == "用户昵称"


def test_invalid_case_reports_file_and_schema_message(tmp_path):
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    invalid_case = case_dir / "bad.yaml"
    invalid_case.write_text(
        "id: bad_case\n"
        "title: Missing required fields\n",
        encoding="utf-8",
    )

    with pytest.raises(CaseValidationError) as error:
        load_cases(case_dir, Path("schemas/case.schema.json"))

    assert "bad.yaml" in str(error.value)
    assert "required property" in str(error.value)
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_case_loader.py -v
```

预期：失败，错误为 `ModuleNotFoundError: No module named 'miniapp_ui_auto.case_loader'`。

- [ ] **步骤 3：实现数据模型**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/models.py`：

```python
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
```

- [ ] **步骤 4：实现用例加载器**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/case_loader.py`：

```python
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
        steps=steps,
        assertions=assertions,
        source_path=str(source_path),
    )
```

- [ ] **步骤 5：运行用例加载测试**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_case_loader.py -v
```

预期：通过，输出 `2 passed`。

- [ ] **步骤 6：提交**

```bash
git add miniapp-ui-auto/src/miniapp_ui_auto/models.py miniapp-ui-auto/src/miniapp_ui_auto/case_loader.py miniapp-ui-auto/tests/test_case_loader.py
git commit -m "feat: load and validate yaml cases"
```

---

## 任务 3：实现用例过滤

**涉及文件：**
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/filtering.py`
- 新增：`miniapp-ui-auto/tests/test_filtering.py`

- [ ] **步骤 1：先写失败测试**

创建 `miniapp-ui-auto/tests/test_filtering.py`：

```python
from miniapp_ui_auto.filtering import CaseFilter, filter_cases
from miniapp_ui_auto.models import TestCase


def make_case(case_id: str, tags: tuple[str, ...], priority: str, module: str, driver: str = "dry-run"):
    return TestCase(
        id=case_id,
        title=case_id,
        platform="miniapp",
        driver=driver,
        module=module,
        priority=priority,
        tags=tags,
        owner="qa",
        version=1,
        preconditions=(),
        steps=(),
        assertions=(),
        source_path=f"{case_id}.yaml",
    )


def test_filter_by_tag_priority_module_and_driver():
    cases = [
        make_case("case_1", ("smoke",), "P0", "login"),
        make_case("case_2", ("regression",), "P1", "order"),
        make_case("case_3", ("smoke",), "P0", "login", driver="minium"),
    ]

    selected = filter_cases(
        cases,
        CaseFilter(tags=("smoke",), priorities=("P0",), modules=("login",), drivers=("dry-run",)),
    )

    assert [case.id for case in selected] == ["case_1"]


def test_empty_filter_returns_all_cases():
    cases = [
        make_case("case_1", ("smoke",), "P0", "login"),
        make_case("case_2", ("regression",), "P1", "order"),
    ]

    selected = filter_cases(cases, CaseFilter())

    assert [case.id for case in selected] == ["case_1", "case_2"]
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_filtering.py -v
```

预期：失败，错误为 `ModuleNotFoundError: No module named 'miniapp_ui_auto.filtering'`。

- [ ] **步骤 3：实现过滤逻辑**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/filtering.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

from miniapp_ui_auto.models import TestCase


@dataclass(frozen=True)
class CaseFilter:
    tags: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    drivers: tuple[str, ...] = ()


def filter_cases(cases: list[TestCase], case_filter: CaseFilter) -> list[TestCase]:
    return [case for case in cases if _matches(case, case_filter)]


def _matches(case: TestCase, case_filter: CaseFilter) -> bool:
    if case_filter.tags and not set(case_filter.tags).issubset(case.tags):
        return False
    if case_filter.priorities and case.priority not in case_filter.priorities:
        return False
    if case_filter.modules and case.module not in case_filter.modules:
        return False
    if case_filter.platforms and case.platform not in case_filter.platforms:
        return False
    if case_filter.drivers and case.driver not in case_filter.drivers:
        return False
    return True
```

- [ ] **步骤 4：运行过滤测试**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_filtering.py -v
```

预期：通过，输出 `2 passed`。

- [ ] **步骤 5：提交**

```bash
git add miniapp-ui-auto/src/miniapp_ui_auto/filtering.py miniapp-ui-auto/tests/test_filtering.py
git commit -m "feat: filter automation cases"
```

---

## 任务 4：实现 Driver 抽象和 Minium 边界

**涉及文件：**
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/base.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/dry_run.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/minium_driver.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/drivers/registry.py`
- 新增：`miniapp-ui-auto/tests/test_minium_driver.py`

- [ ] **步骤 1：先写 Minium 边界失败测试**

创建 `miniapp-ui-auto/tests/test_minium_driver.py`：

```python
import pytest

from miniapp_ui_auto.drivers.minium_driver import MiniumDriver, MiniumUnavailableError
from miniapp_ui_auto.models import RunContext


def test_minium_driver_fails_clearly_when_minium_is_not_installed():
    driver = MiniumDriver()

    with pytest.raises(MiniumUnavailableError) as error:
        driver.setup(RunContext(env="test", trigger="local"))

    assert "pip install minium" in str(error.value)
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_minium_driver.py -v
```

预期：失败，错误为 `ModuleNotFoundError: No module named 'miniapp_ui_auto.drivers'`。

- [ ] **步骤 3：实现统一 Driver 接口**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/drivers/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from miniapp_ui_auto.models import RunContext, Step, StepResult


class AutomationDriver(ABC):
    name: str

    @abstractmethod
    def setup(self, context: RunContext) -> None:
        """Prepare the driver before executing cases."""

    @abstractmethod
    def execute_step(self, step: Step) -> StepResult:
        """Execute one normalized automation step."""

    @abstractmethod
    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        """Capture screenshots, logs, or other useful artifacts."""

    @abstractmethod
    def teardown(self) -> None:
        """Release resources after the run."""
```

- [ ] **步骤 4：实现 dry-run Driver**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/drivers/dry_run.py`：

```python
from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class DryRunDriver(AutomationDriver):
    name = "dry-run"

    def __init__(self) -> None:
        self.context: RunContext | None = None
        self.executed_steps: list[Step] = []

    def setup(self, context: RunContext) -> None:
        self.context = context

    def execute_step(self, step: Step) -> StepResult:
        self.executed_steps.append(step)
        return StepResult(
            action=step.action,
            target=step.target,
            status="passed",
            message=f"dry-run executed {step.action} on {step.target}",
        )

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        self.context = None
```

- [ ] **步骤 5：实现 Minium Driver 边界**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/drivers/minium_driver.py`：

```python
from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class MiniumUnavailableError(RuntimeError):
    """Raised when Minium is not installed or cannot be imported."""


class MiniumDriver(AutomationDriver):
    name = "minium"

    def __init__(self) -> None:
        self._minium_module = None

    def setup(self, context: RunContext) -> None:
        try:
            import minium  # type: ignore
        except ImportError as exc:
            raise MiniumUnavailableError(
                "Minium is not installed. Install and configure it with `pip install minium` "
                "after the WeChat DevTools environment is ready."
            ) from exc
        self._minium_module = minium

    def execute_step(self, step: Step) -> StepResult:
        if self._minium_module is None:
            return StepResult(
                action=step.action,
                target=step.target,
                status="failed",
                message="Minium driver is not set up.",
            )
        return StepResult(
            action=step.action,
            target=step.target,
            status="failed",
            message="Real Minium step execution will be wired after the local WeChat DevTools environment is ready.",
        )

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        self._minium_module = None
```

- [ ] **步骤 6：实现 Driver Registry**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/drivers/registry.py`：

```python
from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.drivers.dry_run import DryRunDriver
from miniapp_ui_auto.drivers.minium_driver import MiniumDriver


def create_driver(name: str) -> AutomationDriver:
    if name == "dry-run":
        return DryRunDriver()
    if name == "minium":
        return MiniumDriver()
    supported = "dry-run, minium"
    raise ValueError(f"Unsupported driver '{name}'. Supported drivers: {supported}")
```

- [ ] **步骤 7：运行 Minium 边界测试**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_minium_driver.py -v
```

预期：通过，输出 `1 passed`。

- [ ] **步骤 8：提交**

```bash
git add miniapp-ui-auto/src/miniapp_ui_auto/drivers/base.py miniapp-ui-auto/src/miniapp_ui_auto/drivers/dry_run.py miniapp-ui-auto/src/miniapp_ui_auto/drivers/minium_driver.py miniapp-ui-auto/src/miniapp_ui_auto/drivers/registry.py miniapp-ui-auto/tests/test_minium_driver.py
git commit -m "feat: add driver abstraction and minium boundary"
```

---

## 任务 5：实现执行编排、报告和失败分析

**涉及文件：**
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/ai/failure_analyzer.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/reporter.py`
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/runner.py`
- 新增：`miniapp-ui-auto/tests/test_runner_dry_run.py`

- [ ] **步骤 1：先写 dry-run 执行测试**

创建 `miniapp-ui-auto/tests/test_runner_dry_run.py`：

```python
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

    assert result.total == 1
    assert result.passed == 1
    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["cases"][0]["case_id"] == "miniapp_login_001"
    assert summary["cases"][0]["status"] == "passed"
    assert "本次回归共执行 1 条" in summary["ai_summary"]
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_runner_dry_run.py -v
```

预期：失败，错误为 `ModuleNotFoundError: No module named 'miniapp_ui_auto.runner'`。

- [ ] **步骤 3：实现失败分析入口**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/ai/failure_analyzer.py`：

```python
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
    if "not installed" in combined or "environment" in combined:
        return "环境问题", "执行环境或依赖未准备完成。"
    if "assert" in combined.lower():
        return "功能缺陷", "断言未满足，需要结合截图和接口日志确认业务行为。"
    return "脚本问题", "执行步骤失败，需要检查用例步骤、元素定位或 Driver 映射。"
```

- [ ] **步骤 4：实现 Summary JSON 报告**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/reporter.py`：

```python
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
```

- [ ] **步骤 5：实现执行编排**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/runner.py`：

```python
from __future__ import annotations

from pathlib import Path

from miniapp_ui_auto.ai.failure_analyzer import classify_failure
from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import CaseResult, RunContext, StepResult, TestCase
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
        status=status,
        steps=tuple(step_results),
        failure_category=category,
        failure_summary=summary,
    )
```

- [ ] **步骤 6：运行 dry-run 执行测试**

运行：

```bash
cd miniapp-ui-auto
python -m pytest tests/test_runner_dry_run.py -v
```

预期：通过，输出 `1 passed`。

- [ ] **步骤 7：提交**

```bash
git add miniapp-ui-auto/src/miniapp_ui_auto/ai/failure_analyzer.py miniapp-ui-auto/src/miniapp_ui_auto/reporter.py miniapp-ui-auto/src/miniapp_ui_auto/runner.py miniapp-ui-auto/tests/test_runner_dry_run.py
git commit -m "feat: run dry-run cases and write summary"
```

---

## 任务 6：实现命令行执行入口

**涉及文件：**
- 新增：`miniapp-ui-auto/src/miniapp_ui_auto/cli.py`
- 修改：`miniapp-ui-auto/README.md`

- [ ] **步骤 1：实现 CLI**

创建 `miniapp-ui-auto/src/miniapp_ui_auto/cli.py`：

```python
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
```

- [ ] **步骤 2：运行全量测试**

运行：

```bash
cd miniapp-ui-auto
python -m pytest -v
```

预期：通过，输出 `6 passed`。

- [ ] **步骤 3：运行 CLI dry-run**

运行：

```bash
cd miniapp-ui-auto
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

预期输出：

```text
total=1 passed=1 failed=0 skipped=0
```

预期文件：`miniapp-ui-auto/reports/summary/summary.json` 存在，并包含 `miniapp_login_001`。

- [ ] **步骤 4：补充 README 验证方式**

在 `miniapp-ui-auto/README.md` 增加：

````markdown
## 本地验证

```bash
python -m pytest -v
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

dry-run 命令会写出 `reports/summary/summary.json`。
````

- [ ] **步骤 5：提交**

```bash
git add miniapp-ui-auto/src/miniapp_ui_auto/cli.py miniapp-ui-auto/README.md miniapp-ui-auto/reports/summary/summary.json
git commit -m "feat: add automation runner cli"
```

---

## 任务 7：最终验证和文档关联

**涉及文件：**
- 修改：`docs/superpowers/specs/2026-06-09-miniapp-ui-automation-platform-design.md`
- 修改：`miniapp-ui-auto/README.md`

- [ ] **步骤 1：在设计文档里关联 MVP 工程入口**

在 `docs/superpowers/specs/2026-06-09-miniapp-ui-automation-platform-design.md` 末尾追加：

```markdown
## 一期 MVP 工程入口

首版工程位于 `miniapp-ui-auto/`，先提供可本地验证的 dry-run Driver，并保留 Minium Driver 边界。真实 Minium 环境接入时，只需要继续完善 `src/miniapp_ui_auto/drivers/minium_driver.py`，用例加载、筛选、执行编排和报告能力不需要重写。
```

- [ ] **步骤 2：运行最终验证**

运行：

```bash
cd miniapp-ui-auto
python -m pytest -v
python -m miniapp_ui_auto.cli run --cases cases --driver dry-run --tag smoke --report-dir reports/summary
```

预期：

```text
6 passed
total=1 passed=1 failed=0 skipped=0
```

- [ ] **步骤 3：检查 Git 状态**

运行：

```bash
git status --short
```

预期：只有本次计划内文件处于修改或未跟踪状态。已有的 `prompt_pretrain_agent_samples.csv` 和 `prompt_pretrain_agent_samples.xlsx` 仍保持未跟踪，且不被暂存。

- [ ] **步骤 4：提交**

```bash
git add docs/superpowers/specs/2026-06-09-miniapp-ui-automation-platform-design.md miniapp-ui-auto/README.md
git commit -m "docs: link miniapp automation mvp"
```

---

## 自检结果

需求覆盖：

- YAML 用例管理：任务 1、任务 2 覆盖。
- Minium 优先的 Driver 架构：任务 4 覆盖。
- 统一 Driver 协议：任务 4 覆盖。
- 命令行和 CI 友好执行：任务 6 覆盖。
- Summary JSON 和 AI 可读失败分析：任务 5 覆盖。
- 第一版本地可验证闭环：任务 5、任务 6、任务 7 覆盖。
- Allure 报告暂不放入本 MVP：第一版先把 Summary 数据模型和 dry-run 执行链路打通，后续真实 Minium 截图和日志接入后再加 Allure 输出。

占位检查：

- 本计划没有未定义的实现项。
- `minium_driver.py` 对真实 Minium 执行只保留清晰边界说明，这是本期范围控制，不是遗漏。

类型一致性：

- `TestCase`、`Step`、`Assertion`、`RunContext`、`StepResult`、`CaseResult`、`RunSummary` 都先定义再使用。
- `CaseFilter`、`load_cases`、`create_driver`、`run_cases`、`write_summary` 在测试和实现中的名称保持一致。
