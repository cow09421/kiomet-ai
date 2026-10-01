"""M1B tick-relative control gate; the historical M1 readiness stays unchanged."""
from dataclasses import dataclass
from .state import GameState, Knowledge, Lifecycle

CLIENT_PIN='fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c'


@dataclass(frozen=True, slots=True)
class ControlTime:
    world_sequence: int
    world_sequence_observed_at: int
    state_extracted_at: int
    match_epoch: str
    document_identity: str
    source_mode: str

    @classmethod
    def from_state(cls, state: GameState):
        at=state.world_sequence_observed_at_ms.value
        if at is None and state.source_update_window_ms.value is not None:
            # Legacy recorded cohorts have a client-application bracket, not
            # the new exact first-observation field. Its upper endpoint is a
            # conservative observation cue; never relabel it server time.
            at=state.source_update_window_ms.value[1]
        if at is None or state.tick.value is None or state.match_id.value is None:
            return None
        return cls(state.tick.value,at,state.received_at_ms,state.match_id.value,
                   state.document_id,state.source_mode.value)


def control_readiness_gaps(state: GameState, now_ms: int, stall_ms: int=1000):
    """Minimum observable world inputs, independent of absolute server age.

    This certifies input availability only. The simulator independently rejects
    unsupported mechanics and unobserved events; it is not command permission.
    """
    gaps=[]
    timing=ControlTime.from_state(state)
    if state.client_sha256!=CLIENT_PIN: gaps.append('client_version')
    if state.lifecycle.value!=Lifecycle.IN_MATCH: gaps.append('lifecycle')
    if state.source_mode.value!='NETWORK': gaps.append('source_mode')
    for name in ('match_id','tick','player_id','forces'):
        if getattr(state,name).knowledge==Knowledge.UNKNOWN: gaps.append(name)
    if (type(now_ms) is not int or now_ms<state.received_at_ms or timing is None or
            not 0<=now_ms-timing.world_sequence_observed_at<=stall_ms):
        gaps.append('source_continuity')
    if state.coverage!='PLAYER_VISIBLE_COMPLETE': gaps.append('coverage')
    if not state.towers: gaps.append('towers')
    for tower in state.towers:
        for name in ('owner','relation','tower_type','units','deployable','capacity',
                     'production','position','neighbors','delay_ticks','effects'):
            if getattr(tower,name).knowledge==Knowledge.UNKNOWN:
                gaps.append(f'tower:{tower.id}:{name}')
    for index,force in enumerate(state.forces.value or ()):
        for name in ('owner','relation','source','destination','units','unit_count','progress'):
            if getattr(force,name).knowledge==Knowledge.UNKNOWN:
                gaps.append(f'force:{index}:{name}')
    return tuple(gaps)
