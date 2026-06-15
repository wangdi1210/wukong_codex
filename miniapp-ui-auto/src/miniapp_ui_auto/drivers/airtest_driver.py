from __future__ import annotations

import shutil
import subprocess
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import xml.etree.ElementTree as ET

import yaml

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class AirtestUnavailableError(RuntimeError):
    """Raised when Airtest is not installed or cannot be imported."""


@dataclass(frozen=True)
class AirtestConfig:
    device_uri: str = ""
    package: str = "com.tencent.mm"
    miniapp_name: str = ""
    image_threshold: float = 0.8
    image_dir: str = "assets/images"
    poco_enabled: bool = True


class AirtestDriver(AutomationDriver):
    name = "airtest"

    def __init__(
        self,
        config_path: Path | None = None,
        airtest_api: Any | None = None,
        template_factory: Callable[..., Any] | None = None,
        poco_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config_path = config_path or Path("config/airtest.yaml")
        self.config = AirtestConfig()
        self._airtest_api = airtest_api
        self._template_factory = template_factory
        self._poco_factory = poco_factory
        self._poco = None

    def setup(self, context: RunContext) -> None:
        self.config = load_airtest_config(self.config_path)
        if self._airtest_api is None:
            try:
                from airtest.core import api as airtest_api  # type: ignore
            except ImportError as exc:
                raise AirtestUnavailableError(
                    "Airtest is not installed. Install and configure it with `pip install airtest pocoui` "
                    "after the Android/iOS device or emulator is ready."
                ) from exc
            self._airtest_api = airtest_api
        if self._template_factory is None:
            self._template_factory = self._airtest_api.Template
        device_uri = self.config.device_uri or resolve_adb_device_uri()
        if device_uri:
            self._airtest_api.connect_device(device_uri)
        if self.config.poco_enabled:
            self._poco = self._create_poco()

    def execute_step(self, step: Step) -> StepResult:
        if self._airtest_api is None:
            return StepResult(
                action=step.action,
                target=step.target,
                status="failed",
                message="Airtest driver is not set up.",
            )
        try:
            message = self._execute(step)
            return StepResult(action=step.action, target=step.target, status="passed", message=message)
        except Exception as exc:  # noqa: BLE001 - convert driver exceptions into reportable step results.
            return StepResult(action=step.action, target=step.target, status="failed", message=str(exc))

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        if self._airtest_api is None:
            return ()
        artifact_path = Path("reports") / "artifacts" / f"{case_id}.png"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self._airtest_api.snapshot(filename=str(artifact_path))
        return (str(artifact_path),)

    def teardown(self) -> None:
        self._poco = None

    def _execute(self, step: Step) -> str:
        if step.action == "open_app":
            self._airtest_api.start_app(self.config.package)
            time.sleep(1)
            return f"started app package {self.config.package}"
        if step.action == "open_miniapp":
            return self._open_miniapp(step.target)
        if step.action == "search_miniapp":
            return self._search_miniapp(step.target)
        if step.action == "tap":
            self._tap(step.target)
            return f"tapped {step.target}"
        if step.action == "input":
            self._tap(step.target)
            self._input_text("" if step.value is None else str(step.value), submit=True)
            return f"input text into {step.target}"
        if step.action == "swipe":
            self._swipe(step.target)
            time.sleep(1)
            return f"swiped {step.target}"
        if step.action == "wait":
            self._wait(step.target, timeout_ms=step.timeout_ms)
            return f"waited for {step.target}"
        if step.action in ("assert_text", "assert_element", "assert_data"):
            self._assert_exists(step.target)
            return f"asserted {step.target} exists"
        if step.action == "screenshot":
            self._airtest_api.snapshot()
            return "captured screenshot"
        if step.action in ("mock", "set_storage", "open_page"):
            raise NotImplementedError(f"{step.action} requires source-level or project-specific integration.")
        raise ValueError(f"Unsupported Airtest action: {step.action}")

    def _open_miniapp(self, target: str) -> str:
        miniapp_name = target or self.config.miniapp_name
        if not miniapp_name:
            raise ValueError("open_miniapp requires a target miniapp name or config.airtest.miniapp_name.")
        if self._poco is not None:
            self._poco(text=miniapp_name).click()
            return f"opened miniapp by Poco text {miniapp_name}"
        raise NotImplementedError(
            "open_miniapp needs a project-specific entry strategy. Enable Poco or add image templates/search steps."
        )

    def _search_miniapp(self, target: str) -> str:
        miniapp_name = (target or self.config.miniapp_name).strip()
        if not miniapp_name:
            raise ValueError("search_miniapp requires a miniapp name.")
        if self._tap_recent_miniapp(miniapp_name):
            time.sleep(1)
            return f"opened recent miniapp {miniapp_name}"
        # 最近列表找不到目标时，再进入搜索框输入小程序名称。
        self._focus_miniapp_search_box()
        time.sleep(0.5)
        self._input_search_text(miniapp_name)
        time.sleep(1)
        self._tap_miniapp_search_result(miniapp_name)
        time.sleep(1)
        return f"searched miniapp {miniapp_name}"

    def _tap_recent_miniapp(self, miniapp_name: str) -> bool:
        if self._poco is not None:
            try:
                self._poco(text=miniapp_name).click()
                return True
            except Exception:
                pass
        if self._tap_by_uiautomator_exact_text(miniapp_name):
            return True
        coordinate = _known_recent_miniapp_coordinate(miniapp_name)
        if coordinate is None:
            return False
        self._touch_ratio(coordinate)
        return True

    def _focus_miniapp_search_box(self) -> None:
        if self._tap_by_uiautomator_text(("搜索小程序", "搜索", "搜一搜")):
            return
        # 微信下拉搜索页的输入框在顶部，不同机型状态栏高度略有差异，连续点两个顶部候选位置。
        self._touch_ratio((0.5, 0.07))
        time.sleep(0.3)
        self._touch_ratio((0.5, 0.095))

    def _tap_by_uiautomator_text(self, keywords: tuple[str, ...]) -> bool:
        xml_text = self._dump_ui_xml()
        point = _bounds_center_for_keywords(xml_text, keywords)
        if point is None:
            return False
        self._airtest_api.touch(point)
        return True

    def _tap_by_uiautomator_exact_text(self, text: str) -> bool:
        xml_text = self._dump_ui_xml()
        point = _bounds_center_for_exact_text(xml_text, text)
        if point is None:
            return False
        self._airtest_api.touch(point)
        return True

    def _dump_ui_xml(self) -> str:
        try:
            adb = self._airtest_api.device().adb
            for path in ("/sdcard/window.xml", "/data/local/tmp/window.xml"):
                adb.shell(["uiautomator", "dump", "--compressed", path])
                xml_text = str(adb.shell(["cat", path]) or "")
                if "<hierarchy" in xml_text:
                    return xml_text
            xml_text = str(adb.shell(["uiautomator", "dump", "--compressed", "/dev/tty"]) or "")
            if "<hierarchy" in xml_text:
                return xml_text
        except Exception:
            return ""
        return ""

    def _tap_miniapp_search_result(self, miniapp_name: str) -> None:
        if self._poco is not None:
            try:
                self._poco(text=miniapp_name).click()
                return
            except Exception:
                pass
        self._touch_ratio((0.5, 0.23))

    def _input_search_text(self, value: str) -> None:
        self._input_text(value, editor_code="3")

    def _input_text(self, value: str, *, submit: bool = False, editor_code: str | None = None) -> None:
        if _has_non_ascii(value):
            try:
                device = self._airtest_api.device()
                ime = getattr(device, "yosemite_ime")
                try:
                    ime.text(value)
                except Exception:
                    ime.start()
                    device.adb.shell(["am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", value])
                if editor_code is not None:
                    ime.code(editor_code)
                elif submit:
                    device.adb.shell(["input", "keyevent", "ENTER"])
                return
            except Exception as exc:  # noqa: BLE001 - provide an actionable device-side setup error.
                raise RuntimeError(
                    "中文输入需要 Airtest Yosemite 输入法。请保持手机亮屏并允许安装/启用 YosemiteIme，"
                    f"然后在设备页重新检查环境后再执行。原始错误：{exc}"
                ) from exc
        self._airtest_api.text(value, enter=submit, search=editor_code == "3")

    def _tap(self, target: str) -> None:
        target = _clean_action_target(target)
        coordinate = _known_coordinate_target(target)
        if coordinate is not None:
            self._touch_ratio(coordinate)
            return
        image_path = self._image_path(target)
        if image_path is not None:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            self._airtest_api.touch(template)
            return
        if self._poco is not None:
            self._poco(text=target).click()
            return
        self._airtest_api.touch(target)

    def _swipe(self, direction: str) -> None:
        direction = direction.lower().strip()
        vectors = {
            "down": ((0.5, 0.35), (0.5, 0.75)),
            "up": ((0.5, 0.75), (0.5, 0.35)),
            "left": ((0.75, 0.5), (0.25, 0.5)),
            "right": ((0.25, 0.5), (0.75, 0.5)),
        }
        if direction not in vectors:
            raise ValueError(f"Unsupported swipe direction: {direction}. Use down, up, left, or right.")
        start, end = vectors[direction]
        self._airtest_api.swipe(self._point(start), self._point(end))

    def _touch_ratio(self, point: tuple[float, float]) -> None:
        self._airtest_api.touch(self._point(point))

    def _point(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        if x > 1 or y > 1:
            return int(x), int(y)
        width, height = self._screen_size()
        return int(width * x), int(height * y)

    def _screen_size(self) -> tuple[int, int]:
        try:
            size = self._airtest_api.device().get_current_resolution()
        except Exception:
            return 1080, 1920
        if not size or len(size) < 2:
            return 1080, 1920
        return int(size[0]), int(size[1])

    def _wait(self, target: str, timeout_ms: int | None) -> None:
        image_path = self._image_path(target)
        timeout = None if timeout_ms is None else timeout_ms / 1000
        if image_path is not None:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            if timeout is None:
                self._airtest_api.wait(template)
            else:
                self._airtest_api.wait(template, timeout=timeout)
            return
        if self._poco is not None:
            node = self._poco(text=target)
            if not node.exists():
                raise AssertionError(f"Poco target not found: {target}")
            return
        raise ValueError(f"wait target has no image template and Poco is unavailable: {target}")

    def _assert_exists(self, target: str) -> None:
        image_path = self._image_path(target)
        if image_path is not None:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            if not self._airtest_api.exists(template):
                raise AssertionError(f"Image target not found: {target}")
            return
        if self._poco is not None:
            if not self._poco(text=target).exists():
                raise AssertionError(f"Poco target not found: {target}")
            return
        raise ValueError(f"assert target has no image template and Poco is unavailable: {target}")

    def _image_path(self, target: str) -> Path | None:
        raw_path = Path(target)
        if raw_path.exists():
            return raw_path
        candidate = Path(self.config.image_dir) / f"{target}.png"
        if candidate.exists():
            return candidate
        return None

    def _create_poco(self) -> Any | None:
        if self._poco_factory is not None:
            return self._poco_factory()
        try:
            from poco.drivers.android.uiautomation import AndroidUiautomationPoco  # type: ignore
        except ImportError:
            return None
        return AndroidUiautomationPoco()


def load_airtest_config(config_path: Path) -> AirtestConfig:
    if not config_path.exists():
        return AirtestConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    airtest = raw.get("airtest", {})
    poco = airtest.get("poco", {})
    return AirtestConfig(
        device_uri=airtest.get("device_uri", "") or "",
        package=airtest.get("package", "com.tencent.mm") or "com.tencent.mm",
        miniapp_name=airtest.get("miniapp_name", "") or "",
        image_threshold=float(airtest.get("image_threshold", 0.8)),
        image_dir=airtest.get("image_dir", "assets/images") or "assets/images",
        poco_enabled=bool(poco.get("enabled", True)),
    )


def _has_non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def _clean_action_target(value: str) -> str:
    return value.strip(" ：:，,。\"'“”‘’")


def _known_coordinate_target(value: str) -> tuple[float, float] | None:
    known_targets = {
        "开始交流": (0.5, 0.82),
        "输入框": (0.5, 0.9),
    }
    return known_targets.get(value)


def _known_recent_miniapp_coordinate(value: str) -> tuple[float, float] | None:
    known_targets = {
        "职悟空": (0.16, 0.28),
    }
    return known_targets.get(value)


def _bounds_center_for_keywords(xml_text: str, keywords: tuple[str, ...]) -> tuple[int, int] | None:
    start = xml_text.find("<hierarchy")
    if start < 0:
        return None
    try:
        root = ET.fromstring(xml_text[start:])
    except ET.ParseError:
        return None
    candidates: list[tuple[int, int, int]] = []
    for node in root.iter("node"):
        attrs = node.attrib
        haystack = " ".join(
            attrs.get(name, "") for name in ("text", "content-desc", "resource-id", "class")
        )
        if not any(keyword in haystack for keyword in keywords):
            continue
        center = _bounds_center(attrs.get("bounds", ""))
        if center is not None:
            x, y = center
            candidates.append((y, x, len(attrs.get("text", "") or attrs.get("content-desc", ""))))
    if not candidates:
        return None
    y, x, _ = sorted(candidates)[0]
    return x, y


def _bounds_center_for_exact_text(xml_text: str, text: str) -> tuple[int, int] | None:
    start = xml_text.find("<hierarchy")
    if start < 0:
        return None
    try:
        root = ET.fromstring(xml_text[start:])
    except ET.ParseError:
        return None
    for node in root.iter("node"):
        attrs = node.attrib
        if text not in (attrs.get("text", ""), attrs.get("content-desc", "")):
            continue
        center = _bounds_center(attrs.get("bounds", ""))
        if center is not None:
            return center
    return None


def _bounds_center(bounds: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", bounds)
    if not match:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if right <= left or bottom <= top:
        return None
    return (left + right) // 2, (top + bottom) // 2


def resolve_adb_device_uri() -> str:
    adb = shutil.which("adb")
    if not adb:
        return ""
    try:
        result = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            return f"Android:///{parts[0]}"
    return ""
