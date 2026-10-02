import pytest

from kiomet_ai.v2.sim.combat import shield_retaining_defense
from kiomet_ai.v2.sim.model import UnsupportedState


def units(**counts):
    indexes = {'shield': 0, 'fighter': 1, 'tank': 4, 'soldier': 5,
               'ruler': 9}
    result = [0] * 10
    for name, count in counts.items():
        result[indexes[name]] = count
    return tuple(result)


@pytest.mark.parametrize(
    ('attacker_morale', 'defender_morale', 'shield_loss'),
    [(False, False, 10), (True, False, 13),
     (False, True, 7), (True, True, 10)],
)
def test_mixed_tank_soldier_damage_with_each_morale_combination(
        attacker_morale, defender_morale, shield_loss):
    result = shield_retaining_defense(
        units(tank=2, soldier=4), units(shield=50, tank=3, soldier=5),
        attacker_morale, defender_morale)

    assert result.winner == 'DEFENDER'
    assert result.attacker == (0,) * 10
    assert result.defender == units(shield=50 - shield_loss, tank=3, soldier=5)
    assert not result.attacker_ruler_lost and not result.defender_ruler_lost


@pytest.mark.parametrize(
    ('attacker', 'defender', 'defender_morale', 'expected_shields'),
    [(units(soldier=4), units(shield=20, soldier=12), True, 19),
     (units(tank=2), units(shield=20, soldier=12), True, 17)],
)
def test_pinned_example_arithmetic(attacker, defender, defender_morale,
                                   expected_shields):
    result = shield_retaining_defense(attacker, defender, False,
                                      defender_morale)
    assert result.defender[0] == expected_shields
    assert result.defender[5] == 12


def test_defender_bonus_can_reduce_shield_loss_to_zero():
    result = shield_retaining_defense(
        units(soldier=1), units(shield=4, soldier=20), False, True)
    assert result.defender == units(shield=4, soldier=20)


def test_strict_shield_bound_is_required():
    with pytest.raises(UnsupportedState, match='UNPROVED_SHIELD_RETAINING_DEFENSE'):
        shield_retaining_defense(
            units(tank=1), units(shield=3, soldier=1), False, False)
    # The retention guard uses the full attacker-morale upper bound even when
    # the current known morale flags would make the realized bonus zero.
    with pytest.raises(UnsupportedState, match='UNPROVED_SHIELD_RETAINING_DEFENSE'):
        shield_retaining_defense(
            units(tank=2, soldier=4), units(shield=13, soldier=4),
            False, False)


@pytest.mark.parametrize(
    ('attacker', 'defender', 'attacker_morale', 'defender_morale', 'reason'),
    [
        (units(shield=1, soldier=1), units(shield=20, soldier=10),
         False, False, 'UNPROVED_SHIELD_RETAINING_DEFENSE'),
        (units(soldier=1), units(shield=20, soldier=10, fighter=1),
         False, False, 'UNPROVED_SHIELD_RETAINING_DEFENSE'),
        (units(soldier=1), units(shield=20, soldier=10, ruler=1),
         False, False, 'UNPROVED_SHIELD_RETAINING_DEFENSE'),
        (units(soldier=1), units(shield=20, soldier=10),
         None, False, 'UNKNOWN_COMBAT_MORALE'),
        ((0, 0, 0, 0, True, 1, 0, 0, 0, 0),
         units(shield=20, soldier=10), False, False, 'INVALID_COMBAT_VECTOR'),
        ((0,) * 9, units(shield=20, soldier=10),
         False, False, 'INVALID_COMBAT_VECTOR'),
        ((0, 0, 0, 0, -1, 1, 0, 0, 0, 0),
         units(shield=20, soldier=10), False, False, 'INVALID_COMBAT_VECTOR'),
        (units(soldier=256), units(shield=255, soldier=10),
         False, False, 'INVALID_COMBAT_VECTOR'),
    ],
)
def test_out_of_scope_inputs_fail_closed(attacker, defender,
                                         attacker_morale, defender_morale,
                                         reason):
    with pytest.raises(UnsupportedState, match=reason):
        shield_retaining_defense(attacker, defender,
                                 attacker_morale, defender_morale)
