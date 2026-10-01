from dataclasses import replace

import pytest

from kiomet_ai.v2.sim import Launch, UnsupportedState, step
from kiomet_ai.v2.sim.model import SimForce
from test_v2_sim import empty_world


SOLDIERS = (0, 0, 0, 0, 0, 1, 0, 0, 0, 0)


def test_morale_source_launch_copies_boost_and_initializes_progress_and_fuel_after_production():
    state = empty_world()
    source = replace(
        state.towers[0],
        units=(0,) * 10,
        production=((5, 1),),
        morale=True,
    )
    state = replace(state, towers=(source, state.towers[1]))

    launched = step(state, (Launch(3, 4, SOLDIERS),))

    assert launched.towers[0].units[5] == 0  # Production occurs before the launch.
    assert launched.forces == (
        SimForce(7, 3, 4, SOLDIERS, 0, True, "SELF", True, 150),
    )


def test_morale_source_newborn_keeps_boost_for_two_current_leg_ticks():
    state = empty_world()
    source = replace(state.towers[0], units=(0, 0, 0, 0, 0, 3, 0, 0, 0, 0), morale=True)
    launched = step(replace(state, towers=(source, state.towers[1])), (Launch(3, 4, SOLDIERS),))

    one_tick = step(launched)
    two_ticks = step(one_tick)

    assert one_tick.forces[0].progress == 2
    assert two_ticks.forces[0].progress == 4
    assert two_ticks.forces[0].accelerated is True
    assert (two_ticks.forces[0].source, two_ticks.forces[0].destination) == (3, 4)
    assert two_ticks.forces[0].fuel == 150


@pytest.mark.parametrize("unit_index", (6, 7, 8, 9))
def test_morale_source_does_not_allow_special_or_ruler_launches(unit_index):
    state = empty_world()
    units = tuple(1 if i == unit_index else 0 for i in range(10))
    source = replace(state.towers[0], units=units, morale=True)

    with pytest.raises(UnsupportedState, match="SPECIAL_OR_RULER_LAUNCH"):
        step(replace(state, towers=(source, state.towers[1])), (Launch(3, 4, units),))


def test_existing_accelerated_force_still_uses_shortened_arrival_threshold():
    state = empty_world()
    force = SimForce(7, 3, 4, (0, 0, 0, 0, 0, 3, 0, 0, 0, 0), 70, True,
                     "SELF", True, 150)

    accelerated = step(replace(state, forces=(force,)))
    ordinary = step(replace(state, forces=(replace(force, accelerated=False),)))

    assert accelerated.forces == ()  # 70 + 2 reaches the accelerated threshold of 72.
    assert accelerated.towers[1].owner == 7
    assert ordinary.forces[0].progress == 72
    assert ordinary.forces[0].accelerated is False
