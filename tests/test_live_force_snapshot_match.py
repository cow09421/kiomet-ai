"""Live force snapshots are scoped to the match in which they were read."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController


class SwitchingBrowser:
    def __init__(self):
        self.game = {"state": "IN_MATCH", "match": {"id": "match-a"}}
        self.read_calls = 0

    async def read_wasm_bytes(self, _address, length):
        self.read_calls += 1
        self.game = {"state": "IN_MATCH", "match": {"id": "match-b"}}
        return bytes(length)


def test_snapshot_is_marked_when_match_changes_during_wasm_read(tmp_path):
    browser = SwitchingBrowser()
    controller = LiveController(SimpleNamespace(root=tmp_path,
                                                browser=browser))

    snapshot = asyncio.run(controller.snapshot_collections(0x1000))

    assert browser.read_calls == 1
    assert snapshot["match_id"] == "match-a"
    assert snapshot["error"] == "match-changed-during-snapshot"


def test_snapshot_refuses_to_read_without_a_known_match(tmp_path):
    browser = SwitchingBrowser()
    browser.game = {"state": "IN_MATCH", "match": {}}
    controller = LiveController(SimpleNamespace(root=tmp_path,
                                                browser=browser))

    snapshot = asyncio.run(controller.snapshot_collections(0x1000))

    assert browser.read_calls == 0
    assert snapshot["match_id"] is None
    assert snapshot["error"] == "match-id-unknown"


def test_source_safety_rejects_snapshot_from_another_match(tmp_path):
    controller = LiveController(SimpleNamespace(root=tmp_path, browser=None))
    source = SimpleNamespace(
        match_id="match-b", tower_id=1,
        freshness=lambda _match_id, _now: "FRESH")
    snapshot = {"match_id": "match-a", "collections": {
        "inbound": {"length": 0, "entries": []}}}

    result = controller.evaluate_live_source_safety(
        "match-b", source, snapshot, {})

    assert result == {
        "result": "UNKNOWN", "reason": "source-snapshot-match-mismatch"}
