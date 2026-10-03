from dataclasses import replace
import pytest
from kiomet_ai.v2.sim import ordinary_arrival_boundary, UnsupportedState, step
from kiomet_ai.v2.sim.model import SimForce
from test_v2_sim import empty_world


def case():
    world = empty_world()
    source, dest = world.towers
    dest = replace(dest, owner=7, units=(0,)*10, supply_line_present=False)
    force = SimForce(7, source.id, dest.id, (0,0,0,0,0,3,0,0,0,0), 88, False)
    return world, source, dest, force


def boundary(force, source, dest, **changes):
    options = dict(other_inbound=(), inbound_context_complete=True, fixed_morale=True)
    options.update(changes)
    return ordinary_arrival_boundary(force, source, dest, 65535, **options)


def test_v2_arrival_boundary_survives_unknown_terminal_without_faking_merge():
    world, source, dest, force = case()
    event = boundary(force, source, dest)
    assert event.tick == 0 and event.branch == 'REINFORCEMENT_REQUIRED'
    assert event.status == 'SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN'
    assert event.downstream_censors == ('UNKNOWN_POST_ARRIVAL_PATH',)
    assert dest.units == (0,)*10 and force.progress == 88
    with pytest.raises(UnsupportedState, match='POST_ARRIVAL_PATH'):
        step(replace(world, towers=(source, dest), forces=(force,)))
    assert boundary(replace(force, progress=0), source, dest) is None


def test_v2_arrival_neutral_and_combat_required_branches_do_not_claim_result():
    _, source, dest, force = case()
    neutral = replace(dest, owner=0, supply_line_present=None)
    event = boundary(force, source, neutral)
    assert event.branch == 'CAPTURE_REQUIRED'
    assert 'UNKNOWN_ARRIVAL_FUEL' in event.downstream_censors
    occupied = replace(dest, owner=8, units=(0,0,0,0,0,2,0,0,0,0), supply_line_present=None)
    event = boundary(force, source, occupied)
    assert event.branch == 'COMBAT_REQUIRED'
    assert 'UNVERIFIED_NORMAL_COMBAT' in event.downstream_censors


def test_v2_arrival_unknown_context_and_unknown_line_are_explicit_censors():
    _, source, dest, force = case()
    event = boundary(force, source, replace(dest, supply_line_present=None), inbound_context_complete=False)
    assert set(event.downstream_censors) == {'UNKNOWN_INBOUND_CONTEXT',
        'UNKNOWN_REINFORCEMENT_SUPPLY_LINE', 'UNKNOWN_POST_ARRIVAL_PATH', 'UNKNOWN_ARRIVAL_FUEL'}


def test_v2_arrival_already_reached_and_nonboolean_acceleration_do_not_create_event():
    _, source, dest, force = case()
    with pytest.raises(UnsupportedState, match='ALREADY_REACHED'):
        boundary(replace(force, progress=90), source, dest)
    with pytest.raises(UnsupportedState, match='INVALID_ARRIVAL_ACCELERATION'):
        boundary(replace(force, accelerated=1), source, dest)
    with pytest.raises(UnsupportedState, match='UNKNOWN_ARRIVAL_DELAY'):
        boundary(force, replace(source, delay=None), dest)


@pytest.mark.parametrize('change,reason', [
    ('acceleration', 'ACCELERATION'), ('special', 'NONORDINARY'),
    ('delay', 'UPGRADE_OR_EMP'), ('relay', 'SUPPLY_LINE_RELAY'),
    ('aura', 'DYNAMIC_MORALE'), ('multiple', 'MULTIFORCE')])
def test_v2_arrival_excludes_unsupported_contexts(change, reason):
    _, source, dest, force = case()
    args = {}
    if change == 'acceleration': force = replace(force, accelerated=None)
    if change == 'special': force = replace(force, units=(0,0,0,0,0,0,1,0,0,0))
    if change == 'delay': dest = replace(dest, delay=1)
    if change == 'relay': dest = replace(dest, supply_line_present=True)
    if change == 'aura': args['fixed_morale'] = False
    if change == 'multiple': args['other_inbound'] = (force,)
    with pytest.raises(UnsupportedState, match=reason): boundary(force, source, dest, **args)
