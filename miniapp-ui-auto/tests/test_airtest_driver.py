import pytest
import builtins

from miniapp_ui_auto.drivers.airtest_driver import AirtestDriver, AirtestUnavailableError, load_airtest_config
from miniapp_ui_auto.models import RunContext, Step


class FakeAirtestApi:
    Template = staticmethod(lambda filename, threshold=None: {"filename": filename, "threshold": threshold})

    def __init__(self, ui_xml=""):
        self.calls = []
        self.ui_xml = ui_xml

    def connect_device(self, device_uri):
        self.calls.append(("connect_device", device_uri))

    def start_app(self, package):
        self.calls.append(("start_app", package))

    def touch(self, target):
        self.calls.append(("touch", target))

    def text(self, value, **kwargs):
        self.calls.append(("text", value, kwargs))

    def keyevent(self, value):
        self.calls.append(("keyevent", value))

    def swipe(self, start, end, **kwargs):
        self.calls.append(("swipe", start, end, kwargs))

    def exists(self, target):
        self.calls.append(("exists", target))
        return True

    def wait(self, target, timeout=None):
        self.calls.append(("wait", target, timeout))

    def snapshot(self, filename=None):
        self.calls.append(("snapshot", filename))

    def device(self):
        self.calls.append(("device",))
        return FakeDevice(self.calls, self.ui_xml)


class FakeYosemiteIme:
    def __init__(self, calls):
        self.calls = calls

    def text(self, value):
        self.calls.append(("yosemite_text", value))

    def code(self, value):
        self.calls.append(("yosemite_code", value))


class FakeDevice:
    def __init__(self, calls, ui_xml=""):
        self.adb = FakeAdb(calls, ui_xml)
        self.yosemite_ime = FakeYosemiteIme(calls)

    def get_current_resolution(self):
        return (1000, 2000)


class FakeAdb:
    def __init__(self, calls, ui_xml=""):
        self.calls = calls
        self.ui_xml = ui_xml

    def shell(self, value):
        self.calls.append(("adb_shell", value))
        if isinstance(value, list) and value[:1] == ["cat"]:
            return self.ui_xml
        if isinstance(value, list) and value[:2] == ["uiautomator", "dump"]:
            return "UI hierarchy dumped"
        return ""


class FakePocoNode:
    def __init__(self, calls, text):
        self.calls = calls
        self.text = text

    def click(self):
        self.calls.append(("poco_click", self.text))

    def exists(self):
        self.calls.append(("poco_exists", self.text))
        return True


class FakePoco:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        return FakePocoNode(self.calls, kwargs["text"])


def test_airtest_driver_fails_clearly_when_airtest_is_not_installed(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "airtest.core":
            raise ImportError("airtest missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    driver = AirtestDriver()

    with pytest.raises(AirtestUnavailableError) as error:
        driver.setup(RunContext(env="test", trigger="local"))

    assert "pip install airtest pocoui" in str(error.value)


def test_load_airtest_config(tmp_path):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  device_uri: Android:///127.0.0.1:7555\n"
        "  package: com.tencent.mm\n"
        "  miniapp_name: 职悟空\n"
        "  image_threshold: 0.9\n"
        "  image_dir: assets/templates\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )

    config = load_airtest_config(config_path)

    assert config.device_uri == "Android:///127.0.0.1:7555"
    assert config.package == "com.tencent.mm"
    assert config.image_threshold == 0.9
    assert config.image_dir == "assets/templates"
    assert config.poco_enabled is False


def test_airtest_driver_executes_steps_with_fake_api_and_poco(tmp_path):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  device_uri: Android:///127.0.0.1:7555\n"
        "  package: com.tencent.mm\n"
        "  miniapp_name: 职悟空\n"
        "  poco:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    fake_poco = FakePoco()
    driver = AirtestDriver(
        config_path=config_path,
        airtest_api=fake_api,
        poco_factory=lambda: fake_poco,
    )
    driver.setup(RunContext(env="test", trigger="pytest"))

    results = [
        driver.execute_step(Step(action="open_app", target="微信")),
        driver.execute_step(Step(action="open_miniapp", target="职悟空")),
        driver.execute_step(Step(action="tap", target="我的")),
        driver.execute_step(Step(action="input", target="手机号输入框", value="13800000000")),
        driver.execute_step(Step(action="assert_text", target="用户昵称")),
    ]

    assert [result.status for result in results] == ["passed", "passed", "passed", "passed", "passed"]
    assert ("connect_device", "Android:///127.0.0.1:7555") in fake_api.calls
    assert ("start_app", "com.tencent.mm") in fake_api.calls
    assert ("poco_click", "职悟空") in fake_poco.calls
    assert ("poco_click", "我的") in fake_poco.calls
    assert ("poco_click", "手机号输入框") in fake_poco.calls
    assert ("text", "13800000000", {"enter": True, "search": False}) in fake_api.calls
    assert ("poco_exists", "用户昵称") in fake_poco.calls


def test_airtest_driver_taps_image_template(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "确认登录.png").write_bytes(b"fake image")
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        f"  image_dir: {image_dir.as_posix()}\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="tap", target="确认登录"))

    assert result.status == "passed"
    assert fake_api.calls[-1] == ("touch", {"filename": str(image_dir / "确认登录.png"), "threshold": 0.8})


def test_airtest_driver_uses_adb_device_when_config_uri_is_empty(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  device_uri: ''\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "Android:///94b63a3b")
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)

    driver.setup(RunContext(env="test", trigger="pytest"))

    assert ("connect_device", "Android:///94b63a3b") in fake_api.calls


def test_airtest_driver_executes_swipe_direction(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="swipe", target="down"))

    assert result.status == "passed"
    assert ("swipe", (500, 700), (500, 1500), {}) in fake_api.calls


