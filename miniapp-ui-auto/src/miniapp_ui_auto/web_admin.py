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
        "status": "启用",
        "created_at": _format_created_at(Path(case.source_path)),
    }


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
    .panel { padding: 22px 24px; }
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
          <button class="btn success" onclick="runSelected()">执行选中</button>
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
      <div class="panel">
        <h2>设备配置</h2>
        <pre>当前通过 config/airtest.yaml 管理设备。
示例：
device_uri: Android:///127.0.0.1:7555
package: com.tencent.mm
miniapp_name: 职悟空
poco.enabled: true</pre>
      </div>
    </section>
  </main>
  <div class="modal-mask" id="modalMask">
    <div class="modal">
      <div class="modal-head"><div class="modal-title">新增用例</div><button class="close" onclick="closeModal()">×</button></div>
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

    async function api(path, options) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }
    function switchTab(tab) {
      document.querySelectorAll('.nav button').forEach(item => item.classList.toggle('active', item.dataset.tab === tab));
      document.querySelectorAll('.tab-page').forEach(item => item.classList.toggle('active', item.id === tab));
      if (tab === 'reports') loadReport();
    }
    function toast(message) {
      const el = document.getElementById('toast');
      el.textContent = message;
      el.classList.add('show');
      setTimeout(() => el.classList.remove('show'), 2400);
    }
    function openModal() { document.getElementById('modalMask').classList.add('show'); }
    function closeModal() { document.getElementById('modalMask').classList.remove('show'); }
    function splitLines(value) { return value.split(/\\n+/).map(item => item.replace(/^\\s*\\d+[.、)]\\s*/, '').trim()).filter(Boolean); }
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
      const payload = { case_id: caseIdFrom(title), title, module, priority: document.getElementById('formPriority').value, tags: ['smoke'], text, driver: 'airtest' };
      await api('/api/cases/generate', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(payload) });
      closeModal();
      toast('用例已保存');
      await loadCases();
    }
    async function loadCases() {
      const data = await api('/api/cases');
      allCases = data.cases;
      fillModuleFilter();
      renderCaseTable();
      renderMetrics();
    }
    function fillModuleFilter() {
      const current = document.getElementById('moduleFilter').value;
      const modules = [...new Set(allCases.map(item => item.module))].sort();
      document.getElementById('moduleFilter').innerHTML = '<option value="">全部模块</option>' + modules.map(item => `<option>${item}</option>`).join('');
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
        return `<tr>
          <td><input class="checkbox row-check" type="checkbox" ${checked} onchange="toggleSelect('${item.id}', this.checked)"></td>
          <td>${index + 1}</td>
          <td>${item.title}</td>
          <td>${item.module}</td>
          <td><span class="tag tag-${item.priority.toLowerCase()}">${item.priority}</span></td>
          <td><span class="tag status-on">${item.status}</span></td>
          <td>${item.created_at}</td>
          <td><button class="btn text" onclick="toast('编辑能力下一步接入')">编辑</button><button class="btn text" onclick="toast('删除能力下一步接入')">删除</button></td>
        </tr>`;
      }).join('');
      document.getElementById('caseRows').innerHTML = rows || '<tr><td colspan="8" class="empty">暂无用例</td></tr>';
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
        toast('请先选择要执行的用例');
        return;
      }
      const data = await api('/api/runs', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({ driver: 'dry-run', case_ids: ids }) });
      renderReport(data);
      document.getElementById('metricToday').textContent = data.total || 0;
      document.getElementById('runLog').textContent = `已执行 ${ids.length} 条用例：\\n${ids.join('\\n')}`;
      toast('执行完成');
    }
    async function loadReport() { renderReport(await api('/api/reports/latest')); }
    function renderReport(data) {
      document.getElementById('reportTotal').textContent = data.total || 0;
      document.getElementById('reportPassed').textContent = data.passed || 0;
      document.getElementById('reportFailed').textContent = data.failed || 0;
      document.getElementById('reportSkipped').textContent = data.skipped || 0;
      document.getElementById('aiSummary').textContent = data.ai_summary || '暂无执行报告。';
    }
    loadCases();
    loadReport();
  </script>
</body>
</html>
"""
