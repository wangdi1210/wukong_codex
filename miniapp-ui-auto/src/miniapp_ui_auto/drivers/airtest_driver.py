from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class AirtestUnavailableError(RuntimeError):
    """Raised when Airtest is not installed or cannot be imported."""


class AirtestDriver(AutomationDriver):
    name = "airtest"

    def __init__(self) -> None:
        self._airtest_api = None

    def setup(self, context: RunContext) -> None:
        try:
            from airtest.core import api as airtest_api  # type: ignore
        except ImportError as exc:
            raise AirtestUnavailableError(
                "Airtest is not installed. Install and configure it with `pip install airtest pocoui` "
                "after the Android/iOS device or emulator is ready."
            ) from exc
        self._airtest_api = airtest_api

    def execute_step(self, step: Step) -> StepResult:
        if self._airtest_api is None:
            return StepResult(
                action=step.action,
                target=step.target,
                status="failed",
                message="Airtest driver is not set up.",
            )
        return StepResult(
            action=step.action,
            target=step.target,
            status="failed",
            message="Real Airtest step execution will be wired after device connection and image templates are ready.",
        )

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        self._airtest_api = None
