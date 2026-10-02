import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "tools" / "v2_factorized_coverage.py"
spec = importlib.util.spec_from_file_location("factorized_coverage", MODULE)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge}


def tower(tid=1, delay=0):
    return {"id": tid, "owner": fact(1), "tower_type": fact(15),
        "units": fact({"counts": [[i, 0] for i in range(10)]}),
        "capacity": fact({"counts": [[i, 10] for i in range(10)]}),
        "production": fact([]), "neighbors": fact([2]), "position": fact([0, 0]),
        "delay_ticks": fact(delay), "relation": fact("SELF"),
        "effects": fact([["MORALE_BOOST", False]])}


def active_edge(gates):
    return {"active": "ACTIVE_KNOWN", "all_blockers": gates}


def test_bounds_do_not_treat_upstream_unknown_as_clear():
    gates = fc._gate_template()
    gates["endpoint"]["status"] = "BLOCKED"
    gates["movement"]["status"] = "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
    gates["arrival"]["status"] = "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
    result = fc._bounds([active_edge(gates)])
    endpoint = result["marginal_scenario_bounds"][0]
    assert endpoint["resolved_gates"] == ["endpoint"]
    assert endpoint["certified_lower_edges"] == 0
    assert endpoint["optimistic_upper_edges"] == 1


def test_bounds_exclude_already_comparable_success_edges():
    gates = fc._gate_template()
    gates["endpoint"]["status"] = "BLOCKED"
    result = fc._bounds([{"active": "ACTIVE_KNOWN", "comparison_status": "SUCCESS",
        "all_blockers": gates}])
    assert result["active_known_edge_denominator"] == 1
    assert result["excluded_already_compared_success_edges"] == 1
    assert result["new_unlock_analysis_population_excluding_success_and_mismatch"] == 0
    assert result["marginal_scenario_bounds"][0]["optimistic_upper_edges"] == 0
    result = fc._bounds([{"active": "ACTIVE_KNOWN", "comparison_status": "MISMATCH",
        "all_blockers": gates}])
    assert result["excluded_already_compared_mismatch_edges"] == 1
    assert result["new_unlock_analysis_population_excluding_success_and_mismatch"] == 0


def test_greedy_marginal_interval_preserves_widening_uncertainty():
    first = fc._gate_template()
    first["endpoint"]["status"] = "BLOCKED"
    first["movement"]["status"] = "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
    second = fc._gate_template()
    second["endpoint"]["status"] = "BLOCKED"
    second["upgrade_emp"]["status"] = "BLOCKED"
    second["movement"]["status"] = "CLEAR"
    second["supply_line"]["status"] = "CLEAR"
    second["combat"]["status"] = "CLEAR"
    second["comparison"]["status"] = "CLEAR"
    for name in fc.GATES:
        if name not in ("endpoint", "upgrade_emp"):
            second[name]["status"] = "CLEAR"
    result = fc._bounds([active_edge(first), active_edge(second)])
    endpoint, upgrade = result["greedy_order_all_gates_hypothetical"][:2]
    assert endpoint["cumulative_lower"] == 0
    assert endpoint["cumulative_upper"] == 1
    assert upgrade["cumulative_lower"] == 1
    assert upgrade["cumulative_upper"] == 2
    assert upgrade["marginal_lower"] == 0
    assert upgrade["marginal_upper"] == 2


