"""不行動原因分類回歸（P0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.abstain_taxonomy import (REASONS, classify_reason,
                                        summarize_window, window_stats)


def test_canonical_passthrough():
    for reason in REASONS:
        assert classify_reason(reason) == reason


def test_alias_mapping():
    assert classify_reason("not_in_match") == "MATCH_TRANSITION"
    assert classify_reason("anchor_failed") == "WORLD_STALE"
    assert classify_reason("insufficient_force") == "INSUFFICIENT_UNITS"
    assert classify_reason("no_enemy") == "NO_ENEMY_TARGET"
    assert classify_reason("token_stale") == "TOKEN_INVALID"


def test_unknown_not_guessed():
    assert classify_reason("wat_happened") == "UNKNOWN"
    assert classify_reason(None) == "UNKNOWN"
    assert classify_reason("") == "UNKNOWN"


def test_no_fake_zero_proportion_empty():
    result = summarize_window([])
    assert result["total"] == 0
    assert all(v is None for v in result["proportions"].values())


def test_proportions_sum():
    result = summarize_window(["WORLD_STALE", "WORLD_STALE",
                               "NO_ENEMY_TARGET", "wat"])
    assert result["total"] == 4
    assert result["counts"]["WORLD_STALE"] == 2
    assert result["counts"]["NO_ENEMY_TARGET"] == 1
    assert result["counts"]["UNKNOWN"] == 1
    assert result["proportions"]["WORLD_STALE"] == 0.5


def test_window_stats_slicing():
    records = [{"reason": "WORLD_STALE"}] * 60 + [
        {"reason": "NO_ENEMY_TARGET"}] * 10
    stats = window_stats(records, windows=(50, 100))
    assert stats["last_50"]["total"] == 50
    assert stats["last_50"]["counts"]["NO_ENEMY_TARGET"] == 10
    assert stats["last_100"]["total"] == 70
    assert stats["match"]["total"] == 70


def test_sent_actions_excluded_from_abstains():
    records = [{"reason": "WORLD_STALE", "actions_sent": 1},
               {"reason": "WORLD_STALE", "actions_sent": 0}]
    stats = window_stats(records, windows=(50,))
    assert stats["last_50"]["total"] == 1


def test_no_fake_zero_in_window():
    records = [{"reason": "OTHER", "actions_sent": 1}]
    stats = window_stats(records, windows=(50,))
    assert stats["last_50"]["total"] == 0
    assert stats["last_50"]["proportions"]["OTHER"] is None
