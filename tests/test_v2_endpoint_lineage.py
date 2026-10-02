from __future__ import annotations

import hashlib
import json

from kiomet_ai.v2.state import Fact, Force, Knowledge
from tools import v2_endpoint_lineage as lineage


def _fact(value, knowledge="OBSERVED", source="fixture"):
    return {"value": value, "knowledge": knowledge, "source": source,
            "observed_at_ms": 100 if knowledge != "UNKNOWN" else None}


def _unknown_fact():
    return {"value": None, "knowledge": "UNKNOWN", "source": "unavailable",
            "observed_at_ms": None}


def test_unknown_retained_endpoint_is_record_boundary_absence_not_information_ceiling():
    source = lineage._fact({"source": _unknown_fact()}, "source")
    target = lineage._fact({"destination": _fact(12)}, "destination")
    classification, reason = lineage.classify_lineage(source, target)
    assert classification == "A_RAW_ABSENT"
    assert "upstream first-loss layer unresolved" in reason
    assert lineage.endpoint_field_status(source) == "NO"
    assert lineage.endpoint_field_status(target) == "YES"


def test_lineage_requires_positive_paired_evidence_for_b_to_f():
    unknown = lineage._fact({"source": _unknown_fact()}, "source")
    target = lineage._fact({"destination": _unknown_fact()}, "destination")
    assert lineage.classify_lineage(unknown, target)[0] == "A_RAW_ABSENT"
    assert lineage.classify_lineage(unknown, target, {
        "canonical_serialized_has_endpoint": True,
        "gamestate_after_restore_has_endpoint": False})[0] == "C_GAMESTATE_LOSS"
    assert lineage.classify_lineage(unknown, target, {
        "current_player_visibility_excludes_endpoint": True})[0] == "F_TRUE_INFORMATION_CEILING"
    assert lineage.classify_lineage(unknown, target, {
        "raw_extractor_has_endpoint": True,
        "extractor_output_has_endpoint": False})[0] == "B_EXTRACTOR_LOSS"


def test_endpoint_unknown_facts_survive_force_restore_and_serialization_roundtrip():
    raw = {
        "id": _fact("scope:f:1", "DERIVED", "tracker"),
        "visibility": _fact(True, "OBSERVED", "renderer"),
        "owner": _fact(5), "relation": _fact("SELF", "OBSERVED", "owner comparison"),
        "source": _unknown_fact(), "destination": _fact(12, "OBSERVED", "visible tower intersection"),
        "units": _fact({"counts": [[i, 1 if i == 0 else 0] for i in range(10)]}),
        "launch_ms": _unknown_fact(), "unit_count": _fact(1, "DERIVED", "sum"),
        "eta_ms": _unknown_fact(), "progress": _fact(0), "first_seen_ms": _fact(100),
        "confidence": _fact("NEW_TRACK", "DERIVED", "tracker"), "accelerated": _fact(False)}
    restored = lineage.entity_from_dict(Force, raw)
    roundtrip = lineage.entity_from_dict(Force, __import__("dataclasses").asdict(restored))
    assert restored.source == Fact(None, Knowledge.UNKNOWN, "unavailable", None)
    assert restored.destination.value == 12
    assert roundtrip.source == restored.source
    assert roundtrip.destination == restored.destination


def test_age_requires_reliable_zero_progress_birth_and_consecutive_observations():
    assert lineage.age_class("NEW_TRACK", 0, None, True) == "NEWBORN"
    assert lineage.age_class("NEW_TRACK", 3, None, True) == "UNKNOWN_AGE"
    assert lineage.age_class("UNIQUE_CONTINUATION", 2, 1, True) == "PERSISTENT"
    assert lineage.age_class("UNIQUE_CONTINUATION", 4, 2, True) == "LONG_LIVED"
    assert lineage.age_class("UNIQUE_CONTINUATION", 4, 2, False) == "UNKNOWN_AGE"


