from dataclasses import dataclass
import math
from statistics import median
from ..control import control_readiness_gaps
from ..observe.rules import DOWNGRADE
from ..observe.forces import motion
from ..state import Units


class UnsupportedState(ValueError):
    """Required mechanics or knowledge are unavailable; never a silent approximation."""


@dataclass(frozen=True, slots=True)
class RuntimeTimeModel:
    tick_duration_ms: float | None=None
    provenance: str='UNKNOWN'

    @classmethod
    def from_live_evidence(cls, receipt):
        periods=[c['runtime_tick_model']['median_event_ms_per_tick'] for c in receipt['cohorts']
                 if c['runtime_tick_model']['advance_events']>=100]
        if not periods or any(not math.isfinite(p) or p<=0 for p in periods):
            raise UnsupportedState('UNKNOWN_TIME_MODEL')
        return cls(median(periods),'DERIVED: pinned live observed cadence; M1B cohort manifest')

    def milliseconds(self,ticks):
        if self.tick_duration_ms is None: raise UnsupportedState('UNKNOWN_TIME_MODEL')
        return ticks*self.tick_duration_ms


@dataclass(frozen=True, slots=True)
class SimTower:
    id: int
    owner: int
    kind: int
    units: tuple[int,...]
    capacity: tuple[int,...]
    production: tuple[tuple[int,int],...]
    neighbors: tuple[int,...]
    position: tuple[int,int]
    delay: int
    morale: bool
    relation: str | None=None
    supply_line_present: bool | None=None

    def __post_init__(self):
        if self.supply_line_present is not None and type(self.supply_line_present) is not bool:
            raise UnsupportedState('INVALID_SUPPLY_LINE_FLAG')


@dataclass(frozen=True, slots=True)
class SimForce:
    owner: int
    source: int
    destination: int
    units: tuple[int,...]
    progress: int
    accelerated: bool | None
    relation: str | None=None
    terminal: bool | None=None
    fuel: int | None=None


@dataclass(frozen=True, slots=True)
class SimulationState:
    world_sequence: int
    player: int
    match_epoch: str
    document: str
    towers: tuple[SimTower,...]
    forces: tuple[SimForce,...]
    simulated_ticks: int=0

    def __post_init__(self):
        if any(t.supply_line_present is not None and
               (type(self.player) is not int or self.player <= 0 or
                type(t.owner) is not int or t.owner <= 0 or t.owner != self.player)
               for t in self.towers):
            raise ValueError('known supply-line presence is own-only')

    @property
    def visible_rulers(self):
        return tuple((t.owner,'tower',t.id) for t in self.towers if t.units[9])+tuple(
            (f.owner,'force',f.source,f.destination) for f in self.forces if f.units[9])


def unit_tuple(fact, allow_stationary_special=False):
    if fact.value is None: raise UnsupportedState('UNKNOWN_UNITS')
    counts=dict(fact.value.counts)
    if set(counts)!=set(range(10)): raise UnsupportedState('INCOMPLETE_UNIT_VECTOR')
    if sum(bool(counts[i]) for i in range(6,10))>1 or (
        any(counts[i] for i in range(6,10)) and any(counts[i] for i in range(1,6))):
        raise UnsupportedState('INVALID_UNIT_CATEGORY')
    if not allow_stationary_special and any(counts[i] for i in (6,7,8)):
        raise UnsupportedState('SPECIAL_UNITS')
    return tuple(counts[i] for i in range(10))


def from_canonical(state, now_ms=None):
    gaps=control_readiness_gaps(state,state.received_at_ms if now_ms is None else now_ms)
    if gaps: raise UnsupportedState('NOT_READY: '+','.join(gaps[:12]))
    towers=[]
    for tower in state.towers:
        # Stationary special inventory is preserved exactly. Any actual
        # special production, dispatch or combat remains unsupported.
        units=unit_tuple(tower.units,allow_stationary_special=True)
        cap=tuple(dict(tower.capacity.value.counts)[i] for i in range(10))
        if tower.delay_ticks.value: raise UnsupportedState('ACTIVE_UPGRADE_OR_EMP')
        periods=tower.production.value
        effects=dict(tower.effects.value)
        if set(effects)-{'MORALE_BOOST'}: raise UnsupportedState('COMPLEX_AURA')
        if 'MORALE_BOOST' not in effects: raise UnsupportedState('UNKNOWN_MORALE')
        towers.append(SimTower(tower.id,tower.owner.value,tower.tower_type.value,units,cap,
            periods,tower.neighbors.value,tower.position.value,tower.delay_ticks.value,effects['MORALE_BOOST'],tower.relation.value,
            tower.supply_line_present.value))
    forces=[]
    for force in state.forces.value or ():
        units=unit_tuple(force.units)
        if sum(units)!=force.unit_count.value: raise UnsupportedState('INCONSISTENT_FORCE_COUNT')
        if not force.owner.value: raise UnsupportedState('ZOMBIE_FORCE')
        accelerated=force.accelerated.value
        if accelerated is None and force.eta_ms.value is not None and 'pinned current-leg' in force.eta_ms.source:
            # The historical ETA fact was computed from the actual boost flag.
            # Invert only a unique match of that pinned estimator; never treat
            # ambiguous ETA or unavailable geometry as false acceleration.
            positions={t.id:t.position for t in towers}
            candidates=[boost for boost in (False,True) if motion(Units(tuple(enumerate(units))),
                positions[force.source.value],positions[force.destination.value],boost,
                force.progress.value)[2]==force.eta_ms.value]
            if len(candidates)==1: accelerated=candidates[0]
        forces.append(SimForce(force.owner.value,force.source.value,force.destination.value,units,
                               force.progress.value,accelerated,force.relation.value))
    return SimulationState(state.tick.value,state.player_id.value,state.match_id.value,
                           state.document_id,tuple(towers),tuple(forces))
