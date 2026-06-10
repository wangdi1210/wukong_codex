import pytest
import builtins

from miniapp_ui_auto.drivers.airtest_driver import AirtestDriver, AirtestUnavailableError, load_airtest_config
from miniapp_ui_auto.models import RunContext, Step


class FakeAirtestApi:
    Template = staticmethod(lambda filename, threshold=None: {"filename": filename, "threshold": threshold})

    def __init__(self):
        self.calls = []

    def connect_device(self, device_uri):
        self.calls.append(("connect_device", device_uri))

    def start_app(self, package):
        self.calls.append(("start_app", package))

    def touch(self, target):
        self.calls.append(("touch", target))

    def text(self, value):
        self.calls.append(("text", value))

    def keyevent(self, value):
        self.calls.append(("keyevent", value))

    def swipe(self, start, end):
        self.calls.append(("swipe", start, end))

    def exists(self, target):
        self.calls.append(("exists", target))
        return True

    def wait(self, target, timeout=None):
        self.calls.append(("wait", target, timeout))

    def snapshot(self, filename=None):
        self.calls.append(("snapshot", filename))

    def device(self):
        self.calls.append(("device",))
        return FakeDevice(self.calls)


class FakeYosemiteIme:
    def __init__(self, calls):
        self.calls = calls

    def text(self, value):
        self.calls.append(("yosemite_text", value))

    def code(self, value):
        self.calls.append(("yosemite_code", value))


class FakeDevice:
    def __init__(self, calls):
        self.yosemite_ime = FakeYosemiteIme(calls)


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
    assert ("text", "13800000000") in fake_api.calls
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
    assert ("swipe", (0.5, 0.35), (0.5, 0.75)) in fake_api.calls


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
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="search_miniapp", target="职悟空"))

    assert result.status == "passed"
    assert fake_api.calls == [
        ("touch", (0.5, 0.12)),
        ("touch", (0.5, 0.16)),
        ("device",),
        ("yosemite_text", "职悟空"),
        ("yosemite_code", "3"),
        ("touch", (0.5, 0.23)),
    ]


def test_airtest_driver_taps_known_business_button_by_coordinate(tmp_path, monkeypatch):
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
    driver = AirtestDriver(config_path=config_path, airtest_api=fake_api, poco_factory=lambda: fake_poco)
    driver.setup(RunContext(env="test", trigger="pytest"))

    result = driver.execute_step(Step(action="tap", target="“开始交流”"))

    assert result.status == "passed"
    assert ("touch", (0.5, 0.82)) in fake_api.calls
    assert fake_poco.calls == []
