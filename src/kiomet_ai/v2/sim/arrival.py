"""Ordinary current-leg arrival boundary, independent of downstream admission.

This factor result never supplies a replacement world state. A reached current
leg can be supported while terminal route, relay, fuel or combat remains unknown.
"""
from dataclasses import dataclass
from functools import lru_cache
from ..state import Units
from ..observe.forces import motion
from .model import SimForce, SimTower, UnsupportedState


@lru_cache(maxsize=4096)
def movement_parameters(units, source_position, destination_position):
    speed, required, _ = motion(Units(tuple(enumerate(units))),
                                source_position, destination_position, False, 0)
    return speed, required


@dataclass(frozen=True, slots=True)
class CurrentLegAdvance:
    progress: int
    required: int
    reached: bool


def advance_current_leg(force: SimForce, source: SimTower, destination: SimTower):
    speed, required = movement_parameters(force.units, source.position, destination.position)
    if force.accelerated is None:
        if force.progress + speed >= max(1, required * 4 // 5):
            raise UnsupportedState('UNKNOWN_ARRIVAL_ACCELERATION')
    elif force.accelerated:
        required = max(1, required * 4 // 5)
    progress = min(255, force.progress + speed)
    return CurrentLegAdvance(progress, required, progress >= required)


@dataclass(frozen=True, slots=True)
class ArrivalBoundary:
    status: str
    tick: int
    source: int
    destination: int
    owner: int
    units: tuple[int, ...]
    progress: int
    required: int
    branch: str
    downstream_censors: tuple[str, ...]


def ordinary_arrival_boundary(force: SimForce, source: SimTower, destination: SimTower,
                              before_tick: int, *, other_inbound: tuple[SimForce, ...],
                              inbound_context_complete: bool, fixed_morale: bool):
    """Return one-tick arrival or None; all premises are explicit before inputs.

    Unknown inbound context is retained as a censor, not treated as an empty
    queue. Known simultaneous arrivals and visible opposed combat are excluded.
    Supply-line UNKNOWN only permits the current-leg boundary, never a merge.
    """
    if type(before_tick) is not int or not 0 <= before_tick <= 65535:
        raise UnsupportedState('INVALID_ARRIVAL_TICK')
    if fixed_morale is not True:
        raise UnsupportedState('DYNAMIC_MORALE_AURA')
    if force.source != source.id or force.destination != destination.id or source.id == destination.id:
        raise UnsupportedState('INVALID_ARRIVAL_ENDPOINTS')
    if (type(force.units) is not tuple or len(force.units) != 10 or
            any(type(n) is not int or not 0 <= n <= 255 for n in force.units) or
            not any(force.units) or any(force.units[6:])):
        raise UnsupportedState('NONORDINARY_ARRIVAL')
    if type(force.owner) is not int or force.owner <= 0:
        raise UnsupportedState('INVALID_ARRIVAL_OWNER')
    if type(force.progress) is not int or not 0 <= force.progress <= 255:
        raise UnsupportedState('INVALID_ARRIVAL_PROGRESS')
    if force.accelerated is not None and type(force.accelerated) is not bool:
        raise UnsupportedState('INVALID_ARRIVAL_ACCELERATION')
    if any(type(tower.delay) is not int or not 0 <= tower.delay <= 255 for tower in (source, destination)):
        raise UnsupportedState('UNKNOWN_ARRIVAL_DELAY')
    if source.delay or destination.delay:
        raise UnsupportedState('ACTIVE_UPGRADE_OR_EMP')
    if any(destination.units[6:]):
        raise UnsupportedState('SPECIAL_DESTINATION_ARRIVAL')
    if destination.supply_line_present is True:
        raise UnsupportedState('SUPPLY_LINE_RELAY_ARRIVAL')
    moved = advance_current_leg(force, source, destination)
    if force.progress >= moved.required:
        raise UnsupportedState('ALREADY_REACHED_CURRENT_LEG')
    if not moved.reached:
        return None
    for other in other_inbound:
        if (other.source, other.destination) == (force.destination, force.source) and other.owner != force.owner:
            raise UnsupportedState('OPPOSED_FORCE_COMBAT')
        # Its movement source need not be this source; without that geometry,
        # conservatively exclude any visible simultaneous inbound candidate.
        if other.destination == force.destination:
            raise UnsupportedState('MULTIFORCE_ARRIVAL_CONTEXT')
    censors = []
    if inbound_context_complete is not True:
        censors.append('UNKNOWN_INBOUND_CONTEXT')
    if destination.owner == force.owner:
        branch = 'REINFORCEMENT_REQUIRED'
        if destination.supply_line_present is not False:
            censors.append('UNKNOWN_REINFORCEMENT_SUPPLY_LINE')
    elif destination.owner == 0 and not any(destination.units):
        branch = 'CAPTURE_REQUIRED' if any(force.units[1:6]) else 'NON_CLAIMING_FORCE'
    else:
        branch = 'COMBAT_REQUIRED'
        censors.append('UNVERIFIED_NORMAL_COMBAT')
    if force.terminal is not True:
        censors.append('UNKNOWN_POST_ARRIVAL_PATH')
    fuel_irrelevant = (destination.owner == force.owner and destination.supply_line_present is False
                      and any(force.units[i] for i in (4, 5))
                      and not any(force.units[i] or destination.units[i] for i in (1, 2, 3, 6, 7, 8, 9)))
    if force.fuel is None and not fuel_irrelevant:
        censors.append('UNKNOWN_ARRIVAL_FUEL')
    elif force.fuel is not None and (force.fuel < 0 or force.fuel == 0 and not fuel_irrelevant):
        censors.append('EXPIRED_ARRIVAL')
    return ArrivalBoundary('SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN' if censors else
                           'ARRIVAL_REACHED_SUPPORTED_BOUNDARY', (before_tick + 1) & 65535,
                           force.source, force.destination, force.owner, force.units,
                           moved.progress, moved.required, branch, tuple(censors))
