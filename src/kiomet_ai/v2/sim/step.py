from dataclasses import dataclass, replace
from functools import lru_cache
from ..state import Units
from ..observe.forces import motion
from ..observe.rules import DOWNGRADE, production
from .model import SimulationState, SimForce, UnsupportedState
from .combat import fight_ground, fight_ordinary


@dataclass(frozen=True,slots=True)
class Launch:
    source: int
    destination: int
    units: tuple[int,...]
    owner: int | None=None
    terminal: bool | None=True


@dataclass(frozen=True,slots=True)
class LaunchAll:
    """Manual own-side DeployForce using current deployable source inventory."""
    source: int
    destination: int
    terminal: bool | None=None
    owner: int | None=None


@dataclass(frozen=True,slots=True)
class Scenario:
    # Explicit scenario assumptions, not observations of hidden opponents.
    fixed_morale: bool=True
    terminal_forces: tuple[int,...]=()
    ground_combat: bool=False  # Validation candidate until live ordering is verified.
    opponent_launches: tuple[Launch,...]=()
    ordinary_combat: bool=False  # Separate wider hypothesis; never enabled implicitly.
    no_supply_line_towers: tuple[int,...]=()  # Explicit before-input scenario, never inferred from terminal path.


@lru_cache(maxsize=4096)
def phase_offset(tower_id):
    # Static arithmetic only: no actor facts, world clock, or lifecycle state.
    return ((tower_id>>4)&4095)+((tower_id>>20)<<8)


def phase(sequence,tower_id):
    return (sequence+phase_offset(tower_id)) & 65535


@lru_cache(maxsize=4096)
def movement_parameters(units,source_position,destination_position):
    # Pure immutable rule inputs; cache never keys on identity or clock.
    vector=Units(tuple(enumerate(units)))
    speed,required,_=motion(vector,source_position,destination_position,False,0)
    return speed,required


def _captured_relation(owner,player,arriving_relation):
    if owner==player and player>0: return 'SELF'
    if owner==0: return 'NEUTRAL'
    return arriving_relation if arriving_relation in ('ALLY','ENEMY') else None


def _merge_arriving_units(existing,incoming,capacity,error_reason):
    # Units::add_inner applies this table after ordinary capacity, only on the
    # owned/overflow-allowed path. Preserve existing over-cap stock and clip
    # only the arriving count. Other kinds retain the model's prior fail-closed
    # behavior when the combined count exceeds observed capacity.
    result=list(existing)
    for unit,count in enumerate(incoming):
        if unit in (4,5):
            limit=capacity[unit]+(5 if unit==4 else 10)
            if limit>255: raise UnsupportedState('UNKNOWN_OVERFLOW_REPRESENTATION')
            room=max(0,limit-existing[unit])
            result[unit]=existing[unit]+min(count,room)
        else:
            total=existing[unit]+count
            if total>capacity[unit]: raise UnsupportedState(error_reason)
            result[unit]=total
    return tuple(result)


def _validate_launch_all(action, state, towers):
    if type(action.source) is not int or type(action.destination) is not int:
        raise UnsupportedState('INVALID_LAUNCH_ENDPOINT')
    if action.owner is not None and (type(action.owner) is not int or action.owner<=0):
        raise UnsupportedState('INVALID_LAUNCH_OWNER')
    if type(state.player) is not int or state.player<=0:
        raise UnsupportedState('INVALID_LAUNCH_OWNER')
    if action.owner not in (None,state.player):
        raise UnsupportedState('FOREIGN_ACTION_OWNER')
    if action.terminal is not None and type(action.terminal) is not bool:
        raise UnsupportedState('INVALID_LAUNCH_TERMINAL')
    if action.source not in towers or action.destination not in towers:
        raise UnsupportedState('HIDDEN_ACTION_ENDPOINT')
    units=towers[action.source].units
    if type(units) is not tuple or len(units)!=10 or any(type(n) is not int or not 0<=n<=255 for n in units):
        raise UnsupportedState('INVALID_DEPLOYMENT_INVENTORY')


