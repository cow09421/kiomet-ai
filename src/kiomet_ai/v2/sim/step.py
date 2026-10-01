from dataclasses import dataclass, replace
from ..state import Units
from ..observe.forces import motion
from ..observe.rules import DOWNGRADE, production
from .model import SimulationState, SimForce, UnsupportedState


@dataclass(frozen=True,slots=True)
class Launch:
    source: int
    destination: int
    units: tuple[int,...]


@dataclass(frozen=True,slots=True)
class Scenario:
    # Explicit scenario assumptions, not observations of hidden opponents.
    fixed_morale: bool=True
    terminal_forces: tuple[int,...]=()


def phase(sequence,tower_id):
    x=tower_id & 65535
    y=tower_id >> 16
    return (sequence+(x>>4)+((y>>4)<<8)) & 65535


def step(state: SimulationState, actions: tuple[Launch,...]=(), scenario: Scenario=Scenario()):
    if not scenario.fixed_morale: raise UnsupportedState('DYNAMIC_MORALE_AURA')
    towers={tower.id:tower for tower in state.towers}
    forces=list(state.forces)
    terminals=set(scenario.terminal_forces)
    if any(type(i) is not int or not 0<=i<len(forces) for i in terminals):
        raise UnsupportedState('INVALID_TERMINAL_SCENARIO')
    for action in actions:
        if action.source not in towers or action.destination not in towers: raise UnsupportedState('HIDDEN_ACTION_ENDPOINT')
        tower=towers[action.source]
        if tower.owner!=state.player or action.destination not in tower.neighbors: raise UnsupportedState('ILLEGAL_VISIBLE_LAUNCH')
        if len(action.units)!=10 or any(type(n) is not int or n<0 for n in action.units) or not any(action.units):
            raise UnsupportedState('INVALID_LAUNCH_UNITS')
        if any(action.units[i] for i in (6,7,8,9)): raise UnsupportedState('SPECIAL_OR_RULER_LAUNCH')
        if action.units[0] and tower.kind!=15: raise UnsupportedState('IMMOBILE_SHIELDS')
        if any(n>tower.units[i] for i,n in enumerate(action.units)): raise UnsupportedState('INSUFFICIENT_UNITS')
        towers[tower.id]=replace(tower,units=tuple(n-action.units[i] for i,n in enumerate(tower.units)))
        terminals.add(len(forces))
        forces.append(SimForce(state.player,action.source,action.destination,action.units,0,tower.morale))
    sequence=(state.world_sequence+1)&65535
    for i,force in enumerate(forces):
        if any(other.owner!=force.owner and (other.source,other.destination)==(force.destination,force.source)
               for other in forces[i+1:]):
            raise UnsupportedState('OPPOSED_FORCE_COMBAT')
    for key,tower in tuple(towers.items()):
        clock=phase(sequence,tower.id)
        if not tower.owner and DOWNGRADE[tower.kind]!=27 and clock%240==0:
            raise UnsupportedState('NEUTRAL_DOWNGRADE')
        if not tower.owner and any(tower.units) and clock%40==0:
            raise UnsupportedState('NEUTRAL_UNIT_DECAY')
        if tower.delay: raise UnsupportedState('ACTIVE_UPGRADE_OR_EMP')
        units=list(tower.units)
        for unit,period in tower.production:
            if period<=0: raise UnsupportedState('INVALID_PRODUCTION_PERIOD')
            if clock%period==0:
                if unit in (6,7,8,9): raise UnsupportedState('SPECIAL_PRODUCTION')
                if unit and units[9]: continue  # Ruler has Single priority.
                units[unit]=min(units[unit]+1,tower.capacity[unit])
        if tuple(units)!=tower.units: towers[key]=replace(tower,units=tuple(units))
    remaining=[]
    for index,force in enumerate(forces):
        src,dst=towers[force.source],towers[force.destination]
        vector=Units(tuple(enumerate(force.units)))
        speed,required,_=motion(vector,src.position,dst.position,False,force.progress)
        if force.accelerated is None:
            earliest=max(1,required*4//5)
            if force.progress+speed>=earliest: raise UnsupportedState('UNKNOWN_ARRIVAL_ACCELERATION')
        elif force.accelerated:
            required=max(1,required*4//5)
        progress=min(255,force.progress+speed)
        if progress<required:
            remaining.append(replace(force,progress=progress))
            continue
        if index not in terminals: raise UnsupportedState('UNKNOWN_POST_ARRIVAL_PATH')
        if force.units[9]: raise UnsupportedState('RULER_ARRIVAL_AURA')
        if dst.owner==force.owner:
            if dst.units[9] and any(force.units[1:6]): raise UnsupportedState('SINGLE_REINFORCEMENT_PRIORITY')
            combined=tuple(a+b for a,b in zip(dst.units,force.units))
            if any(n>dst.capacity[i] for i,n in enumerate(combined)): raise UnsupportedState('REINFORCEMENT_OVERFLOW')
            towers[dst.id]=replace(dst,units=combined)
        elif dst.owner==0 and not any(dst.units):
            if force.units[0]: raise UnsupportedState('OFFENSIVE_SHIELD_CAPTURE')
            if not any(force.units[1:6]): raise UnsupportedState('NON_CLAIMING_FORCE')
            if any(n>dst.capacity[i] for i,n in enumerate(force.units)): raise UnsupportedState('CAPTURE_OVERFLOW')
            periods=production(dst.kind,vector,force.owner,dst.delay,dst.morale)
            towers[dst.id]=replace(dst,owner=force.owner,units=force.units,production=periods)
        else:
            raise UnsupportedState('UNVERIFIED_NORMAL_COMBAT')
    return replace(state,world_sequence=sequence,towers=tuple(towers[key] for key in sorted(towers)),
                   forces=tuple(remaining),simulated_ticks=state.simulated_ticks+1)
