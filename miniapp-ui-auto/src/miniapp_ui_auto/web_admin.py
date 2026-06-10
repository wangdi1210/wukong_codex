from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from miniapp_ui_auto.case_generator import generate_case_from_text, write_generated_case
from miniapp_ui_auto.case_loader import load_cases
from miniapp_ui_auto.drivers.airtest_driver import load_airtest_config
from miniapp_ui_auto.drivers.registry import create_driver
from miniapp_ui_auto.filtering import CaseFilter, filter_cases
from miniapp_ui_auto.models import RunContext, TestCase
from miniapp_ui_auto.runner import run_cases


class WebAdminService:
    def __init__(
        self,
        *,
        case_root: Path = Path("cases"),
        schema_path: Path = Path("schemas/case.schema.json"),
        report_dir: Path = Path("reports/summary"),
    ) -> None:
        self.case_root = case_root
        self.schema_path = schema_path
        self.report_dir = report_dir
        self._last_device_environment: dict[str, Any] | None = None

    def list_cases(self) -> list[dict[str, Any]]:
        return [_case_record(case) for case in load_cases(self.case_root, self.schema_path)]

    def get_case(self, case_id: str) -> dict[str, Any]:
        case = self._find_case(case_id)
        return _case_detail(case)

    def generate_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _required(payload, "case_id")
        generated = generate_case_from_text(
            _required(payload, "text"),
            case_id=case_id,
            title=_required(payload, "title"),
            module=_required(payload, "module"),
            priority=payload.get("priority", "P0"),
            tags=tuple(payload.get("tags") or ["smoke", "ai-generated"]),
            owner=payload.get("owner", "qa"),
            driver=payload.get("driver", "airtest"),
        )
        output = self.case_root / payload.get("folder", "smoke") / f"{case_id}.yaml"
        write_generated_case(generated, output)
        load_cases(output.parent, self.schema_path)
        return {"path": str(output), "case": generated.payload}

    def update_case(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self._find_case(case_id)
        generated = generate_case_from_text(
            _required(payload, "text"),
            case_id=case_id,
            title=_required(payload, "title"),
            module=_required(payload, "module"),
            priority=payload.get("priority", existing.priority),
            tags=tuple(payload.get("tags") or existing.tags),
            owner=payload.get("owner", existing.owner),
            driver=payload.get("driver", existing.driver),
        )
        output = Path(existing.source_path)
        write_generated_case(generated, output)
        load_cases(output.parent, self.schema_path)
        return {"path": str(output), "case": generated.payload}

    def delete_case(self, case_id: str) -> dict[str, Any]:
        case = self._find_case(case_id)
        path = Path(case.source_path)
        path.unlink()
        return {"deleted": case_id, "path": str(path)}

    def run_cases(self, payload: dict[str, Any]) -> dict[str, Any]:
        cases = load_cases(self.case_root, self.schema_path)
        selected = filter_cases(
            cases,
            CaseFilter(
                tags=tuple(payload.get("tags") or []),
                priorities=tuple(payload.get("priorities") or []),
                modules=tuple(payload.get("modules") or []),
                drivers=tuple(payload.get("case_drivers") or []),
            ),
        )
        case_ids = set(payload.get("case_ids") or [])
        if case_ids:
            selected = [case for case in selected if case.id in case_ids]
        summary = run_cases(
            cases=selected,
            driver=create_driver(payload.get("driver", "dry-run")),
            context=RunContext(env=payload.get("env", "test"), trigger="web"),
            report_dir=self.report_dir,
        )
        return self.load_summary() | {"summary": asdict(summary)}

    def load_summary(self) -> dict[str, Any]:
        summary_path = self.report_dir / "summary.json"
        if not summary_path.exists():
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "ai_summary": "暂无执行报告。",
                "cases": [],
            }
        return json.loads(summary_path.read_text(encoding="utf-8"))

    def check_device_environment(self) -> dict[str, Any]:
        config = load_airtest_config(Path("config/airtest.yaml"))
        adb_check = _check_adb_devices()
        device_uri = config.device_uri or _device_uri_from_adb(adb_check.get("devices", []))
        config_payload = asdict(config) | {"resolved_device_uri": device_uri}
        checks = [
            adb_check,
            _check_airtest_connect(device_uri),
            _check_poco_connect(device_uri, enabled=config.poco_enabled),
        ]
        config_check = {
            "name": "设备配置",
            "ok": bool(device_uri),
            "message": f"使用设备地址：{device_uri}" if device_uri else "未配置 device_uri，且 ADB 未发现可用设备。",
            "command": "config/airtest.yaml",
        }
        checks.append(config_check)
        result = {
            "checks": checks,
            "config": config_payload,
            "devices": adb_check.get("devices", []),
            "ready": all(item["ok"] for item in checks),
            "checked_at": _now_text(),
        }
        self._last_device_environment = result
        return result

    def device_environment_status(self) -> dict[str, Any]:
        if self._last_device_environment is not None:
            return self._last_device_environment | {"cached": True}
        config = load_airtest_config(Path("config/airtest.yaml"))
        return {
            "checks": [
                {"name": "ADB", "ok": False, "message": "未检测，请点击“检查环境”进行真实检测。"},
                {"name": "Airtest", "ok": False, "message": "未检测，请点击“检查环境”进行真实检测。"},
                {"name": "Poco", "ok": False, "message": "未检测，请点击“检查环境”进行真实检测。"},
                {"name": "设备配置", "ok": bool(config.device_uri), "message": "已读取配置，尚未进行真实连接检测。"},
            ],
            "config": asdict(config) | {"resolved_device_uri": config.device_uri},
            "devices": [],
            "ready": False,
            "cached": False,
            "checked_at": "",
        }

    def _find_case(self, case_id: str) -> TestCase:
        for case in load_cases(self.case_root, self.schema_path):
            if case.id == case_id:
                return case
        raise ValueError(f"未找到用例：{case_id}")


