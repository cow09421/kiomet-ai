from types import SimpleNamespace

import pytest

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import TowerUnitCounts
from kiomet_ai.pvp_live import battle_case_for_tower_attack


def many(soldier=2, shield=3):
    return TowerUnitCounts(
        units_kind="MANY", fighter=0, chopper=0, bomber=0, tank=0,
        soldier=soldier, shield=shield)


def vector(soldier=4):
    return {name: (soldier if name == "Soldier" else 0) for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Ruler", "Shell", "Emp", "Nuke")}


def states(*, source_owner="SELF", target_owner="ENEMY"):
    source = SimpleNamespace(
        owner=source_owner, unit_counts=many(8, 4),
        deployable_force=SimpleNamespace(counts=vector()))
    target = SimpleNamespace(
        owner=target_owner, unit_counts=many(), tower_type="Cliff")
    return source, target


def build(source, target, *, self_id=7, attacker_id=7, defender_id=12,
          attacker_aura=False, defender_aura=False):
    return battle_case_for_tower_attack(
        source, target, self_id, attacker_id, defender_id,
        attacker_aura, defender_aura, CAPACITIES)


@pytest.mark.parametrize(
    "source_owner,target_owner",
    [("ENEMY", "ENEMY"), ("SELF", "NEUTRAL"),
     ("UNKNOWN", "ENEMY"), ("SELF", "UNKNOWN")],
)
def test_attack_case_requires_observed_self_to_enemy_ownership(
        source_owner, target_owner):
    source, target = states(source_owner=source_owner,
                            target_owner=target_owner)

    assert build(source, target) is None


@pytest.mark.parametrize(
    "self_id,attacker_id,defender_id",
    [(True, True, 12), (7, 8, 12), (7, 7, 7), (7, None, 12),
     (None, 7, 12), (7, 7, True)],
)
def test_attack_case_requires_consistent_valid_player_ids(
        self_id, attacker_id, defender_id):
    source, target = states()

    assert build(source, target, self_id=self_id, attacker_id=attacker_id,
                 defender_id=defender_id) is None


@pytest.mark.parametrize("aura", [None, 0, 1, "false"])
def test_attack_case_requires_boolean_aura_snapshots(aura):
    source, target = states()

    assert build(source, target, attacker_aura=aura) is None
    assert build(source, target, defender_aura=aura) is None


def test_valid_observed_self_to_enemy_case_is_preserved():
    source, target = states()

    case = build(source, target, attacker_aura=True, defender_aura=False)

    assert case is not None
    assert case["self_owner_id"] == 7
    assert case["attacker_owner_id"] == 7
    assert case["defender_owner_id"] == 12
