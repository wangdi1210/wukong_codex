from __future__ import annotations

from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.drivers.dry_run import DryRunDriver
from miniapp_ui_auto.drivers.minium_driver import MiniumDriver


def create_driver(name: str) -> AutomationDriver:
    if name == "dry-run":
        return DryRunDriver()
    if name == "minium":
        return MiniumDriver()
    supported = "dry-run, minium"
    raise ValueError(f"Unsupported driver '{name}'. Supported drivers: {supported}")
