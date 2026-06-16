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
    driver: str = "airtest",
    depends_on_previous: bool = False,
) -> GeneratedCase:
    lines = _clean_lines(text)
    preconditions: list[str] = []
    steps: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []

    for line in lines:
        if line.startswith(("前置条件", "前置")):
            preconditions.append(_strip_known_prefixes(line, ("前置条件", "前置")).strip(" ：:"))
        elif _looks_like_assertion(line):
            assertions.append(_parse_assertion(line))
        else:
            step = _parse_step(line)
            if _is_redundant_miniapp_entry_step(step, steps):
                continue
            steps.append(step)

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
        "preconditions": preconditions,
        "depends_on_previous": depends_on_previous,
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
    swipe_direction = _parse_swipe_direction(line)
    if swipe_direction:
        return {"action": "swipe", "target": swipe_direction}
    miniapp_search = _parse_miniapp_search(line)
    if miniapp_search:
        return {"action": "search_miniapp", "target": miniapp_search}
    if line.startswith(("打开", "进入", "访问")):
        target = _extract_target(line, ("打开", "进入", "访问"))
        if target in ("微信", "WeChat", "wechat"):
            return {"action": "open_app", "target": "微信"}
        if "小程序" in target:
            return {"action": "open_miniapp", "target": target.replace("小程序", "").strip() or target}
        return {"action": "open_page", "target": target}
    if line.startswith(("点击", "点", "选择")):
        return {"action": "tap", "target": _extract_target(line, ("点击", "点", "选择"))}
    inline_input = _parse_inline_input(line)
    if inline_input:
        target, value = inline_input
        return {"action": "input", "target": target, "value": value}
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


def _parse_swipe_direction(line: str) -> str:
    if any(keyword in line for keyword in ("下拉", "向下滑", "往下滑", "下滑")):
        return "down"
    if any(keyword in line for keyword in ("上拉", "向上滑", "往上滑", "上滑", "滑到底部")):
        return "up"
    if any(keyword in line for keyword in ("左滑", "向左滑", "往左滑")):
        return "left"
    if any(keyword in line for keyword in ("右滑", "向右滑", "往右滑")):
        return "right"
    return ""


def _parse_miniapp_search(line: str) -> str:
    if line.startswith("search_miniapp"):
        return _clean_target(line.removeprefix("search_miniapp"))
    if "输入框" in line and any(keyword in line for keyword in ("搜索", "搜")):
        target = _value_after_colon(line)
        if target:
            return _clean_target(target)
    if "小程序" not in line or not any(keyword in line for keyword in ("搜索", "查找", "搜", "找到")):
        return ""
    target = _strip_known_prefixes(line, ("搜索", "查找", "搜一下", "搜"))
    target = target.replace("从列表中找到", "").replace("小程序", "").replace("并进入", "").replace("点击进入", "").replace("进入", "")
    return _clean_target(target)


def _is_redundant_miniapp_entry_step(step: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    if not steps or steps[-1].get("action") != "search_miniapp":
        return False
    if step.get("action") == "search_miniapp":
        return True
    if step.get("action") != "tap":
        return False
    target = str(step.get("target") or "")
    return target in ("进入", "进入小程序", "打开", "打开小程序") or ("小程序" in target and "进入" in target)


def _parse_inline_input(line: str) -> tuple[str, str] | None:
    if "输入框" not in line or not any(keyword in line for keyword in ("发送", "输入", "填写", "填入")):
        return None
    value = _value_after_colon(line)
    if not value:
        return None
    return "输入框", _clean_target(value)


def _parse_input(line: str) -> tuple[str, str]:
    content = _extract_target(line, ("输入", "填写", "填入"))
    match = re.match(r"(.+?)(?:为|：|:)(.+)", content)
    if match:
        return match.group(1).strip(), match.group(2).strip().strip("\"'")
    return content, ""


def _value_after_colon(line: str) -> str:
    parts = re.split(r"[:：]", line, maxsplit=1)
    if len(parts) != 2:
        return ""
    return parts[1].strip()


def _extract_target(line: str, prefixes: tuple[str, ...]) -> str:
    target = _strip_known_prefixes(line, prefixes)
    return _clean_target(target)


def _strip_known_prefixes(line: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return line.strip()


def _clean_target(value: str) -> str:
    return value.strip(" ：:，,。\"'“”‘’")
