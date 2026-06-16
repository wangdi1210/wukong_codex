import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from miniapp_ui_auto.web_admin import WebAdminService, _INDEX_HTML


def test_web_admin_inline_script_is_parseable(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = _INDEX_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
    script_path = tmp_path / "web_admin_inline.js"
    script_path.write_text(script, encoding="utf-8")

    result = subprocess.run([node, "--check", str(script_path)], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr


def test_web_admin_generates_lists_runs_and_reports(tmp_path):
    service = WebAdminService(
        case_root=tmp_path / "cases",
        schema_path=Path("schemas/case.schema.json"),
        report_dir=tmp_path / "reports",
    )

    generated = service.generate_case(
        {
            "case_id": "web_login_001",
            "title": "手机号验证码登录成功",
            "module": "login",
            "tags": ["smoke", "web"],
            "depends_on_previous": True,
            "text": "打开 微信。进入 职悟空小程序。点击 我的。输入 手机号输入框：13800000000。断言 用户昵称",
        }
    )
    cases = service.list_cases()
    run_result = service.run_cases({"driver": "dry-run", "tags": ["smoke"]})
    latest = service.load_summary()

    assert generated["path"].endswith("web_login_001.yaml")
    assert cases[0]["id"] == "web_login_001"
    assert cases[0]["driver"] == "airtest"
    assert cases[0]["depends_on_previous"] is True
    assert run_result["total"] == 1
    assert latest["passed"] == 1
    assert "本次回归共执行 1 条" in latest["ai_summary"]


def test_web_admin_runs_only_selected_case_ids(tmp_path):
    service = WebAdminService(
        case_root=tmp_path / "cases",
        schema_path=Path("schemas/case.schema.json"),
        report_dir=tmp_path / "reports",
    )
    for case_id, title in (("selected_case", "选中的用例"), ("ignored_case", "未选中的用例")):
        service.generate_case(
            {
                "case_id": case_id,
                "title": title,
                "module": "login",
                "tags": ["smoke"],
                "text": "打开 微信。进入 职悟空小程序。断言 用户昵称",
            }
        )

    result = service.run_cases({"driver": "dry-run", "case_ids": ["selected_case"]})

    assert result["total"] == 1
    assert result["cases"][0]["case_id"] == "selected_case"


def test_web_admin_can_get_update_and_delete_case(tmp_path):
    service = WebAdminService(
        case_root=tmp_path / "cases",
        schema_path=Path("schemas/case.schema.json"),
        report_dir=tmp_path / "reports",
    )
    service.generate_case(
        {
            "case_id": "editable_case",
            "title": "编辑前标题",
            "module": "login",
            "tags": ["smoke"],
            "text": "前置条件 用户已登录。点击 我的。断言 用户昵称",
        }
    )

    detail = service.get_case("editable_case")
    updated = service.update_case(
        "editable_case",
        {
            "title": "编辑后标题",
            "module": "profile",
            "priority": "P1",
            "tags": ["smoke"],
            "depends_on_previous": True,
            "text": "前置条件 用户已登录。点击 个人中心。断言 资料页",
        },
    )
    updated_detail = service.get_case("editable_case")
    deleted = service.delete_case("editable_case")

    assert detail["natural_steps"] == "点击 我的"
    assert updated["case"]["title"] == "编辑后标题"
    assert updated_detail["module"] == "profile"
    assert updated_detail["priority"] == "P1"
    assert updated_detail["depends_on_previous"] is True
    assert updated_detail["natural_expected"] == "资料页"
    assert deleted["deleted"] == "editable_case"
    assert service.list_cases() == []


def test_web_admin_renders_search_miniapp_as_natural_step(tmp_path):
    service = WebAdminService(
        case_root=tmp_path / "cases",
        schema_path=Path("schemas/case.schema.json"),
        report_dir=tmp_path / "reports",
    )
    service.generate_case(
        {
            "case_id": "search_case",
            "title": "搜索小程序",
            "module": "miniapp",
            "tags": ["smoke"],
            "text": "打开 微信\n在输入框搜索：职悟空\n断言 进入职悟空小程序",
        }
    )

    detail = service.get_case("search_case")

    assert "在输入框搜索：职悟空" in detail["natural_steps"]
    assert "search_miniapp" not in detail["natural_steps"]


def test_web_admin_device_check_returns_config_and_checks(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "airtest.yaml").write_text(
        "airtest:\n"
        "  device_uri: Android:///127.0.0.1:7555\n"
        "  package: com.tencent.mm\n"
        "  miniapp_name: 职悟空\n"
        "  poco:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    service = WebAdminService(case_root=tmp_path / "cases", schema_path=Path("schemas/case.schema.json"), report_dir=tmp_path / "reports")

    adb_result = {
        "name": "ADB",
        "ok": True,
        "message": "已连接 1 台设备：real-device。",
        "devices": [{"serial": "real-device", "status": "device"}],
        "command": "adb devices",
    }
    with (
        patch("miniapp_ui_auto.web_admin.Path", side_effect=lambda value: config_dir / "airtest.yaml" if value == "config/airtest.yaml" else Path(value)),
        patch("miniapp_ui_auto.web_admin._check_adb_devices", return_value=adb_result),
        patch("miniapp_ui_auto.web_admin._check_airtest_connect", return_value={"name": "Airtest", "ok": True, "message": "真实连接成功"}),
        patch("miniapp_ui_auto.web_admin._check_poco_connect", return_value={"name": "Poco", "ok": True, "message": "真实连接成功"}),
    ):
        result = service.check_device_environment()

    assert result["config"]["device_uri"] == "Android:///127.0.0.1:7555"
    assert result["config"]["resolved_device_uri"] == "Android:///127.0.0.1:7555"
    assert any(item["name"] == "Airtest" for item in result["checks"])
    assert any(item["name"] == "ADB" for item in result["checks"])
    assert result["ready"] is True


def test_web_admin_device_check_uses_adb_device_when_config_missing(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "airtest.yaml").write_text(
        "airtest:\n"
        "  device_uri: ''\n"
        "  poco:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    service = WebAdminService(case_root=tmp_path / "cases", schema_path=Path("schemas/case.schema.json"), report_dir=tmp_path / "reports")
    adb_result = {
        "name": "ADB",
        "ok": True,
        "message": "已连接 1 台设备：94b63a3b。",
        "devices": [{"serial": "94b63a3b", "status": "device"}],
        "command": "adb devices",
    }

    with (
        patch("miniapp_ui_auto.web_admin.Path", side_effect=lambda value: config_dir / "airtest.yaml" if value == "config/airtest.yaml" else Path(value)),
        patch("miniapp_ui_auto.web_admin._check_adb_devices", return_value=adb_result),
        patch("miniapp_ui_auto.web_admin._check_airtest_connect", return_value={"name": "Airtest", "ok": True, "message": "真实连接成功"}),
        patch("miniapp_ui_auto.web_admin._check_poco_connect", return_value={"name": "Poco", "ok": True, "message": "真实连接成功"}),
    ):
        result = service.check_device_environment()

    assert result["config"]["device_uri"] == ""
    assert result["config"]["resolved_device_uri"] == "Android:///94b63a3b"
    assert result["devices"] == [{"serial": "94b63a3b", "status": "device"}]
    assert result["ready"] is True


def test_web_admin_device_status_returns_last_check_without_rechecking(tmp_path):
    service = WebAdminService(case_root=tmp_path / "cases", schema_path=Path("schemas/case.schema.json"), report_dir=tmp_path / "reports")
    adb_result = {
        "name": "ADB",
        "ok": True,
        "message": "connected",
        "devices": [{"serial": "stable-device", "status": "device"}],
        "command": "adb devices",
    }

    with (
        patch("miniapp_ui_auto.web_admin._check_adb_devices", return_value=adb_result) as adb_mock,
        patch("miniapp_ui_auto.web_admin._check_airtest_connect", return_value={"name": "Airtest", "ok": True, "message": "ok"}),
        patch("miniapp_ui_auto.web_admin._check_poco_connect", return_value={"name": "Poco", "ok": True, "message": "ok"}),
    ):
        checked = service.check_device_environment()
        status = service.device_environment_status()

    assert checked["devices"] == [{"serial": "stable-device", "status": "device"}]
    assert status["cached"] is True
    assert status["devices"] == [{"serial": "stable-device", "status": "device"}]
    assert adb_mock.call_count == 1
