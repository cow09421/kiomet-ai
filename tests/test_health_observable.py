"""可觀測健康路由回歸（P0 §5）。

health_from_snapshot 對真實 snapshot 形狀的轉接；
目前 GPU blocker 情境（browser disconnected）須回 FAILED。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.health import health_from_snapshot

NOW = 1000.0


def _snap(**over):
    base = {
        "state": "RUNNING",
        "mode": "live",
        "browser": {"connected": True},
        "live_controller": {"phase": "NO_SAFE_PROPOSAL", "cycles": 42,
                            "updated_at": NOW - 1},
        "game": {"state": "IN_MATCH", "match": {"id": "m1"}},
        "live": {"captured_at": NOW - 1, "sequence": 5},
    }
    base.update(over)
    return base


def test_current_blocker_browser_disconnected_is_failed():
    result = health_from_snapshot(_snap(browser={"connected": False},
                                        state="ERROR"), NOW)
    assert result["state"] == "FAILED"
    assert "browser_disconnected" in result["reasons"]


def test_healthy_snapshot():
    result = health_from_snapshot(_snap(), NOW)
    assert result["state"] == "HEALTHY"
    assert result["source"] == "app.snapshot()"


def test_stale_world_when_not_in_match():
    result = health_from_snapshot(_snap(game={"state": "MENU"}), NOW)
    assert result["state"] == "STALE"


def test_controller_cycle_stale_is_degraded():
    result = health_from_snapshot(
        _snap(live_controller={"updated_at": NOW - 999}), NOW)
    assert result["state"] == "DEGRADED"
    assert "controller_cycle_stale" in result["reasons"]


def test_paused_snapshot():
    assert health_from_snapshot(_snap(state="PAUSED"), NOW)["state"] == \
        "PAUSED"


def test_missing_browser_is_unknown_not_healthy():
    snap = _snap()
    del snap["browser"]
    result = health_from_snapshot(snap, NOW)
    assert result["state"] in ("UNKNOWN", "RECOVERING", "PAUSED", "FAILED")


def test_none_snapshot():
    result = health_from_snapshot(None, NOW)
    assert result["state"] == "FAILED"  # browser_connected None, process dead


def test_source_tag_present():
    assert health_from_snapshot(_snap(), NOW)["source"] == "app.snapshot()"
