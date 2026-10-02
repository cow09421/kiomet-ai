from dataclasses import replace
import json
from pathlib import Path
import pytest
from kiomet_ai.v2.sim import from_canonical, step, Launch, Scenario, UnsupportedState, RuntimeTimeModel
from kiomet_ai.v2.sim.model import SimForce, SimTower, SimulationState
from kiomet_ai.v2.state import Fact
from kiomet_ai.v2.sim.combat import fight_ground, fight_ordinary
from test_v2_control import control_fixture
from tools.v2_sim_differential import input_has_potential_event, signature
from kiomet_ai.v2.sim.step import phase


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
    soldiers=(0,0,0,0,0,2,0,0,0,0)
    assert fight_ground(soldiers,soldiers,attacker_morale=True).winner=='ATTACKER'
    assert fight_ground(soldiers,soldiers,defender_morale=True).winner=='DEFENDER'
    with pytest.raises(UnsupportedState,match='UNKNOWN_COMBAT_MORALE'):
        fight_ground(soldiers,soldiers,attacker_morale=None)


@pytest.mark.parametrize('count,survivors',[(1,0),(2,1),(6,3),(12,3)])
def test_ground_morale_half_headcount_is_capped_at_three(count,survivors):
    soldiers=(0,0,0,0,0,count,0,0,0,0)
    attack=fight_ground(soldiers,soldiers,attacker_morale=True)
    defend=fight_ground(soldiers,soldiers,defender_morale=True)
    assert attack.attacker[5]==survivors and not any(attack.defender)
    assert defend.defender[5]==survivors and not any(defend.attacker)


def test_retained_daf_ground_defense_candidate_consumes_one_shield():
    # Real before seq125/tick23737: Force4Soldier vs Barracks Shield20+Soldier12.
    # This regression records the local event, not a claim of external isolation.
    attacker=(0,0,0,0,0,4,0,0,0,0)
    defender=(20,0,0,0,0,12,0,0,0,0)
    result=fight_ground(attacker,defender,defender_morale=True)
    assert result.winner=='DEFENDER' and not any(result.attacker)
    assert result.defender==(19,0,0,0,0,12,0,0,0,0)


@pytest.mark.parametrize('fixture',['v2_ground_daf23737.json','v2_ground_7d46518.json'])
def test_retained_complete_ground_transition_matches_all_visible_state(fixture):
    receipt=json.loads((Path(__file__).parent/'fixtures'/fixture).read_text())
    data=receipt['input']
    towers=tuple(SimTower(**{key:tuple(tuple(p) for p in value) if key=='production'
                   else tuple(value) if key in ('units','capacity','neighbors','position') else value
                   for key,value in row.items()}) for row in data.pop('towers'))
    forces=tuple(SimForce(**{**row,'units':tuple(row['units'])}) for row in data.pop('forces'))
    state=SimulationState(**data,towers=towers,forces=forces)
    with pytest.raises(UnsupportedState,match='UNVERIFIED_NORMAL_COMBAT'):
        step(state)  # One development regression does not enable combat globally.
    result=step(state,scenario=Scenario(ground_combat=True))
    actual={'world_sequence':result.world_sequence,
            'towers':[(t.id,t.owner,t.kind,t.units,t.delay,t.morale) for t in result.towers],
            'forces':sorted((f.owner,f.source,f.destination,f.units,f.progress) for f in result.forces),
            'rulers':sorted(result.visible_rulers)}
    assert json.loads(json.dumps(actual))==receipt['expected']
    wider=step(state,scenario=Scenario(ordinary_combat=True))
    assert wider==result
    # Independently pinned narrow formula, still an explicit scenario: these
    # retained development receipts do not prove external-action isolation.
    narrow=step(state,scenario=Scenario(shield_retaining_combat=True))
    assert narrow==result


def test_ordinary_bomber_air_damage_to_surface_and_air_targets():
    bomber=(0,0,0,1,0,0,0,0,0,0)
    shield=(4,0,0,0,0,0,0,0,0,0)
    fighter=(0,1,0,0,0,0,0,0,0,0)
    assert fight_ordinary(bomber,shield,(4,)*10).winner=='ATTACKER'
    air=fight_ordinary(bomber,fighter,(0,)*10)
    assert air.winner=='DEFENDER' and air.defender==fighter and not any(air.attacker)
    with pytest.raises(UnsupportedState,match='AIR_OR_SPECIAL'):
        fight_ground(bomber,shield)


