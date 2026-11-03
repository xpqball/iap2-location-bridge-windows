import sys

import pytest

from iap2_location_bridge_windows import cli


def test_windows_bluetooth_rejected_before_connection(monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["iap2-location-bridge-windows", "probe", "--transport", "bluetooth"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "use --transport usb" in capsys.readouterr().err