def step(state: SimulationState, actions: tuple[Launch|LaunchAll,...]=(), scenario: Scenario=Scenario()):
    if not scenario.fixed_morale: raise UnsupportedState('DYNAMIC_MORALE_AURA')
    towers={tower.id:tower for tower in state.towers}
    if len(towers)!=len(state.towers): raise UnsupportedState('DUPLICATE_TOWER_IDS')
    forces=list(state.forces)
    if scenario.no_supply_line_towers and any(type(i) is not int or i not in towers for i in scenario.no_supply_line_towers):
        raise UnsupportedState('INVALID_SUPPLY_LINE_SCENARIO')
    if scenario.terminal_forces and any(type(i) is not int or not 0<=i<len(forces) for i in scenario.terminal_forces):
        raise UnsupportedState('INVALID_TERMINAL_SCENARIO')
    for action in actions:
        if isinstance(action,LaunchAll): _validate_launch_all(action,state,towers)
    if any(isinstance(action,LaunchAll) for action in scenario.opponent_launches):
        raise UnsupportedState('OPPONENT_LAUNCH_ALL_UNSUPPORTED')
    # Empty default premises need no per-step set allocation. Validate before
    # deduplicating: Python bool/int aliases must not hide invalid input types.
    terminals=set(scenario.terminal_forces) if scenario.terminal_forces else ()
    no_supply_lines=set(scenario.no_supply_line_towers) if scenario.no_supply_line_towers else ()
    sequence=(state.world_sequence+1)&65535
    if len(forces)>1:
        for i,force in enumerate(forces[:-1]):
            if any(other.owner!=force.owner and (other.source,other.destination)==(force.destination,force.source)
                   for other in forces[i+1:]):
                raise UnsupportedState('OPPOSED_FORCE_COMBAT')
    for tower in state.towers:
        key=tower.id
        clock=(sequence+phase_offset(tower.id)) & 65535
        if not tower.owner and DOWNGRADE[tower.kind]!=27 and clock%240==0:
            raise UnsupportedState('NEUTRAL_DOWNGRADE')
        if not tower.owner and clock%40==0 and any(tower.units):
            raise UnsupportedState('NEUTRAL_UNIT_DECAY')
        if tower.delay: raise UnsupportedState('ACTIVE_UPGRADE_OR_EMP')
        units=tower.units
        # Pinned Chunk tick: owned decay every 120 phase ticks precedes
        # generation. Mobile decay may trigger an unobserved supply line.
        if tower.owner and clock%120==0:
            for unit,n in enumerate(units):
                if n>tower.capacity[unit]:
                    if unit in (4,5) and tower.supply_line_present is False:
                        if units is tower.units: units=list(units)
                        units[unit]-=1
                    elif unit or tower.kind==15:
                        raise UnsupportedState('MOBILE_OVERFLOW_SUPPLY_LINE')
                    else:
                        if units is tower.units: units=list(units)
                        units[unit]-=1
        for unit,period in tower.production:
            if period<=0: raise UnsupportedState('INVALID_PRODUCTION_PERIOD')
            if clock%period==0:
                if unit in (6,7,8,9): raise UnsupportedState('SPECIAL_PRODUCTION')
                if 1<=unit<=5 and any(units[6:10]): continue  # Many cannot enter a Single vector.
                if (tower.owner and not units[9] and (unit or tower.kind==15)
                        and tower.capacity[unit]-units[unit]<2 and tower.supply_line_present is not False):
                    raise UnsupportedState('PRODUCTION_SUPPLY_LINE')
                # add_inner does not truncate pre-existing overflow.
                if units[unit]<tower.capacity[unit]:
                    if units is tower.units: units=list(units)
                    units[unit]+=1
        if units is not tower.units: towers[key]=replace(tower,units=tuple(units))
    remaining=[]
    for index,force in enumerate(forces):
        src,dst=towers[force.source],towers[force.destination]
        speed,required=movement_parameters(force.units,src.position,dst.position)
        if force.accelerated is None:
            earliest=max(1,required*4//5)
            if force.progress+speed>=earliest: raise UnsupportedState('UNKNOWN_ARRIVAL_ACCELERATION')
        elif force.accelerated:
            required=max(1,required*4//5)
        progress=min(255,force.progress+speed)
        if progress<required:
            remaining.append(SimForce(force.owner,force.source,force.destination,force.units,
                                      progress,force.accelerated,force.relation,force.terminal,force.fuel))
            continue
        same_owner_before_arrival=dst.owner==force.owner
        if dst.owner!=force.owner and (dst.owner or any(dst.units)):
            if not (scenario.ground_combat or scenario.ordinary_combat): raise UnsupportedState('UNVERIFIED_NORMAL_COMBAT')
            known_enemy=(dst.owner==state.player and force.relation=='ENEMY' or
                         force.owner==state.player and dst.relation=='ENEMY' or dst.owner==0)
            if not known_enemy: raise UnsupportedState('UNKNOWN_PAIR_RELATION')
            fight=(fight_ordinary(force.units,dst.units,dst.capacity,attacker_morale=force.accelerated,defender_morale=dst.morale)
                   if scenario.ordinary_combat else
                   fight_ground(force.units,dst.units,attacker_morale=force.accelerated,defender_morale=dst.morale))
            if fight.attacker_ruler_lost or fight.defender_ruler_lost:
                raise UnsupportedState('UNVERIFIED_RULER_ELIMINATION')
            towers[dst.id]=dst=replace(dst,units=fight.defender)
            if fight.winner=='DEFENDER': continue  # No future-route knowledge needed.
            if fight.winner is None: raise UnsupportedState('DESTRUCTION_DOWNGRADE')
            force=replace(force,units=fight.attacker)
            periods=production(dst.kind,Units(tuple(enumerate(force.units))),force.owner,dst.delay,dst.morale)
            towers[dst.id]=dst=replace(dst,owner=force.owner,production=periods,
                                      relation=_captured_relation(force.owner,state.player,force.relation),
                                      supply_line_present=False if force.owner==state.player else None)
        if index not in terminals and force.terminal is not True: raise UnsupportedState('UNKNOWN_POST_ARRIVAL_PATH')
        # A terminal ground Many merge (Shield/Tank/Soldier only) into a
        # visibly line-free tower that already had the same owner discards the
        # force at arrival. Pinned arrival ordering does not consult fuel on
        # this branch. This depends on observed absence, never the broader
        # no-supply-line hypothesis; air and special vectors remain guarded.
        unsupported_merge_kinds=(1,2,3,6,7,8,9)
        fuel_irrelevant_merge=(same_owner_before_arrival and
            dst.supply_line_present is False and
            any(force.units[i] for i in (4,5)) and
            not any(force.units[i] for i in unsupported_merge_kinds) and
            not any(dst.units[i] for i in unsupported_merge_kinds))
        if force.fuel is None and not fuel_irrelevant_merge:
            raise UnsupportedState('UNKNOWN_ARRIVAL_FUEL')
        if force.fuel is not None and (force.fuel<0 or
                force.fuel==0 and not fuel_irrelevant_merge):
            raise UnsupportedState('EXPIRED_ARRIVAL')
        if force.units[9]: raise UnsupportedState('RULER_ARRIVAL_AURA')
        if dst.owner==force.owner:
            # A terminal Many force can acquire the destination supply line
            # and move on instead of merging. Ownership changes clear that line;
            # an already friendly destination requires an independent premise.
            if same_owner_before_arrival:
                if dst.supply_line_present is True:
                    raise UnsupportedState('UNSUPPORTED_REINFORCEMENT_SUPPLY_LINE')
                if dst.supply_line_present is not False and dst.id not in no_supply_lines:
                    raise UnsupportedState('UNKNOWN_REINFORCEMENT_SUPPLY_LINE')
            if dst.units[9] and any(force.units[1:6]): raise UnsupportedState('SINGLE_REINFORCEMENT_PRIORITY')
            combined=_merge_arriving_units(dst.units,force.units,dst.capacity,'REINFORCEMENT_OVERFLOW')
            towers[dst.id]=replace(dst,units=combined)
        elif dst.owner==0 and not any(dst.units):
            if not any(force.units[1:6]): raise UnsupportedState('NON_CLAIMING_FORCE')
            merged=_merge_arriving_units(dst.units,force.units,dst.capacity,'CAPTURE_OVERFLOW')
            periods=production(dst.kind,Units(tuple(enumerate(force.units))),force.owner,dst.delay,dst.morale)
            towers[dst.id]=replace(dst,owner=force.owner,units=merged,production=periods,
                                  relation=_captured_relation(force.owner,state.player,force.relation),
                                  supply_line_present=False if force.owner==state.player else None)
        else:
            raise UnsupportedState('UNVERIFIED_NORMAL_COMBAT')
    # Kiomet tick_before_inputs advances the existing world, then inputs create
    # fresh forces applied by tick_after_inputs. New forces are observed at
    # progress zero; do not advance a newly launched force in this same tick.
    for action,is_opponent in [(a,False) for a in actions]+[(a,True) for a in scenario.opponent_launches]:
        if action.source not in towers or action.destination not in towers: raise UnsupportedState('HIDDEN_ACTION_ENDPOINT')
        tower=towers[action.source]
        owner=action.owner if is_opponent else state.player
        if not owner or tower.owner!=owner or action.destination not in tower.neighbors:
            raise UnsupportedState('ILLEGAL_VISIBLE_LAUNCH')
        if isinstance(action,LaunchAll):
            if (type(tower.units) is not tuple or len(tower.units)!=10 or
                    any(type(n) is not int or not 0<=n<=255 for n in tower.units)):
                raise UnsupportedState('INVALID_DEPLOYMENT_INVENTORY')
            units=list(tower.units)
            if any(units[i] for i in (6,7,8,9)):
                raise UnsupportedState('SPECIAL_OR_RULER_LAUNCH')
            if tower.kind!=15: units[0]=0
            if not any(units): raise UnsupportedState('INVALID_LAUNCH_UNITS')
            force_units=tuple(units)
        else:
            if not is_opponent and action.owner not in (None,state.player): raise UnsupportedState('FOREIGN_ACTION_OWNER')
            units=action.units
            force_units=action.units
        if len(units)!=10 or any(type(n) is not int or n<0 for n in units) or not any(units):
            raise UnsupportedState('INVALID_LAUNCH_UNITS')
        if any(units[i] for i in (6,7,8,9)): raise UnsupportedState('SPECIAL_OR_RULER_LAUNCH')
        if units[0] and tower.kind!=15: raise UnsupportedState('IMMOBILE_SHIELDS')
        if any(n>tower.units[i] for i,n in enumerate(units)): raise UnsupportedState('INSUFFICIENT_UNITS')
        towers[tower.id]=replace(tower,units=tuple(n-units[i] for i,n in enumerate(tower.units)))
        # Manual DeployForce reaches Tower::deploy_force (Chunk::apply_0 0x7d542).
        # It copies Tower.morale to Force+21 and initializes progress/fuel via
        # 0x9600 at Force+22/+23; see V2_M2A_LAUNCH_RULE.md.
        remaining.append(SimForce(owner,action.source,action.destination,force_units,0,tower.morale,
                                  'SELF' if owner==state.player else tower.relation,action.terminal,150))
    return SimulationState(sequence,state.player,state.match_epoch,state.document,
                           tuple(towers[key] for key in sorted(towers)),tuple(remaining),
                           state.simulated_ticks+1)
