from dataclasses import replace
import pytest
from kiomet_ai.v2.sim import from_canonical, step, Launch, Scenario, UnsupportedState, RuntimeTimeModel
from kiomet_ai.v2.sim.model import SimForce
from kiomet_ai.v2.state import Fact
from test_v2_control import control_fixture


def empty_world():
    source=control_fixture()
    source=replace(source,forces=replace(source.forces,value=()))
    return from_canonical(source)


def test_compact_conversion_keeps_unknown_server_time_outside_simulation():
    state=empty_world()
    assert state.world_sequence==55 and state.match_epoch=='test-epoch'
    assert state.visible_rulers==((7,'tower',3),)
    assert step(state)==step(state)
    assert state.simulated_ticks==0 and step(state).simulated_ticks==1
    with pytest.raises(UnsupportedState,match='NOT_READY'):
        from_canonical(replace(control_fixture(),match_id=Fact()))


def test_tick_wrap_and_runtime_time_has_no_implicit_period():
    state=replace(empty_world(),world_sequence=65535)
    assert step(state).world_sequence==0
    with pytest.raises(UnsupportedState,match='TIME_MODEL'):
        RuntimeTimeModel().milliseconds(1)


def test_unknown_terminal_path_rejects_arrival_but_allows_current_segment():
    state=empty_world()
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False)
    moved=step(replace(state,forces=(replace(force,progress=2),)))
    assert moved.forces[0].progress==4
    arriving=replace(state,forces=(force,))  # positions differ5: required90.
    with pytest.raises(UnsupportedState,match='POST_ARRIVAL_PATH'):
        step(arriving)
    result=step(arriving,scenario=Scenario(terminal_forces=(0,)))
    assert result.forces==() and result.towers[1].owner==7
    assert result.towers[1].units[5]==3


def test_launch_is_local_only_and_rejects_unknown_or_immobile_inventory():
    state=empty_world()
    with pytest.raises(UnsupportedState,match='SHIELDS'):
        step(state,(Launch(3,4,(1,0,0,0,0,0,0,0,0,0)),))
    with pytest.raises(UnsupportedState,match='HIDDEN'):
        step(state,(Launch(3,99,(0,0,0,0,0,1,0,0,0,0)),))


def test_unknown_acceleration_near_arrival_and_opposed_combat_fail_closed():
    state=empty_world()
    units=(0,0,0,0,0,3,0,0,0,0)
    force=SimForce(7,3,4,units,70,None)
    with pytest.raises(UnsupportedState,match='ACCELERATION'):
        step(replace(state,forces=(force,)))
    with pytest.raises(UnsupportedState,match='OPPOSED'):
        step(replace(state,forces=(replace(force,progress=0,accelerated=False),SimForce(8,4,3,units,0,False))))
