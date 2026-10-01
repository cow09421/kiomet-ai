from dataclasses import FrozenInstanceError, replace
import pytest

from kiomet_ai.v2.state import Fact, GameState, Knowledge, Tower, Units
from kiomet_ai.v2.observe.extractor import decode_many, normalize
from kiomet_ai.v2.observe.source_clock import SourceClock


def fact(value):
    return Fact(value, Knowledge.OBSERVED, "test-only", 100)


def raw():
    return {"sampled_at_ms": 100, "player_id": 7, "towers": [{
        "id": 3, "visible": True, "visibility_source": "test-only visibility",
        "owner": 0, "relation": "NEUTRAL", "type": 14,
        "units7": [0, 1, 2, 3, 4, 5, 6], "position": [100, 200]}]}


def test_unknown_is_not_observed_zero_or_empty():
    assert Fact().value is None
    assert fact(0).knowledge == Knowledge.OBSERVED
    assert fact(()).knowledge == Knowledge.OBSERVED
    with pytest.raises(ValueError):
        Fact(0)
    with pytest.raises(ValueError):
        Fact(None, Knowledge.OBSERVED, "test", 100)


def test_state_and_nested_values_are_immutable():
    state = normalize(raw(), "session", "document", 1, 101)
    with pytest.raises(FrozenInstanceError):
        state.sequence = 2
    with pytest.raises(TypeError):
        fact([1, 2])
    with pytest.raises(ValueError):
        Units(((1, 2), (1, 3)))


def test_hidden_entity_and_hidden_graph_endpoints_are_rejected():
    payload = raw()
    payload["towers"][0]["visible"] = False
    with pytest.raises(ValueError, match="visibility"):
        normalize(payload, "s", "d", 1, 101)
    tower = Tower(3, fact(True), neighbors=fact((99,)))
    with pytest.raises(ValueError, match="unobserved"):
        GameState("s", "d", Fact(), 1, 100, 101, "version", towers=(tower,))


def test_complete_sensor_actor_coverage_requires_count_and_live_gates():
    payload=raw()
    payload.update(coverage='PLAYER_VISIBLE_COMPLETE',positive_refs=1,
        transport_mode='NETWORK',active=True,visible_pending=False,online=True,
        transport_connected=True,expanded_visibility=False,play_text=None)
    state=normalize(payload,'s','d',1,101)
    assert state.coverage=='PLAYER_VISIBLE_COMPLETE'
    assert state.coverage_evidence.knowledge==Knowledge.DERIVED
    assert 'freshness' in state.readiness_gaps(101)
    for change in ({'positive_refs':2},{'visible_pending':True},
            {'transport_connected':False},{'expanded_visibility':True}):
        with pytest.raises(ValueError,match='coverage'):
            normalize(dict(payload,**change),'s','d',1,101)
    partial=normalize(dict(payload,coverage='PARTIAL',positive_refs=2),'s','d',1,101)
    assert partial.coverage=='PARTIAL' and partial.coverage_evidence.knowledge==Knowledge.UNKNOWN
    with pytest.raises(ValueError,match='coverage'):
        replace(partial,coverage='PLAYER_VISIBLE_COMPLETE')


def test_many_units_are_typed_and_single_stays_unknown():
    assert dict(decode_many([0, 1, 2, 3, 4, 5, 6]).counts) == {
        0: 6, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 0, 7: 0, 8: 0, 9: 0}
    assert decode_many([1, 1, 9, 0, 0, 0, 30]) is None
    for malformed in ([2, 0, 0, 0, 0, 0, 0], [0, -1, 0, 0, 0, 0, 0], [0]):
        with pytest.raises(ValueError):
            decode_many(malformed)


def test_polling_never_claims_authoritative_freshness_or_readiness():
    state = normalize(raw(), "s", "d", 1, 101)
    assert state.age_ms(101) is None
    assert "freshness" in state.readiness_gaps(101)
    assert "match_id" in state.readiness_gaps(101)
    assert "forces" in state.readiness_gaps(101)
    known_update = replace(state, updated_at_ms=fact(100))
    assert replace(known_update, sampled_at_ms=1000, received_at_ms=1001).age_ms(1001) == 901


def test_browser_clock_skew_does_not_reorder_host_capture():
    payload = raw()
    payload["sampled_at_ms"] = 1002
    state = normalize(payload, "s", "d", 1, 1001, sample_started_ms=1000)
    assert state.sampled_at_ms == 1000
    assert state.client_sampled_at_ms.value == 1002
    assert state.age_ms(1001) is None


