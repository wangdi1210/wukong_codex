from __future__ import annotations

import shutil
import subprocess
import time
import re
from dataclasses import dataclass
from datetime import datetime
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
            source = self._tap(step.target)
            return f"tapped {step.target}; source={source}"
        if step.action == "input":
            source = self._tap(step.target)
            self._input_text("" if step.value is None else str(step.value), submit=True)
            return f"input text into {step.target}; focus_source={source}"
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
        search_box_source = self._focus_miniapp_search_box()
        time.sleep(0.5)
        self._input_search_text(miniapp_name)
        time.sleep(1)
        result_source = self._tap_miniapp_search_result(miniapp_name)
        time.sleep(1)
        self._assert_foreground_package()
        return f"searched miniapp {miniapp_name}; search_box={search_box_source}; result={result_source}"

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

    def _focus_miniapp_search_box(self) -> str:
        visual_point = self._wait_visual_search_box_center(timeout_seconds=2)
        if visual_point is not None:
            self._touch_absolute(visual_point)
            return "visual_search_box"
        panel_source = self._enter_miniapp_search_panel()
        visual_point = self._wait_visual_search_box_center(timeout_seconds=4)
        if visual_point is not None:
            self._touch_absolute(visual_point)
            return f"{panel_source}+visual_search_box"
        if self._tap_by_uiautomator_text(("搜索小程序", "搜索", "搜一搜")):
            return f"{panel_source}+uiautomator_text"
        raise RuntimeError(
            "未检测到微信小程序搜索页。已尝试拉起微信首页并慢速下拉，但没有通过视觉识别找到“搜索小程序”输入框，"
            "为避免跑到公众号/服务号搜索，本步骤已停止。请确认当前微信是否在首页聊天列表，或重新执行。"
        )

    def _wait_visual_search_box_center(self, timeout_seconds: float) -> tuple[int, int] | None:
        deadline = time.time() + timeout_seconds
        while True:
            point = self._find_visual_search_box_center()
            if point is not None:
                return point
            if time.time() >= deadline:
                return None
            time.sleep(0.5)

    def _enter_miniapp_search_panel(self) -> str:
        sources: list[str] = []
        for attempt in range(3):
            self._open_wechat_launcher()
            sources.append("launcher")
            time.sleep(0.8)
            self._slow_pull_down()
            sources.append("slow_pull_down")
            if self._wait_visual_search_box_center(timeout_seconds=2) is not None:
                return "+".join(sources)
        return "+".join(sources)

    def _open_wechat_launcher(self) -> None:
        try:
            self._airtest_api.device().adb.shell(
                ["am", "start", "-n", f"{self.config.package}/.ui.LauncherUI"]
            )
            return
        except Exception:
            pass
        try:
            self._airtest_api.start_app(self.config.package)
        except Exception:
            pass

    def _press_back(self) -> None:
        try:
            self._airtest_api.keyevent("BACK")
            return
        except Exception:
            pass
        try:
            self._airtest_api.device().adb.shell(["input", "keyevent", "BACK"])
        except Exception:
            pass

    def _slow_pull_down(self) -> None:
        start = self._point((0.5, 0.24))
        end = self._point((0.5, 0.78))
        try:
            self._airtest_api.swipe(start, end, duration=1.2)
            return
        except Exception:
            pass
        try:
            self._airtest_api.device().adb.shell(
                ["input", "swipe", str(start[0]), str(start[1]), str(end[0]), str(end[1]), "1200"]
            )
            return
        except Exception:
            pass
        self._airtest_api.swipe(start, end)

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

    def _tap_miniapp_search_result(self, miniapp_name: str) -> str:
        template_point = self._find_template_center(miniapp_name)
        if template_point is not None:
            self._touch_absolute(template_point)
            return "visual_template"
        ocr_point = self._find_ocr_text_center(miniapp_name)
        if ocr_point is not None:
            self._touch_absolute(ocr_point)
            return "visual_ocr"
        if self._poco is not None:
            try:
                self._poco(text=miniapp_name).click()
                return "poco_text"
            except Exception:
                pass
        if self._tap_by_uiautomator_exact_text(miniapp_name):
            return "uiautomator_text"
        first_result_point = self._find_visual_first_result_center()
        if first_result_point is not None:
            self._touch_absolute(first_result_point)
            return "visual_first_result"
        raise RuntimeError(
            f"未检测到“{miniapp_name}”的小程序搜索结果页。为避免误点公众号、聊天页或外部应用，本步骤未执行坐标兜底。"
        )

    def _find_visual_search_box_center(self) -> tuple[int, int] | None:
        image_path = self._snapshot_for_visual("search_box")
        if image_path is None:
            return None
        return _find_search_box_center(image_path, require_dark_panel=True)

    def _find_visual_first_result_center(self) -> tuple[int, int] | None:
        image_path = self._snapshot_for_visual("first_result")
        if image_path is None:
            return None
        search_box = _find_search_box_center(image_path, require_dark_panel=False)
        if search_box is None:
            return None
        width, height = self._screen_size()
        x, y = search_box
        return x, min(int(height * 0.9), y + int(height * 0.14))

    def _find_template_center(self, target: str) -> tuple[int, int] | None:
        image_path = self._image_path(target)
        if image_path is None:
            return None
        screen_path = self._snapshot_for_visual("template")
        if screen_path is not None:
            point = _match_template_center(screen_path, image_path, self.config.image_threshold)
            if point is not None:
                return point
        try:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            point = self._airtest_api.exists(template)
        except Exception:
            return None
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return int(point[0]), int(point[1])
        return None

    def _find_ocr_text_center(self, text: str) -> tuple[int, int] | None:
        image_path = self._snapshot_for_visual("ocr")
        if image_path is None:
            return None
        return _find_text_center_by_ocr(image_path, text)

    def _snapshot_for_visual(self, name: str) -> Path | None:
        artifact_dir = Path("reports") / "artifacts" / "visual"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        image_path = artifact_dir / f"{name}_{timestamp}.png"
        try:
            self._airtest_api.snapshot(filename=str(image_path))
        except Exception:
            return None
        if image_path.exists():
            return image_path
        return None

    def _input_search_text(self, value: str) -> None:
        self._input_text(value, editor_code="3")

    def _assert_foreground_package(self) -> None:
        current_package = self._current_foreground_package()
        if current_package and current_package != self.config.package:
            raise RuntimeError(
                f"执行后前台应用不是微信：current_package={current_package}，expected={self.config.package}。"
            )

    def _current_foreground_package(self) -> str:
        try:
            output = str(
                self._airtest_api.device().adb.shell(["dumpsys", "window", "windows"]) or ""
            )
        except Exception:
            return ""
        match = re.search(r"mCurrentFocus=Window\{[^ ]+ [^ ]+ ([^/]+)/", output)
        if match:
            return match.group(1)
        match = re.search(r"mFocusedApp=.* ([^/]+)/", output)
        if match:
            return match.group(1)
        return ""

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

    def _tap(self, target: str) -> str:
        target = _clean_action_target(target)
        image_path = self._image_path(target)
        if image_path is not None:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            self._airtest_api.touch(template)
            return "image_template"
        if self._poco is not None:
            try:
                self._poco(text=target).click()
                return "poco_text"
            except Exception:
                pass
        if self._tap_by_uiautomator_exact_text(target):
            return "uiautomator_text"
        if _looks_like_input_target(target) and self._tap_first_editable_field():
            return "uiautomator_editable"
        coordinate = _known_coordinate_target(target)
        if coordinate is not None:
            self._touch_ratio(coordinate)
            return "coordinate_fallback"
        self._airtest_api.touch(target)
        return "airtest_raw_target"

    def _tap_first_editable_field(self) -> bool:
        xml_text = self._dump_ui_xml()
        point = _bounds_center_for_editable(xml_text)
        if point is None:
            return False
        self._airtest_api.touch(point)
        return True

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

    def _touch_absolute(self, point: tuple[int, int]) -> None:
        self._airtest_api.touch([int(point[0]), int(point[1])])

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


