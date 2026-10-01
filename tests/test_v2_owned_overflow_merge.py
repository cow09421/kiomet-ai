from dataclasses import replace

import pytest

from kiomet_ai.v2.sim import Scenario, UnsupportedState, step
from kiomet_ai.v2.sim.model import SimForce
from kiomet_ai.v2.sim.step import phase_offset
from test_v2_sim import empty_world


def owned_destination(state, units=(0,) * 10, capacity=None, line=False):
    capacity = capacity or (10, 10, 10, 10, 2, 4, 10, 10, 10, 10)
    return replace(state.towers[1], owner=7, units=units, capacity=capacity,
                   production=(), relation='SELF', supply_line_present=line)


def arriving(units, owner=7, relation=None, progress=255):
    return SimForce(owner, 3, 4, units, progress, False, relation,
                    terminal=True, fuel=150)


def test_owned_tank_soldier_merge_keeps_normal_in_capacity_counts():
    state = empty_world()
    dst = owned_destination(state, units=(0, 0, 0, 0, 1, 2, 0, 0, 0, 0))
    force = arriving((0, 0, 0, 0, 1, 2, 0, 0, 0, 0))

    result = step(replace(state, towers=(state.towers[0], dst), forces=(force,)))

    assert result.towers[1].units[4:6] == (2, 4)


def test_neutral_capture_clips_incoming_tank_soldier_to_owned_capacity_allowance():
    state = empty_world()
    dst = replace(state.towers[1], capacity=(10, 10, 10, 10, 2, 4, 10, 10, 10, 10))
    force = arriving((0, 0, 0, 0, 9, 18, 0, 0, 0, 0))

    result = step(replace(state, towers=(state.towers[0], dst), forces=(force,)))

    assert result.towers[1].owner == 7
    assert result.towers[1].units[4:6] == (7, 14)


def test_ordinary_combat_winner_merges_mixed_tank_soldier_survivors_with_candidate_enabled():
    state = empty_world()
    dst = replace(state.towers[1], owner=8, units=(0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
                  capacity=(10, 10, 10, 10, 2, 4, 10, 10, 10, 10),
                  production=(), relation='ENEMY', supply_line_present=None)
    force = arriving((0, 0, 0, 0, 9, 18, 0, 0, 0, 0), relation='ENEMY')

    result = step(replace(state, towers=(state.towers[0], dst), forces=(force,)),
                  scenario=Scenario(ordinary_combat=True))

    assert result.towers[1].owner == 7
    assert result.towers[1].units[4:6] == (7, 14)


def test_merge_preserves_existing_stock_above_overflow_limit_and_adds_none():
    state = empty_world()
    dst = owned_destination(state, units=(0, 0, 0, 0, 9, 15, 0, 0, 0, 0))
    force = arriving((0, 0, 0, 0, 2, 2, 0, 0, 0, 0))

    result = step(replace(state, towers=(state.towers[0], dst), forces=(force,)))

    assert result.towers[1].units[4:6] == (9, 15)


def test_unestablished_packed_limit_above_255_fails_closed():
    state = empty_world()
    dst = owned_destination(state, capacity=(10, 10, 10, 10, 251, 4, 10, 10, 10, 10))
    force = arriving((0, 0, 0, 0, 1, 0, 0, 0, 0, 0))

    with pytest.raises(UnsupportedState, match='UNKNOWN_OVERFLOW_REPRESENTATION'):
        step(replace(state, towers=(state.towers[0], dst), forces=(force,)))


@pytest.mark.parametrize(('line', 'expected'), [(False, (2, 4)), (True, None), (None, None)])
def test_owned_mobile_overflow_phase_shrinks_once_only_with_observed_no_line(line, expected):
    state = empty_world()
    capacity = (10, 10, 10, 10, 2, 4, 10, 10, 10, 10)
    dst = replace(state.towers[0], units=(0, 0, 0, 0, 3, 5, 0, 0, 0, 0),
                  capacity=capacity, production=(), supply_line_present=line)
    sequence = (119 - phase_offset(dst.id)) & 65535
    state = replace(state, world_sequence=sequence, towers=(dst,))

    if line is False:
        result = step(state)
        assert result.towers[0].units[4:6] == expected
    else:
        with pytest.raises(UnsupportedState, match='MOBILE_OVERFLOW_SUPPLY_LINE'):
            step(state)


def test_known_no_line_does_not_extend_cleanup_to_other_mobile_unit_kinds():
    state = empty_world()
    capacity = (10, 2, 10, 10, 2, 4, 10, 10, 10, 10)
    dst = replace(state.towers[0], units=(0, 3, 0, 0, 3, 5, 0, 0, 0, 0),
                  capacity=capacity, production=(), supply_line_present=False)
    sequence = (119 - phase_offset(dst.id)) & 65535

    with pytest.raises(UnsupportedState, match='MOBILE_OVERFLOW_SUPPLY_LINE'):
        step(replace(state, world_sequence=sequence, towers=(dst,)))


def test_other_unit_overflow_remains_rejected_on_friendly_merge():
    state = empty_world()
    dst = owned_destination(state, capacity=(10, 0, 10, 10, 2, 4, 10, 10, 10, 10))
    force = arriving((0, 1, 0, 0, 0, 0, 0, 0, 0, 0))

    with pytest.raises(UnsupportedState, match='REINFORCEMENT_OVERFLOW'):
        step(replace(state, towers=(state.towers[0], dst), forces=(force,)))
