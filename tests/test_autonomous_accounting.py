"""自主行動統計回歸（P1-E）。

單一統計邏輯，區分 manual API／LIVE_CONTROLLER／UNKNOWN origin，
輸出中立擴張／增援／對敵攻擊／防守／失敗／棄權／未知驗證。
避免 Dashboard 和 journal 各算各的。

成功證據：真實索引 19 筆全自主、0 人工；18 verified＋1 unknown；
4 筆新局中立擴張；無 double counting。
失敗證據：origin 混算、種類重複計數、UNKNOWN 被歸類。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from evidence_index import build_index, summarize_autonomy

ROOT = Path("E:/SteamLibrary/kiomet")

requires_runtime = pytest.mark.skipif(
    not (ROOT / "runtime/logs/live_actions.jsonl").exists(),
    reason="runtime evidence not present (gitignored)")


def _action(action_id, origin="LIVE_CONTROLLER", verdict="TARGET_CONTESTED",
            match_id="m1"):
    return {"action_id": action_id, "match_id": match_id, "origin": origin,
            "source": 1, "target": 2, "owner_relation": None,
            "verdict": verdict, "timestamp": 1.0,
            "evidence_path": "test"}


def _diff(action_id, relation):
    return {"action_id": action_id, "match_id": "m1", "source": 1,
            "target": 2, "owner_relation": relation,
            "verdict": "NOT_APPLICABLE_NEUTRAL_TARGET", "prediction": None,
            "timestamp": None, "evidence_path": "test"}


def test_origins_separated():
    index = {"actions": [
        _action("a1"),
        _action("a2", origin="MANUAL_PROBE"),
        _action("a3", origin=None),
    ], "differentials": []}
    out = summarize_autonomy(index)
    assert out["autonomous_total"] == 1
    assert out["manual_total"] == 1
    assert out["unknown_origin_total"] == 1


def test_kinds_classified_by_target_relation():
    index = {"actions": [
        _action("a1"), _action("a2"), _action("a3"), _action("a4"),
    ], "differentials": [
        _diff("a1", "NEUTRAL"), _diff("a2", "SELF"),
        _diff("a3", "ENEMY"),
    ]}
    out = summarize_autonomy(index)
    assert out["autonomous_neutral_expansion"] == 1
    assert out["autonomous_reinforcement"] == 1
    assert out["autonomous_enemy_attack"] == 1
    assert out["autonomous_unclassified"] == 1
    assert out["autonomous_defense"] == 0


def test_explicit_attack_action_kind_classifies_without_differential():
    attack = {**_action("attack-1"), "action_kind": "ATTACK_ENEMY"}
    out = summarize_autonomy({"actions": [attack], "differentials": []})
    assert out["autonomous_enemy_attack"] == 1
    assert out["autonomous_unclassified"] == 0
    assert out["by_action"]["attack-1"]["kind"] == "enemy_attack"


def test_verdict_buckets_no_double_count():
    index = {"actions": [
        _action("a1", verdict="TARGET_CONTESTED"),
        _action("a2", verdict="TARGET_CAPTURED"),
        _action("a3", verdict="UNKNOWN"),
        _action("a4", verdict="ACTION_TIMEOUT"),
    ], "differentials": []}
    out = summarize_autonomy(index)
    assert out["verified"] == 2
    assert out["unknown_verifier"] == 1
    assert out["failed"] == 1
    assert (out["verified"] + out["unknown_verifier"] + out["failed"]
            == out["autonomous_total"] == 4)


def test_abstained_comes_from_journal_cycles():
    from evidence_index import summarize_autonomy
    index = {"actions": [_action("a1")], "differentials": [],
             "journal": {"no_safe_proposals": 41,
                         "abstain_reasons": {
                             "OTHER_EXPLICIT_REASON": 40,
                             "no_candidate": 1}}}
    out = summarize_autonomy(index)
    assert out["abstained"] == 41
    assert out["abstain_reasons"] == {"OTHER_EXPLICIT_REASON": 40,
                                      "no_candidate": 1}


def test_abstained_zero_without_journal():
    from evidence_index import summarize_autonomy
    out = summarize_autonomy({"actions": [_action("a1")],
                              "differentials": []})
    assert out["abstained"] == 0


@requires_runtime
def test_real_abstained_matches_journal():
    index = build_index(ROOT)
    out = summarize_autonomy(index)
    assert out["autonomous_total"] == 19
    assert out["manual_total"] == 0
    assert out["unknown_origin_total"] == 0
    assert out["verified"] == 18
    assert out["unknown_verifier"] == 1
    assert out["failed"] == 0
    assert out["autonomous_neutral_expansion"] == 13
    assert out["autonomous_unclassified"] == 6
    assert out["autonomous_reinforcement"] == 0
    assert out["autonomous_enemy_attack"] == 0
    assert out["autonomous_defense"] == 0


@requires_runtime
def test_real_by_action_entries():
    index = build_index(ROOT)
    out = summarize_autonomy(index)
    assert len(out["by_action"]) == 19
    kinds = {v["kind"] for v in out["by_action"].values()}
    assert kinds <= {"neutral_expansion", "reinforcement", "enemy_attack",
                     "unclassified"}