def test_ordinary_tower_aircraft_field_depends_on_overflow_capacity():
    attacker=(0,1,0,0,0,0,0,0,0,0)
    defender=(0,2,0,0,0,0,0,0,0,0)
    housed=fight_ordinary(attacker,defender,(2,)*10)
    overflow=fight_ordinary(attacker,defender,(0,)*10)
    assert housed.winner=='ATTACKER' and housed.attacker==attacker
    assert overflow.winner=='DEFENDER' and overflow.defender[1]==1
    with pytest.raises(UnsupportedState,match='UNKNOWN_COMBAT_CAPACITY'):
        fight_ordinary(attacker,defender,None)
    with pytest.raises(UnsupportedState,match='SPECIAL_COMBAT'):
        fight_ordinary((0,0,0,0,0,0,1,0,0,0),defender,(2,)*10)


def test_event_selection_rejects_stationary_capacity_and_single_blocked_ticks():
    state=empty_world()
    tower=replace(state.towers[0],units=(10,0,0,0,0,0,0,0,0,0),
                  capacity=(10,)*10,production=((0,1),))
    capped=replace(state,towers=(tower,))
    assert not input_has_potential_event(capped)
    assert step(capped).towers==capped.towers
    blocked=replace(tower,units=(0,0,0,0,0,0,0,0,0,1),production=((5,1),))
    assert not input_has_potential_event(replace(state,towers=(blocked,)))
    producing=replace(tower,units=(9,0,0,0,0,0,0,0,0,0))
    assert input_has_potential_event(replace(state,towers=(producing,)))


def test_event_selection_keeps_possible_mobile_supply_line_for_explicit_rejection():
    state=empty_world()
    tower=replace(state.towers[0],units=(0,0,0,0,0,10,0,0,0,0),
                  capacity=(10,)*10,production=((5,1),))
    possible=replace(state,towers=(tower,))
    assert input_has_potential_event(possible)
    with pytest.raises(UnsupportedState,match='PRODUCTION_SUPPLY_LINE'):
        step(possible)


def test_cached_phase_preserves_chunk_coordinates_and_u16_wrap():
    for x in (0,15,16,511):
        for y in (0,15,16,511):
            for tick in (0,1,65535):
                assert phase(tick,x|(y<<16))==(tick+(x>>4)+((y>>4)<<8))&65535
    state=empty_world()
    with pytest.raises(UnsupportedState,match='DUPLICATE_TOWER_IDS'):
        step(replace(state,towers=(state.towers[0],state.towers[0])))


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


def test_terminal_friendly_arrival_requires_independent_no_supply_line_premise():
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,)*10,production=(),relation='SELF')
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,terminal=True,fuel=150)
    state=replace(state,towers=(state.towers[0],destination),forces=(force,))
    with pytest.raises(UnsupportedState,match='UNKNOWN_REINFORCEMENT_SUPPLY_LINE'):
        step(state)
    with pytest.raises(UnsupportedState,match='UNKNOWN_REINFORCEMENT_SUPPLY_LINE'):
        step(state,scenario=Scenario(terminal_forces=(0,)))
    result=step(state,scenario=Scenario(no_supply_line_towers=(4,)))
    assert not result.forces and result.towers[1].units[5]==3
    with pytest.raises(UnsupportedState,match='INVALID_SUPPLY_LINE_SCENARIO'):
        step(state,scenario=Scenario(no_supply_line_towers=(99,)))


@pytest.mark.parametrize('fuel',[None,0,150])
def test_observed_no_line_terminal_many_merge_ignores_only_arrival_fuel(fuel):
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,0,0,0,0,19,0,0,0,0),
        capacity=(10,)*10,production=(),relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,(0,0,0,0,0,4,0,0,0,0),88,False,
        relation='SELF',terminal=True,fuel=fuel)
    result=step(replace(state,towers=(state.towers[0],destination),forces=(force,)))
    assert not result.forces
    assert result.towers[1].units==(0,0,0,0,0,20,0,0,0,0)


