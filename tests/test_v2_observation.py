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
    assert state.age_bounds_ms(510) == (195,310)
    assert "freshness" in state.readiness_gaps(510)
    # A recent client application cannot certify server-state freshness.
    recent=replace(state,source_update_window_ms=Fact((300,500),Knowledge.DERIVED,'test client apply',500))
    assert recent.age_bounds_ms(510)==(10,210)
    assert "freshness" in recent.readiness_gaps(510)


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
