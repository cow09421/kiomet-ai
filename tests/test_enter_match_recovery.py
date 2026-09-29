"""The explicit join flow must recover when its isolated page is replaced."""
import asyncio

import pytest

from kiomet_ai import browser as browser_module
from kiomet_ai.browser import BrowserHost
from kiomet_ai.app import JOIN_NON_ERROR_CODES


def run(coro):
    return asyncio.run(coro)


class ConnectedBrowser:
    def is_connected(self):
        return True


def game_state(**overrides):
    return {
        "state": "UNKNOWN", "evidence": "test", "evidences": [],
        "source": "test", "updated_at": None,
        "join_armed": False, "join_busy": False, "join_clicks": 0,
        "match": {"index": 0, "id": None, "state": None,
                  "started_at": None, "ended_at": None},
        "match_events": [], **overrides,
    }


def test_sense_timeout_does_not_stick_on_a_hung_page_evaluate(monkeypatch):
    host = BrowserHost.__new__(BrowserHost)
    host._page_generation = 0
    host.game = game_state()
    host.browser = ConnectedBrowser()
    host.guard = lambda: None

    class HangingPage:
        def is_closed(self):
            return False

        async def evaluate(self, _script):
            await asyncio.Event().wait()

    host.game_page = HangingPage()
    monkeypatch.setattr(browser_module, "GAME_STATE_SENSE_TIMEOUT_S", 0.01,
                        raising=False)

    async def scenario():
        result = await asyncio.wait_for(host.sense_game_state(), timeout=0.1)
        assert result["state"] == "DISCONNECTED"
        assert result["source"] == "sense_error"

    run(scenario())


def test_late_old_page_error_does_not_overwrite_recovered_state(monkeypatch):
    host = BrowserHost.__new__(BrowserHost)
    host._page_generation = 0
    host.game = game_state()
    host.browser = ConnectedBrowser()
    host.guard = lambda: None

    class ReplacedPage:
        def is_closed(self):
            return False

        async def evaluate(self, _script):
            host._page_generation = 1
            host.game.update(state="UNKNOWN", evidence="new page recovered",
                             source="recovery")
            await asyncio.Event().wait()

    host.game_page = ReplacedPage()
    monkeypatch.setattr(browser_module, "GAME_STATE_SENSE_TIMEOUT_S", 0.01,
                        raising=False)

    result = run(host.sense_game_state())

    assert result["state"] == "UNKNOWN"
    assert result["source"] == "recovery"
    assert result["evidence"] == "new page recovered"


@pytest.mark.parametrize(("join_armed", "join_busy"), [
    (False, True), (True, False), (False, False),
])
def test_recover_page_preserves_only_an_in_flight_explicit_join(
        join_armed, join_busy):
    host = BrowserHost.__new__(BrowserHost)
    host._start_url = "https://kiomet.com/"
    host._page_generation = 0
    host.game = game_state(join_busy=join_busy, join_armed=join_armed)

    class Page:
        async def close(self, **_kwargs):
            return None

        def set_default_timeout(self, _timeout):
            return None

        async def goto(self, _url, **_kwargs):
            return None

    old_page = Page()
    host.game_page = old_page
    new_page = Page()

    async def create_background_page():
        return new_page

    async def apply_live_token():
        return True

    host.create_background_page = create_background_page
    host._apply_live_token = apply_live_token

    result = run(host.recover_page())

    assert result["result"] == "RECOVERED"
    assert host._page_generation == 1
    assert host.game["join_armed"] is (join_armed or join_busy)
    assert host.game["join_busy"] is False
    assert host.game["state"] == "UNKNOWN"


def test_recover_chromium_preserves_pending_join_and_invalidates_old_wait():
    host = BrowserHost.__new__(BrowserHost)
    host._start_url = "https://kiomet.com/"
    host._start_probe_url = "http://127.0.0.1/probe"
    host._page_generation = 4
    host.game = game_state(join_busy=True, join_armed=False)

    async def close():
        return None

    async def start(_url, _probe_url):
        return None

    async def apply_live_token():
        return True

    host.close = close
    host.start = start
    host._apply_live_token = apply_live_token

    result = run(host.recover_chromium())

    assert result["result"] == "RECOVERED"
    assert host._page_generation == 5
    assert host.game["join_armed"] is True
    assert host.game["join_busy"] is False
    assert host.game["state"] == "UNKNOWN"


def test_in_flight_join_returns_retry_when_recovery_replaces_page(monkeypatch):
    host = BrowserHost.__new__(BrowserHost)
    host._page_generation = 0
    host.game = game_state(join_armed=True)
    host.guard = lambda: None

    class Gate:
        async def dispatch(self, operation):
            return await operation()

    class Page:
        async def wait_for_selector(self, *_args, **_kwargs):
            return None

        async def click(self, *_args, **_kwargs):
            return None

    host.gate = Gate()
    host.game_page = Page()

    async def sense_game_state():
        host.game["state"] = "MENU"
        return host.game

    host.sense_game_state = sense_game_state
    original_sleep = asyncio.sleep
    sleeps = 0

    async def replace_page_on_first_sleep(_delay):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            host._page_generation += 1
            host.game["state"] = "UNKNOWN"
        else:
            await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", replace_page_on_first_sleep)

    result = run(host.enter_match())

    assert result["code"] == "RETRY_AFTER_RECOVERY"
    assert result["ok"] is False
    assert host.game["join_armed"] is True
    assert host.game["join_busy"] is False
    assert host.game["join_clicks"] == 1


def test_recovery_retry_is_not_recorded_as_platform_error():
    assert "RETRY_AFTER_RECOVERY" in JOIN_NON_ERROR_CODES
    assert "TIMEOUT" not in JOIN_NON_ERROR_CODES
