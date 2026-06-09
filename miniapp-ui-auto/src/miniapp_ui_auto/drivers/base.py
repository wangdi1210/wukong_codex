from __future__ import annotations

from abc import ABC, abstractmethod

from miniapp_ui_auto.models import RunContext, Step, StepResult


class AutomationDriver(ABC):
    name: str

    @abstractmethod
    def setup(self, context: RunContext) -> None:
        """Prepare the driver before executing cases."""

    @abstractmethod
    def execute_step(self, step: Step) -> StepResult:
        """Execute one normalized automation step."""

    @abstractmethod
    def capture_artifact(self, case_id: str) -> tuple[str, ...]:
        """Capture screenshots, logs, or other useful artifacts."""

    @abstractmethod
    def teardown(self) -> None:
        """Release resources after the run."""