def run_web_admin(host: str, port: int, service: WebAdminService | None = None) -> None:
    service = service or WebAdminService()

    class Handler(WebAdminHandler):
        web_service = service

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"miniapp-ui-auto web admin: http://{host}:{port}")
    server.serve_forever()


class WebAdminHandler(BaseHTTPRequestHandler):
    web_service: WebAdminService

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path).path
        if route == "/":
            self._send_html(_INDEX_HTML)
            return
        if route == "/api/cases":
            self._send_json({"cases": self.web_service.list_cases()})
            return
        if route.startswith("/api/cases/"):
            self._send_json(self.web_service.get_case(_route_id(route, "/api/cases/")))
            return
        if route == "/api/reports/latest":
            self._send_json(self.web_service.load_summary())
            return
        if route == "/api/devices/status":
            self._send_json(self.web_service.device_environment_status())
            return
        if route == "/api/devices/check":
            self._send_json(self.web_service.check_device_environment())
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path).path
        try:
            payload = self._read_payload()
            if route == "/api/cases/generate":
                self._send_json(self.web_service.generate_case(payload), HTTPStatus.CREATED)
                return
            if route == "/api/runs":
                self._send_json(self.web_service.run_cases(payload))
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - convert web errors into JSON responses.
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path).path
        try:
            if route.startswith("/api/cases/"):
                self._send_json(self.web_service.update_case(_route_id(route, "/api/cases/"), self._read_payload()))
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - convert web errors into JSON responses.
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path).path
        try:
            if route.startswith("/api/cases/"):
                self._send_json(self.web_service.delete_case(_route_id(route, "/api/cases/")))
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - convert web errors into JSON responses.
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        content_type = self.headers.get("content-type", "")
        if "application/json" in content_type:
            return json.loads(raw or "{}")
        parsed = parse_qs(raw)
        return {key: values[-1] for key, values in parsed.items()}

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _case_record(case: TestCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "module": case.module,
        "priority": case.priority,
        "tags": list(case.tags),
        "driver": case.driver,
        "owner": case.owner,
        "version": case.version,
        "source_path": case.source_path,
        "status": "启用",
        "created_at": _format_created_at(Path(case.source_path)),
    }


def _case_detail(case: TestCase) -> dict[str, Any]:
    record = _case_record(case)
    record.update(
        {
            "preconditions": list(case.preconditions),
            "steps": [asdict(step) for step in case.steps],
            "assertions": [asdict(assertion) for assertion in case.assertions],
            "natural_steps": _steps_to_natural_text(case),
            "natural_expected": "\n".join(str(item.expected if item.expected != "visible" else item.target) for item in case.assertions),
        }
    )
    return record


def _steps_to_natural_text(case: TestCase) -> str:
    lines = []
    for step in case.steps:
        if step.action == "open_app":
            lines.append(f"打开 {step.target}")
        elif step.action == "open_miniapp":
            lines.append(f"进入 {step.target}小程序")
        elif step.action == "tap":
            lines.append(f"点击 {step.target}")
        elif step.action == "input":
            value = "" if step.value is None else str(step.value)
            lines.append(f"输入 {step.target}：{value}")
        elif step.action == "swipe":
            labels = {"down": "下拉", "up": "上滑", "left": "左滑", "right": "右滑"}
            lines.append(labels.get(step.target, f"滑动 {step.target}"))
        elif step.action == "wait":
            lines.append(f"等待 {step.target}")
        elif step.action == "screenshot":
            lines.append("截图")
        else:
            lines.append(f"{step.action} {step.target}")
    return "\n".join(lines)


def _route_id(route: str, prefix: str) -> str:
    from urllib.parse import unquote

    case_id = unquote(route.removeprefix(prefix)).strip("/")
    if not case_id:
        raise ValueError("缺少用例 ID")
    return case_id


def _required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"缺少必填字段：{key}")
    return value


def _format_created_at(path: Path) -> str:
    try:
        from datetime import datetime

        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "-"


def _now_text() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _check_python_module(name: str, module_name: str) -> dict[str, Any]:
    try:
        module = __import__(module_name)
    except ImportError as exc:
        return {"name": name, "ok": False, "message": f"未安装或不可导入：{exc}"}
    return {"name": name, "ok": True, "message": "已安装", "detail": getattr(module, "__file__", "")}


