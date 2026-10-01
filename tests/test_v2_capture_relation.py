from dataclasses import replace

import pytest

from kiomet_ai.v2.sim import Scenario, UnsupportedState, step
from kiomet_ai.v2.sim.model import SimForce
from test_v2_sim import empty_world


def arriving_force(owner=7, relation=None):
    return SimForce(owner, 3, 4, (0, 0, 0, 0, 0, 3, 0, 0, 0, 0),
                    88, False, relation, terminal=True, fuel=150)


def test_player_claim_of_empty_neutral_tower_replaces_stale_relation():
    state = empty_world()
    destination = replace(state.towers[1], relation="ENEMY")
    state = replace(state, towers=(state.towers[0], destination),
                    forces=(arriving_force(relation="SELF"),))

    result = step(state)

    assert result.towers[1].owner == state.player
    assert result.towers[1].relation == "SELF"
    assert result.towers[1].supply_line_present is False


@pytest.mark.parametrize(
    "force_relation, expected_relation",
    (("ALLY", "ALLY"), ("ENEMY", "ENEMY"), ("SELF", None), (None, None)),
)
def test_foreign_claim_uses_only_valid_arriving_relation(
    force_relation, expected_relation
):
    state = empty_world()
    destination = replace(state.towers[1], relation="ENEMY")
    state = replace(state, towers=(state.towers[0], destination),
                    forces=(arriving_force(8, force_relation),))

    result = step(state)

    assert result.towers[1].owner == 8
    assert result.towers[1].relation == expected_relation
    assert result.towers[1].supply_line_present is None


def test_combat_capture_replaces_relation_and_default_combat_guard_remains():
    state = empty_world()
    destination = replace(state.towers[1], owner=8, units=(0,) * 10,
                          relation="ENEMY", production=())
    force = arriving_force(7, "ENEMY")
    state = replace(state, towers=(state.towers[0], destination), forces=(force,))

    with pytest.raises(UnsupportedState, match="UNVERIFIED_NORMAL_COMBAT"):
        step(state)

    result = step(state, scenario=Scenario(ground_combat=True))
    assert result.towers[1].owner == state.player
    assert result.towers[1].relation == "SELF"
    assert result.towers[1].supply_line_present is False