def test_owner_uses_recorded_relation_and_does_not_guess_unknown_owner():
    owner = lambda value: lineage._fact({"owner": _fact(value)}, "owner")
    relation = lambda value, knowledge: lineage._fact(
        {"relation": _fact(value, knowledge)}, "relation")
    unknown = lineage._fact({"relation": _unknown_fact()}, "relation")
    assert lineage.owner_class(owner(5), relation("SELF", "OBSERVED"), 5) == "SELF"
    assert lineage.owner_class(owner(8), relation("ALLY", "DERIVED"), 5) == "ALLY"
    assert lineage.owner_class(owner(None), unknown, 5) == "UNKNOWN_OWNER"
    assert lineage.owner_class(owner(5), relation("ENEMY", "DERIVED"), 5) == "UNKNOWN_OWNER"


def test_percentiles_use_linear_interpolation():
    assert lineage._percentile([1, 2, 3, 4], .75) == 3.25


def test_after_only_unknown_force_uses_after_observation_and_keeps_continuity(tmp_path):
    force_before = {"id": _fact("d:m:f:1", "DERIVED"), "visibility": _fact(True),
        "owner": _fact(5), "relation": _fact("SELF", "DERIVED"),
        "source": _fact(10), "destination": _fact(11),
        "confidence": _fact("NEW_TRACK", "DERIVED"), "progress": _fact(0)}
    force_after = {**force_before, "source": _unknown_fact(),
        "confidence": _fact("UNIQUE_CONTINUATION", "DERIVED"), "progress": _fact(1)}
    records = [
        {"document_id": "d", "match_id": _fact("m"), "player_id": _fact(5),
         "sequence": 1, "tick": _fact(100), "sampled_at_ms": 100,
         "forces": _fact([force_before])},
        {"document_id": "d", "match_id": _fact("m"), "player_id": _fact(5),
         "sequence": 2, "tick": _fact(101), "sampled_at_ms": 350,
         "forces": _fact([force_after])},
    ]
    raw = tmp_path / "snapshots.jsonl"
    payload = b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in records)
    raw.write_bytes(payload)
    edge = {"cohort": "test", "split": "development", "edge_index": 1,
        "before_line": 1, "after_line": 2, "before_sequence": 1, "after_sequence": 2,
        "comparison_execution": "EXECUTED", "control_readiness_gaps": [],
        "after_input_readiness_gaps": ["force:0:source"]}
    selected, continuity, meta = lineage._cohort_snapshot_summaries(raw, [edge], hashlib.sha256(payload).hexdigest())
    stage, blocked_line, blocked_sequence, gaps = lineage._blocked_observation(edge)
    assert (stage, blocked_line, blocked_sequence) == ("AFTER", 2, 2)
    assert gaps == {0: {"source"}}
    blocked = selected[(blocked_line)]
    force = blocked["forces"][0]
    assert force["endpoints"]["source"]["knowledge"] == "UNKNOWN"
    assert force["age_class"] == "PERSISTENT"
    assert meta["matches_pin"] is True
    assert len(continuity) == 1
    assert continuity[0]["endpoint"] == "source"
    assert continuity[0]["from_sequence"] == 1 and continuity[0]["to_sequence"] == 2


def test_executed_edge_uses_after_gate_even_if_before_has_unrelated_endpoint_gap():
    edge = {"comparison_execution": "EXECUTED", "before_line": 10,
        "before_sequence": 20, "after_line": 11, "after_sequence": 21,
        "control_readiness_gaps": ["force:2:destination"],
        "after_input_readiness_gaps": ["force:0:source"]}
    assert lineage._blocked_observation(edge) == (
        "AFTER", 11, 21, {0: {"source"}})


def test_not_attempted_edge_uses_before_gate_and_ignores_after_rows():
    edge = {"comparison_execution": "NOT_ATTEMPTED", "before_line": 10,
        "before_sequence": 20, "after_line": 11, "after_sequence": 21,
        "control_readiness_gaps": ["force:1:destination"],
        "after_input_readiness_gaps": ["force:0:source"]}
    assert lineage._blocked_observation(edge) == (
        "BEFORE", 10, 20, {1: {"destination"}})
