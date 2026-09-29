"""自主產能報告回歸（P0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from autonomy_report import build_report


def _journal():
    return {
        "cycles": 100, "sent_actions": 10, "verified_moves": 8,
        "no_safe_proposals": 90,
        "threat_state": {"match_id": "m1", "freshness": "FRESH",
                         "coverage": {"self_towers": 3}},
        "recent_cycles": [
            {"raw_reason": "not_in_match", "dispatch": None},
            {"no_action_reason": "anchor_failed", "dispatch": None},
            {"no_action_reason": "no_enemy", "dispatch": None},
            {"raw_reason": "OTHER", "dispatch": {"action_id": "x"}},
        ],
    }


def test_build_report_kpi():
    report = build_report(_journal(), [{}], now=1000.0)
    assert report["kpi"]["cycles"] == 100
    assert report["kpi"]["ACTION_RATE"] == 0.1
    assert report["generated_at"] == 1000.0


def test_abstain_windows_from_cycles():
    report = build_report(_journal(), [], now=1000.0)
    stats = report["abstain_windows"]
    assert stats["match"]["total"] == 3  # 3 abstains, 1 dispatched
    assert stats["match"]["counts"]["MATCH_TRANSITION"] == 1
    assert stats["match"]["counts"]["WORLD_STALE"] == 1
    assert stats["match"]["counts"]["NO_ENEMY_TARGET"] == 1


def test_idle_not_applicable_when_not_fresh():
    report = build_report(_journal(), [], now=1000.0)
    # world_fresh True, self_towers 3, controller_running True,
    # but in_match depends on threat match_id -> True; idle not triggered
    # since only 3 trailing idle < 10
    assert report["idle"]["status"] == "OK"


def test_no_fake_zero_empty():
    report = build_report({}, [], now=1000.0)
    assert report["kpi"]["ACTION_RATE"] is None
    assert report["abstain_windows"]["last_50"]["total"] == 0
    assert report["abstain_windows"]["last_50"]["proportions"][
        "WORLD_STALE"] is None


def test_cycle_records_count():
    assert build_report(_journal(), [], now=1.0)["cycle_records"] == 4


def test_report_source_stated():
    report = build_report(_journal(), [], now=1.0)
    assert "live_controller.json" in report["source"]
