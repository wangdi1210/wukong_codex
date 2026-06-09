from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class MiniumUnavailableError(RuntimeError):
    """Raised when Minium is not installed or cannot be imported."""


class MiniumDriver(AutomationDriver):
    name = "minium"

    def __init__(self) -> None:
        self._minium_module = None

    def setup(self, context: RunContext) -> None:
        try:
            import minium  # type: ignore
        except ImportError as exc:
            raise MiniumUnavailableError(
                "Minium is not installed. Install and configure it with `pip install minium` "
                "after the WeChat DevTools environment is ready."
            ) from exc
        self._minium_module = minium

    def execute_step(self, step: Step) -> StepResult:
        if self._minium_module is None:
            return StepResult(
                action=step.action,
                target=step.target,
                status="failed",
                message="Minium driver is not set up.",
            )
        return StepResult(
            action=step.action,
            target=step.target,
            status="failed",
            message="Real Minium step execution will be wired after the local WeChat DevTools environment is ready.",
        )

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        self._minium_module = None
