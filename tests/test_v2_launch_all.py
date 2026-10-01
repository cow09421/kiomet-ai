from dataclasses import replace

import pytest

from kiomet_ai.v2.sim import LaunchAll, Scenario, UnsupportedState, step
from test_v2_sim import empty_world


def launch_state(*, kind=7, units=(0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
                 capacity=(10,) * 10, production=(), morale=True,
                 supply_line_present=None, world_sequence=55):
    state = empty_world()
    source = replace(state.towers[0], kind=kind, units=units, capacity=capacity,
                     production=production, morale=morale,
                     supply_line_present=supply_line_present)
    return replace(state, world_sequence=world_sequence,
                   towers=(source, state.towers[1]))


def test_launch_all_uses_post_production_inventory_and_initializes_new_force():
    state = launch_state(units=(0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
                         production=((5, 1),), morale=True)

    result = step(state, (LaunchAll(3, 4, terminal=True),))

    assert result.towers[0].units[5] == 0
    assert result.forces[-1].units == (0, 0, 0, 0, 0, 2, 0, 0, 0, 0)
    assert result.forces[-1].progress == 0
    assert result.forces[-1].accelerated is True
    assert result.forces[-1].fuel == 150
    assert result.forces[-1].terminal is True


def test_launch_all_materializes_after_known_overflow_cleanup():
    units = (0, 0, 0, 0, 12, 0, 0, 0, 0, 0)
    capacity = (10, 10, 10, 10, 2, 10, 10, 10, 10, 10)
    state = launch_state(units=units, capacity=capacity,
                         supply_line_present=False, world_sequence=119)

    result = step(state, (LaunchAll(3, 4, terminal=True),))

    assert result.towers[0].units[4] == 0
    assert result.forces[-1].units[4] == 11


def test_launch_all_rechecks_inventory_after_production_for_u8_overflow():
    units = (0, 0, 0, 0, 0, 255, 0, 0, 0, 0)
    capacity = (10, 10, 10, 10, 10, 300, 10, 10, 10, 10)
    state = launch_state(units=units, capacity=capacity, production=((5, 1),))

    with pytest.raises(UnsupportedState, match='INVALID_DEPLOYMENT_INVENTORY'):
        step(state, (LaunchAll(3, 4),))


@pytest.mark.parametrize('supply_line', [None, True])
def test_launch_all_refuses_due_mobile_overflow_cleanup_without_false_line(supply_line):
    state = launch_state(units=(0, 0, 0, 0, 12, 0, 0, 0, 0, 0),
                         capacity=(10, 10, 10, 10, 2, 10, 10, 10, 10, 10),
                         supply_line_present=supply_line, world_sequence=119)

    with pytest.raises(UnsupportedState, match='MOBILE_OVERFLOW_SUPPLY_LINE'):
        step(state, (LaunchAll(3, 4),))


def test_launch_all_leaves_immobile_shield_at_non_projector():
    state = launch_state(units=(6, 0, 0, 0, 0, 2, 0, 0, 0, 0))

    result = step(state, (LaunchAll(3, 4, terminal=True),))

    assert result.forces[-1].units == (0, 0, 0, 0, 0, 2, 0, 0, 0, 0)
    assert result.towers[0].units[0] == 6
    assert result.towers[0].units[5] == 0


def test_launch_all_includes_projector_shields():
    state = launch_state(kind=15, units=(6, 0, 0, 0, 0, 2, 0, 0, 0, 0))

    result = step(state, (LaunchAll(3, 4, terminal=True),))

    assert result.forces[-1].units == (6, 0, 0, 0, 0, 2, 0, 0, 0, 0)
    assert result.towers[0].units[:6] == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize('unit_index', [6, 7, 8, 9])
def test_launch_all_fails_closed_with_special_or_ruler_inventory(unit_index):
    units = [0] * 10
    units[5] = 1
    units[unit_index] = 1
    state = launch_state(units=tuple(units))

    with pytest.raises(UnsupportedState, match='SPECIAL_OR_RULER_LAUNCH'):
        step(state, (LaunchAll(3, 4),))


def test_launch_all_with_unknown_terminal_is_allowed_until_arrival():
    state = launch_state()
    result = step(state, (LaunchAll(3, 4),))
    assert result.forces[-1].terminal is None

    for _ in range(100):
        try:
            result = step(result)
        except UnsupportedState as error:
            assert 'UNKNOWN_POST_ARRIVAL_PATH' in str(error)
            break
    else:
        pytest.fail('force did not reach the adjacent destination within the bounded test loop')


@pytest.mark.parametrize('action', [
    LaunchAll(True, 4),
    LaunchAll(3, 4, terminal=1),
    LaunchAll(3, 4, owner=True),
    LaunchAll(3, 4, owner=0),
    LaunchAll(3, 4, owner=8),
])
def test_launch_all_rejects_malformed_or_foreign_action_fields(action):
    with pytest.raises(UnsupportedState):
        step(launch_state(), (action,))


@pytest.mark.parametrize('units', [
    (0,) * 9,
    (0, True, 0, 0, 0, 0, 0, 0, 0, 0),
    (0, 256, 0, 0, 0, 0, 0, 0, 0, 0),
    (0, -1, 0, 0, 0, 0, 0, 0, 0, 0),
])
def test_launch_all_rejects_malformed_source_inventory(units):
    state = launch_state(units=units)
    with pytest.raises(UnsupportedState, match='INVALID_DEPLOYMENT_INVENTORY'):
        step(state, (LaunchAll(3, 4),))


def test_launch_all_is_not_assumed_for_opponents_or_empty_deployable_inventory():
    state = launch_state(units=(6, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    with pytest.raises(UnsupportedState, match='INVALID_LAUNCH_UNITS'):
        step(state, (LaunchAll(3, 4),))
    with pytest.raises(UnsupportedState, match='OPPONENT_LAUNCH_ALL_UNSUPPORTED'):
        step(state, scenario=Scenario(opponent_launches=(LaunchAll(3, 4),)))
