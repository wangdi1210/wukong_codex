from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GeneratedCase:
    payload: dict[str, Any]
    yaml_text: str


def generate_case_from_text(
    text: str,
    *,
    case_id: str,
    title: str,
    module: str,
    priority: str = "P0",
    tags: tuple[str, ...] = ("smoke",),
    owner: str = "qa",
    driver: str = "dry-run",
) -> GeneratedCase:
    lines = _clean_lines(text)
    steps: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []

    for line in lines:
        if _looks_like_assertion(line):
            assertions.append(_parse_assertion(line))
        else:
            steps.append(_parse_step(line))

    if not steps:
        raise ValueError("自然语言内容中没有可生成的执行步骤。")
    if not assertions:
        assertions.append({"type": "text", "target": title, "expected": "visible"})

    payload = {
        "id": case_id,
        "title": title,
        "platform": "miniapp",
        "driver": driver,
        "module": module,
        "priority": priority,
        "tags": _dedupe(tags),
        "owner": owner,
        "version": 1,
        "preconditions": [],
        "steps": steps,
        "assertions": assertions,
    }
    yaml_text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return GeneratedCase(payload=payload, yaml_text=yaml_text)


def write_generated_case(generated_case: GeneratedCase, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generated_case.yaml_text, encoding="utf-8")
    return output_path


def _clean_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("；", "\n").replace("。", "\n")
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"^\s*[-*0-9.、）)]*\s*", "", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _dedupe(values: tuple[str, ...]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _looks_like_assertion(line: str) -> bool:
    assertion_prefixes = ("断言", "校验", "验证", "看到", "展示", "显示")
    result_keywords = ("提示", "成功", "失败")
    return line.startswith(assertion_prefixes) or any(line.endswith(keyword) for keyword in result_keywords)


def _parse_assertion(line: str) -> dict[str, Any]:
    target = _strip_known_prefixes(line, ("断言", "校验", "验证", "看到", "展示", "显示"))
    target = target.replace("页面", "").replace("成功", "成功").strip(" ：:")
    if not target:
        target = line
    return {"type": "text", "target": target, "expected": "visible"}


def _parse_step(line: str) -> dict[str, Any]:
    if line.startswith(("打开", "进入", "访问")):
        return {"action": "open_page", "target": _extract_target(line, ("打开", "进入", "访问"))}
    if line.startswith(("点击", "点", "选择")):
        return {"action": "tap", "target": _extract_target(line, ("点击", "点", "选择"))}
    if line.startswith(("输入", "填写", "填入")):
        target, value = _parse_input(line)
        step: dict[str, Any] = {"action": "input", "target": target}
        if value:
            step["value"] = value
        return step
    if line.startswith(("等待", "等到")):
        return {"action": "wait", "target": _extract_target(line, ("等待", "等到"))}
    if "截图" in line:
        return {"action": "screenshot", "target": _extract_target(line, ("截图", "保存截图")) or "当前页面"}
    return {"action": "tap", "target": line}


def _parse_input(line: str) -> tuple[str, str]:
    content = _extract_target(line, ("输入", "填写", "填入"))
    match = re.match(r"(.+?)(?:为|：|:)(.+)", content)
    if match:
        return match.group(1).strip(), match.group(2).strip().strip("\"'")
    return content, ""


def _extract_target(line: str, prefixes: tuple[str, ...]) -> str:
    target = _strip_known_prefixes(line, prefixes)
    return target.strip(" ：:，,。")


def _strip_known_prefixes(line: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return line.strip()
