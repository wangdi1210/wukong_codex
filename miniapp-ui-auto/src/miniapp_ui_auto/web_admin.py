from __future__ import annotations

import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from miniapp_ui_auto.case_generator import generate_case_from_text, write_generated_case
from miniapp_ui_auto.case_loader import load_cases
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

    def list_cases(self) -> list[dict[str, Any]]:
        return [_case_record(case) for case in load_cases(self.case_root, self.schema_path)]

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
        if route == "/api/reports/latest":
            self._send_json(self.web_service.load_summary())
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
    }


def _required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"缺少必填字段：{key}")
    return value


_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小程序 UI 自动化管理台</title>
  <style>
    :root { color-scheme: light; font-family: Arial, "Microsoft YaHei", sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #20242a; }
    header { padding: 18px 24px; background: #14213d; color: #fff; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(320px, 420px) 1fr; gap: 16px; padding: 16px; }
    section { background: #fff; border: 1px solid #d8dde6; border-radius: 8px; padding: 16px; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    label { display: block; margin: 10px 0 4px; font-size: 13px; color: #4d5562; }
    input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid #bcc5d2; border-radius: 6px; padding: 8px; font: inherit; }
    textarea { min-height: 160px; resize: vertical; }
    button { border: 0; border-radius: 6px; padding: 9px 12px; background: #1f7a8c; color: #fff; cursor: pointer; font-weight: 600; }
    button.secondary { background: #586069; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid #edf0f4; padding: 8px; text-align: left; vertical-align: top; }
    th { color: #4d5562; background: #f8fafc; }
    code, pre { background: #f1f4f8; border-radius: 6px; }
    pre { padding: 10px; overflow: auto; min-height: 80px; }
    .summary { display: grid; grid-template-columns: repeat(4, minmax(80px, 1fr)); gap: 8px; }
    .metric { background: #f8fafc; border: 1px solid #e5e9f0; border-radius: 6px; padding: 10px; }
    .metric strong { display: block; font-size: 20px; }
    @media (max-width: 860px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header><h1>小程序 UI 自动化管理台</h1></header>
  <main>
    <section>
      <h2>自然语言生成用例</h2>
      <div class="row">
        <div><label>用例 ID</label><input id="caseId" value="airtest_login_generated_001"></div>
        <div><label>模块</label><input id="module" value="login"></div>
      </div>
      <label>标题</label><input id="title" value="手机号验证码登录成功">
      <div class="row">
        <div><label>优先级</label><select id="priority"><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></div>
        <div><label>标签</label><input id="tags" value="smoke,ai-generated"></div>
      </div>
      <label>自然语言步骤</label>
      <textarea id="text">打开 微信。进入 职悟空小程序。点击 我的。点击 登录。输入 手机号输入框：13800000000。输入 验证码输入框：123456。点击 确认登录。断言 用户昵称</textarea>
      <div class="actions">
        <button onclick="generateCase()">生成 YAML</button>
        <button class="secondary" onclick="loadCases()">刷新列表</button>
      </div>
      <pre id="generateResult">等待生成。</pre>
    </section>
    <section>
      <h2>执行控制</h2>
      <div class="row">
        <div><label>执行 Driver</label><select id="runDriver"><option value="dry-run">dry-run</option><option value="airtest">airtest</option><option value="poco">poco</option></select></div>
        <div><label>执行标签</label><input id="runTags" value="smoke"></div>
      </div>
      <div class="actions">
        <button onclick="runCases()">执行用例</button>
        <button class="secondary" onclick="loadReport()">刷新报告</button>
      </div>
      <div class="summary" id="summary"></div>
      <pre id="aiSummary">暂无执行报告。</pre>
      <h2>用例列表</h2>
      <div id="caseTable"></div>
    </section>
  </main>
  <script>
    async function api(path, options) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }
    function tagsFrom(id) {
      return document.getElementById(id).value.split(',').map(v => v.trim()).filter(Boolean);
    }
    async function generateCase() {
      const payload = {
        case_id: document.getElementById('caseId').value,
        title: document.getElementById('title').value,
        module: document.getElementById('module').value,
        priority: document.getElementById('priority').value,
        tags: tagsFrom('tags'),
        text: document.getElementById('text').value,
        driver: 'airtest'
      };
      try {
        const data = await api('/api/cases/generate', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload) });
        document.getElementById('generateResult').textContent = JSON.stringify(data, null, 2);
        await loadCases();
      } catch (error) {
        document.getElementById('generateResult').textContent = error.message;
      }
    }
    async function loadCases() {
      const data = await api('/api/cases');
      const rows = data.cases.map(item => `<tr><td>${item.id}</td><td>${item.title}</td><td>${item.module}</td><td>${item.priority}</td><td>${item.tags.join(', ')}</td><td>${item.driver}</td></tr>`).join('');
      document.getElementById('caseTable').innerHTML = `<table><thead><tr><th>ID</th><th>标题</th><th>模块</th><th>优先级</th><th>标签</th><th>Driver</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    async function runCases() {
      const payload = { driver: document.getElementById('runDriver').value, tags: tagsFrom('runTags') };
      const data = await api('/api/runs', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload) });
      renderReport(data);
      await loadCases();
    }
    async function loadReport() {
      renderReport(await api('/api/reports/latest'));
    }
    function renderReport(data) {
      document.getElementById('summary').innerHTML = ['total', 'passed', 'failed', 'skipped'].map(key => `<div class="metric"><span>${key}</span><strong>${data[key] || 0}</strong></div>`).join('');
      document.getElementById('aiSummary').textContent = data.ai_summary || '暂无执行报告。';
    }
    loadCases();
    loadReport();
  </script>
</body>
</html>
"""
