"""Pinned local rule derivations for currently visible entities only."""
import json
from pathlib import Path
from ..state import Units

_DATA=json.loads(Path(__file__).with_name('rules_fae13.json').read_text())
CAPACITY=tuple(tuple(row) for row in _DATA['capacity'])
GENERATION=tuple(tuple(row) for row in _DATA['generation_ticks'])
PREREQUISITES=tuple(tuple(row) for row in _DATA['prerequisites'])
DOWNGRADE=tuple(_DATA['downgrade'])
UPGRADE_DELAY=tuple(_DATA['delay_ticks'])


def upgrade_candidates(tower_type,counts,delay):
    """Normal prerequisite presentation, not unlock/command eligibility."""
    if counts is None or delay:
        return None if counts is None else ()
    return tuple((target,tuple((kind,counts[kind],need) for kind,need in enumerate(PREREQUISITES[target]) if need),
                  all(have>=need for have,need in zip(counts,PREREQUISITES[target])))
                 for target,parent in enumerate(DOWNGRADE) if parent==tower_type)


def locked_for_target(target,policy,unlocked_types):
    """Normal UI predicate; unavailable inputs are not false.

    TowerType::level is zero exactly when it has no prerequisite or downgrade.
    The lock condition is an AND, so a proven false term resolves the result
    even when an irrelevant term is unavailable.
    """
    if DOWNGRADE[target]==27 and not any(PREREQUISITES[target]):
        return False
    if unlocked_types is not None and target in unlocked_types:
        return False
    if policy is None:
        return None
    available=policy.get('rewarded_ad_available')
    restricted=policy.get('rank_requires_unlocks')
    if available is False or restricted is False:
        return False
    if available is True and restricted is True and unlocked_types is not None:
        return True
    return None


def upgrade_locks(tower_type,delay,policy,unlocked_types):
    """Lock flags for normal own active upgrade/basis-downgrade buttons."""
    if delay is None:
        return None
    if delay:
        return ()
    targets=[t for t,parent in enumerate(DOWNGRADE) if parent==tower_type]
    basis=tower_type
    seen=set()
    while DOWNGRADE[basis]!=27:
        if basis in seen:
            raise ValueError('invalid pinned downgrade cycle')
        seen.add(basis)
        basis=DOWNGRADE[basis]
    if basis!=tower_type:
        targets.append(basis)
    result=tuple((t,locked_for_target(t,policy,unlocked_types)) for t in targets)
    return None if any(locked is None for _,locked in result) else result


def capacity(tower_type,morale):
    return Units(tuple((unit,n+(10 if unit==0 and morale else 0))
                       for unit,n in enumerate(CAPACITY[tower_type])))


def production(tower_type,units,owner,delay,morale):
    """Potential intervals in source ticks; capacity/priority may block output.

    This is not an arrival timestamp or a promise that a unit is produced.
    Ruler occupancy suppresses non-shield generation. Nonzero delay/neutral
    ownership disables generation; boost halves intervals (minimum one tick).
    """
    if not owner or delay:
        return ()
    ruler=dict(units.counts)[9]>0
    return tuple((unit,max(1,ticks//2) if morale else ticks)
        for unit,ticks in enumerate(GENERATION[tower_type])
        if ticks is not None and (unit==0 or not ruler))


def mobile_inventory(tower_type,units):
    """Composition eligible for force formation, before route validity checks."""
    return Units(tuple((unit,n if unit!=0 or tower_type==15 else 0)
                       for unit,n in units.counts))


def player_mobile_inventory(tower_type,units,owner,player):
    """Own source inventory; a known non-owned source permits zero own units.

    Unknown player identity remains unknown. Route validity and command timing
    are separate; inactivity is not assumed to forbid existing troop movement.
    """
    if type(player) is not int or not 0 < player <= 65535:
        return None
    if owner != player:
        return Units(tuple((unit,0) for unit,_ in units.counts))
    return mobile_inventory(tower_type,units)
