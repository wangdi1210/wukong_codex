from pathlib import Path

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
