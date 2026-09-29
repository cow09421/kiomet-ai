from types import SimpleNamespace

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import TowerUnitCounts
from kiomet_ai.pvp_live import (
    battle_case_for_tower_attack,
    evaluate_multi_threat,
    evaluate_source_safety,
)


UNIT_NAMES = (
    "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
    "Ruler", "Shell", "Emp", "Nuke",
)


def full_vector(**counts):
    return {name: counts.get(name, 0) for name in UNIT_NAMES}


def tower_counts(*, kind="MANY", soldier=10, shield=10,
                 single_type=None, single_count=0):
    return TowerUnitCounts(
        units_kind=kind, fighter=0, chopper=0, bomber=0, tank=0,
        soldier=soldier, shield=shield, single_unit_type=single_type,
        single_count=single_count)


def test_partial_incoming_force_cannot_be_treated_as_missing_units_zero():
    defenders = full_vector(Shield=10, Soldier=10)
    threat = [{"eta_ticks": 5, "units": {"Soldier": 1}}]

    multi = evaluate_multi_threat(
        defenders, threat, CAPACITIES, "Cliff", self_id=7, enemy_id=12)
    source = evaluate_source_safety(
        defenders, threat, CAPACITIES, "Cliff", self_id=7, enemy_id=12)

    assert multi["result"] == "UNKNOWN"
    assert source["result"] == "UNKNOWN"


def test_partial_defender_vector_cannot_be_safe_without_known_garrison():
    partial = {"Shield": 10, "Soldier": 10}

    source = evaluate_source_safety(partial, [], CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(partial, [], CAPACITIES, "Cliff", 7, 12)

    assert source["result"] == "UNKNOWN"
    assert multi["result"] == "UNKNOWN"


def test_incomplete_deployable_force_cannot_build_attack_case():
    counts = tower_counts()
    source = SimpleNamespace(
        unit_counts=counts,
        deployable_force=SimpleNamespace(counts={
            "Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0,
            "Tank": 0, "Soldier": 4,
        }))
    target = SimpleNamespace(unit_counts=counts, tower_type="Cliff")

    case = battle_case_for_tower_attack(
        source, target, 7, 7, 12, False, False, CAPACITIES)

    assert case is None


def test_single_special_unit_on_target_is_not_dropped_from_tower_case():
    source = SimpleNamespace(
        unit_counts=tower_counts(soldier=8, shield=4),
        deployable_force=SimpleNamespace(counts=full_vector(Soldier=4)))
    target = SimpleNamespace(
        unit_counts=tower_counts(kind="SINGLE", soldier=0, shield=3,
                                 single_type="Nuke", single_count=1),
        tower_type="Cliff")

    case = battle_case_for_tower_attack(
        source, target, 7, 7, 12, False, False, CAPACITIES)

    assert case is None


def test_explicit_complete_ordinary_force_vector_remains_evaluable():
    result = evaluate_multi_threat(
        full_vector(Shield=10, Soldier=10),
        [{"eta_ticks": 5, "units": full_vector(Soldier=1)}],
        CAPACITIES, "Cliff", self_id=7, enemy_id=12)

    assert result["result"] == "SAFE"
