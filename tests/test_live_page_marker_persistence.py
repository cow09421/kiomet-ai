"""The app-owned page marker survives document reloads and recovery."""
import asyncio
import json

from kiomet_ai.browser import BrowserHost


class FakePage:
    def __init__(self, marker=None):
        self.marker = marker
        self.init_scripts = []
        self.evaluations = []

    async def add_init_script(self, script):
        self.init_scripts.append(script)

    async def evaluate(self, script):
        self.evaluations.append(script)
        if script == "() => window.__kiometLiveToken ?? null":
            return self.marker
        if script.startswith("window.__kiometLiveToken = "):
            self.marker = json.loads(script.split("=", 1)[1])
            return None
        return None


def make_host(page, token="controller-token"):
    host = object.__new__(BrowserHost)
    host.game_page = page
    host._live_token = token
    return host


def test_mark_live_page_installs_persistent_and_current_document_marker():
    page = FakePage()
    host = make_host(page, token=None)

    marked = asyncio.run(host.mark_live_page("controller-token"))

    assert marked is True
    assert host._live_token == "controller-token"
    assert page.marker == "controller-token"
    assert page.init_scripts == [
        'window.__kiometLiveToken = "controller-token"']


def test_ensure_live_token_does_not_duplicate_script_when_marker_matches():
    page = FakePage(marker="controller-token")
    host = make_host(page)

    assert asyncio.run(host._ensure_live_token()) is True
    assert page.init_scripts == []


def test_ensure_live_token_restores_marker_after_document_reload():
    page = FakePage(marker=None)
    host = make_host(page)

    assert asyncio.run(host._ensure_live_token()) is True
    assert page.marker == "controller-token"
    assert page.init_scripts == [
        'window.__kiometLiveToken = "controller-token"']


def test_token_marker_fails_closed_when_page_is_unavailable():
    host = make_host(None)

    assert asyncio.run(host._ensure_live_token()) is False
    assert asyncio.run(host._apply_live_token()) is False
