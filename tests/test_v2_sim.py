from dataclasses import replace
import pytest
from kiomet_ai.v2.sim import from_canonical, step, Launch, Scenario, UnsupportedState, RuntimeTimeModel
from kiomet_ai.v2.sim.model import SimForce
from kiomet_ai.v2.state import Fact
from kiomet_ai.v2.sim.combat import fight_ground
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
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,fuel=150)
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


def test_ground_defense_consumes_damage_without_needing_future_route():
    attacker=(0,0,0,0,0,4,0,0,0,0)
    defender=(20,0,0,0,0,0,0,0,0,1)
    fight=fight_ground(attacker,defender)
    assert fight.winner=='DEFENDER' and fight.attacker==(0,)*10
    assert fight.defender[0]==16 and fight.defender[9]==1
    assert not fight.defender_ruler_lost
    state=empty_world()
    force=SimForce(8,4,3,attacker,88,False,'ENEMY')
    predicted=step(replace(state,forces=(force,)),scenario=Scenario(ground_combat=True))
    assert not predicted.forces and predicted.towers[0].units[9]==1


def test_reference_combat_reports_ruler_loss_direction_and_rejects_air():
    unit=lambda kind,n=1:tuple(n if i==kind else 0 for i in range(10))
    fight=fight_ground(unit(5),unit(9))
    assert fight.defender_ruler_lost and not fight.attacker_ruler_lost
    assert fight.winner=='DEFENDER'  # Tower wins a ground tie; death is separate.
    with pytest.raises(UnsupportedState,match='AIR'):
        fight_ground(unit(1),unit(0,10))


def test_production_precedes_launch_and_new_force_starts_at_zero():
    state=empty_world()
    source=replace(state.towers[0],units=(0,)*10,production=((5,1),),morale=False)
    state=replace(state,towers=(source,state.towers[1]))
    launched=step(state,(Launch(3,4,(0,0,0,0,0,1,0,0,0,0)),))
    assert launched.towers[0].units[5]==0
    assert launched.forces[0].progress==0 and launched.forces[0].terminal is True
    assert launched.forces[0].fuel==150
    assert step(launched).forces[0].progress==2


def test_owned_shield_overflow_decays_before_production_without_truncation():
    state=empty_world()
    tower=replace(state.towers[0],id=0,kind=19,units=(19,0,0,0,0,0,0,0,0,0),
                  capacity=(10,)*10,production=((0,1),))
    state=replace(state,world_sequence=118,towers=(tower,))
    assert step(state).towers[0].units[0]==19
    decayed=step(step(state))
    assert decayed.towers[0].units[0]==18
    # The same decrease on a Projector could launch a hidden supply line.
    with pytest.raises(UnsupportedState,match='MOBILE_OVERFLOW'):
        step(replace(state,world_sequence=119,towers=(replace(tower,kind=15),)))


def test_stationary_single_inventory_blocks_many_generation_and_preserves_unknown_mechanics():
    state=empty_world()
    tower=replace(state.towers[0],units=(2,0,0,0,0,0,0,1,0,0),production=((5,1),))
    assert step(replace(state,towers=(tower,))).towers[0].units==tower.units
    with pytest.raises(UnsupportedState,match='SPECIAL_PRODUCTION'):
        step(replace(state,towers=(replace(tower,production=((7,1),)),)))
    from kiomet_ai.v2.sim.model import unit_tuple
    from kiomet_ai.v2.state import Units
    with pytest.raises(UnsupportedState,match='INVALID_UNIT_CATEGORY'):
        unit_tuple(replace(control_fixture().towers[0].units,
            value=Units(tuple(enumerate((0,0,0,0,0,1,0,1,0,0))))))


def test_near_capacity_mobile_production_rejects_unknown_supply_line():
    state=empty_world()
    tower=replace(state.towers[0],units=(0,0,0,0,0,9,0,0,0,0),capacity=(10,)*10,
                  production=((5,1),))
    with pytest.raises(UnsupportedState,match='PRODUCTION_SUPPLY_LINE'):
        step(replace(state,towers=(tower,)))


def test_pinned_morale_bonus_changes_ground_tie_direction_as_candidate_only():
    soldiers=(0,0,0,0,0,1,0,0,0,0)
    assert fight_ground(soldiers,soldiers,attacker_morale=True).winner=='ATTACKER'
    assert fight_ground(soldiers,soldiers,defender_morale=True).winner=='DEFENDER'
    with pytest.raises(UnsupportedState,match='UNKNOWN_COMBAT_MORALE'):
        fight_ground(soldiers,soldiers,attacker_morale=None)


def test_terminal_empty_capture_accepts_shield_with_living_claiming_unit():
    state=empty_world()
    units=(1,0,0,0,0,1,0,0,0,0)
    force=SimForce(7,3,4,units,88,False,terminal=True,fuel=150)
    captured=step(replace(state,forces=(force,)))
    assert captured.towers[1].owner==7 and captured.towers[1].units==units
    with pytest.raises(UnsupportedState,match='NON_CLAIMING_FORCE'):
        step(replace(state,forces=(replace(force,units=(1,0,0,0,0,0,0,0,0,0)),)))


def test_terminal_hypothesis_does_not_turn_unknown_fuel_into_nonexpired():
    state=empty_world()
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,terminal=True)
    with pytest.raises(UnsupportedState,match='UNKNOWN_ARRIVAL_FUEL'):
        step(replace(state,forces=(force,)))
    with pytest.raises(UnsupportedState,match='EXPIRED_ARRIVAL'):
        step(replace(state,forces=(replace(force,fuel=0),)))
