from pathlib import Path
from unittest.mock import patch

from miniapp_ui_auto.web_admin import WebAdminService


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
            "text": "打开 微信。进入 职悟空小程序。点击 我的。输入 手机号输入框：13800000000。断言 用户昵称",
        }
    )
    cases = service.list_cases()
    run_result = service.run_cases({"driver": "dry-run", "tags": ["smoke"]})
    latest = service.load_summary()

    assert generated["path"].endswith("web_login_001.yaml")
    assert cases[0]["id"] == "web_login_001"
    assert cases[0]["driver"] == "airtest"
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
            "text": "前置条件 用户已登录。点击 个人中心。断言 资料页",
        },
    )
    updated_detail = service.get_case("editable_case")
    deleted = service.delete_case("editable_case")

    assert detail["natural_steps"] == "点击 我的"
    assert updated["case"]["title"] == "编辑后标题"
    assert updated_detail["module"] == "profile"
    assert updated_detail["priority"] == "P1"
    assert updated_detail["natural_expected"] == "资料页"
    assert deleted["deleted"] == "editable_case"
    assert service.list_cases() == []


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

    with patch("miniapp_ui_auto.web_admin.Path", side_effect=lambda value: config_dir / "airtest.yaml" if value == "config/airtest.yaml" else Path(value)):
        result = service.check_device_environment()

    assert result["config"]["device_uri"] == "Android:///127.0.0.1:7555"
    assert any(item["name"] == "Airtest" for item in result["checks"])
    assert any(item["name"] == "ADB" for item in result["checks"])
