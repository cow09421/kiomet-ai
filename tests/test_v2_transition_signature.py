from dataclasses import replace

from kiomet_ai.v2.sim.model import SimForce
from test_v2_sim import empty_world
from tools.v2_sim_differential import signature


def test_signature_includes_complete_tower_context():
    state = empty_world()
    baseline = signature(state)
    tower = state.towers[0]
    changes = (
        replace(tower, relation="ALLY"),
        replace(tower, position=(tower.position[0] + 1, tower.position[1])),
        replace(tower, capacity=tuple(n + 1 for n in tower.capacity)),
        replace(tower, production=((5, 2),)),
        replace(tower, neighbors=(tower.neighbors[0] + 1,)),
    )

    for changed_tower in changes:
        changed = replace(state, towers=(changed_tower,) + state.towers[1:])
        assert signature(changed) != baseline


def test_signature_includes_force_acceleration_and_relation_context():
    state = empty_world()
    force = SimForce(7, 3, 4, (0, 0, 0, 0, 0, 3, 0, 0, 0, 0),
                     10, None, None)
    baseline = signature(replace(state, forces=(force,)))

    changed_acceleration = replace(force, accelerated=False)
    assert signature(replace(state, forces=(changed_acceleration,))) != baseline

    changed_relation = replace(force, relation="ENEMY")
    assert signature(replace(state, forces=(changed_relation,))) != baseline


def test_same_destination_inbound_order_is_part_of_signature():
    state = empty_world()
    first = SimForce(7, 3, 4, (0, 0, 0, 0, 0, 2, 0, 0, 0, 0),
                     10, False, "SELF")
    second = SimForce(8, 3, 4, (0, 0, 0, 0, 0, 4, 0, 0, 0, 0),
                      10, False, "ENEMY")

    forward = signature(replace(state, forces=(first, second)))
    reversed_order = signature(replace(state, forces=(second, first)))

    assert forward["forces"] == reversed_order["forces"]
    assert forward["force_context"] == reversed_order["force_context"]
    assert forward["inbound_order"] != reversed_order["inbound_order"]
    assert forward != reversed_order


def test_cross_destination_force_order_does_not_change_signature():
    state = empty_world()
    first = SimForce(7, 3, 4, (0, 0, 0, 0, 0, 2, 0, 0, 0, 0),
                     10, False, "SELF")
    second = SimForce(8, 4, 3, (0, 0, 0, 0, 0, 4, 0, 0, 0, 0),
                      10, True, "ENEMY")

    assert signature(replace(state, forces=(first, second))) == signature(
        replace(state, forces=(second, first))
    )


def test_unknown_supply_lines_remain_absent_from_signature():
    state = empty_world()
    state = replace(state, towers=tuple(
        replace(tower, supply_line_present=None) for tower in state.towers
    ))

    assert "supply_lines" not in signature(state)
