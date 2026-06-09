import pytest
import builtins

from miniapp_ui_auto.drivers.airtest_driver import AirtestDriver, AirtestUnavailableError
from miniapp_ui_auto.models import RunContext


def test_airtest_driver_fails_clearly_when_airtest_is_not_installed(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "airtest.core":
            raise ImportError("airtest missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    driver = AirtestDriver()

    with pytest.raises(AirtestUnavailableError) as error:
        driver.setup(RunContext(env="test", trigger="local"))

    assert "pip install airtest pocoui" in str(error.value)
