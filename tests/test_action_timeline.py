"""行動時間線回歸（P1 §11）。

每次 NO_ACTION 必須有具體原因（raw_reason），
派送週期必須連到驗證結果；缺欄顯示 UNKNOWN。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from action_timeline import build_timeline, render_text


def _cycle(cycle_id, **over):
    base = {"cycle_id": cycle_id, "timestamp": 1000.0 + cycle_id,
            "match_id": "m1", "phase": "NO_SAFE_PROPOSAL",
            "candidate_count": None, "proposal": None, "preflight": None,
            "authorization": True, "gate_state": "RUNNING",
            "dispatch": None, "verification": None,
            "no_action_reason": "OTHER_EXPLICIT_REASON",
            "raw_reason": "not_in_match"}
    base.update(over)
    return base


def test_no_action_shows_concrete_reason():
    entries = build_timeline({"recent_cycles": [_cycle(1)]}, {})
    assert len(entries) == 1
    text = render_text(entries)
    assert "not_in_match" in text
    assert "NO_SAFE_PROPOSAL" in text


def test_dispatch_cycle_links_verification():
    dispatch = {"action_id": "m1:1->2:100"}
    actions = {"m1:1->2:100": {"verifier": "TARGET_CONTESTED"}}
    entries = build_timeline(
        {"recent_cycles": [_cycle(2, phase="DISPATCHED",
                                  dispatch=dispatch)]},
        actions)
    assert entries[0]["dispatched_action"] == "m1:1->2:100"
    assert entries[0]["verified"] == "TARGET_CONTESTED"
    assert "TARGET_CONTESTED" in render_text(entries)


def test_missing_fields_render_unknown():
    entries = build_timeline({"recent_cycles": [{}]}, {})
    text = render_text(entries)
    assert "UNKNOWN" in text


def test_limit_keeps_newest():
    cycles = [_cycle(i) for i in range(10)]
    entries = build_timeline({"recent_cycles": cycles}, {}, limit=3)
    assert [e["cycle_id"] for e in entries] == [7, 8, 9]


def test_empty_journal_yields_no_entries():
    assert build_timeline({}, {}) == []
    assert build_timeline(None, None) == []
    assert render_text([]) == ""


def test_journal_cycles_have_reasons():
    journal = {"recent_cycles": [
        _cycle(i, raw_reason=f"fixture-reason-{i}")
        for i in range(1, 5)]}
    entries = build_timeline(journal, {}, limit=50)
    assert len(entries) == 4
    assert all(e.get("raw_reason") or e.get("no_action_reason")
               for e in entries)


# ===== §12 欄位補全（MUSE-TIMELINE-ENRICH） =====

def test_rows_carry_kind_source_target_origin_verdict():
    dispatch = {"action_id": "m1:10->20:100"}
    actions = {"m1:10->20:100": {"verifier": "TARGET_CONTESTED",
                                 "origin": "LIVE_CONTROLLER"}}
    entries = build_timeline(
        {"recent_cycles": [_cycle(3, phase="DISPATCHED",
                                  dispatch=dispatch)]},
        actions)
    row = entries[0]
    assert row["action_kind"] == "UNKNOWN"
    assert row["source"] == 10
    assert row["target"] == 20
    assert row["origin"] == "LIVE_CONTROLLER"
    assert row["verdict"] == "TARGET_CONTESTED"
    text = render_text(entries)
    assert "10 → 20" in text
    assert "origin=LIVE_CONTROLLER" in text


def test_source_target_from_action_row_preferred():
    dispatch = {"action_id": "m1:10->20:100"}
    actions = {"m1:10->20:100": {"source": 99, "target": 88,
                                 "result": "REJECTED"}}
    entries = build_timeline(
        {"recent_cycles": [_cycle(4, phase="DISPATCHED",
                                  dispatch=dispatch)]},
        actions)
    assert entries[0]["source"] == 99
    assert entries[0]["target"] == 88
    assert entries[0]["verdict"] == "REJECTED"


def test_no_action_rows_have_unknown_fields():
    entries = build_timeline({"recent_cycles": [_cycle(5)]}, {})
    row = entries[0]
    assert row["action_kind"] == "UNKNOWN"
    assert row["origin"] == "UNKNOWN"
    assert row["verdict"] == "UNKNOWN"
    assert row["source"] is None
    assert row["target"] is None


def test_verdict_never_fabricated_without_evidence():
    dispatch = {"action_id": "m1:1->2:100"}
    actions = {"m1:1->2:100": {}}
    entries = build_timeline(
        {"recent_cycles": [_cycle(6, phase="DISPATCHED",
                                  dispatch=dispatch)]},
        actions)
    assert entries[0]["verdict"] == "UNKNOWN"