def test_airtest_driver_searches_miniapp_without_poco_text_lookup(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: (420, 260))
    monkeypatch.setattr(AirtestDriver, "_find_visual_first_result_center", lambda self: (500, 460))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="测试小程序"))

    assert result.status == "passed"
    assert ("touch", [420, 260]) in fake_api.calls
    assert ("yosemite_text", "测试小程序") in fake_api.calls
    assert ("touch", [500, 460]) in fake_api.calls


def test_airtest_driver_focuses_search_box_by_uiautomator_bounds(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    ui_xml = (
        '<hierarchy><node text="搜索小程序" content-desc="" '
        'resource-id="" class="android.widget.EditText" bounds="[80,120][1120,210]" /></hierarchy>'
    )
    fake_api = FakeAirtestApi(ui_xml=ui_xml)
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: None)
    monkeypatch.setattr(AirtestDriver, "_find_visual_first_result_center", lambda self: (500, 460))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="测试小程序"))

    assert result.status == "passed"
    assert ("touch", (600, 165)) in fake_api.calls
    assert ("touch", (500, 140)) not in fake_api.calls


def test_airtest_driver_searches_even_when_recent_list_contains_target(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    ui_xml = (
        '<hierarchy><node text="职悟空" content-desc="" '
        'resource-id="" class="android.widget.TextView" bounds="[90,590][210,650]" /></hierarchy>'
    )
    fake_api = FakeAirtestApi(ui_xml=ui_xml)
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: (420, 260))
    monkeypatch.setattr(AirtestDriver, "_find_visual_first_result_center", lambda self: (500, 460))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "passed"
    assert "searched miniapp 职悟空" in result.message
    assert ("yosemite_text", "职悟空") in fake_api.calls


def test_airtest_driver_prefers_visual_search_box_and_ocr_result(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: (420, 260))
    monkeypatch.setattr(AirtestDriver, "_find_ocr_text_center", lambda self, text: (360, 520))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "passed"
    assert "search_box=visual_search_box" in result.message
    assert "result=visual_ocr" in result.message
    assert ("touch", [420, 260]) in fake_api.calls
    assert ("touch", [360, 520]) in fake_api.calls
    assert ("yosemite_text", "职悟空") in fake_api.calls


def test_airtest_driver_recovers_miniapp_panel_before_searching(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    wait_results = iter([None, None, (420, 260), (420, 260)])

    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(
        AirtestDriver,
        "_wait_visual_search_box_center",
        lambda self, timeout_seconds: next(wait_results),
    )
    monkeypatch.setattr(AirtestDriver, "_find_visual_first_result_center", lambda self: (500, 460))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "passed"
    assert "search_box=launcher+slow_pull_down+launcher+slow_pull_down+visual_search_box" in result.message
    assert ("swipe", (500, 480), (500, 1560), {"duration": 1.2}) in fake_api.calls
    assert ("keyevent", "BACK") not in fake_api.calls
    assert ("touch", [420, 260]) in fake_api.calls
    assert ("yosemite_text", "职悟空") in fake_api.calls


def test_airtest_driver_stops_when_miniapp_panel_is_not_detected(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()

    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: None)
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "failed"
    assert "未检测到微信小程序搜索页" in result.message
    assert ("touch", (500, 260)) not in fake_api.calls
    assert ("yosemite_text", "职悟空") not in fake_api.calls


def test_airtest_driver_prefers_poco_search_result_when_available(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    fake_poco = FakePoco()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.time.sleep", lambda _: None)
    monkeypatch.setattr(AirtestDriver, "_wait_visual_search_box_center", lambda self, timeout_seconds: (420, 260))
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api, poco_factory=lambda: fake_poco)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "passed"
    assert ("poco_click", "职悟空") in fake_poco.calls
    assert ("touch", (500, 460)) not in fake_api.calls


def test_airtest_driver_uses_coordinate_only_as_tap_fallback(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    fake_api = FakeAirtestApi()
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="tap", target="“开始交流”"))

    assert result.status == "passed"
    assert "source=coordinate_fallback" in result.message
    assert ("touch", (500, 1640)) in fake_api.calls


def test_airtest_driver_inputs_chinese_text_by_editable_field_and_yosemite(tmp_path, monkeypatch):
    config_path = tmp_path / "airtest.yaml"
    config_path.write_text(
        "airtest:\n"
        "  poco:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    ui_xml = (
        '<hierarchy><node text="" content-desc="" resource-id="chat_input" '
        'class="android.widget.EditText" clickable="true" focusable="true" '
        'enabled="true" bounds="[80,1660][920,1760]" /></hierarchy>'
    )
    fake_api = FakeAirtestApi(ui_xml=ui_xml)
    monkeypatch.setattr("miniapp_ui_auto.drivers.airtest_driver.resolve_adb_device_uri", lambda: "")
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="input", target="输入框", value="你好"))

    assert result.status == "passed"
    assert "focus_source=uiautomator_editable" in result.message
    assert ("touch", (500, 1710)) in fake_api.calls
    assert ("yosemite_text", "你好") in fake_api.calls
    assert ("adb_shell", ["input", "keyevent", "ENTER"]) in fake_api.calls
