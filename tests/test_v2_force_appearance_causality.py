from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tools import v2_force_appearance_causality as analysis


def fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge}


def vector(values=(0, 5, 0, 0, 0, 0, 0, 0, 0, 0)):
    return fact({"counts": list(enumerate(values))})


def force(ident, *, progress=0, source=100, units=(0, 2, 0, 0, 0, 0, 0, 0, 0, 0), confidence="NEW_TRACK"):
    return {"id": fact(ident, "DERIVED"), "visibility": fact(True),
        "owner": fact(7), "relation": fact("SELF", "DERIVED"),
        "source": fact(source) if source is not None else fact(None, "UNKNOWN"),
        "destination": fact(200), "units": vector(units),
        "progress": fact(progress), "confidence": fact(confidence, "DERIVED")}


def record(tick, forces=(), source_units=(0, 5, 0, 0, 0, 0, 0, 0, 0, 0), line=None):
    return {"document_id": "doc", "match_id": fact("match"), "player_id": fact(7),
        "tick": fact(tick), "coverage": "PLAYER_VISIBLE_COMPLETE",
        "towers": [{"id": 100, "visibility": fact(True), "owner": fact(7),
            "relation": fact("SELF", "DERIVED"), "units": vector(source_units),
            "capacity": vector((10,) * 10), "production": fact([]),
            "supply_line_present": line or fact(None, "UNKNOWN")}],
        "forces": fact(list(forces))}


def edge_for(ident, src=100):
    return {"cohort": "dev", "split": "development", "edge_index": 1,
        "before_line": 1, "after_line": 2, "before_sequence": 1, "after_sequence": 2,
        "before_tick": 1, "after_tick": 2,
        "new_force_diagnostic": {"candidates": [{"observer_id": ident, "source": src}]}}


def test_committed_fixture_is_exact_646_edges_and_preserves_694_entity_candidates():
    edges, _ = analysis._load_fixture()
    assert len(edges) == 646
    assert sum(edge["new_force_diagnostic"]["candidate_count"] for edge in edges) == 694
    assert len({edge["cohort"] for edge in edges}) == 6


def test_source_depletion_equal_to_new_force_batch_is_still_ambiguous_not_external():
    before = record(1, source_units=(0, 5) + (0,) * 8)
    newborn = force("f1", units=(0, 2) + (0,) * 8)
    after = record(2, [newborn], source_units=(0, 3) + (0,) * 8)
    case = analysis._analyze_candidate(edge_for("f1"), before, after, [before], {})
    assert case["entity_candidates"][0]["age"] == "NEWBORN"
    assert case["source_features"]["all_source_batches_conserved"] is True
    assert case["classification"] == "AMBIGUOUS"
    assert case["causal_credit"] == 0


def test_unknown_source_and_unobserved_zero_progress_remain_unknown():
    before = record(1)
    missing_source = force("f2", source=None)
    after = record(2, [missing_source])
    case = analysis._analyze_candidate(edge_for("f2", None), before, after, [before], {})
    assert case["classification"] == "UNKNOWN"
    assert case["entity_candidates"][0]["age"] == "UNKNOWN_AGE"

    moved = force("f3", progress=1)
    after_moved = record(2, [moved])
    case_moved = analysis._analyze_candidate(edge_for("f3"), before, after_moved, [before], {})
    assert case_moved["classification"] == "UNKNOWN"
    assert case_moved["entity_candidates"][0]["age"] == "UNKNOWN_AGE"


def test_unknown_capacity_and_unknown_inbound_destination_do_not_become_no_event():
    before = record(1, source_units=(0, 12) + (0,) * 8)
    before["towers"][0]["capacity"] = fact(None, "UNKNOWN")
    hidden_inbound = force("incoming", progress=12)
    hidden_inbound["destination"] = fact(None, "UNKNOWN")
    before["forces"] = fact([hidden_inbound])
    newborn = force("f4", units=(0, 2) + (0,) * 8)
    after = record(2, [hidden_inbound, newborn], source_units=(0, 10) + (0,) * 8)
    case = analysis._analyze_candidate(edge_for("f4"), before, after, [before], {})
    source = case["source_features"]["sources"][0]
    assert source["capacity_status"] == "UNKNOWN"
    assert source["overflow_cleanup_due_local_rule"] is None
    assert source["visible_inbound_status"] == "UNKNOWN_DESTINATIONS"
    assert len(source["visible_force_destinations_unknown"]) == 1


def test_hidden_candidate_and_hidden_source_fields_are_not_used():
    before = record(1)
    before["towers"][0]["visibility"] = fact(False)
    newborn = force("f_hidden")
    newborn["visibility"] = fact(False)
    after = record(2, [newborn])
    case = analysis._analyze_candidate(edge_for("f_hidden"), before, after, [before], {})
    entity = case["entity_candidates"][0]
    assert case["classification"] == "UNKNOWN"
    assert entity["visibility_observed_true"] is False
    assert entity["source"] is None and entity["unit_vector"] is None
    hidden_source = analysis._source_features(before, after, 100, [before])
    assert hidden_source["source_tower_visible_before_birth"] == "NO"
    assert hidden_source["source_units_before"] is None


def test_internal_label_requires_known_line_and_repeated_prebirth_interval_and_batch():
    rows = []
    current = []
    births = {2: "f2", 5: "f5", 8: "f8"}
    for tick in range(1, 11):
        if tick in births:
            current = current + [force(births[tick], progress=0,
                                      units=(0, 2) + (0,) * 8)]
        else:
            current = [{**item, "confidence": fact("UNIQUE_CONTINUATION", "DERIVED"),
                        "progress": fact(tick)} for item in current]
        rows.append(record(tick, current, line=fact(True)))
    before = rows[-1]
    newborn = force("f11", units=(0, 2) + (0,) * 8)
    after = record(11, current + [newborn], source_units=(0, 3) + (0,) * 8,
                   line=fact(True))
    case = analysis._analyze_candidate(edge_for("f11"), before, after, rows, {})
    assert case["source_features"]["sources"][0]["prior_intervals"] == [3, 3]
    assert case["source_features"]["sources"][0]["composition_batch_recurrence"] == "REPEATED_SAME_INTERVAL_AND_BATCH"
    assert case["classification"] == "LIKELY_INTERNAL"

    nonconserved_after = record(11, current + [newborn], source_units=(0, 5) + (0,) * 8,
                                line=fact(True))
    nonconserved = analysis._analyze_candidate(edge_for("f11"), before, nonconserved_after, rows, {})
    assert nonconserved["source_features"]["all_source_batches_conserved"] is False
    assert nonconserved["classification"] == "AMBIGUOUS"


def test_development_rule_hash_is_stable_and_contains_no_holdout_outcome():
    dev = [{"fixture_candidate_entity_count": 2, "classification": "AMBIGUOUS"}]
    frozen = analysis._freeze_development_rule(dev)
    assert frozen["dev_candidate_edges"] == 1
    assert frozen["dev_classification_counts"] == {"AMBIGUOUS": 1}
    assert "holdout" in frozen["holdout_tuning"]
    assert len(frozen["rule_sha256"]) == 64
