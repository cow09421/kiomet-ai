"""派送觀察缺口回歸：force_match NOT_FOUND 必須被標記。

Match m1-1790644011 的真實案例：controller 計入 sent_actions，
但 WASM 中從未出現己方部隊（force_match NOT_FOUND）。
replay 必須標記 DISPATCH_NOT_OBSERVED，不得假裝已觀察。

成功證據：NOT_FOUND → DISPATCH_NOT_OBSERVED + flag；
VERIFIED → FORCE_OBSERVED（無 flag）。
失敗證據：NOT_FOUND 被放行或誤判為已觀察。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import _check_force_observed, replay_case


def _bundle(**over):
    entry = {"ref": 9, "path": [2, 1], "owner_id": 5,
             "units": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                       "Bomber": 0, "Tank": 0, "Soldier": 12,
                       "Ruler": 0, "Shell": 0, "Emp": 0, "Nuke": 0},
             "progress": 10}
    base = {
        "action_id": "m:1->2:100", "match_id": "m",
        "force_match_source": "FORCE_MATCH_VERIFIED",
        "force_match_target": "FORCE_MATCH_VERIFIED",
        "t0": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
        "t1": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": [entry]}}},
               "target": {"collections": {"inbound": {"entries": [entry]},
                                          "outbound": {"entries": []}}}},
        "t2": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
        "t3": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
    }
    base.update(over)
    return base


def _diff(**over):
    base = {
        "action_id": "m:1->2:100", "match_id": "m",
        "source_tower": 1, "target_tower": 2, "target_type": "Cliff",
        "source_owner": "SELF",
        "before_attacker": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                            "Bomber": 0, "Tank": 0, "Soldier": 12},
        "before_defender": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                            "Bomber": 0, "Tank": 0, "Soldier": 0},
        "after_source": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                         "Bomber": 0, "Tank": 0, "Soldier": 0},
        "after_target": {"owner": "NEUTRAL",
                         "units": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                                   "Bomber": 0, "Tank": 0, "Soldier": 12}},
        "prediction": None,
    }
    base.update(over)
    return base


def test_force_match_not_found_is_flagged():
    result = _check_force_observed(
        _bundle(force_match_source="FORCE_MATCH_NOT_FOUND",
                force_match_target="FORCE_MATCH_NOT_FOUND"), 5)
    assert result["status"] == "DISPATCH_NOT_OBSERVED"
    assert result["reason"] == "force_match_not_found"


def test_force_match_verified_is_observed():
    result = _check_force_observed(_bundle(), 5)
    assert result["status"] == "FORCE_OBSERVED"


def test_force_match_derived_is_unknown():
    result = _check_force_observed(
        _bundle(force_match_source="DERIVED"), 5)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "force-match-not-verified"


def test_replay_case_flags_not_observed_dispatch():
    bundle = _bundle(force_match_source="FORCE_MATCH_NOT_FOUND",
                     force_match_target="FORCE_MATCH_NOT_FOUND")
    out = replay_case({"case_id": "x", "diff": _diff(),
                       "bundle": bundle})
    assert out["force_observed"]["status"] == "DISPATCH_NOT_OBSERVED"
    assert "force_observed:DISPATCH_NOT_OBSERVED" in out["flags"]
    assert out["status"] == "FLAGGED"


def test_replay_case_verified_dispatch_not_flagged():
    out = replay_case({"case_id": "x", "diff": _diff(),
                       "bundle": _bundle()})
    assert out["force_observed"]["status"] == "FORCE_OBSERVED"
    assert "force_observed:DISPATCH_NOT_OBSERVED" not in out["flags"]
