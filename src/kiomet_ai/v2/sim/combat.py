"""Reference fights, adapted from AGPL Kiomet Combatants::fight.

Pure damage/field values and initial morale offset follow pinned static WASM.
Fight ordering remains a hypothesis until independently checked live.
"""
from dataclasses import dataclass
from .model import UnsupportedState


@dataclass(frozen=True,slots=True)
class GroundFight:
    winner: str | None
    attacker: tuple[int,...]
    defender: tuple[int,...]
    attacker_ruler_lost: bool
    defender_ruler_lost: bool


def fight_ground(attacker,defender,defender_is_tower=True,attacker_morale=False,defender_morale=False):
    if any(attacker[i] or defender[i] for i in (1,2,3,6,7,8)):
        raise UnsupportedState('AIR_OR_SPECIAL_COMBAT')
    return _fight(attacker,defender,defender_is_tower,attacker_morale,defender_morale,(0,)*10)


def fight_ordinary(attacker,defender,defender_capacity,defender_is_tower=True,
                   attacker_morale=False,defender_morale=False):
    """Ordinary air/surface candidate; special attacks remain unsupported."""
    if any(attacker[i] or defender[i] for i in (6,7,8)):
        raise UnsupportedState('SPECIAL_COMBAT')
    if defender_is_tower and (defender_capacity is None or len(defender_capacity)!=10):
        raise UnsupportedState('UNKNOWN_COMBAT_CAPACITY')
    return _fight(attacker,defender,defender_is_tower,attacker_morale,defender_morale,defender_capacity)


def shield_retaining_defense(attacker,defender,attacker_morale,defender_morale):
    """Pinned shield-retaining ordinary defense subcase; not a full fight model."""
    for vector in (attacker, defender):
        if (not isinstance(vector, (tuple, list)) or len(vector) != 10 or
                any(type(count) is not int or count < 0 or count > 255
                    for count in vector)):
            raise UnsupportedState('INVALID_COMBAT_VECTOR')
    if type(attacker_morale) is not bool or type(defender_morale) is not bool:
        raise UnsupportedState('UNKNOWN_COMBAT_MORALE')

    if (attacker[0] != 0 or any(attacker[i] for i in (1, 2, 3, 6, 7, 8, 9)) or
            attacker[4] + attacker[5] == 0):
        raise UnsupportedState('UNPROVED_SHIELD_RETAINING_DEFENSE')
    if (any(defender[i] for i in (1, 2, 3, 6, 7, 8, 9)) or
            defender[4] + defender[5] == 0):
        raise UnsupportedState('UNPROVED_SHIELD_RETAINING_DEFENSE')

    tanks, soldiers = attacker[4], attacker[5]
    attack_bonus = (min(3, (tanks + soldiers) // 2)
                    if attacker_morale and not defender_morale else 0)
    defense_bonus = (min(3, (defender[4] + defender[5]) // 2)
                     if defender_morale and not attacker_morale else 0)
    shield_retention_bound = 3 * tanks + soldiers + min(3, (tanks + soldiers) // 2)
    if defender[0] <= shield_retention_bound:
        raise UnsupportedState('UNPROVED_SHIELD_RETAINING_DEFENSE')

    shield_loss = max(0, 3 * tanks + soldiers + attack_bonus - defense_bonus)
    remaining = list(defender)
    remaining[0] -= shield_loss
    return GroundFight('DEFENDER', (0,) * 10, tuple(remaining), False, False)


def _fight(attacker,defender,defender_is_tower,attacker_morale,defender_morale,defender_capacity):
    if type(attacker_morale) is not bool or type(defender_morale) is not bool:
        raise UnsupportedState('UNKNOWN_COMBAT_MORALE')
    units=[list(attacker),list(defender)]
    original_rulers=(attacker[9],defender[9])
    if defender_is_tower: units[0][0]=0  # Offensive shields cannot fight a tower.
    last=[None,None]
    # func4969 removes offensive Shields before morale_advantage is called.
    # Force+21 reaches scratch309 via an aggregate i32 copy; Tower+45 is the
    # defender flag. A mismatch starts with a signed non-single-use bonus.
    # The iterator explicitly skips enum zero (Shield) at 0xffb1d..0xffb27.
    # 0xffb43..0xffb51 pushes [3, headcount>>1, headcount>>1>=3];
    # WASM select takes the FIRST operand on true, hence a cap, not a floor.
    damage=(min(3,sum(units[0][1:])//2) if attacker_morale else
            -min(3,sum(units[1][1:])//2)) if attacker_morale!=defender_morale else 0
    def unused(side):
        return ((i,n-(last[side]==i)) for i,n in enumerate(units[side]) if n-(last[side]==i)>0)
    def unit_field(side,unit,count,any_air):
        if unit==0: return int(any_air)
        in_force=side==0 or not defender_is_tower
        overflow=not in_force and count>defender_capacity[unit]
        return int(in_force or overflow) if unit in (1,2,3) else 0
    def next_unit(side,field):
        def inner(any_air):
            return next(((i,f) for i,n in unused(side)
                         if (f:=unit_field(side,i,n,any_air))>=field),None)
        first=inner(False)
        # func2408 calls the selector again with any_air when field=Air and
        # a first candidate exists; this moves its group's Shield to Air.
        return inner(True) if first is not None and field==1 else first
    def consume(side,unit):
        if last[side] is not None: units[side][last[side]]-=1
        if unit is not None: last[side]=unit
    def signed_damage(side,unit,own_field,enemy_field):
        value=(3 if unit==4 else 3 if unit in (1,2) and own_field==1 else
               5 if unit==3 and own_field==1 and enemy_field==0 else 1)
        return value*(1 if side==0 else -1)
    for field in (1,0):  # Pinned Air before Surface, without resetting damage.
        while True:
            side=0 if damage<=0 else 1
            selected=next_unit(side,field)
            if damage==0 and next_unit(1,field) is None: selected=None
            if selected is None: break
            unit,own_field=selected
            consume(side,unit)
            damage+=signed_damage(side,unit,own_field,field)
    nexts=[next((i for i,n in unused(side)),None) for side in (0,1)]
    order=(1,0) if nexts[1] is not None else (0,1)
    for side in order:
        if side==0 and damage<=0 or side==1 and damage>=0:
            unit=nexts[side]
            if unit is not None: damage+=signed_damage(side,unit,0,0)
            consume(side,unit)
    alive=lambda side:any(units[side][i] for i in (1,2,3,4,5,9))
    winner='ATTACKER' if alive(0) else 'DEFENDER' if alive(1) or defender_is_tower and damage<=0 else None
    return GroundFight(winner,tuple(units[0]),tuple(units[1]),
                       bool(original_rulers[0] and not units[0][9]),
                       bool(original_rulers[1] and not units[1][9]))
