"""PvP 即時句柄測試：編號未知即 ABSTAIN、威脅／攻擊案例構建。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.force import ForceUnits, MovingForceState
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    UNIT_NAMES,
    build_real_tower_states,
)
from kiomet_ai.pvp_live import (
    PlayerIdRegistry,
    battle_case_for_tower_attack,
    threat_from_force,
)


def many(**values):
    return TowerUnitCounts(units_kind="MANY", fighter=values.get("fighter", 0),
                           chopper=values.get("chopper", 0),
                           bomber=values.get("bomber", 0),
                           tank=values.get("tank", 0),
                           soldier=values.get("soldier", 0),
                           shield=values.get("shield", 0))


def test_registry_self_unknown_until_observed():
    registry = PlayerIdRegistry()
    assert registry.self_id() is None
    registry.observe("ENEMY", 12)
    assert registry.self_id() is None
    assert registry.known_id("ENEMY", 12) is True
    assert registry.known_id("ENEMY", 13) is False
    registry.observe("SELF", 7)
    assert registry.self_id() == 7


def test_attack_case_requires_self_id():
    now = time.time()
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway", units_detail=many(fighter=4, shield=5)),
        ObservedTower(tower_id=2, tower_ref=22, owner="ENEMY",
                      tower_type="Cliff", units_detail=many(soldier=2, shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, 2),))
    states = {s.tower_id: s for s in build_real_tower_states(obs)}
    assert battle_case_for_tower_attack(
        states[1], states[2], None, 7, 12, False, False, CAPACITIES) is None
    case = battle_case_for_tower_attack(
        states[1], states[2], 7, 7, 12, False, False, CAPACITIES)
    assert case is not None
    assert case["attacker_owner_relation"] == "SELF"
    assert case["tower_capacity"] == CAPACITIES["Cliff"]


def test_threat_from_force_targets_self():
    units = ForceUnits(
        tag=0,
        counts={name: int(name == "Soldier") for name in UNIT_NAMES},
    )
    force = MovingForceState(
        match_id="m1", collection_role="INBOUND", anchor_tower_id=2,
        owner_id=12, owner_relation="ENEMY", path=(2, 9),
        current_source=9, current_destination=2, final_destination=2,
        units=units, speed_flag=0, progress=4,
        evidence_status="CANDIDATE")
    threat = threat_from_force(force, {2}, {9: (0.0, 0.0), 2: (100.0, 0.0)})
    assert threat is not None
    assert threat["target_tower_id"] == 2
    assert threat["eta_ticks"] == 126
    assert threat["confidence"] == "CANDIDATE"
    assert threat_from_force(force, {99}, None) is None


def test_special_units_rejected_in_builder():
    now = time.time()
    single = TowerUnitCounts(units_kind="SINGLE", single_unit_type="Nuke",
                             single_count=1, shield=3)
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Silo", units_detail=single),
        ObservedTower(tower_id=2, tower_ref=22, owner="ENEMY",
                      tower_type="Cliff", units_detail=many(shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, 2),))
    states = {s.tower_id: s for s in build_real_tower_states(obs)}
    # Single 來源無 deployable（觀察器維持 UNKNOWN）→ 案例 None
    assert battle_case_for_tower_attack(
        states[1], states[2], 7, 7, 12, False, False, CAPACITIES) is None