def ready_force_fixture():
    # Synthetic readiness isolation, never a live age/coverage certificate.
    payload = raw()
    payload['towers'][0].update(owner=7, relation='SELF', units7=[1,1,9,0,0,0,6],
        morale=1, delay_ticks=0, neighbors=[4])
    payload['towers'].append(dict(payload['towers'][0], id=4, owner=0,
        relation='NEUTRAL', units7=[0,0,0,0,0,0,0], position=[105,200],
        morale=0, neighbors=[3]))
    payload.update(tick=55, coverage='PLAYER_VISIBLE_COMPLETE', positive_refs=2,
        transport_mode='NETWORK', active=True, visible_pending=False, online=True,
        transport_connected=True, expanded_visibility=False, play_text=None,
        own_tower_counts=[0]*27, forces=[dict(visible=True, visibility_source='test-only',
            owner=7, relation='SELF', source=3, destination=4,
            units7=[0,0,0,0,0,3,0], progress=0, accelerated=0)])
    state = normalize(payload, 's', 'd', 1, 101, match_identity='test-epoch')
    return replace(state, updated_at_ms=fact(100))


def test_observed_force_collection_does_not_clear_unknown_member_fields():
    state = ready_force_fixture()
    assert state.readiness_gaps(101) == ()
    force = state.forces.value[0]
    assert force.launch_ms.knowledge == Knowledge.UNKNOWN  # Never invent a launch clock.
    partial = replace(force, source=Fact(), eta_ms=Fact())
    gaps = replace(state, forces=fact((partial,))).readiness_gaps(101)
    assert 'force:0:source' in gaps and 'force:0:eta_ms' in gaps
    assert 'forces' not in gaps  # The collection is observed; its geometry is unavailable.
    ambiguous = replace(force, id=Fact(), first_seen_ms=Fact())
    assert 'force:0:id' in replace(state, forces=fact((ambiguous,))).readiness_gaps(101)


def test_observed_empty_forces_and_unavailable_forces_have_different_readiness():
    state = ready_force_fixture()
    assert replace(state, forces=fact(())).readiness_gaps(101) == ()
    assert 'forces' in replace(state, forces=Fact()).readiness_gaps(101)


def test_malformed_and_duplicate_towers_do_not_enter_state():
    payload = raw()
    payload["towers"].append(dict(payload["towers"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        normalize(payload, "s", "d", 1, 101)
    with pytest.raises(ValueError, match="receipt"):
        normalize(raw(), "s", "d", 1, 99)


def test_source_clock_requires_a_real_transition_and_bounds_uncertainty():
    clock = SourceClock()
    key = ("doc", 400, 7)
    assert clock.observe(key, 55, 100, 110, 1000) is None
    assert clock.observe(key, 55, 200, 210, 1100) is None
    assert clock.observe(key, 56, 300, 315, 1200) == (200, 315)
    # Polling a frozen world must age its prior source update, not refresh it.
    assert clock.observe(key, 56, 500, 510, 1400) == (200, 315)
    payload = raw()
    payload["tick"] = 56
    state = normalize(payload, "s", "d", 1, 510, 500, update_window=(200,315))
    assert state.tick.knowledge == Knowledge.OBSERVED
    assert state.source_update_window_ms.knowledge == Knowledge.DERIVED
    assert state.updated_at_ms.knowledge == Knowledge.UNKNOWN
    assert state.age_ms(510) is None
    assert state.age_bounds_ms(510) == (194,311)
    assert "freshness" in state.readiness_gaps(510)
    # A recent client application cannot certify server-state freshness.
    recent=replace(state,source_update_window_ms=Fact((300,500),Knowledge.DERIVED,'test client apply',500))
    assert recent.age_bounds_ms(510)==(9,211)
    assert "freshness" in recent.readiness_gaps(510)
    edge=replace(state,source_update_window_ms=Fact((260,500),Knowledge.DERIVED,'quantized client apply',500))
    assert edge.age_bounds_ms(510)==(9,251)


def test_source_clock_resets_for_identity_clock_discontinuity_and_long_gap():
    clock = SourceClock()
    a = ("d1",400,7)
    clock.observe(a,65535,100,101,1000)
    assert clock.observe(a,0,200,201,1100) == (100,201)
    assert clock.observe(a,0,1500,1501,2400) is None
    assert clock.observe(a,1,1600,1601,2500) == (1500,1601)
    assert clock.observe(("d2",400,7),2,1700,1701,2600) is None
    assert clock.observe(("d2",400,8),3,1800,1801,2700) is None
    assert clock.observe(("d2",400,8),4,2800,2801,2800) is None
    with pytest.raises(ValueError,match="window"):
        GameState("s","d",Fact(),1,100,101,"v",tick=fact(1),
                  source_update_window_ms=fact((100,102)))