def test_observed_no_line_merge_keeps_negative_fuel_invalid():
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,)*10,production=(),
        relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,
        relation='SELF',terminal=True,fuel=-1)
    with pytest.raises(UnsupportedState,match='EXPIRED_ARRIVAL'):
        step(replace(state,towers=(state.towers[0],destination),forces=(force,)))


@pytest.mark.parametrize('fuel',[None,0,150])
def test_ground_many_merge_can_include_shields_tank_and_soldiers(fuel):
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,)*10,production=(),
        relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,(2,0,0,0,1,3,0,0,0,0),89,False,
        relation='SELF',terminal=True,fuel=fuel)
    result=step(replace(state,towers=(state.towers[0],destination),forces=(force,)))
    assert not result.forces
    assert result.towers[1].units==(2,0,0,0,1,3,0,0,0,0)


def test_scenario_terminal_force_annotation_unlocks_only_the_existing_terminal_gate():
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,)*10,production=(),
        relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,
        relation='SELF',terminal=None,fuel=None)
    result=step(replace(state,towers=(state.towers[0],destination),forces=(force,)),
                scenario=Scenario(terminal_forces=(0,)))
    assert not result.forces and result.towers[1].units[5]==3


def test_merge_fuel_exception_does_not_use_scenario_line_hypothesis_or_cover_other_arrivals():
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=(0,)*10,production=(),
        relation='SELF',supply_line_present=None)
    unknown_fuel=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,
        relation='SELF',terminal=True,fuel=None)
    no_line_scenario=Scenario(no_supply_line_towers=(4,))
    with pytest.raises(UnsupportedState,match='UNKNOWN_ARRIVAL_FUEL'):
        step(replace(state,towers=(state.towers[0],destination),forces=(unknown_fuel,)),
             scenario=no_line_scenario)
    with pytest.raises(UnsupportedState,match='EXPIRED_ARRIVAL'):
        step(replace(state,towers=(state.towers[0],destination),forces=(replace(unknown_fuel,fuel=0),)),
             scenario=no_line_scenario)

    explicit_line=replace(destination,supply_line_present=True)
    with pytest.raises(UnsupportedState,match='UNKNOWN_ARRIVAL_FUEL'):
        step(replace(state,towers=(state.towers[0],explicit_line),forces=(unknown_fuel,)),
             scenario=no_line_scenario)
    with pytest.raises(UnsupportedState,match='UNSUPPORTED_REINFORCEMENT_SUPPLY_LINE'):
        step(replace(state,towers=(state.towers[0],explicit_line),
                     forces=(replace(unknown_fuel,fuel=150),)),scenario=no_line_scenario)

    nonterminal=replace(unknown_fuel,terminal=None)
    line_free=replace(destination,supply_line_present=False)
    with pytest.raises(UnsupportedState,match='UNKNOWN_POST_ARRIVAL_PATH'):
        step(replace(state,towers=(state.towers[0],line_free),forces=(nonterminal,)))


@pytest.mark.parametrize('units,destination_units',[
    ((1,0,0,0,0,0,0,0,0,0),(0,)*10),
    ((0,0,0,0,0,3,1,0,0,0),(0,)*10),
    ((0,0,0,0,0,3,0,0,0,0),(0,0,0,0,0,0,1,0,0,0)),
    ((0,0,0,0,0,3,0,0,0,0),(0,0,0,0,0,0,0,0,0,1)),
    ((0,1,0,0,0,0,0,0,0,0),(0,)*10),
    ((0,0,1,0,0,0,0,0,0,0),(0,)*10),
    ((0,0,0,1,0,0,0,0,0,0),(0,)*10),
    ((0,0,0,0,0,3,0,0,0,0),(0,1,0,0,0,0,0,0,0,0)),
    ((0,0,0,0,0,3,0,0,0,0),(0,0,1,0,0,0,0,0,0,0)),
    ((0,0,0,0,0,3,0,0,0,0),(0,0,0,1,0,0,0,0,0,0)),
])
def test_non_ground_many_air_special_or_ruler_vectors_never_use_no_fuel_merge_exception(units,destination_units):
    state=empty_world()
    destination=replace(state.towers[1],owner=7,units=destination_units,
        capacity=(10,)*10,production=(),relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,units,88,False,relation='SELF',terminal=True,fuel=None)
    with pytest.raises(UnsupportedState,match='UNKNOWN_ARRIVAL_FUEL'):
        step(replace(state,towers=(state.towers[0],destination),forces=(force,)))


