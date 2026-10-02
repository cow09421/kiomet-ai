import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "tools" / "v2_coverage_denominator.py"
spec = importlib.util.spec_from_file_location("coverage_denominator", MODULE)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def fact(value, knowledge="KNOWN", **extra):
    return {"value": value, "knowledge": knowledge, **extra}


def tower(units=(1, 0, 0, 0, 0, 0, 0, 0, 0, 0), effects=(), line=None, visible=True):
    return {
        "id": 10,
        "visibility": fact(visible),
        "owner": fact(1),
        "relation": fact("OWN"),
        "tower_type": fact("TOWER"),
        "units": fact({"counts": list(enumerate(units))}) if units is not None else fact(None, "UNKNOWN"),
        "capacity": fact({"counts": list(enumerate((5,) * 10))}),
        "production": fact([[0, 2]]),
        "neighbors": fact([11]),
        "position": fact([0, 0]),
        "delay_ticks": fact(0),
        "effects": fact(list(effects)),
        "supply_line_present": line,
        "host_timestamp": "ignore-me",
    }


def raw(rows, coverage_value="PLAYER_VISIBLE_COMPLETE", forces=None, tick=1, scope="m"):
    return {"document_id": "d", "match_id": fact(scope), "player_id": fact(1),
            "tick": fact(tick), "coverage": coverage_value,
            "towers": rows, "forces": fact(forces or []),
            "received_at_ms": tick * 1000}


def test_knowledge_and_observer_metadata_do_not_create_activity():
    a = raw([tower()]); b = raw([tower()], tick=2)
    b["received_at_ms"] += 50000
    b["forces"] = fact([] , source="different observer provenance")
    assert coverage._active(coverage._raw_semantic_signature(a),
                            coverage._raw_semantic_signature(b)) == "INACTIVE"


def test_known_effects_and_known_optional_supply_line_changes_are_activity():
    a = raw([tower(effects=[["MORALE_BOOST", True], ["OTHER", 4]], line=fact(False))])
    b = raw([tower(effects=[["MORALE_BOOST", True], ["OTHER", 5]], line=fact(False))], tick=2)
    assert coverage._active(coverage._raw_semantic_signature(a),
                            coverage._raw_semantic_signature(b)) == "ACTIVE_KNOWN"
    c = raw([tower(effects=[["MORALE_BOOST", True], ["OTHER", 4]], line=fact(True))], tick=2)
    assert coverage._active(coverage._raw_semantic_signature(a),
                            coverage._raw_semantic_signature(c)) == "ACTIVE_KNOWN"


def test_optional_unknown_supply_line_does_not_make_signature_unknown():
    a, b = raw([tower()]), raw([tower()], tick=2)
    sa, sb = coverage._raw_semantic_signature(a), coverage._raw_semantic_signature(b)
    assert sa[1] and sb[1]
    assert coverage._active(sa, sb) == "INACTIVE"


def test_unknown_to_known_and_visible_set_change_are_activity_unknown():
    known = coverage._raw_semantic_signature(raw([tower()]))
    unknown = coverage._raw_semantic_signature(raw([tower(units=None)]))
    assert coverage._active(unknown, known) == "ACTIVE_UNKNOWN"
    hidden = coverage._raw_semantic_signature(raw([tower(visible=False)]))
    assert coverage._active(hidden, known) == "ACTIVE_UNKNOWN"


def test_same_known_tower_field_difference_is_activity_even_with_other_unknowns():
    a = coverage._raw_semantic_signature(raw([tower(units=None)]))
    b = coverage._raw_semantic_signature(raw([tower(units=None, effects=[["MORALE_BOOST", False]])], tick=2))
    assert coverage._active(a, b) == "ACTIVE_KNOWN"


def test_partial_force_known_progress_change_is_activity_when_unique_track_aligns():
    force_a = {"id": fact("track"), "visibility": fact(True), "owner": fact(1),
        "relation": fact("OWN"), "source": fact(10), "destination": fact(11),
        "units": fact({"counts": list(enumerate((1,) + (0,) * 9))}),
        "progress": fact(10), "accelerated": fact(None, "UNKNOWN")}
    force_b = {**force_a, "progress": fact(11)}
    a = coverage._raw_semantic_signature(raw([], forces=[force_a]))
    b = coverage._raw_semantic_signature(raw([], forces=[force_b], tick=2))
    assert not a[1] and not b[1]
    assert coverage._active(a, b) == "ACTIVE_KNOWN"


def test_tick_wrap_is_consecutive_but_scope_change_and_gap_are_not():
    before, after = raw([], tick=65535), raw([], tick=0)
    assert coverage._consecutive(before, after) == (True, 1)
    changed_scope = raw([], tick=0, scope="another")
    assert not coverage._consecutive(before, changed_scope)[0]
    skipped = raw([], tick=1)
    assert not coverage._consecutive(before, skipped)[0]


def test_birth_is_candidate_with_unknown_actor_and_cause():
    before = raw([], forces=[])
    after = raw([], tick=2, forces=[{"id": fact("observer-1"), "confidence": fact("NEW_TRACK"),
        "owner": fact(1), "source": fact(10), "destination": fact(11),
        "units": fact({"counts": list(enumerate((1,) + (0,) * 9))}), "progress": fact(0)}])
    birth = coverage._birth_diagnostic(before, after)
    assert birth["status"] == "CANDIDATE"
    assert birth["candidates"][0]["cause"] == "UNKNOWN"
    assert birth["candidates"][0]["classification"] == "CANDIDATE"


def test_readiness_transition_and_bucket_counts_deduplicate_normalized_force_reasons():
    gaps = ["force:0:destination", "force:2:destination", "force:3:source"]
    normalized, buckets = coverage._readiness_edge_labels("before", gaps)
    assert normalized == ["before:force:*:destination", "before:force:*:source"]
    assert buckets == ["before:path_or_force_input"]


def test_not_ready_maps_current_leg_endpoint_and_clock_gaps_explicitly():
    category, classification, stage = coverage._not_ready_classification(
        ["force:0:source", "force:1:destination"])
    assert (category, classification, stage) == (
        "UNKNOWN_PATH", "REJECTED_UNKNOWN_PATH", "current_leg_endpoint")
    category, classification, stage = coverage._not_ready_classification(["source_continuity"])
    assert (category, classification, stage) == (
        "OBSERVATION_GAP", "REJECTED_OBSERVATION_GAP", "clock")


def test_semantic_unsupported_state_is_rejection_not_coverage_gap():
    assert coverage._unsupported_status("ACTIVE_UPGRADE_OR_EMP") == ("REJECTED", "OTHER")