def _looks_like_input_target(value: str) -> bool:
    return any(keyword in value for keyword in ("输入框", "输入栏", "文本框", "编辑框", "input", "textarea"))


def _find_search_box_center(image_path: Path, *, require_dark_panel: bool = False) -> tuple[int, int] | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return None
    image = cv2.imread(str(image_path))
    if image is None:
        image = _read_cv_image(image_path)
    if image is None:
        return None
    height, width = image.shape[:2]
    top_region = image[: int(height * 0.32), :]
    gray = cv2.cvtColor(top_region, cv2.COLOR_BGR2GRAY)
    if require_dark_panel and float(gray.mean()) > 130:
        return None
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(40, int(width * 0.05)),
        param1=50,
        param2=18,
        minRadius=max(10, int(width * 0.012)),
        maxRadius=max(28, int(width * 0.035)),
    )
    if circles is not None:
        circle_candidates: list[tuple[int, int, int]] = []
        for x, y, radius in np.round(circles[0]).astype(int):
            if width * 0.2 <= x <= width * 0.65 and height * 0.08 <= y <= height * 0.2:
                circle_candidates.append((x, y, radius))
        if circle_candidates:
            x, y, _ = sorted(circle_candidates, key=lambda item: (item[1], item[0]))[0]
            return width // 2, y

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    mask = cv2.inRange(blurred, 45, 170)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 45), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < width * 0.35 or h < height * 0.025:
            continue
        if h > height * 0.12 or y < height * 0.08 or y > height * 0.2:
            continue
        candidates.append((x, y, w, h))
    if not candidates:
        return None
    x, y, w, h = sorted(candidates, key=lambda item: (item[1], -item[2]))[0]
    return x + w // 2, y + h // 2


