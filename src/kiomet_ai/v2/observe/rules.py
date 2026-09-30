"""Pinned local rule derivations for currently visible entities only."""
import json
from pathlib import Path
from ..state import Units

_DATA=json.loads(Path(__file__).with_name('rules_fae13.json').read_text())
CAPACITY=tuple(tuple(row) for row in _DATA['capacity'])
GENERATION=tuple(tuple(row) for row in _DATA['generation_ticks'])


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
