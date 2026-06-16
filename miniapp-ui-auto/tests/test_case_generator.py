from pathlib import Path

from miniapp_ui_auto.case_generator import generate_case_from_text, write_generated_case
from miniapp_ui_auto.case_loader import load_cases


def test_generate_case_from_natural_language_and_load_it(tmp_path):
    text = """
    打开 微信
    进入 职悟空小程序
    点击 我的
    点击 登录
    输入 手机号输入框：13800000000
    输入 验证码输入框：123456
    点击 确认登录
    断言 用户昵称
    """

    generated = generate_case_from_text(
        text,
        case_id="miniapp_login_generated_001",
        title="手机号验证码登录成功",
        module="login",
        tags=("smoke", "ai-generated"),
    )
    output_path = write_generated_case(generated, tmp_path / "miniapp_login_generated_001.yaml")
    cases = load_cases(tmp_path, Path("schemas/case.schema.json"))

    assert output_path.exists()
    assert len(cases) == 1
    case = cases[0]
    assert case.id == "miniapp_login_generated_001"
    assert case.driver == "airtest"
    assert case.steps[0].action == "open_app"
    assert case.steps[1].action == "open_miniapp"
    assert case.steps[4].action == "input"
    assert case.steps[4].value == "13800000000"
    assert case.assertions[0].target == "用户昵称"


def test_generate_case_keeps_preconditions(tmp_path):
    generated = generate_case_from_text(
        "前置条件 用户已登录\n点击 我的\n断言 用户昵称",
        case_id="precondition_case",
        title="前置条件用例",
        module="login",
    )
    write_generated_case(generated, tmp_path / "precondition_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.preconditions == ("用户已登录",)
    assert case.depends_on_previous is False


def test_generate_case_can_depend_on_previous_case(tmp_path):
    generated = generate_case_from_text(
        "点击 开始交流\n断言 进入会话详情",
        case_id="dependent_case",
        title="进入会话",
        module="chat",
        depends_on_previous=True,
    )
    write_generated_case(generated, tmp_path / "dependent_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.depends_on_previous is True


def test_generate_case_turns_swipe_language_into_swipe_step(tmp_path):
    generated = generate_case_from_text(
        "打开 微信\n在微信内持续做下拉操作\n断言 职悟空",
        case_id="swipe_case",
        title="下拉进入小程序",
        module="miniapp",
    )
    write_generated_case(generated, tmp_path / "swipe_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.steps[1].action == "swipe"
    assert case.steps[1].target == "down"


def test_generate_case_turns_miniapp_search_into_search_step(tmp_path):
    generated = generate_case_from_text(
        "打开 微信\n搜索 职悟空 小程序\n点击 进入\n断言 进入职悟空小程序",
        case_id="search_miniapp_case",
        title="搜索进入小程序",
        module="miniapp",
    )
    write_generated_case(generated, tmp_path / "search_miniapp_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.steps[1].action == "search_miniapp"
    assert case.steps[1].target == "职悟空"
    assert len(case.steps) == 2


def test_generate_case_strips_quotes_from_tap_target(tmp_path):
    generated = generate_case_from_text(
        "点击 “开始交流”\n断言 进入悟空会话",
        case_id="quoted_tap_case",
        title="开始交流",
        module="chat",
    )
    write_generated_case(generated, tmp_path / "quoted_tap_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.steps[0].action == "tap"
    assert case.steps[0].target == "开始交流"


def test_generate_case_turns_input_box_search_into_miniapp_search(tmp_path):
    generated = generate_case_from_text(
        "打开 微信\n在输入框搜索：职悟空\n从列表中找到 职悟空小程序，点击进入\n断言 进入职悟空小程序",
        case_id="input_box_search_case",
        title="搜索小程序",
        module="miniapp",
    )
    write_generated_case(generated, tmp_path / "input_box_search_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert [step.action for step in case.steps] == ["open_app", "search_miniapp"]
    assert case.steps[1].target == "职悟空"


def test_generate_case_keeps_internal_search_miniapp_text_compatible(tmp_path):
    generated = generate_case_from_text(
        "打开 微信\nsearch_miniapp 职悟空\n断言 进入职悟空小程序",
        case_id="internal_search_text_case",
        title="搜索小程序",
        module="miniapp",
    )
    write_generated_case(generated, tmp_path / "internal_search_text_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.steps[1].action == "search_miniapp"
    assert case.steps[1].target == "职悟空"


def test_generate_case_turns_send_text_into_input_step(tmp_path):
    generated = generate_case_from_text(
        "在输入框内发送：你好\n断言 触发模型回答",
        case_id="send_message_case",
        title="发送消息",
        module="chat",
    )
    write_generated_case(generated, tmp_path / "send_message_case.yaml")
    case = load_cases(tmp_path, Path("schemas/case.schema.json"))[0]

    assert case.steps[0].action == "input"
    assert case.steps[0].target == "输入框"
    assert case.steps[0].value == "你好"