def _check_adb_devices() -> dict[str, Any]:
    adb = shutil.which("adb")
    if not adb:
        return {"name": "ADB", "ok": False, "message": "未找到 adb 命令，请安装 Android SDK platform-tools 并加入 PATH。", "devices": [], "command": "adb devices"}
    try:
        result = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": "ADB", "ok": False, "message": f"执行 adb devices 失败：{exc}", "devices": [], "command": "adb devices"}

    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "status": parts[1]})
    ok_devices = [item for item in devices if item["status"] == "device"]
    base = {
        "name": "ADB",
        "command": f"{adb} devices",
        "devices": devices,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if ok_devices:
        return base | {"ok": True, "message": f"已连接 {len(ok_devices)} 台设备：{', '.join(item['serial'] for item in ok_devices)}。"}
    return base | {"ok": False, "message": "未发现可用设备，请确认 USB 调试和授权弹窗。"}


def _device_uri_from_adb(devices: list[dict[str, Any]]) -> str:
    for device in devices:
        if device.get("status") == "device" and device.get("serial"):
            return f"Android:///{device['serial']}"
    return ""


def _check_airtest_connect(device_uri: str) -> dict[str, Any]:
    module_check = _check_python_module("Airtest", "airtest.core.api")
    if not module_check["ok"]:
        return module_check
    if not device_uri:
        return {"name": "Airtest", "ok": False, "message": "没有可连接的设备地址，先处理 ADB 连接。", "command": "connect_device"}
    script = """
import json
from airtest.core.api import connect_device
uri = __DEVICE_URI__
device = connect_device(uri)
print(json.dumps({"ok": True, "uuid": getattr(device, "uuid", ""), "uri": uri}, ensure_ascii=False))
""".replace("__DEVICE_URI__", repr(device_uri))
    return _run_probe("Airtest", script, f"connect_device({device_uri})", timeout=20)


def _check_poco_connect(device_uri: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"name": "Poco", "ok": True, "message": "配置未启用 Poco，已跳过真实初始化。", "command": "config.airtest.poco.enabled=false"}
    module_check = _check_python_module("Poco", "poco.drivers.android.uiautomation")
    if not module_check["ok"]:
        return module_check
    if not device_uri:
        return {"name": "Poco", "ok": False, "message": "没有可连接的设备地址，先处理 ADB 连接。", "command": "AndroidUiautomationPoco"}
    script = """
import json
from airtest.core.api import connect_device
from poco.drivers.android.uiautomation import AndroidUiautomationPoco
uri = __DEVICE_URI__
connect_device(uri)
poco = AndroidUiautomationPoco(use_airtest_input=True, screenshot_each_action=False)
print(json.dumps({"ok": True, "uri": uri, "poco": type(poco).__name__}, ensure_ascii=False))
""".replace("__DEVICE_URI__", repr(device_uri))
    return _run_probe("Poco", script, f"AndroidUiautomationPoco({device_uri})", timeout=25)


def _run_probe(name: str, script: str, command: str, *, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "message": f"真实检测超时（{timeout}s），请检查设备授权或连接状态。", "command": command}
    except OSError as exc:
        return {"name": name, "ok": False, "message": f"真实检测执行失败：{exc}", "command": command}

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode == 0:
        detail = stdout.splitlines()[-1] if stdout else ""
        return {"name": name, "ok": True, "message": "真实连接成功", "command": command, "stdout": detail, "stderr": stderr}
    message = stderr or stdout or f"进程退出码 {result.returncode}"
    return {"name": name, "ok": False, "message": message, "command": command, "stdout": stdout, "stderr": stderr}


_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>职悟空 · UI自动化测试</title>
  <style>
    :root { font-family: Arial, "Microsoft YaHei", sans-serif; color: #1f2329; background: #f4f6fa; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f4f6fa; }
    .topbar { height: 60px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: #fff; border-bottom: 1px solid #e5e6eb; }
    .brand { color: #1677ff; font-size: 18px; font-weight: 700; letter-spacing: 0; }
    .nav { display: flex; gap: 34px; height: 100%; align-items: center; }
    .nav button { height: 100%; border: 0; background: transparent; color: #303133; font-size: 14px; cursor: pointer; border-bottom: 2px solid transparent; border-radius: 0; padding: 0; }
    .nav button.active { color: #1677ff; border-bottom-color: #1677ff; font-weight: 600; }
    main { max-width: 1354px; margin: 0 auto; padding: 24px 0 48px; }
    .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .metric-card { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(15, 23, 42, .06); padding: 24px; min-height: 116px; border: 1px solid #edf0f5; }
    .metric-label { color: #858b99; font-size: 14px; margin-bottom: 18px; }
    .metric-value { font-size: 30px; font-weight: 700; line-height: 1; }
    .blue { color: #1677ff; } .green { color: #52c41a; } .orange { color: #fa8c16; } .dark { color: #1f2329; }
    .toolbar, .table-card, .panel { background: #fff; border-radius: 8px; border: 1px solid #edf0f5; box-shadow: 0 1px 3px rgba(15, 23, 42, .04); }
    .toolbar { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; margin-bottom: 14px; gap: 16px; }
    .left-tools, .right-tools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    button, select, input, textarea { font: inherit; }
    .btn { border: 1px solid #d9d9d9; background: #fff; color: #1f2329; height: 36px; padding: 0 18px; border-radius: 4px; cursor: pointer; }
    .btn.primary { background: #1677ff; border-color: #1677ff; color: #fff; }
    .btn.success { background: #52c41a; border-color: #52c41a; color: #fff; }
    .btn.text { border: 0; background: transparent; color: #1677ff; padding: 0 6px; height: auto; }
    select, input { height: 34px; border: 1px solid #d9d9d9; border-radius: 4px; padding: 0 12px; background: #fff; min-width: 102px; }
    .search { width: 200px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    thead { background: #fafafa; }
    th, td { padding: 14px 16px; border-bottom: 1px solid #f0f0f0; text-align: left; white-space: nowrap; }
    th { color: #333; font-weight: 600; }
    tbody tr:hover { background: #fafcff; }
    .checkbox { width: 16px; height: 16px; accent-color: #1677ff; }
    .tag { display: inline-block; border-radius: 2px; padding: 3px 8px; font-size: 12px; line-height: 18px; }
    .tag-p0 { color: #cf1322; background: #fff1f0; }
    .tag-p1 { color: #f5222d; background: #fff1f0; }
    .tag-p2 { color: #fa8c16; background: #fff7e6; }
    .tag-p3 { color: #1677ff; background: #e6f4ff; }
    .status-on { color: #52c41a; background: #f6ffed; }
    .empty { padding: 36px; text-align: center; color: #858b99; }
    .tab-page { display: none; }
    .tab-page.active { display: block; }
    .panel { padding: 22px 24px; margin-bottom: 16px; }
    .panel h2 { margin: 0 0 16px; font-size: 18px; }
    pre { background: #f6f8fb; border: 1px solid #e8edf3; border-radius: 6px; padding: 14px; min-height: 120px; overflow: auto; white-space: pre-wrap; }
    .modal-mask { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.45); align-items: center; justify-content: center; z-index: 10; }
    .modal-mask.show { display: flex; }
    .modal { width: 600px; max-width: calc(100vw - 32px); background: #fff; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,.18); }
    .modal-head { height: 66px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; border-bottom: 1px solid #f0f0f0; }
    .modal-title { font-size: 18px; font-weight: 700; }
    .close { border: 0; background: transparent; font-size: 24px; color: #8c8c8c; cursor: pointer; }
    .modal-body { padding: 24px; }
    .modal-foot { height: 68px; display: flex; align-items: center; justify-content: flex-end; gap: 20px; padding: 0 32px; border-top: 1px solid #f0f0f0; }
    label { display: block; margin: 0 0 8px; color: #555; font-size: 14px; }
    .field { margin-bottom: 18px; }
    .field input, .field select, .field textarea { width: 100%; min-width: 0; }
    .field textarea { height: 80px; padding: 10px 12px; resize: vertical; border: 1px solid #d9d9d9; border-radius: 4px; }
    .toast { position: fixed; right: 24px; bottom: 24px; background: #1f2329; color: #fff; padding: 12px 16px; border-radius: 6px; display: none; z-index: 20; }
    .toast.show { display: block; }
    .device-wrap { max-width: 1152px; margin: 0 auto; }
    .check-row { display: flex; gap: 24px; align-items: center; margin: 22px 0; flex-wrap: wrap; }
    .check-item { display: inline-flex; align-items: center; gap: 8px; font-size: 20px; }
    .dot { width: 12px; height: 12px; border-radius: 50%; background: #d9d9d9; display: inline-block; }
    .dot.ok { background: #52c41a; }
    .dot.fail { background: #ff4d4f; }
    .dot.pending { background: #d9d9d9; }
    .check-detail { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    .check-card { border: 1px solid #edf0f5; border-radius: 6px; padding: 12px; background: #fafcff; }
    .check-title { display: flex; align-items: center; gap: 8px; font-weight: 700; margin-bottom: 8px; }
    .check-message { color: #4e5969; line-height: 1.5; white-space: pre-wrap; word-break: break-all; }
    .check-command { margin-top: 8px; color: #858b99; font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }
    .step-list { margin-top: 20px; }
    .step { display: grid; grid-template-columns: 44px 1fr; gap: 0; padding: 18px 0; border-bottom: 1px solid #f0f0f0; }
    .step:last-child { border-bottom: 0; }
    .step-no { width: 28px; height: 28px; border-radius: 50%; background: #1677ff; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; }
    .step-title { font-size: 22px; margin-bottom: 8px; }
    .step-desc { color: #4e5969; font-size: 14px; }
    .code-line { background: #f6f8fb; border-radius: 4px; padding: 18px; font-family: Consolas, monospace; color: #1d2129; overflow-x: auto; }
    .config-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    .config-item { background: #f8fafc; border: 1px solid #edf0f5; border-radius: 6px; padding: 12px; }
    .config-item span { display: block; color: #858b99; font-size: 13px; margin-bottom: 6px; }
    .device-table { margin-top: 14px; }
    @media (max-width: 900px) {
      main { padding: 16px; }
      .metrics { grid-template-columns: repeat(2, 1fr); }
      .toolbar { align-items: stretch; flex-direction: column; }
      .right-tools { justify-content: flex-start; }
      .table-card { overflow-x: auto; }
      .topbar { align-items: flex-start; height: auto; gap: 12px; flex-direction: column; padding: 14px 16px; }
      .nav { height: 40px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">职悟空 · UI自动化测试</div>
    <nav class="nav">
      <button class="active" data-tab="cases" onclick="switchTab('cases')">用例管理</button>
      <button data-tab="runs" onclick="switchTab('runs')">执行记录</button>
      <button data-tab="reports" onclick="switchTab('reports')">测试报告</button>
      <button data-tab="devices" onclick="switchTab('devices')">📱 设备</button>
    </nav>
  </header>
  <main>
    <section id="cases" class="tab-page active">
      <div class="metrics">
        <div class="metric-card"><div class="metric-label">总用例数</div><div class="metric-value blue" id="metricTotal">0</div></div>
        <div class="metric-card"><div class="metric-label">已启用</div><div class="metric-value green" id="metricEnabled">0</div></div>
        <div class="metric-card"><div class="metric-label">已禁用</div><div class="metric-value orange" id="metricDisabled">0</div></div>
        <div class="metric-card"><div class="metric-label">今日执行</div><div class="metric-value dark" id="metricToday">0</div></div>
      </div>
      <div class="toolbar">
        <div class="left-tools">
          <button class="btn primary" onclick="openModal()">+ 新增用例</button>
          <button class="btn success" id="runSelectedBtn" onclick="runSelected()">执行选中</button>
          <button class="btn" onclick="selectAllRows(true)">全选</button>
          <button class="btn" onclick="selectAllRows(false)">清空</button>
        </div>
        <div class="right-tools">
          <select id="moduleFilter" onchange="renderCaseTable()"><option value="">全部模块</option></select>
          <select id="priorityFilter" onchange="renderCaseTable()"><option value="">全部优先级</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
          <input class="search" id="searchInput" oninput="renderCaseTable()" placeholder="搜索用例...">
        </div>
      </div>
      <div class="table-card">
        <table>
          <thead>
            <tr>
              <th><input class="checkbox" type="checkbox" id="headCheck" onchange="selectAllRows(this.checked)"></th>
              <th>ID</th><th>用例标题</th><th>模块</th><th>优先级</th><th>状态</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody id="caseRows"></tbody>
        </table>
      </div>
    </section>
    <section id="runs" class="tab-page">
      <div class="panel">
        <h2>执行记录</h2>
        <pre id="runLog">暂无执行记录。请在“用例管理”中执行选中用例。</pre>
      </div>
    </section>
    <section id="reports" class="tab-page">
      <div class="panel">
        <h2>测试报告</h2>
        <div class="metrics">
          <div class="metric-card"><div class="metric-label">执行总数</div><div class="metric-value blue" id="reportTotal">0</div></div>
          <div class="metric-card"><div class="metric-label">通过</div><div class="metric-value green" id="reportPassed">0</div></div>
          <div class="metric-card"><div class="metric-label">失败</div><div class="metric-value orange" id="reportFailed">0</div></div>
          <div class="metric-card"><div class="metric-label">跳过</div><div class="metric-value dark" id="reportSkipped">0</div></div>
        </div>
        <pre id="aiSummary">暂无执行报告。</pre>
      </div>
    </section>
    <section id="devices" class="tab-page">
      <div class="device-wrap">
        <div class="panel">
          <h2>📱 连接设备</h2>
          <div class="check-row" id="deviceChecks">
            <span class="check-item"><span class="dot pending"></span>ADB 未检测</span>
            <span class="check-item"><span class="dot pending"></span>Airtest 未检测</span>
            <span class="check-item"><span class="dot pending"></span>Poco 未检测</span>
            <span class="check-item"><span class="dot pending"></span>设备配置 未检测</span>
          </div>
          <button class="btn primary" onclick="checkDevice()">检查环境</button>
          <div class="check-detail" id="checkDetail"></div>
          <div class="config-grid" id="deviceConfig"></div>
          <div class="device-table" id="deviceTable"></div>
        </div>
        <div class="panel">
          <h2>📋 连接步骤</h2>
          <div class="step-list">
            <div class="step"><div class="step-no">1</div><div><div class="step-title">开启手机开发者模式</div><div class="step-desc">设置 → 关于手机 → 连续点击“版本号”7次 → 返回设置 → 出现“开发者选项”</div></div></div>
            <div class="step"><div class="step-no">2</div><div><div class="step-title">开启USB调试</div><div class="step-desc">设置 → 开发者选项 → USB调试 → 开启</div></div></div>
            <div class="step"><div class="step-no">3</div><div><div class="step-title">连接手机到电脑</div><div class="step-desc">用USB数据线连接手机，手机上选择“传输文件”模式，弹窗时点击“确定”</div></div></div>
            <div class="step"><div class="step-no">4</div><div><div class="step-title">验证连接</div><div class="step-desc">点击上方“检查环境”，或在终端执行 adb devices，看到设备序列号即成功</div></div></div>
            <div class="step"><div class="step-no">5</div><div><div class="step-title">运行测试</div><div class="step-desc">在用例管理创建用例，选择要执行的用例，点击“执行选中”</div></div></div>
          </div>
        </div>
        <div class="panel">
          <h2>⚡ 快捷命令</h2>
          <div class="code-line">adb devices  # 检查设备<br>python -m miniapp_ui_auto.cli run --cases cases --driver airtest --tag smoke --report-dir reports/summary  # 运行测试</div>
        </div>
      </div>
    </section>
  </main>
  <div class="modal-mask" id="modalMask">
    <div class="modal">
      <div class="modal-head"><div class="modal-title" id="modalTitle">新增用例</div><button class="close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div class="field"><label>用例标题 *</label><input id="formTitle" placeholder="请输入用例标题"></div>
        <div class="field"><label>所属模块</label><input id="formModule" placeholder="例如：登录、首页、个人中心"></div>
        <div class="field"><label>优先级</label><select id="formPriority"><option value="P2">P2 - 中</option><option value="P0">P0 - 阻塞</option><option value="P1">P1 - 高</option><option value="P3">P3 - 低</option></select></div>
        <div class="field"><label>前置条件</label><textarea id="formPreconditions" placeholder="执行此用例前需要满足的条件"></textarea></div>
        <div class="field"><label>测试步骤 *</label><textarea id="formSteps" placeholder="1. 打开微信&#10;2. 进入职悟空小程序&#10;3. 点击我的&#10;4. 输入手机号"></textarea></div>
        <div class="field"><label>预期结果 *</label><textarea id="formExpected" placeholder="描述期望看到的结果"></textarea></div>
      </div>
      <div class="modal-foot"><button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveCase()">保存</button></div>
    </div>
  </div>
  <div class="toast" id="toast"></div>
  <script>
    let allCases = [];
    let selectedIds = new Set();
    let editingCaseId = '';

    async function api(path, options) {
      const response = await fetch(path, options);
      const raw = await response.text();
      let data = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch (error) {
        throw new Error(raw || response.statusText);
      }
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }
    function switchTab(tab) {
      document.querySelectorAll('.nav button').forEach(item => item.classList.toggle('active', item.dataset.tab === tab));
      document.querySelectorAll('.tab-page').forEach(item => item.classList.toggle('active', item.id === tab));
      if (tab === 'reports') loadReport().catch(error => toast(`加载报告失败：${error.message}`));
    }
    function toast(message) {
      const el = document.getElementById('toast');
      el.textContent = message;
      el.classList.add('show');
      setTimeout(() => el.classList.remove('show'), 2400);
    }
    function openModal() {
      editingCaseId = '';
      document.getElementById('modalTitle').textContent = '新增用例';
      clearForm();
      document.getElementById('modalMask').classList.add('show');
    }
    function closeModal() { document.getElementById('modalMask').classList.remove('show'); }
    function clearForm() {
      document.getElementById('formTitle').value = '';
      document.getElementById('formModule').value = '';
      document.getElementById('formPriority').value = 'P2';
      document.getElementById('formPreconditions').value = '';
      document.getElementById('formSteps').value = '';
      document.getElementById('formExpected').value = '';
    }
    function splitLines(value) { return value.split(/\\n+/).map(item => item.replace(/^\\s*\\d+[.、)]\\s*/, '').trim()).filter(Boolean); }
    function jsArg(value) { return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\'"); }
    function escapeHtml(value) {
      const el = document.createElement('div');
      el.textContent = value == null ? '' : String(value);
      return el.innerHTML;
    }
    function escapeAttr(value) { return escapeHtml(value).replace(/"/g, '&quot;'); }
    function showActionError(action, error) {
      const message = `${action}失败：${error.message || error}`;
      toast(message);
      const log = document.getElementById('runLog');
      if (log) log.textContent = message;
    }
    function caseIdFrom(title) {
      const now = new Date();
      const stamp = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}${String(now.getSeconds()).padStart(2,'0')}`;
      return `airtest_case_${stamp}`;
    }
    async function saveCase() {
      const title = document.getElementById('formTitle').value.trim();
      const module = document.getElementById('formModule').value.trim() || '默认模块';
      const steps = splitLines(document.getElementById('formSteps').value);
      const expected = splitLines(document.getElementById('formExpected').value);
      if (!title || steps.length === 0 || expected.length === 0) {
        toast('请填写用例标题、测试步骤和预期结果');
        return;
      }
      const text = [...splitLines(document.getElementById('formPreconditions').value).map(item => `前置条件 ${item}`), ...steps, ...expected.map(item => `断言 ${item}`)].join('。');
      const payload = { case_id: editingCaseId || caseIdFrom(title), title, module, priority: document.getElementById('formPriority').value, tags: ['smoke'], text, driver: 'airtest' };
      try {
        if (editingCaseId) {
          await api(`/api/cases/${encodeURIComponent(editingCaseId)}`, { method: 'PUT', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload) });
        } else {
          await api('/api/cases/generate', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload) });
        }
        closeModal();
        toast(editingCaseId ? '用例已更新' : '用例已保存');
        editingCaseId = '';
        await loadCases();
      } catch (error) {
        showActionError('保存用例', error);
      }
    }
    async function editCase(id) {
      try {
        const data = await api(`/api/cases/${encodeURIComponent(id)}`);
        editingCaseId = id;
        document.getElementById('modalTitle').textContent = '编辑用例';
        document.getElementById('formTitle').value = data.title || '';
        document.getElementById('formModule').value = data.module || '';
        document.getElementById('formPriority').value = data.priority || 'P2';
        document.getElementById('formPreconditions').value = (data.preconditions || []).join('\\n');
        document.getElementById('formSteps').value = data.natural_steps || '';
        document.getElementById('formExpected').value = data.natural_expected || '';
        document.getElementById('modalMask').classList.add('show');
      } catch (error) {
        showActionError('打开编辑弹窗', error);
      }
    }
    async function deleteCase(id) {
      if (!confirm(`确认删除用例 ${id}？删除后会移除对应 YAML 文件。`)) {
        return;
      }
      try {
        await api(`/api/cases/${encodeURIComponent(id)}`, { method: 'DELETE' });
        selectedIds.delete(id);
        toast('用例已删除');
        await loadCases();
      } catch (error) {
        showActionError('删除用例', error);
      }
    }
    async function loadCases() {
      try {
        const data = await api('/api/cases');
        allCases = data.cases;
        const validIds = new Set(allCases.map(item => item.id));
        selectedIds = new Set([...selectedIds].filter(id => validIds.has(id)));
        if (selectedIds.size === 0) {
          allCases.forEach(item => selectedIds.add(item.id));
        }
        fillModuleFilter();
        renderCaseTable();
        renderMetrics();
      } catch (error) {
        document.getElementById('caseRows').innerHTML = `<tr><td colspan="8" class="empty">加载用例失败：${escapeHtml(error.message)}</td></tr>`;
        toast(`加载用例失败：${error.message}`);
      }
    }
    function fillModuleFilter() {
      const current = document.getElementById('moduleFilter').value;
      const modules = [...new Set(allCases.map(item => item.module))].sort();
      document.getElementById('moduleFilter').innerHTML = '<option value="">全部模块</option>' + modules.map(item => `<option value="${escapeAttr(item)}">${escapeHtml(item)}</option>`).join('');
      document.getElementById('moduleFilter').value = current;
    }
    function filteredCases() {
      const module = document.getElementById('moduleFilter').value;
      const priority = document.getElementById('priorityFilter').value;
      const keyword = document.getElementById('searchInput').value.trim().toLowerCase();
      return allCases.filter(item => (!module || item.module === module) && (!priority || item.priority === priority) && (!keyword || `${item.id} ${item.title} ${item.module}`.toLowerCase().includes(keyword)));
    }
    function renderCaseTable() {
      const rows = filteredCases().map((item, index) => {
        const checked = selectedIds.has(item.id) ? 'checked' : '';
        const idArg = jsArg(item.id);
        const priorityClass = escapeAttr(String(item.priority || '').toLowerCase().replace(/[^a-z0-9_-]/g, ''));
        return `<tr>
          <td><input class="checkbox row-check" type="checkbox" ${checked} onchange="toggleSelect('${idArg}', this.checked)"></td>
          <td>${index + 1}</td>
          <td>${escapeHtml(item.title)}</td>
          <td>${escapeHtml(item.module)}</td>
          <td><span class="tag tag-${priorityClass}">${escapeHtml(item.priority)}</span></td>
          <td><span class="tag status-on">${escapeHtml(item.status)}</span></td>
          <td>${escapeHtml(item.created_at)}</td>
          <td><button class="btn text" onclick="editCase('${idArg}')">编辑</button><button class="btn text" onclick="deleteCase('${idArg}')">删除</button></td>
        </tr>`;
      }).join('');
      document.getElementById('caseRows').innerHTML = rows || '<tr><td colspan="8" class="empty">暂无用例</td></tr>';
      document.getElementById('headCheck').checked = filteredCases().length > 0 && filteredCases().every(item => selectedIds.has(item.id));
    }
    function renderMetrics() {
      document.getElementById('metricTotal').textContent = allCases.length;
      document.getElementById('metricEnabled').textContent = allCases.length;
      document.getElementById('metricDisabled').textContent = 0;
    }
    function toggleSelect(id, checked) {
      checked ? selectedIds.add(id) : selectedIds.delete(id);
    }
    function selectAllRows(checked) {
      filteredCases().forEach(item => checked ? selectedIds.add(item.id) : selectedIds.delete(item.id));
      document.getElementById('headCheck').checked = checked;
      renderCaseTable();
    }
    async function runSelected() {
      const ids = [...selectedIds];
      if (ids.length === 0) {
        document.getElementById('runLog').textContent = '未执行：请先勾选要执行的用例。';
        switchTab('runs');
        toast('请先选择要执行的用例');
        return;
      }
      const runButton = document.getElementById('runSelectedBtn');
      runButton.disabled = true;
      runButton.textContent = '执行中...';
      document.getElementById('runLog').textContent = `正在通过 Airtest 真机执行 ${ids.length} 条用例：\\n${ids.join('\\n')}`;
      switchTab('runs');
      try {
        const data = await api('/api/runs', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({ driver: 'airtest', case_ids: ids }) });
        renderReport(data);
        document.getElementById('metricToday').textContent = data.total || 0;
        document.getElementById('runLog').textContent = formatRunLog(data, ids);
        toast('执行完成，请查看执行记录和测试报告');
      } catch (error) {
        document.getElementById('runLog').textContent = `执行失败：${error.message}`;
        toast(`执行失败：${error.message}`);
      } finally {
        runButton.disabled = false;
        runButton.textContent = '执行选中';
      }
    }
    async function loadReport() { renderReport(await api('/api/reports/latest')); }
    function formatRunLog(data, selectedIds) {
      const lines = [];
      const cases = data.cases || [];
      lines.push(`执行完成：选中 ${selectedIds.length} 条，实际执行 ${data.total || cases.length || 0} 条`);
      lines.push(`通过：${data.passed || 0}，失败：${data.failed || 0}，跳过：${data.skipped || 0}`);
      if (data.ai_summary) {
        lines.push('');
        lines.push(`摘要：${data.ai_summary}`);
      }
      lines.push('');
      lines.push('失败定位：');
      const failedCases = cases.filter(item => item.status === 'failed');
      if (failedCases.length === 0) {
        lines.push('无失败用例');
      } else {
        failedCases.forEach(item => {
          const failedStepIndex = (item.steps || []).findIndex(step => step.status === 'failed');
          const failedStep = failedStepIndex >= 0 ? item.steps[failedStepIndex] : null;
          lines.push(`- ${item.case_id} / ${item.title || ''}`);
          if (item.failure_category) lines.push(`  分类：${item.failure_category}`);
          if (item.failure_summary) lines.push(`  摘要：${item.failure_summary}`);
          if (failedStep) {
            lines.push(`  失败步骤：#${failedStepIndex + 1} ${failedStep.action} ${failedStep.target}`);
            lines.push(`  原始错误：${failedStep.message || '未返回错误信息'}`);
            const hint = explainRunError(failedStep.message || '');
            if (hint) lines.push(`  可能原因：${hint}`);
          }
        });
      }
      lines.push('');
      lines.push('步骤明细：');
      if (cases.length === 0) {
        lines.push('无用例结果返回');
      }
      cases.forEach(item => {
        lines.push(`用例：${item.case_id} | ${item.title || ''} | ${item.status}`);
        lines.push(`模块：${item.module || '-'}，优先级：${item.priority || '-'}，标签：${(item.tags || []).join(', ') || '-'}`);
        (item.steps || []).forEach((step, index) => {
          lines.push(`  #${index + 1} [${step.status}] ${step.action} ${step.target}`);
          if (step.message) lines.push(`      message: ${step.message}`);
          if (step.artifact_paths && step.artifact_paths.length) {
            lines.push(`      artifacts: ${step.artifact_paths.join(', ')}`);
          }
        });
        if (item.failure_category || item.failure_summary) {
          lines.push(`  failure_category: ${item.failure_category || '-'}`);
          lines.push(`  failure_summary: ${item.failure_summary || '-'}`);
        }
        lines.push('');
      });
      return lines.join('\\n');
    }
    function explainRunError(message) {
      if (!message) return '';
      if (message.includes('ConnectionResetError') || message.includes('Connection broken') || message.includes('10054') || message.includes('Expecting value: line 1 column 1')) {
        return 'Poco/Airtest 与手机端 PocoService 的连接被远端断开。常见原因：手机端 PocoService 被系统杀掉或重启、手机息屏/锁屏/USB 瞬断、微信页面切换导致 UIAutomator 服务不稳定，或把“下拉/滑动”等动作描述误当成 Poco 文本控件点击。建议先在设备页重新检查环境，保持手机亮屏，再把该步骤改成明确控件点击、图片点击或后续支持的滑动动作。';
      }
      if (message.includes('Poco target not found')) {
        return 'Poco 没找到目标文本控件，检查控件文案是否真实存在，或改用截图模板定位。';
      }
      if (message.includes('Image target not found')) {
        return '图片模板未匹配到目标，检查截图模板、分辨率和 image_threshold。';
      }
      return '';
    }
    function renderReport(data) {
      document.getElementById('reportTotal').textContent = data.total || 0;
      document.getElementById('reportPassed').textContent = data.passed || 0;
      document.getElementById('reportFailed').textContent = data.failed || 0;
      document.getElementById('reportSkipped').textContent = data.skipped || 0;
      document.getElementById('aiSummary').textContent = data.ai_summary || '暂无执行报告。';
    }
    async function checkDevice() {
      document.getElementById('deviceChecks').innerHTML = '<span class="check-item"><span class="dot pending"></span>正在真实检测...</span>';
      document.getElementById('checkDetail').innerHTML = '';
      try {
        const data = await api('/api/devices/check');
        renderDevice(data);
        toast(data.ready ? '设备环境检查通过' : '设备环境仍需处理');
      } catch (error) {
        document.getElementById('deviceChecks').innerHTML = '<span class="check-item"><span class="dot fail"></span>检测失败</span>';
        document.getElementById('checkDetail').innerHTML = `<div class="check-card"><div class="check-title"><span class="dot fail"></span>检测失败</div><div class="check-message">${escapeHtml(error.message)}</div></div>`;
        toast(`设备检测失败：${error.message}`);
      }
    }
    function renderDevice(data) {
      const checks = data.checks || [];
      document.getElementById('deviceChecks').innerHTML = checks.map(item => `<span class="check-item"><span class="dot ${item.ok ? 'ok' : 'fail'}"></span>${escapeHtml(item.name)}</span>`).join('');
      document.getElementById('checkDetail').innerHTML = checks.map(item => `<div class="check-card"><div class="check-title"><span class="dot ${item.ok ? 'ok' : 'fail'}"></span>${escapeHtml(item.name)}</div><div class="check-message">${escapeHtml(item.message || '')}</div><div class="check-command">${escapeHtml(item.command || '')}</div></div>`).join('');
      const config = data.config || {};
      const configItems = [
        ['设备地址', config.device_uri || '未配置'],
        ['实际连接地址', config.resolved_device_uri || '未发现可用设备'],
        ['微信包名', config.package || 'com.tencent.mm'],
        ['小程序名', config.miniapp_name || '未配置'],
        ['图片目录', config.image_dir || 'assets/images'],
        ['识别阈值', config.image_threshold ?? '0.8'],
        ['Poco', config.poco_enabled ? '已启用' : '未启用']
      ];
      document.getElementById('deviceConfig').innerHTML = configItems.map(([label, value]) => `<div class="config-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');
      const rows = (data.devices || []).map(item => `<tr><td>${escapeHtml(item.serial)}</td><td>${escapeHtml(item.status)}</td></tr>`).join('');
      document.getElementById('deviceTable').innerHTML = rows ? `<table><thead><tr><th>设备序列号</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty">暂无 ADB 设备</div>';
    }
    loadCases();
    loadReport().catch(error => toast(`加载报告失败：${error.message}`));
  </script>
</body>
</html>
"""
