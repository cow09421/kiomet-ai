"""儀表板真實性分類回歸（P1 §8）。

上一局資料 → LAST_MATCH；過期 → STALE；斷線 → OFFLINE；
NEXT ACTION 只有目前 match + 新鮮 cycle 才 READY。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dashboard_truth import (classify_field, label_snapshot,
                                       next_action_status)


def test_live_field():
    assert classify_field(browser_connected=True, game_state="IN_MATCH",
                          current_match_id="m1", data_match_id="m1",
                          data_age_s=2) == "LIVE"


def test_offline_when_disconnected():
    assert classify_field(browser_connected=False, game_state="IN_MATCH",
                          current_match_id="m1", data_match_id="m1",
                          data_age_s=1) == "OFFLINE"


def test_stale_field():
    assert classify_field(browser_connected=True, game_state="IN_MATCH",
                          current_match_id="m1", data_match_id="m1",
                          data_age_s=100) == "STALE"


def test_last_match_not_live():
    assert classify_field(browser_connected=True, game_state="IN_MATCH",
                          current_match_id="m2", data_match_id="m1",
                          data_age_s=1) == "LAST_MATCH"


def test_result_screen_data_is_last_match():
    assert classify_field(browser_connected=True, game_state="RESULT_SCREEN",
                          current_match_id="m1", data_match_id="m1",
                          data_age_s=1) == "LAST_MATCH"


def test_unknown_when_no_data():
    assert classify_field(browser_connected=True, game_state="IN_MATCH",
                          current_match_id="m1", has_data=False) == "UNKNOWN"
    assert classify_field(browser_connected=True, game_state="IN_MATCH",
                          current_match_id="m1", data_match_id=None) == \
        "UNKNOWN"


def _nx(**over):
    base = {"browser_connected": True, "game_state": "IN_MATCH",
            "current_match_id": "m1", "proposal": {"s": 1},
            "proposal_match_id": "m1", "proposal_cycle": 5,
            "current_cycle": 5, "proposal_age_s": 2}
    base.update(over)
    return next_action_status(**base)


def test_next_action_ready_only_current_fresh():
    assert _nx() == "READY"


def test_next_action_no_active_match():
    assert _nx(game_state="MENU") == "NO_ACTIVE_MATCH"
    assert _nx(current_match_id=None) == "NO_ACTIVE_MATCH"
    assert _nx(game_state="RESULT_SCREEN") == "NO_ACTIVE_MATCH"


def test_next_action_no_safe_proposal():
    assert _nx(proposal=None, proposal_match_id=None) == "NO_SAFE_PROPOSAL"


def test_next_action_stale_cycle_or_age():
    assert _nx(proposal_cycle=4, current_cycle=5) == "STALE"
    assert _nx(proposal_age_s=99) == "STALE"


def test_next_action_last_match():
    assert _nx(proposal_match_id="m0") == "LAST_MATCH"


def test_next_action_offline():
    assert _nx(browser_connected=False) == "OFFLINE"


def test_next_action_missing_match_binding_is_unknown():
    """有提案但缺 match 綁定 → UNKNOWN，不得 READY（GPT #166）。"""
    assert _nx(proposal_match_id=None) == "UNKNOWN"


def test_next_action_missing_cycle_binding_is_unknown():
    """缺 proposal_cycle 或 current_cycle → UNKNOWN，不得 READY。"""
    assert _nx(proposal_cycle=None) == "UNKNOWN"
    assert _nx(current_cycle=None) == "UNKNOWN"


def test_next_action_ready_requires_both_bindings_fresh():
    assert _nx(proposal_match_id="m1", proposal_cycle=5,
               current_cycle=5) == "READY"


def test_label_snapshot_full():
    snap = {"browser_connected": True, "game_state": "IN_MATCH",
            "current_match_id": "m1", "current_cycle": 5,
            "proposal": {"x": 1}, "proposal_match_id": "m1",
            "proposal_cycle": 5, "proposal_age_s": 1,
            "score": {"match_id": "m1", "age_s": 1},
            "source": {"match_id": "m1", "age_s": 1},
            "target": {"match_id": "m0", "age_s": 1},
            "world_counts": None}
    labels = label_snapshot(snap)
    assert labels["score"] == "LIVE"
    assert labels["target"] == "LAST_MATCH"
    assert labels["world_counts"] == "UNKNOWN"
    assert labels["next_action"] == "READY"


def test_label_snapshot_offline_all():
    labels = label_snapshot({"browser_connected": False})
    assert all(v == "OFFLINE" for v in labels.values())