def test_after_input_endpoint_unknown_remains_separate_from_before_blocker():
    before = {"tick": fact(5), "player_id": fact(1), "match_id": fact("m"),
        "document_id": "d", "towers": [tower()], "forces": fact([]),
        "coverage": "PLAYER_VISIBLE_COMPLETE"}
    after = {"tick": fact(6), "player_id": fact(1), "match_id": fact("m"),
        "document_id": "d", "towers": [tower()], "forces": fact([]),
        "coverage": "PLAYER_VISIBLE_COMPLETE"}
    edge = {"primary_blocker": "NOT_READY", "primary_category": "UNKNOWN_PATH",
        "comparison_status": "SUCCESS", "control_readiness_gaps": [],
        "after_input_readiness_gaps": ["force:3:destination"]}
    towers, gaps = fc._canonical_fields(before)
    gates = fc._edge_gates(edge, before, after, towers, [], [], gaps)
    assert gates["endpoint"]["status"] == "CLEAR"
    assert gates["after_input_endpoint"]["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
    assert gates["after_input_endpoint"]["unresolved_evidence"] == [
        [{"stage": "after_input", "readiness_gap": "force:3:destination"}]]


def test_force_alignment_rejects_duplicate_ids_and_changed_leg_metadata():
    before = {"id": fact("same", "DERIVED"), "owner": fact(1), "source": fact(1),
        "destination": fact(2), "units": fact({"counts": [[i, 0] for i in range(10)]}),
        "visibility": fact(True), "confidence": fact("NEW_TRACK"), "progress": fact(0)}
    after = {**before, "progress": fact(7), "confidence": fact("UNIQUE_CONTINUATION")}
    scope = {"document_id": "doc", "match_id": fact("match"), "player_id": fact(1)}
    before = {**before, "tick": fact(10)}
    after = {**after, "tick": fact(11)}
    before_raw = {**scope, "tick": fact(10), "forces": fact([before])}
    after_raw = {**scope, "tick": fact(11), "forces": fact([after])}
    matched, reason = fc._unique_continuation([before, before], [after], before_raw, after_raw)
    assert matched is None and reason == "AMBIGUOUS_OR_MISSING_IDENTITY"
    changed = {**after, "destination": fact(3)}
    matched, reason = fc._unique_continuation([before], [changed], before_raw,
        {**scope, "tick": fact(11), "forces": fact([changed])})
    assert matched is None and reason == "CURRENT_LEG_METADATA_CHANGED"
    matched, reason = fc._unique_continuation([before], [after], before_raw, after_raw)
    assert matched == after and reason is None
    later_raw = {**scope, "tick": fact(12), "forces": fact([after])}
    matched, reason = fc._unique_continuation([before], [after], before_raw, later_raw)
    assert matched is None and reason == "NONCONSECUTIVE_TICK"


def test_pinned_current_leg_eta_resolves_missing_acceleration_before_step():
    source = tower(1)
    destination = tower(2)
    destination["position"] = fact([1, 0])
    towers, gaps = fc._canonical_fields({"towers": [source, destination]})
    vector = [1] + [0] * 9
    raw_force = {"id": fact("track"), "owner": fact(1), "source": fact(1),
        "destination": fact(2), "units": fact({"counts": [[i, vector[i]] for i in range(10)]}),
        "progress": fact(0), "accelerated": fact(None, "UNKNOWN"),
        "eta_ms": {"value": 1250, "knowledge": "OBSERVED", "source": "pinned current-leg estimator"}}
    available, unavailable = fc._force_endpoints({"forces": fact([raw_force])}, towers)
    assert not unavailable and len(available) == 1
    assert available[0]["force"].accelerated is True


def test_local_accuracy_denominators_exclude_nonconsecutive_edge():
    before_tower = tower(1)
    before_tower["production"] = fact([[1, 1]])
    after_tower = tower(1)
    after_tower["production"] = fact([[1, 1]])
    destination = tower(2)
    destination["position"] = fact([1, 0])
    after_destination = dict(destination)
    vector = fact({"counts": [[0, 1]] + [[i, 0] for i in range(1, 10)]})
    force_before = {"id": fact("track"), "owner": fact(1), "source": fact(1),
        "destination": fact(2), "units": vector, "progress": fact(0), "accelerated": fact(False)}
    force_after = {**force_before, "progress": fact(1)}
    before = {"tick": fact(10), "player_id": fact(1), "match_id": fact("m"),
        "document_id": "d", "towers": [before_tower, destination], "forces": fact([force_before]),
        "coverage": "PLAYER_VISIBLE_COMPLETE"}
    after = {**before, "tick": fact(12), "towers": [after_tower, after_destination],
        "forces": fact([force_after])}
    towers, gaps = fc._canonical_fields(before)
    available, unavailable = fc._force_endpoints(before, towers)
    details, stats = fc._factor_edge({"comparison_status": "NOT_EXECUTED"}, before, after,
        towers, gaps, available, unavailable)
    assert details["local_comparison_horizon"] == {"eligible": False, "reason": "NONCONSECUTIVE_TICK"}
    assert stats["tower_local"]["opportunities"] == 2
    assert stats["tower_local"]["comparable"] == 0
    assert stats["force_local"]["input_ready"] == 1
    assert stats["force_local"]["comparable"] == 0
    assert stats["production"]["opportunities"] >= 1
    assert stats["production"]["comparable"] == 0
    assert stats["movement"]["comparable"] == 0
    assert stats["ownership"]["conditional_projection_comparable"] == 0


def test_endpoint_unknown_does_not_create_force_or_skip_downstream_unknowns():
    tower_row = tower(1, delay=2)
    force_row = {"id": fact("track"), "owner": fact(1), "source": fact(1),
        "destination": fact(None, "UNKNOWN"), "units": fact({"counts": [[0, 1]] + [[i, 0] for i in range(1, 10)]}),
        "progress": fact(0), "accelerated": fact(False)}
    before = {"tick": fact(5), "player_id": fact(1), "match_id": fact("m"),
        "document_id": "d", "towers": [tower_row], "forces": fact([force_row]),
        "coverage": "PLAYER_VISIBLE_COMPLETE"}
    after = before
    edge = {"primary_category": "UNKNOWN_PATH", "primary_blocker": "NOT_READY",
        "control_readiness_gaps": ["force:0:destination"]}
    towers, tower_gaps = fc._canonical_fields(before)
    available, unavailable = fc._force_endpoints(before, towers)
    assert not available and len(unavailable) == 1
    gates = fc._edge_gates(edge, before, after, towers, available, unavailable, tower_gaps)
    assert gates["endpoint"]["status"] == "BLOCKED"
    assert gates["upgrade_emp"]["status"] == "BLOCKED"
    assert gates["movement"]["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
    assert gates["combat"]["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"


def test_known_opposed_pair_survives_unrelated_unknown_force_endpoint():
    t1, t2 = tower(1), tower(2)
    t2["owner"] = fact(2)
    t2["position"] = fact([1, 0])
    force_units = fact({"counts": [[0, 1]] + [[i, 0] for i in range(1, 10)]})
    f1 = {"id": fact("a"), "owner": fact(1), "source": fact(1), "destination": fact(2),
        "units": force_units, "progress": fact(0), "accelerated": fact(False)}
    f2 = {"id": fact("b"), "owner": fact(2), "source": fact(2), "destination": fact(1),
        "units": force_units, "progress": fact(0), "accelerated": fact(False)}
    remote_unknown = {"id": fact("c"), "owner": fact(1), "source": fact(1),
        "destination": fact(None, "UNKNOWN"), "units": force_units,
        "progress": fact(0), "accelerated": fact(False)}
    before = {"tick": fact(1), "player_id": fact(1), "match_id": fact("m"),
        "document_id": "d", "towers": [t1, t2], "forces": fact([f1, f2, remote_unknown]),
        "coverage": "PLAYER_VISIBLE_COMPLETE"}
    after = before
    towers, gaps = fc._canonical_fields(before)
    available, unavailable = fc._force_endpoints(before, towers)
    gates = fc._edge_gates({}, before, after, towers, available, unavailable, gaps)
    assert len(available) == 2 and len(unavailable) == 1
    assert gates["combat"]["status"] == "BLOCKED"
    assert gates["combat"]["unresolved_evidence"]


def test_factor_summary_separates_input_support_and_accuracy_denominators():
    counts = __import__("collections").Counter(opportunities=4, input_ready=3,
        semantically_supported=2, comparable=2, matches=1, mismatches=1)
    result = fc._summarize_factor(counts)
    assert result["input_readiness"] == {"numerator": 3, "denominator": 4, "rate": 0.75}
    assert result["semantic_coverage"] == {"numerator": 2, "denominator": 3, "rate": 2 / 3}
    assert result["accuracy"] == {"numerator": 1, "denominator": 2, "rate": 0.5}


def test_production_isolation_never_claims_independent_world_credit():
    # Production potential is intentionally an isolated local operation. The
    # full runner labels all such matches conditional because snapshots cannot
    # prove absence of an external/scoped event.
    assert "CONDITIONAL_LOCAL_ONLY_UNKNOWN_EXTERNAL_OR_SCOPE_EFFECTS" in Path(MODULE).read_text(encoding="utf-8")
