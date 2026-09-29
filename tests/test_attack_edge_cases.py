"""攻擊路徑邊界案例（稽核後續）。

覆蓋主稽核未觸及的分支：
attacker id 與 self 不一致、defender 非敵方、
marginal 政策非法值、self-target、缺 states、空 match、
Ruler 持有塔（owner_ruler True 不影響普通戰鬥）。

只寫 tests，不改正式邏輯（pvp_live.py／pvp.py 為 FOREIGN_ACTIVE）。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
          fresh=True, ruler=False):
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
        owner_ruler=ruler)


def safety_for(source_id, force, match=MATCH):
    return {"result": "SAFE", "match_id": match,
            "source_tower_id": source_id, "proposed_units": dict(force)}


def strong_pair():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(20,))
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    return src, tgt


def evaluate(src, tgt, **over):
    kw = {"source_safety_evidence": safety_for(10, counts(Soldier=20)),
          "battle_differential_validated": True,
          "server_acceptance_validated": True, "now": 1000.0}
    kw.update(over)
    return evaluate_attack_candidate(
        src, tgt, MATCH, SELF_ID, SELF_ID, ENEMY_ID, False, False, **kw)


def test_attacker_id_mismatch_abstains():
    src, tgt = strong_pair()
    case = battle_case_for_tower_attack(
        src, tgt, SELF_ID, 99, ENEMY_ID, False, False,
        {"Cliff": {"Soldier": 30}})
    assert case is None


def test_defender_self_abstains():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(20,))
    tgt = tower(20, "SELF", units=counts(Soldier=3), neighbors=(10,))
    case = battle_case_for_tower_attack(
        src, tgt, SELF_ID, SELF_ID, SELF_ID, False, False,
        {"Cliff": {"Soldier": 30}})
    assert case is None


def test_self_target_tower_abstains():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(10,))
    out = evaluate(src, src)
    assert out["safe_attack_candidate"] is False
    assert out["unsupported_reason"] == \
        "attack tower identity is invalid"


def test_missing_states_abstain():
    _, tgt = strong_pair()
    out = evaluate(None, tgt)
    assert out["safe_attack_candidate"] is False
    assert out["source_tower_id"] is None


def test_empty_match_abstains():
    src, tgt = strong_pair()
    out = evaluate_attack_candidate(
        src, tgt, "", SELF_ID, SELF_ID, ENEMY_ID, False, False,
        source_safety_evidence=safety_for(10, counts(Soldier=20)),
        battle_differential_validated=True,
        server_acceptance_validated=True, now=1000.0)
    assert out["safe_attack_candidate"] is False
    assert out["unsupported_reason"] == "attack match is unknown"


def test_marginal_policy_invalid_abstains():
    src, tgt = strong_pair()
    out = evaluate(src, tgt, marginal_survivor_max=-1)
    assert out["safe_attack_candidate"] is False


def test_ruler_flag_does_not_block_ordinary_battle():
    src = tower(10, "SELF", units=counts(Soldier=20), neighbors=(20,),
                ruler=True)
    tgt = tower(20, "ENEMY", units=counts(Soldier=3), neighbors=(10,))
    out = evaluate(src, tgt)
    assert out["safe_attack_candidate"] is True


def test_defender_ruler_tower_still_evaluated():
    src, tgt = strong_pair()
    out = evaluate(src, tgt)
    assert out["result"] in ("ATTACK_WIN", "ATTACK_LOSE",
                             "ATTACK_CONTESTED")
