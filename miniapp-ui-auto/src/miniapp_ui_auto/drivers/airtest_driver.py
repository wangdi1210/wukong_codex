from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
        if self.config.device_uri:
            self._airtest_api.connect_device(self.config.device_uri)
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
            return f"started app package {self.config.package}"
        if step.action == "open_miniapp":
            return self._open_miniapp(step.target)
        if step.action == "tap":
            self._tap(step.target)
            return f"tapped {step.target}"
        if step.action == "input":
            self._tap(step.target)
            self._airtest_api.text("" if step.value is None else str(step.value))
            return f"input text into {step.target}"
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

    def _tap(self, target: str) -> None:
        image_path = self._image_path(target)
        if image_path is not None:
            template = self._template_factory(str(image_path), threshold=self.config.image_threshold)
            self._airtest_api.touch(template)
            return
        if self._poco is not None:
            self._poco(text=target).click()
            return
        self._airtest_api.touch(target)

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