def test_combat_arrival_does_not_use_same_owner_merge_fuel_exception():
    state=empty_world()
    enemy=replace(state.towers[1],owner=8,units=(0,0,0,0,0,1,0,0,0,0),
        production=(),relation='ENEMY',supply_line_present=None)
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,
        relation='SELF',terminal=True,fuel=None)
    with pytest.raises(UnsupportedState,match='UNVERIFIED_NORMAL_COMBAT'):
        step(replace(state,towers=(state.towers[0],enemy),forces=(force,)))
    attacker_wins=replace(force,units=(0,0,0,0,0,5,0,0,0,0))
    combat_state=replace(state,towers=(state.towers[0],enemy),forces=(attacker_wins,))
    with pytest.raises(UnsupportedState,match='UNKNOWN_ARRIVAL_FUEL'):
        step(combat_state,scenario=Scenario(ordinary_combat=True))
    with pytest.raises(UnsupportedState,match='EXPIRED_ARRIVAL'):
        step(replace(combat_state,forces=(replace(attacker_wins,fuel=0),)),
             scenario=Scenario(ordinary_combat=True))


def test_scenario_validation_does_not_lose_bool_int_aliases_in_sets():
    state=empty_world()
    state=replace(state,towers=(replace(state.towers[0],id=1),state.towers[1]))
    with pytest.raises(UnsupportedState,match='INVALID_SUPPLY_LINE_SCENARIO'):
        step(state,scenario=Scenario(no_supply_line_towers=(1,True)))
    force=SimForce(7,1,4,(0,0,0,0,0,3,0,0,0,0),0,False)
    with pytest.raises(UnsupportedState,match='INVALID_TERMINAL_SCENARIO'):
        step(replace(state,forces=(force,)),scenario=Scenario(terminal_forces=(0,False)))


@pytest.mark.parametrize('line',(None,True,False))
def test_mobile_near_capacity_only_known_absence_removes_supply_line_guard(line):
    state=empty_world()
    tower=replace(state.towers[0],units=(0,0,0,0,0,9,0,0,0,0),
                  capacity=(10,)*10,production=((5,1),),supply_line_present=line)
    state=replace(state,towers=(tower,))
    assert input_has_potential_event(state)
    if line is not False:
        with pytest.raises(UnsupportedState,match='PRODUCTION_SUPPLY_LINE'): step(state)
    else:
        result=step(state)
        assert result.towers[0].units[5]==10 and not result.forces
        assert not input_has_potential_event(result)
        assert step(result).towers==result.towers


def test_observed_friendly_absence_permits_merge_but_known_line_cannot_be_overridden():
    state=empty_world()
    dst=replace(state.towers[1],owner=7,units=(0,)*10,production=(),relation='SELF',supply_line_present=False)
    force=SimForce(7,3,4,(0,0,0,0,0,3,0,0,0,0),88,False,terminal=True,fuel=150)
    state=replace(state,towers=(state.towers[0],dst),forces=(force,))
    result=step(state)
    assert not result.forces and result.towers[1].units[5]==3
    with pytest.raises(UnsupportedState,match='UNSUPPORTED_REINFORCEMENT_SUPPLY_LINE'):
        step(replace(state,towers=(state.towers[0],replace(dst,supply_line_present=True))),
             scenario=Scenario(no_supply_line_towers=(4,)))


def test_canonical_conversion_preserves_own_line_unknown_and_observed_false():
    state=control_fixture()
    assert from_canonical(state).towers[0].supply_line_present is None
    state=replace(state,towers=(replace(state.towers[0],supply_line_present=replace(
        state.towers[0].visibility,value=False,source='test own absence')),state.towers[1]))
    converted=from_canonical(state)
    assert converted.towers[0].supply_line_present is False
    assert signature(converted)['supply_lines']==[(3,False)]
    assert signature(converted)!=signature(replace(converted,towers=(replace(converted.towers[0],supply_line_present=True),converted.towers[1])))
