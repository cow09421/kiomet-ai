"""The live BrowserHost exposes no game-memory observation path."""
import asyncio

import pytest

from kiomet_ai.browser import BrowserHost


class NoCdpContext:
    def __init__(self):
        self.calls = 0

    async def new_cdp_session(self, _page):
        self.calls += 1
        raise AssertionError("a memory read must not open a CDP session")


def test_read_wasm_bytes_is_disabled_before_opening_cdp_session():
    host = object.__new__(BrowserHost)
    context = NoCdpContext()
    host.game_page = type("Page", (), {"context": context})()

    with pytest.raises(RuntimeError, match="玩家可見 UI"):
        asyncio.run(host.read_wasm_bytes(0x1000, 24))

    assert context.calls == 0


@pytest.mark.parametrize(("address", "length"), [
    (0, 24),
    (0x1000, 0),
    (0x1000, 70000),
])
def test_read_wasm_bytes_never_opens_cdp_even_for_invalid_requests(address, length):
    host = object.__new__(BrowserHost)
    context = NoCdpContext()
    host.game_page = type("Page", (), {"context": context})()

    with pytest.raises(RuntimeError, match="停用遊戲記憶體讀取"):
        asyncio.run(host.read_wasm_bytes(address, length))

    assert context.calls == 0
