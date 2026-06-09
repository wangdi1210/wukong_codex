import pytest
import builtins

from miniapp_ui_auto.drivers.minium_driver import MiniumDriver, MiniumUnavailableError
from miniapp_ui_auto.models import RunContext


def test_minium_driver_fails_clearly_when_minium_is_not_installed(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "minium":
            raise ImportError("minium missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    driver = MiniumDriver()

    with pytest.raises(MiniumUnavailableError) as error:
        driver.setup(RunContext(env="test", trigger="local"))

    assert "pip install minium" in str(error.value)
