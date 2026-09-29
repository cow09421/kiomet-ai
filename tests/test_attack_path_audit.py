"""攻擊路徑整合稽核回歸。

鏈：battle_case_for_tower_attack → evaluate_attack_candidate
→ evaluate_attack → arbitrate ATTACK_ENEMY。
安全候選需四重合取：ROBUST_WIN＋合法形狀＋伺服器接受＋差分驗證；
任一缺失即棄權，絕不降級放行。

只寫 tests，不改正式邏輯（pvp_live.py／pvp.py 為 FOREIGN_ACTIVE）。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.pvp import arbitrate_pvp_action
from kiomet_ai.pvp_live import (battle_case_for_tower_attack,
                                evaluate_attack_candidate)

SELF_ID = 5
ENEMY_ID = 17
MATCH = "m1"


def counts(**kw):
    out = {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0,
           "Tank": 0, "Soldier": 0, "Ruler": 0, "Shell": 0,
           "Emp": 0, "Nuke": 0}
    out.update(kw)
    return out


def tower(tower_id, owner, match=MATCH, units=None, neighbors=(),
          fresh=True):
    units = units if units is not None else counts()
    state_fresh = "FRESH" if fresh else "STALE"
    return SimpleNamespace(
        tower_id=tower_id, match_id=match, owner=owner,
        neighbors=neighbors, tower_ref=1000 + tower_id,
        tower_type="Cliff",
        freshness=lambda m, now: state_fresh if m == match else "STALE",
        unit_counts=SimpleNamespace(
            units_kind="MANY",
            **{n.lower(): units.get(n, 0) for n in
               ("Shield", "Fighter", "Chopper", "Bomber", "Tank",
                "Soldier")}),
        deployable_force=SimpleNamespace(counts=dict(units)),
        deployable_force_confidence="DERIVED",
        owner_ruler=False)


def safety_for(source_id, force, match=MATCH):
    return {"result": "SAFE", "match_id": match,
            "source_tower_id": source_id, "proposed_units": dict(force)}


def strong_pair():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(20,))
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    return src, tgt


def test_full_conjunction_yields_safe_candidate():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is True
    assert out["result"] == "ATTACK_WIN"
    assert out["evaluation_status"] == "SUPPORTED"


def test_non_neighbor_enemy_abstains():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(99,))
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False
    assert out["unsupported_reason"] == \
        "enemy target is not a verified direct neighbor"


def test_stale_tower_abstains():
    # 同局但新鮮度 STALE → 走 staleness 分支
    stale_src = tower(10, "SELF", units=counts(Soldier=20),
                      neighbors=(20,), fresh=False)
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    out = evaluate_attack_candidate(
        stale_src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False


def test_empty_deployable_abstains():
    src = tower(10, "SELF", units=counts(), neighbors=(20,))
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts()),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False
    assert out["unsupported_reason"] == \
        "source deployable force is unknown or empty"


def test_source_safety_for_other_tower_abstains():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(99, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False
    assert out["unsupported_reason"] == \
        "source safety is not verified for this exact dispatch"


def test_source_safety_from_other_match_abstains():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(
            10, counts(Soldier=20), match="m0"),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False


def test_unvalidated_differential_not_safe():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=False,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False


def test_unaccepted_server_not_safe():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=False, now=1000.0)
    assert out["safe_attack_candidate"] is False


def test_marginal_win_not_safe():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0,
        marginal_survivor_max=100)
    assert out["safety_margin"] == "MARGINAL_WIN"
    assert out["safe_attack_candidate"] is False


def test_unknown_aura_abstains():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, None, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False


def test_end_to_end_candidate_reaches_arbitration():
    src, tgt = strong_pair()
    candidate = evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert candidate["safe_attack_candidate"] is True
    decision = arbitrate_pvp_action(
        defense_evaluations=[{"support_status": "SUPPORTED",
                              "tower_lost": False, "enemy_eta": 10,
                              "target_tower_id": 30}],
        attack_evaluations=[{**candidate, "safe_attack_candidate": True,
                             "target_tower_id": 20,
                             "source_tower_id": 10}],
        neutral_expansion_candidate=None)
    assert decision["action"] == "ATTACK_ENEMY"
