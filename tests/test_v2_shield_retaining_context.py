import pytest

from kiomet_ai.v2.sim import Scenario, UnsupportedState, step
from kiomet_ai.v2.sim.model import SimForce, SimTower, SimulationState


def _state(*, dst_id=2, dst_owner=8, dst_kind=0, defender=None):
    source = SimTower(
        id=1, owner=7, kind=0, units=(0,) * 10, capacity=(255,) * 10,
        production=(), neighbors=(dst_id,), position=(0, 0), delay=0,
        morale=False, relation='SELF', supply_line_present=None,
    )
    destination = SimTower(
        id=dst_id, owner=dst_owner, kind=dst_kind,
        units=defender or (4, 0, 0, 0, 0, 1, 0, 0, 0, 0),
        capacity=(255,) * 10, production=(), neighbors=(1,),
        position=(5, 0), delay=0, morale=False,
        relation='ENEMY' if dst_owner else 'NEUTRAL',
        supply_line_present=None,
    )
    force = SimForce(
        owner=7, source=1, destination=dst_id,
        units=(0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
        progress=255, accelerated=False, relation='ENEMY',
        terminal=None, fuel=None,
    )
    return SimulationState(
        world_sequence=1, player=7, match_epoch='test', document='test-doc',
        towers=(source, destination), forces=(force,),
    )


def test_owned_nonruins_positive_id_shield_retaining_case_is_admitted():
    state = _state()
    with pytest.raises(UnsupportedState, match='UNVERIFIED_NORMAL_COMBAT'):
        step(state)

    result = step(state, scenario=Scenario(shield_retaining_combat=True))
    destination = next(tower for tower in result.towers if tower.id == 2)
    assert destination.owner == 8
    assert destination.units == (3, 0, 0, 0, 0, 1, 0, 0, 0, 0)
    assert result.forces == ()


@pytest.mark.parametrize(
    ('dst_id', 'dst_owner', 'dst_kind'),
    [(2, 0, 0), (2, 8, 27), (0, 8, 0), (2, True, 0), (2, 8, True)],
)
def test_shield_retaining_context_rejects_neutral_ruins_id_zero_and_bool_aliases(
        dst_id, dst_owner, dst_kind):
    state = _state(dst_id=dst_id, dst_owner=dst_owner, dst_kind=dst_kind)
    for scenario in (
        Scenario(shield_retaining_combat=True),
        Scenario(shield_retaining_combat=True, ground_combat=True),
        Scenario(shield_retaining_combat=True, ordinary_combat=True),
    ):
        with pytest.raises(UnsupportedState, match='UNPROVED_SHIELD_RETAINING_CONTEXT'):
            step(state, scenario=scenario)


@pytest.mark.parametrize('broader', [
    Scenario(shield_retaining_combat=True, ground_combat=True),
    Scenario(shield_retaining_combat=True, ordinary_combat=True),
])
def test_narrow_flag_never_falls_back_for_out_of_scope_units(broader):
    # A defender Fighter is outside the narrow Shield/Tank/Soldier proof.
    state = _state(defender=(4, 1, 0, 0, 0, 1, 0, 0, 0, 0))
    with pytest.raises(UnsupportedState, match='UNPROVED_SHIELD_RETAINING_DEFENSE'):
        step(state, scenario=broader)
