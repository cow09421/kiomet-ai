from tools import v2_owner_endpoint_census as census


def fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge, "source": "fixture",
            "observed_at_ms": 1 if knowledge != "UNKNOWN" else None, "valid": True}


def test_owner_class_requires_consistent_relation_and_player_identity():
    assert census.owner_class(fact(5), fact("SELF"), 5) == "SELF"
    assert census.owner_class(fact(8), fact("ALLY"), 5) == "ALLY"
    assert census.owner_class(fact(5), fact("ENEMY"), 5) == "UNKNOWN_OWNER"
    assert census.owner_class(fact(None, "UNKNOWN"), fact(None, "UNKNOWN"), 5) == "UNKNOWN_OWNER"


def test_local_readiness_and_current_leg_are_separate():
    tower = {i: {"visibility": fact(True)} for i in (10, 11)}
    force = {"source": fact(10), "destination": fact(11), "owner": fact(5),
        "relation": fact("SELF"), "progress": fact(0), "unit_count": fact(2),
        "units": fact({"counts": [[i, 2 if i == 0 else 0] for i in range(10)]})}
    ready = census._init_counts()
    census._add(ready, force, 5, set(), 0, tower)
    assert ready["endpoint_known"] == 1 and ready["input_ready"] == 1
    assert ready["current_leg_known"] == 1
    blocked = census._init_counts()
    census._add(blocked, force, 5, {0}, 0, tower)
    assert blocked["input_blocked"] == 1
    assert blocked["current_leg_known"] == 1


def test_partial_endpoint_and_bad_unit_sum_do_not_become_known():
    towers = {10: {"visibility": fact(True)}}
    force = {"source": fact(10), "destination": fact(None, "UNKNOWN"),
        "owner": fact(5), "relation": fact("SELF"), "progress": fact(0),
        "unit_count": fact(2), "units": fact({"counts": [[i, 2 if i == 0 else 0] for i in range(10)]})}
    counts = census._init_counts()
    census._add(counts, force, 5, set(), 0, towers)
    assert counts["endpoint_unknown"] == 1
    assert counts["endpoint_pair_source_only"] == 1
    assert counts["input_blocked"] == 1 and counts["current_leg_unknown"] == 1
    force["destination"] = fact(11)
    force["units"] = fact({"counts": [[i, 1 if i == 0 else 0] for i in range(10)]})
    counts = census._init_counts()
    census._add(counts, force, 5, set(), 0, {**towers, 11: {"visibility": fact(True)}})
    assert counts["endpoint_known"] == 1
    assert counts["current_leg_unknown"] == 1
