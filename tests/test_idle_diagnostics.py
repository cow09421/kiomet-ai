"""防發呆診斷回歸（P0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.idle_diagnostics import evaluate

ACTIVE = {"in_match": True, "world_fresh": True, "self_towers": 3,
          "controller_running": True}


def _idle(n):
    return [{"actions_sent": 0} for _ in range(n)]


def test_idle_10_triggers_diagnostic():
    result = evaluate(ACTIVE, _idle(10))
    assert result["status"] == "IDLE_DIAGNOSTIC"
    assert result["idle_cycles"] == 10


def test_idle_30_triggers_stalled():
    result = evaluate(ACTIVE, _idle(30))
    assert result["status"] == "AUTONOMY_STALLED"
    assert result["stalled"] is True


def test_actions_present_is_ok():
    cycles = _idle(40) + [{"actions_sent": 1}]
    assert evaluate(ACTIVE, cycles)["status"] == "OK"


def test_under_10_is_ok():
    assert evaluate(ACTIVE, _idle(9))["status"] == "OK"


def test_not_in_match_not_applicable():
    result = evaluate({**ACTIVE, "in_match": False}, _idle(50))
    assert result["status"] == "NOT_APPLICABLE"
    assert "in_match" in result["missing"]


def test_no_self_towers_not_applicable():
    result = evaluate({**ACTIVE, "self_towers": 0}, _idle(50))
    assert result["status"] == "NOT_APPLICABLE"


def test_not_applicable_includes_missing():
    result = evaluate({}, _idle(50))
    assert set(result["missing"]) == {"in_match", "world_fresh",
                                      "self_towers", "controller_running"}


def test_kinds_unknown_not_fake_zero():
    result = evaluate(ACTIVE, _idle(12))
    for kind in ("EXPAND", "ATTACK", "REINFORCE"):
        assert result["kinds"][kind]["candidate_count"] == "UNKNOWN"


def test_kinds_from_diagnostics():
    ctx = {**ACTIVE, "kinds": {"EXPAND": {
        "candidate_count": 0, "first_rejection_reason": "PATH_UNKNOWN",
        "next_required_data": "adjacency"}}}
    result = evaluate(ctx, _idle(10))
    assert result["kinds"]["EXPAND"]["candidate_count"] == 0
    assert result["kinds"]["EXPAND"]["first_rejection_reason"] == \
        "PATH_UNKNOWN"
    assert result["kinds"]["ATTACK"]["candidate_count"] == "UNKNOWN"


def test_trailing_idle_stops_at_action():
    cycles = _idle(5) + [{"actions_sent": 1}] + _idle(10)
    result = evaluate(ACTIVE, cycles)
    assert result["idle_cycles"] == 10
    assert result["status"] == "IDLE_DIAGNOSTIC"
