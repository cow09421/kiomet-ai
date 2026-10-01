"""Ground-only reference fight, adapted from AGPL Kiomet Combatants::fight.

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
    if type(attacker_morale) is not bool or type(defender_morale) is not bool:
        raise UnsupportedState('UNKNOWN_COMBAT_MORALE')
    if any(attacker[i] or defender[i] for i in (1,2,3,6,7,8)):
        raise UnsupportedState('AIR_OR_SPECIAL_COMBAT')
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
    def next_unit(side):
        return next((i for i,n in enumerate(units[side]) if n-(last[side]==i)>0),None)
    def consume(side,unit):
        if last[side] is not None: units[side][last[side]]-=1
        if unit is not None: last[side]=unit
    def signed_damage(side,unit):
        return (3 if unit==4 else 1)*(1 if side==0 else -1)
    while True:
        side=0 if damage<=0 else 1
        unit=next_unit(side)
        if damage==0 and next_unit(1) is None: unit=None
        if unit is None: break
        consume(side,unit)
        damage+=signed_damage(side,unit)
    nexts=[next_unit(0),next_unit(1)]
    order=(1,0) if nexts[1] is not None else (0,1)
    for side in order:
        if side==0 and damage<=0 or side==1 and damage>=0:
            unit=nexts[side]
            if unit is not None: damage+=signed_damage(side,unit)
            consume(side,unit)
    alive=lambda side:any(units[side][i] for i in (4,5,9))
    winner='ATTACKER' if alive(0) else 'DEFENDER' if alive(1) or defender_is_tower and damage<=0 else None
    return GroundFight(winner,tuple(units[0]),tuple(units[1]),
                       bool(original_rulers[0] and not units[0][9]),
                       bool(original_rulers[1] and not units[1][9]))