def _find_text_center_by_ocr(image_path: Path, text: str) -> tuple[int, int] | None:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return None
    try:
        image = Image.open(image_path)
    except OSError:
        return None
    for lang in ("chi_sim+eng", "eng"):
        try:
            data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        except Exception:
            continue
        point = _ocr_data_text_center(data, text)
        if point is not None:
            return point
    return None


def _match_template_center(screen_path: Path, template_path: Path, threshold: float) -> tuple[int, int] | None:
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    screen = _read_cv_image(screen_path)
    template = _read_cv_image(template_path)
    if screen is None or template is None:
        return None
    if screen.shape[0] < template.shape[0] or screen.shape[1] < template.shape[1]:
        return None
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_value, _, max_location = cv2.minMaxLoc(result)
    if max_value < threshold:
        return None
    x, y = max_location
    height, width = template.shape[:2]
    return x + width // 2, y + height // 2


def _read_cv_image(image_path: Path) -> Any | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return None
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _ocr_data_text_center(data: dict[str, list[Any]], expected: str) -> tuple[int, int] | None:
    words = data.get("text", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])
    expected_compact = _compact_text(expected)
    candidates: list[tuple[int, int, int, int]] = []
    for index, word in enumerate(words):
        if expected_compact not in _compact_text(str(word)):
            continue
        try:
            left = int(lefts[index])
            top = int(tops[index])
            width = int(widths[index])
            height = int(heights[index])
        except (IndexError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        candidates.append((left, top, width, height))
    if not candidates:
        return None
    left, top, width, height = sorted(candidates, key=lambda item: (item[1], item[0]))[0]
    return left + width // 2, top + height // 2


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


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


def _bounds_center_for_editable(xml_text: str) -> tuple[int, int] | None:
    start = xml_text.find("<hierarchy")
    if start < 0:
        return None
    try:
        root = ET.fromstring(xml_text[start:])
    except ET.ParseError:
        return None
    candidates: list[tuple[int, int, int, int, int]] = []
    for node in root.iter("node"):
        attrs = node.attrib
        class_name = attrs.get("class", "")
        resource_id = attrs.get("resource-id", "")
        clickable = attrs.get("clickable", "")
        enabled = attrs.get("enabled", "")
        focusable = attrs.get("focusable", "")
        editable = (
            "EditText" in class_name
            or "input" in resource_id.lower()
            or "editor" in resource_id.lower()
            or (clickable == "true" and focusable == "true" and enabled != "false")
        )
        if not editable:
            continue
        rect = _bounds_rect(attrs.get("bounds", ""))
        if rect is None:
            continue
        left, top, right, bottom = rect
        candidates.append((top, left, right, bottom, len(attrs.get("text", "") or attrs.get("content-desc", ""))))
    if not candidates:
        return None
    top, left, right, bottom, _ = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
    return (left + right) // 2, (top + bottom) // 2


def _bounds_center(bounds: str) -> tuple[int, int] | None:
    rect = _bounds_rect(bounds)
    if rect is None:
        return None
    left, top, right, bottom = rect
    return (left + right) // 2, (top + bottom) // 2


def _bounds_rect(bounds: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", bounds)
    if not match:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


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
