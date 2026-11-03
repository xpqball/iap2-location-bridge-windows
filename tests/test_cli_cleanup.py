"""All owned resources must close even if another cleanup fails."""

from types import SimpleNamespace

import pytest

from iap2_location_bridge_windows import cli


@pytest.mark.parametrize("failed_close", [None, "link", "phone"])
async def test_cleanup_continues_after_failure(monkeypatch, failed_close):
    closed = []

    class Resource:
        def __init__(self, name):
            self.name = name

        async def close(self):
            closed.append(self.name)
            if self.name == failed_close:
                raise OSError(f"{self.name} cleanup failed")

    class Phone(Resource):
        async def start_lockdown_service(self, name):
            return object()

    class Link(Resource):
        async def handshake(self):
            raise RuntimeError("handshake failed")

    async def connect(**kwargs):
        return Phone("phone")

    monkeypatch.setattr(cli, "create_using_usbmux", connect)
    monkeypatch.setattr(cli, "Link", lambda *args: Link("link"))
    monkeypatch.setattr(cli, "AuthenticationProvider", lambda *args: Resource("auth"))
    args = SimpleNamespace(transport="usb", auth_helper="test-helper")
    with pytest.raises((RuntimeError, OSError)):
        await cli.run(args)
    assert closed == ["link", "phone", "auth"]
