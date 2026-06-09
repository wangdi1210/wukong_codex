from __future__ import annotations

from miniapp_ui_auto.drivers.airtest_driver import AirtestDriver
from miniapp_ui_auto.drivers.base import AutomationDriver
from miniapp_ui_auto.drivers.dry_run import DryRunDriver
from miniapp_ui_auto.drivers.minium_driver import MiniumDriver


def create_driver(name: str) -> AutomationDriver:
    if name == "dry-run":
        return DryRunDriver()
    if name in ("airtest", "poco"):
        return AirtestDriver()
    if name == "minium":
        return MiniumDriver()
    supported = "dry-run, airtest, poco, minium"
    raise ValueError(f"Unsupported driver '{name}'. Supported drivers: {supported}")
