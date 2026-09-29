"""離線戰鬥重評回歸（ENEMY 目標）。

runtime 目前不產生戰鬥預測（prediction 恆為 None），replay 的離線重評
填補該缺口：以差分 sent vs before_defender 建戰案例並重評。

成功證據：攻擊方勝/防守方勝/UNKNOWN 各路徑都有明確輸出；
特殊兵種假設 0 → confidence=DERIVED。
失敗證據：離線重評編造 runtime 未記錄的預測，或特殊兵種外推。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (_enemy_id_from_bundle, _normalize_units,
                              _offline_battle_verdict, replay_case)


def _units6(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier")}
    out.update(kw)
    return out


def _units10(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier", "Ruler", "Shell", "Emp",
                          "Nuke")}
    out.update(kw)
    return out


def _diff(**over):
    base = {
        "action_id": "m:10->20:100",
        "match_id": "m",
        "source_tower": 10,
        "target_tower": 20,
        "target_type": "Cliff",
        "source_owner": "SELF",
        "before_attacker": _units6(Soldier=20),
        "before_defender": _units6(Soldier=5),
        "after_source": _units6(Soldier=0),
        "after_target": {"owner": "OTHER", "units": _units6(Soldier=0)},
        "prediction": None,
        "evaluation_status": "NOT_EVALUATED_MODEL",
        "evaluation_reason": "battle_evaluator_not_invoked",
    }
    base.update(over)
    return base


def _bundle(**over):
    entry_out = {"ref": 9, "path": [20, 10], "owner_id": 5,
                 "units": _units10(Soldier=20), "progress": 10}
    entry_enemy = {"ref": 11, "path": [20, 30], "owner_id": 17,
                   "units": _units10(Soldier=8), "progress": 5}
    base = {
        "action_id": "m:10->20:100",
        "match_id": "m",
        "force_match_source": "FORCE_MATCH_VERIFIED",
        "force_match_target": "FORCE_MATCH_VERIFIED",
        "t0": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
        "t1": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": [entry_out]}}},
               "target": {"collections": {"inbound": {"entries": [entry_out]},
                                          "outbound": {"entries": [entry_enemy]}}}},
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


def test_normalize_units_expands_sparse_to_ten():
    out = _normalize_units({"Soldier": 4, "Shield": 2})
    assert out["Soldier"] == 4 and out["Shield"] == 2
    assert out["Ruler"] == 0 and out["Nuke"] == 0
    assert len(out) == 10


def test_normalize_units_rejects_invalid_values():
    assert _normalize_units(None) is None
    assert _normalize_units({"Soldier": -1}) is None
    assert _normalize_units({"Soldier": "x"}) is None
    assert _normalize_units({"Soldier": 300}) is None


def test_enemy_id_from_bundle_prefers_target_outbound():
    bundle = _bundle()
    assert _enemy_id_from_bundle(bundle, 5) == 17


def test_enemy_id_none_when_only_self_forces():
    bundle = _bundle()
    bundle["t1"]["target"]["collections"]["outbound"]["entries"] = []
    assert _enemy_id_from_bundle(bundle, 5) is None


def test_offline_verdict_attacker_wins():
    result = _offline_battle_verdict(
        _diff(), _bundle(), 5)
    assert result["status"] == "OFFLINE_VERDICT"
    assert result["winner"] == "attacker"
    assert result["confidence"] == "DERIVED"


def test_offline_verdict_defender_wins():
    diff = _diff(before_defender=_units6(Soldier=30),
                 after_target={"owner": "OTHER",
                               "units": _units6(Soldier=25)})
    bundle = _bundle()
    bundle["t1"]["source"]["collections"]["outbound"]["entries"][0]["units"] = \
        _units10(Soldier=3)
    bundle["t1"]["target"]["collections"]["inbound"]["entries"][0]["units"] = \
        _units10(Soldier=3)
    result = _offline_battle_verdict(diff, bundle, 5)
    assert result["status"] == "OFFLINE_VERDICT"
    assert result["winner"] == "defender"


def test_offline_verdict_unknown_when_enemy_id_missing():
    bundle = _bundle()
    bundle["t1"]["target"]["collections"]["outbound"]["entries"] = []
    result = _offline_battle_verdict(_diff(), bundle, 5)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "enemy-id-unknown"


def test_offline_verdict_unknown_when_vectors_missing():
    result = _offline_battle_verdict(
        _diff(before_defender=None), _bundle(), 5)
    assert result["status"] == "UNKNOWN"


def test_offline_verdict_unknown_when_capacity_missing():
    result = _offline_battle_verdict(
        _diff(target_type="UnknownType"), _bundle(), 5)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "tower-capacity-unknown"


def test_replay_case_enemy_target_produces_offline_verdict():
    case = {"diff": _diff(), "bundle": _bundle(),
            "case_id": "m_10_to_20_100"}
    out = replay_case(case)
    assert out["battle"]["status"] == "OFFLINE_VERDICT"
    assert out["battle"]["winner"] == "attacker"
    assert out["arrival"]["status"] == "NOT_APPLICABLE_BATTLE_TARGET"
    assert out["runtime_evaluation"]["status"] == "NOT_EVALUATED_MODEL"
    assert out["runtime_prediction"] is None


def test_replay_case_enemy_target_without_self_id_skips():
    bundle = _bundle()
    bundle["force_match_source"] = "DERIVED"
    case = {"diff": _diff(), "bundle": bundle,
            "case_id": "m_10_to_20_100"}
    out = replay_case(case)
    assert out["battle"]["status"] == "SKIPPED_UNKNOWN_IDS"
