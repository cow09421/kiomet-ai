"""Round 11 安全閘門測試：有效性權杖、原子保留、來源安全、多威脅。

覆盖 GPT 红队关键缺口（静态，离线可测）。
"""
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.action_validity import (
    ReservationBoard,
    build_token,
    tower_state_version,
    validate_token,
)
from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)
from kiomet_ai.pvp_live import evaluate_multi_threat, evaluate_source_safety


class FakeState:
    def __init__(self, tower_id, ref, kind, owner, ruler, counts):
        self.tower_id = tower_id
        self.tower_ref = ref
        self.units_kind = kind
        self.owner = owner
        self.owner_ruler = ruler
        self.unit_counts = counts


def counts(**values):
    full = {"fighter": 0, "chopper": 0, "bomber": 0, "tank": 0,
            "soldier": 0, "shield": 0}
    full.update(values)
    return full


def pvp_units(**values):
    full = {name: 0 for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Ruler", "Shell", "Emp", "Nuke")}
    full.update(values)
    return full


DEPLOYABLE = {"Shield": 5, "Soldier": 4}


def test_stale_proposal_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4, shield=5))
    tgt = FakeState(2, 22, "MANY", "NEUTRAL", False, counts(shield=3))
    token = build_token("m1", 7, 100.0, 101.0, src, tgt, [0, 1.0, 2.0],
                        deployable_counts=DEPLOYABLE)
    assert validate_token(token, "m1", 100.0, 101.0, src, tgt,
                          [0, 1.0, 2.0], current_cycle_id=7,
                          current_deployable_counts=DEPLOYABLE) == "OK"
    assert validate_token(token, "m2", 100.0, 101.0, src, tgt,
                          [0, 1.0, 2.0], current_cycle_id=7,
                          current_deployable_counts=DEPLOYABLE).startswith("STALE_PROPOSAL")


def test_cycle_transition_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 7, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)

    result = validate_token(token, "m1", 100.0, 101.0, src, None, None,
                            current_cycle_id=8,
                            current_deployable_counts=DEPLOYABLE)

    assert result == "STALE_PROPOSAL:cycle-changed"


def test_cycle_id_is_required_at_validation():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 7, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)

    assert validate_token(token, "m1", 100.0, 101.0, src, None,
                          None) == "STALE_PROPOSAL:cycle-unknown"


def test_unknown_or_boolean_token_cycle_is_rejected():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", None, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)

    assert validate_token(token, "m1", 100.0, 101.0, src, None,
                          None, current_cycle_id=7) == "STALE_PROPOSAL:cycle-unknown"
    assert validate_token(build_token("m1", True, 100.0, 101.0, src, None, None,
                                     deployable_counts=DEPLOYABLE),
                          "m1", 100.0, 101.0, src, None,
                          None, current_cycle_id=1,
                          current_deployable_counts=DEPLOYABLE) == "STALE_PROPOSAL:cycle-unknown"


def test_match_transition_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 1, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)
    assert validate_token(token, "m9", 100.0, 101.0, src, None,
                          None, current_cycle_id=1,
                          current_deployable_counts=DEPLOYABLE).startswith("STALE_PROPOSAL")


def test_camera_stale_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 1, 100.0, 101.0, src, None, [0, 1.0, 2.0],
                        deployable_counts=DEPLOYABLE)
    assert validate_token(token, "m1", 100.0, 101.0, src, None,
                          [0, 5.0, 2.0], current_cycle_id=1,
                          current_deployable_counts=DEPLOYABLE).startswith("STALE_PROPOSAL")


def test_aura_stale_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 1, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)
    src2 = FakeState(1, 11, "MANY", "SELF", False, counts(soldier=4))
    assert validate_token(token, "m1", 100.0, 101.0, src2, None,
                          None, current_cycle_id=1,
                          current_deployable_counts=DEPLOYABLE).startswith("STALE_PROPOSAL")


def test_owner_flip_rejection():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    tgt = FakeState(2, 22, "MANY", "NEUTRAL", False, counts(shield=3))
    token = build_token("m1", 1, 100.0, 101.0, src, tgt, None,
                        deployable_counts=DEPLOYABLE)
    tgt2 = FakeState(2, 22, "MANY", "ENEMY", False, counts(shield=3))
    assert validate_token(token, "m1", 100.0, 101.0, src, tgt2,
                          None, current_cycle_id=1,
                          current_deployable_counts=DEPLOYABLE).startswith("STALE_PROPOSAL")


def test_deployable_change_invalidates_token():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4, shield=5))
    token = build_token("m1", 7, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)

    result = validate_token(
        token, "m1", 100.0, 101.0, src, None, None,
        current_cycle_id=7,
        current_deployable_counts={"Shield": 5, "Soldier": 3})

    assert result == "STALE_PROPOSAL:deployable-changed"


