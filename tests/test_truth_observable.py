"""可觀測儀表板真實性路由回歸（P1 §8）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dashboard_truth import truth_from_snapshot

NOW = 1000.0


def _snap(**over):
    base = {
        "browser": {"connected": True},
        "game": {"state": "IN_MATCH", "match": {"id": "m1"}},
        "live": {"captured_at": NOW - 2},
        "anchor_summary": {"match_id": "m1"},
        "live_controller": {"cycles": 5},
        "next_action": {"source": 1, "target": 2, "match_id": "m1",
                        "cycle_id": 5},
    }
    base.update(over)
    return base


def test_truth_in_match_ready():
    labels = truth_from_snapshot(_snap(), NOW)
    assert labels["next_action"] == "READY"
    assert labels["source"] == "LIVE"
    assert labels["game_state"] == "IN_MATCH"
    assert labels["source_of_truth"] == "app.snapshot()"


def test_truth_offline_when_browser_down():
    labels = truth_from_snapshot(_snap(browser={"connected": False}), NOW)
    assert labels["next_action"] == "OFFLINE"
    assert labels["source"] == "OFFLINE"


def test_truth_menu_no_active_match():
    labels = truth_from_snapshot(
        _snap(game={"state": "MENU", "match": {"id": None}}), NOW)
    assert labels["next_action"] == "NO_ACTIVE_MATCH"


def test_truth_last_match_when_world_mismatch():
    labels = truth_from_snapshot(_snap(anchor_summary={"match_id": "m0"}), NOW)
    assert labels["world_counts"] == "LAST_MATCH"
    assert labels["world_match_id"] == "m0"


def test_truth_stale_cycle():
    labels = truth_from_snapshot(
        _snap(next_action={"source": 1, "target": 2, "match_id": "m1",
                           "cycle_id": 4}), NOW)
    assert labels["next_action"] == "STALE"


def test_truth_none_snapshot_offline():
    labels = truth_from_snapshot(None, NOW)
    assert labels["next_action"] == "OFFLINE"


def test_truth_unknown_fields_not_zero():
    labels = truth_from_snapshot(_snap(), NOW)
    assert labels["threats"] == "UNKNOWN"
    assert labels["score"] == "UNKNOWN"
