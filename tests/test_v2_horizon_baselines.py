from tools import v2_horizon_baselines as horizons


def row(n, *, sim=None, reason=None):
    return {"scope": ("doc", "match", 1), "tick": n,
            "sim": n if sim is None else sim, "reason": reason}


def test_continuous_prediction_does_not_reset_to_observed_future():
    rows = [row(0), row(1), row(2, sim=99), row(3)]
    trace = []
    def step(state):
        trace.append(state)
        return state + 1
    result = horizons._continuous(rows, 0, step, lambda s: s)
    assert trace == [0, 1]
    assert result["clean_ticks"] == 1
    assert result["first_stop"] == {"offset": 2, "kind": "MISMATCH", "reason": "EXACT_OBSERVABLE_SIGNATURE_MISMATCH"}
    assert result["outcomes"]["1"] == "EXACT_MATCH"
    assert result["outcomes"]["2"] == "MISMATCH"


def test_unknown_refusal_and_recording_end_remain_distinct_censors():
    def blocked(_):
        raise horizons.coverage.UnsupportedState("UNKNOWN_POST_ARRIVAL_PATH")
    unknown = horizons._continuous([row(0), row(1)], 0, blocked, lambda s: s)
    assert unknown["outcomes"]["1"] == "CENSORED_BY_UNKNOWN"
    end = horizons._continuous([row(0), row(1)], 0, lambda s: s + 1, lambda s: s)
    assert end["outcomes"]["1"] == "EXACT_MATCH"
    assert end["outcomes"]["2"] == "RIGHT_CENSORED_RECORDING_END"


def test_gap_or_unavailable_observed_endpoint_never_receives_forecast_credit():
    gap = horizons._continuous([row(0), row(2)], 0, lambda s: s + 1, lambda s: s)
    assert gap["clean_ticks"] == 0
    after = row(1); after["sim"] = None; after["reason"] = "NOT_READY"
    unknown = horizons._continuous([row(0), after], 0, lambda s: s + 1, lambda s: s)
    assert unknown["first_stop"]["reason"] == "OBSERVED_ENDPOINT:NOT_READY"


def test_velocity_requires_before_only_unique_unchanged_leg_and_two_samples():
    before = {"owner": 1, "source": 10, "destination": 11, "units": (0, 1),
              "progress": 7, "confidence": "UNIQUE_CONTINUATION"}
    current = {**before, "progress": 10}
    assert horizons.velocity_prediction(before, current) == 13
    assert horizons.velocity_prediction(None, current) is None
    assert horizons.velocity_prediction(before, {**current, "destination": 12}) is None
    assert horizons.velocity_prediction(before, {**current, "confidence": "NEW_TRACK"}) is None
    assert horizons.velocity_prediction(before, {**current, "progress": 3}) is None


def test_duplicate_or_unavailable_force_identity_is_not_a_baseline_track():
    fact = lambda v: {"value": v}
    force = {"id": fact("same"), "visibility": fact(True)}
    raw = {"towers": [], "forces": fact([force, force])}
    assert horizons._slim(raw)["forces"] == {}
    assert horizons._slim(raw)["force_count"] == 2
    assert horizons._slim({"towers": [], "forces": fact(None)})["force_count"] is None