def test_dataclass_tower_unit_changes_invalidate_state_token():
    def state(tower_id, owner, unit_counts):
        return SimpleNamespace(
            tower_id=tower_id, tower_ref=tower_id * 10,
            units_kind=unit_counts.units_kind, unit_counts=unit_counts,
            owner=owner, owner_ruler=False)

    source_counts = TowerUnitCounts(
        units_kind="MANY", shield=5, fighter=2, chopper=0,
        bomber=0, tank=0, soldier=4)
    target_counts = TowerUnitCounts(
        units_kind="SINGLE", single_unit_type="Nuke", single_count=1)
    source = state(1, "SELF", source_counts)
    target = state(2, "NEUTRAL", target_counts)
    token = build_token("m1", 7, 100.0, 101.0, source, target, None,
                        deployable_counts=DEPLOYABLE)

    changed_source = state(1, "SELF", replace(source_counts, soldier=3))
    source_result = validate_token(
        token, "m1", 100.0, 101.0, changed_source, target, None,
        current_cycle_id=7, current_deployable_counts=DEPLOYABLE)
    assert source_result == "STALE_PROPOSAL:source-changed"

    changed_target = state(2, "NEUTRAL",
                           replace(target_counts, single_count=2))
    target_result = validate_token(
        token, "m1", 100.0, 101.0, source, changed_target, None,
        current_cycle_id=7, current_deployable_counts=DEPLOYABLE)
    assert target_result == "STALE_PROPOSAL:target-changed"


def test_deployable_snapshot_is_required_and_validated():
    src = FakeState(1, 11, "MANY", "SELF", True, counts(soldier=4))
    token = build_token("m1", 7, 100.0, 101.0, src, None, None,
                        deployable_counts=DEPLOYABLE)
    malformed = build_token("m1", 7, 100.0, 101.0, src, None, None,
                            deployable_counts={"Soldier": True})

    missing = validate_token(token, "m1", 100.0, 101.0, src, None, None,
                             current_cycle_id=7)
    missing_token_snapshot = validate_token(
        malformed, "m1", 100.0, 101.0, src, None, None,
        current_cycle_id=7, current_deployable_counts=DEPLOYABLE)

    assert missing == "STALE_PROPOSAL:deployable-unknown"
    assert missing_token_snapshot == "STALE_PROPOSAL:deployable-unknown"


def test_double_spend_prevention():
    board = ReservationBoard()
    assert board.reserve("a1", 1, 2) is None
    assert board.reserve("a2", 1, 3) == "RESOURCE_RESERVED:source"
    assert board.reserve("a2", 4, 2) == "RESOURCE_RESERVED:target"
    board.release("a1")
    assert board.reserve("a2", 1, 3) is None


def test_source_reserved_action():
    board = ReservationBoard()
    board.reserve("a1", 1, 2)
    assert board.holder(1) == "a1"
    assert board.holder(9) is None


def test_source_safety_gate():
    defenders = pvp_units(Shield=10, Soldier=4)
    assert evaluate_source_safety(defenders, [], CAPACITIES, "Cliff")["result"] == "SAFE"
    assert evaluate_source_safety(None, [], CAPACITIES, "Cliff")["result"] == "UNKNOWN"
    assert evaluate_multi_threat(defenders, [], CAPACITIES, "Cliff", 7, 12)["result"] == "SAFE"
    weak = pvp_units(Soldier=1)
    threat = [{"eta_ticks": 5, "units": pvp_units(Soldier=8)}]
    result = evaluate_source_safety(weak, threat, CAPACITIES, "Cliff", 7, 12)
    assert result["result"] in ("UNSAFE", "UNKNOWN")


def test_source_safety_unknown_ids_abstain():
    defenders = pvp_units(Shield=10, Soldier=4)
    threat = [{"eta_ticks": 5, "units": pvp_units(Soldier=8)}]
    result = evaluate_source_safety(defenders, threat, CAPACITIES, "Cliff")
    assert result["result"] == "UNKNOWN"


def test_multi_threat_sequential():
    defenders = pvp_units(Shield=10, Soldier=10)
    threats = [
        {"eta_ticks": 5, "units": pvp_units(Soldier=2)},
        {"eta_ticks": 9, "units": pvp_units(Soldier=2)},
    ]
    result = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert result["result"] in ("SAFE", "UNSAFE", "UNKNOWN")


def test_same_tick_threat_rejection():
    defenders = pvp_units(Shield=10, Soldier=10)
    threats = [
        {"eta_ticks": 5, "units": pvp_units(Soldier=2)},
        {"eta_ticks": 5, "units": pvp_units(Soldier=2)},
    ]
    result = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "UNSUPPORTED_TEMPORAL_CASE"


def test_unknown_never_becomes_zero():
    defenders = {"Shield": None, "Fighter": 0, "Chopper": 0,
                 "Bomber": 0, "Tank": 0, "Soldier": 4}
    assert evaluate_multi_threat(defenders, [], CAPACITIES, "Cliff", 7, 12)["result"] == "UNKNOWN"
    assert evaluate_source_safety({"Shield": 0}, [], CAPACITIES, "NoSuchType")["result"] == "UNKNOWN"
