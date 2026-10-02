import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "v2_enemy_current_leg.py"
spec = importlib.util.spec_from_file_location("enemy_current_leg", MODULE)
ecl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ecl)


def fact(value, source="current segment endpoint intersect current observed towers", knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge, "source": source}


def test_direct_endpoint_uses_current_values_without_derived_route_claim():
    force = {"source": fact(1), "destination": fact(2), "progress": fact(4),
        "relation": fact("ENEMY")}
    towers = {1: {"neighbors": fact([2])}, 2: {"neighbors": fact([1])}}
    result = ecl.classify_current_leg(force, towers, 1)
    assert result["classification"] == "DIRECT_ENDPOINT"
    assert result["owner_class"] == "ENEMY"
    assert result["direct_endpoint"] is True


def test_single_visible_neighbor_remains_candidate_without_route_semantic_proof():
    force = {"source": fact(1), "destination": fact(None, knowledge="UNKNOWN"),
        "progress": fact(0)}
    towers = {1: {"neighbors": fact([2])}, 2: {"neighbors": fact([1])}}
    result = ecl.classify_current_leg(force, towers, 1)
    assert result["classification"] == "CANDIDATE_SET"
    assert result["candidate_targets_or_sources"] == [2]
    assert "no proved force-route/topology rule" in result["reason"]
    assert result["motion_state"] == "ZERO_PROGRESS_NOT_STATIONARY_EVIDENCE"


def test_without_visible_endpoint_anchor_position_or_direction_route_is_unavailable():
    force = {"source": fact(None, knowledge="UNKNOWN"),
        "destination": fact(None, knowledge="UNKNOWN"), "progress": fact(8)}
    result = ecl.classify_current_leg(force, {1: {"neighbors": fact([2])}}, 1)
    assert result["classification"] == "UNAVAILABLE"
    assert result["motion_state"] == "UNKNOWN_MOTION_NO_FORCE_POSITION_OR_DIRECTION"
    assert result["position_field_present"] is False
    assert result["direction_field_present"] is False


def test_known_owner_fallback_never_calls_other_player_an_enemy_without_relation():
    assert ecl.owner_class({"owner": fact(7)}, 7) == "SELF"
    assert ecl.owner_class({"owner": fact(9)}, 7) == "UNKNOWN_OWNER"
    assert ecl.owner_class({"owner": fact(0)}, 7) == "NEUTRAL"


def test_no_unique_predictions_keep_accuracy_unscored_not_zero_percent():
    summary = {"development": {"ENEMY": {
        "eligible": 10, "derived_unique": 0, "true_unique": 0, "false_unique": 0,
        "unscorable": 10, "total": 10, "endpoint_known": 0,
        "input_ready": 0, "current_leg_known": 0}}, "holdout": {"ENEMY": {
        "eligible": 5, "derived_unique": 0, "true_unique": 0, "false_unique": 0,
        "unscorable": 5, "total": 5, "endpoint_known": 0,
        "input_ready": 0, "current_leg_known": 0}}}
    result = ecl._summarize(summary)
    assert result["development"]["ENEMY"]["unique_rate"] == 0
    assert result["development"]["ENEMY"]["false_unique_rate"] is None
    assert result["development"]["ENEMY"]["accuracy_of_unique"] is None
    assert result["holdout"]["ENEMY"]["unique_rate"] == 0
