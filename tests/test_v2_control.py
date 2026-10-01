from dataclasses import replace
from kiomet_ai.v2.state import Fact, Knowledge
from kiomet_ai.v2.control import control_readiness_gaps, ControlTime
from kiomet_ai.v2.observe.source_clock import SourceClock
from kiomet_ai.v2.observe.lifecycle import MatchLifecycle
from test_v2_observation import ready_force_fixture


def control_fixture():
    state=ready_force_fixture()
    return replace(state,updated_at_ms=Fact(),
        world_sequence_observed_at_ms=Fact(100,Knowledge.OBSERVED,'test observation',100),
        lifecycle=Fact('IN_MATCH',Knowledge.DERIVED,'test lifecycle',100))


def test_m1b_accepts_unknown_server_age_and_permanent_force_id():
    state=control_fixture()
    force=replace(state.forces.value[0],id=Fact(),first_seen_ms=Fact(),eta_ms=Fact())
    state=replace(state,forces=replace(state.forces,value=(force,)))
    assert 'freshness' in state.readiness_gaps(101)  # Historical gate unchanged.
    assert control_readiness_gaps(state,101)==()
    assert ControlTime.from_state(state).world_sequence_observed_at==100


def test_stale_repeated_capture_does_not_refresh_control_source():
    state=replace(control_fixture(),sampled_at_ms=1200,received_at_ms=1201)
    assert 'source_continuity' in control_readiness_gaps(state,1201)
    assert 'source_continuity' in control_readiness_gaps(state,True)


def test_hidden_force_endpoint_still_blocks_minimum_world():
    state=control_fixture()
    force=replace(state.forces.value[0],source=Fact())
    assert 'force:0:source' in control_readiness_gaps(replace(state,forces=replace(state.forces,value=(force,))),101)
    assert 'match_id' in control_readiness_gaps(replace(state,match_id=Fact()),101)


def test_world_order_wrap_is_forward_but_backward_is_not_fresh():
    clock=SourceClock()
    clock.observe(('scope',),65535,100,101,100.)
    clock.observe(('scope',),0,350,351,350.)
    assert clock.observed_at_ms==351
    clock.observe(('scope',),0,400,401,400.)
    assert clock.observed_at_ms==351
    clock.observe(('scope',),65535,450,451,450.)
    assert clock.window is None and clock.observed_at_ms is None


def test_backward_live_sequence_invalidates_epoch():
    life=MatchLifecycle('doc')
    raw={'document_time_origin':1,'player_id':7,'active':True,'transport_connected':True,
         'online':True,'transport_mode':'NETWORK','tick':500}
    _,epoch=life.observe(raw,100)
    assert epoch is not None
    _,backwards=life.observe(dict(raw,tick=499),350)
    assert backwards is None and life.invalidated
