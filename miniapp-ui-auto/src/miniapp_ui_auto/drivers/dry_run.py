from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.models import RunContext, Step, StepResult


class DryRunDriver(AutomationDriver):
    name = "dry-run"

    def __init__(self) -> None:
        self.context: RunContext | None = None
        self.executed_steps: list[Step] = []

    def setup(self, context: RunContext) -> None:
        self.context = context

    def execute_step(self, step: Step) -> StepResult:
        self.executed_steps.append(step)
        return StepResult(
            action=step.action,
            target=step.target,
            status="passed",
            message=f"dry-run executed {step.action} on {step.target}",
        )

    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        return ()

    def teardown(self) -> None:
        self.context = None
