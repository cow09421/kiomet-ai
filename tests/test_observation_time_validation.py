"""Observation freshness must reject non-causal or malformed clock values."""
import math

import pytest

from kiomet_ai.observe import MatchObservation, RealTowerState, gate_check


@pytest.mark.parametrize("timestamp", [
    1000.001,
    math.nan,
    math.inf,
    -math.inf,
    True,
    "1000",
])
def test_match_observation_does_not_mark_future_or_invalid_time_fresh(timestamp):
    observation = MatchObservation(match_id="m1", timestamp=timestamp)

    assert observation.freshness("m1", now=1000.0) == "UNKNOWN"
    assert gate_check(observation, "m1", now=1000.0)[0] is False


@pytest.mark.parametrize("timestamp", [
    1000.001,
    math.nan,
    math.inf,
    -math.inf,
    True,
    "1000",
])
def test_real_tower_state_does_not_mark_future_or_invalid_time_fresh(timestamp):
    state = RealTowerState(tower_id=1, match_id="m1", timestamp=timestamp)

    assert state.freshness("m1", now=1000.0) == "UNKNOWN"


@pytest.mark.parametrize("now", [math.nan, math.inf, -math.inf, True, "1000"])
def test_invalid_current_time_cannot_make_observation_fresh(now):
    observation = MatchObservation(match_id="m1", timestamp=999.0)
    state = RealTowerState(tower_id=1, match_id="m1", timestamp=999.0)

    assert observation.freshness("m1", now=now) == "UNKNOWN"
    assert state.freshness("m1", now=now) == "UNKNOWN"


def test_freshness_boundary_and_old_observation_keep_existing_semantics():
    at_boundary = MatchObservation(match_id="m1", timestamp=970.0)
    just_old = RealTowerState(tower_id=1, match_id="m1", timestamp=969.999)

    assert at_boundary.freshness("m1", now=1000.0) == "FRESH"
    assert just_old.freshness("m1", now=1000.0) == "STALE"
