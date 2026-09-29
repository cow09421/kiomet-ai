"""Many-only 乾跑排名測試：只排名、不送兵、安全門全覆蓋。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dry_rank import rank_expansion_targets, rejection_reasons
from kiomet_ai.force_units import mirror_force_units
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)


def many(**values):
    return TowerUnitCounts(units_kind="MANY", fighter=values.get("fighter", 0),
                           chopper=values.get("chopper", 0),
                           bomber=values.get("bomber", 0),
                           tank=values.get("tank", 0),
                           soldier=values.get("soldier", 0),
                           shield=values.get("shield", 0))


def make_states(match="m1", now=None):
    now = time.time() if now is None else now
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, world_x=0, world_y=0,
                      owner="SELF", owner_confidence="HIGH",
                      tower_type="Runway", units_detail=many(fighter=4, soldier=4, shield=15)),
        ObservedTower(tower_id=2, tower_ref=22, world_x=5, world_y=0,
                      owner="NEUTRAL", tower_type="Cliff",
                      units_detail=many(soldier=2, shield=3)),
        ObservedTower(tower_id=3, tower_ref=33, world_x=9, world_y=0,
                      owner="ENEMY", tower_type="Mine",
                      units_detail=many(soldier=6, shield=10)),
        ObservedTower(tower_id=4, tower_ref=44, world_x=12, world_y=0,
                      owner="SELF", tower_type="Village",
                      units_detail=many(soldier=3, shield=5)),
    )
    obs = MatchObservation(match_id=match, timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, 2), ObservedEdge(2, 3),
                                  ObservedEdge(3, 4)))
    return build_real_tower_states(obs), now


def test_ranks_self_many_to_neutral_neighbor_only():
    states, now = make_states()
    ranked = rank_expansion_targets(states, "m1", now)
    assert len(ranked) == 1
    cand = ranked[0]
    assert cand["source"] == 1 and cand["target"] == 2
    assert cand["SEND"] is False
    assert cand["source_power"] == 8
    assert cand["target_defense"] == 5
    assert cand["confidence"] == "DERIVED"


def test_enemy_and_self_targets_excluded():
    states, now = make_states()
    ranked = rank_expansion_targets(states, "m1", now)
    targets = {c["target"] for c in ranked}
    assert 3 not in targets  # ENEMY 禁止
    assert 1 not in targets  # SELF 禁止


def test_stale_unknown_single_never_ranked():
    states, now = make_states()
    assert rank_expansion_targets(states, "m2", now) == []  # 換局 STALE
    now2 = time.time()
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway",
                      units_detail=TowerUnitCounts(units_kind="SINGLE",
                                                   single_unit_type="Ruler",
                                                   single_count=1, shield=15)),
        ObservedTower(tower_id=2, tower_ref=22, owner="NEUTRAL",
                      tower_type="Cliff", units_detail=many(soldier=2, shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now2, towers=towers,
                           edges=(ObservedEdge(1, 2),))
    assert rank_expansion_targets(build_real_tower_states(obs), "m1", now2) == []


def test_never_sends_and_keeps_composition():
    states, now = make_states()
    for cand in rank_expansion_targets(states, "m1", now):
        assert cand["SEND"] is False
        assert cand["source_deployable"]["Fighter"] == 4
        assert cand["source_deployable"]["Shield"] == 0  # 非 Projector 留塔
        assert "heuristic_score" in cand  # 啟發式分數，非勝率
        assert "win_probability" not in cand
        assert cand["source_type"] == "Runway"
        assert cand["target_type"] == "Cliff"


def test_rejection_reasons_cover_gates():
    states, now = make_states()
    reasons = {(r["source"], r["target"]): r["reason"]
               for r in rejection_reasons(states, "m1", now)}
    assert reasons[(4, 3)] == "TARGET_NOT_NEUTRAL"  # ENEMY 目標
    assert rank_expansion_targets(states, "m9", now) == []
    stale = {(r["source"], r["target"]): r["reason"]
             for r in rejection_reasons(states, "m9", now)}
    assert stale[(1, None)] == "STALE"


def test_frontier_gain_and_shield_capacity_present():
    states, now = make_states()
    ranked = rank_expansion_targets(states, "m1", now)
    cand = ranked[0]
    assert cand["frontier_gain"] >= 1  # 目標 2 的鄰居含非己方塔
    assert cand["target_shield_capacity"] is None  # 缺 +45 旗標→UNKNOWN
    # 旗標接通後容量可推導：Cliff raw 30，中立無加成
    now2 = time.time()
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway", owner_ruler=True,
                      units_detail=many(fighter=4, soldier=4, shield=15)),
        ObservedTower(tower_id=2, tower_ref=22, owner="NEUTRAL",
                      tower_type="Cliff", owner_ruler=False,
                      units_detail=many(soldier=2, shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now2, towers=towers,
                           edges=(ObservedEdge(1, 2),))
    ranked2 = rank_expansion_targets(build_real_tower_states(obs), "m1", now2)
    assert ranked2[0]["target_shield_capacity"] == 30
    assert ranked2[0]["source_power"] == 8


def test_ruler_source_never_ranked():
    """含特殊兵種或缺失特殊兵種快照的來源都不進入 v0 候選。"""
    import time
    now = time.time()
    counts = TowerUnitCounts(units_kind="MANY", fighter=4, chopper=0,
                             bomber=0, tank=0, soldier=0, shield=5)
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway", units_detail=counts),
        ObservedTower(tower_id=2, tower_ref=22, owner="NEUTRAL",
                      tower_type="Cliff", units_detail=many(shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, 2),))
    states = build_real_tower_states(obs)
    # 竄改 deployable 以覆蓋正常 Many mirror 不會產生的特殊兵種。
    import dataclasses
    base = states[0].deployable_force.counts
    for special in ("Ruler", "Shell", "Emp", "Nuke"):
        poisoned = dataclasses.replace(
            states[0].deployable_force,
            counts={**base, special: 1})
        poisoned_states = (
            dataclasses.replace(states[0], deployable_force=poisoned),
            states[1])
        assert rank_expansion_targets(poisoned_states, "m1", now) == []

    missing = dataclasses.replace(
        states[0].deployable_force,
        counts={name: value for name, value in base.items()
                if name != "Shell"})
    missing_states = (
        dataclasses.replace(states[0], deployable_force=missing), states[1])
    assert rank_expansion_targets(missing_states, "m1", now) == []

    malformed = dataclasses.replace(
        states[0].deployable_force,
        counts={**base, "Emp": True})
    malformed_states = (
        dataclasses.replace(states[0], deployable_force=malformed), states[1])
    assert rank_expansion_targets(malformed_states, "m1", now) == []

    unknown = dataclasses.replace(
        states[0].deployable_force,
        counts={**base, "Mystery": 1})
    unknown_states = (
        dataclasses.replace(states[0], deployable_force=unknown), states[1])
    assert rank_expansion_targets(unknown_states, "m1", now) == []
