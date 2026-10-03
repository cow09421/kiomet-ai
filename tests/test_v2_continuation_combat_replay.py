"""Focused regressions for continuation-aware passive combat accounting.

These tests exercise the shared analyzer with synthetic snapshots. They do not
re-score or filter the pinned 31-case retrospective population.
"""
from __future__ import annotations

import json
import gzip
from pathlib import Path

import pytest

from tools import v2_continuation_combat_replay as replay


ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "docs" / "V2_M2A_CONTINUATION_COMBAT_PREREG.json"
RESULT_FIXTURE = ROOT / "tests" / "fixtures" / "v2" / "continuation-aware-combat-replay.json.gz"


def _fact(value, knowledge="KNOWN"):
    return {"value": value, "knowledge": knowledge}


def _units(values, knowledge="KNOWN"):
    return {"value": {"counts": [[i, n] for i, n in enumerate(values)]},
            "knowledge": knowledge}


def _force(ident, *, owner=2, source=10, destination=20, units=None,
           owner_knowledge="KNOWN", source_knowledge="KNOWN",
           destination_knowledge="KNOWN", units_knowledge="KNOWN"):
    values = units if units is not None else [0] * 10
    values = {"visibility": _fact(True),
              "owner": _fact(owner, owner_knowledge),
              "source": _fact(source, source_knowledge),
              "destination": _fact(destination, destination_knowledge),
              "units": _units(values, units_knowledge)}
    return {"id": ident, **values}


def _snapshot(tick, forces=(), *, coverage="PLAYER_VISIBLE_COMPLETE",
              scope=("doc", "match", 2, 0), sequence=None):
    return {
        "provenance": {"scope": list(scope), "tick": tick,
                       "sequence": tick if sequence is None else sequence,
                       "coverage": coverage},
        "towers": [{"id": 10, "owner": _fact(2), "units": _units([0] * 10)}],
        "forces": list(forces),
    }


def _population_prereg():
    return json.loads(PREREG.read_text(encoding="utf-8"))


def test_preregistered_population_is_symmetric_and_qualification_is_unchanged():
    prereg = _population_prereg()
    selection = prereg["selection"]
    ids = selection["all31_case_ids"]
    assert len(ids) == len(set(ids)) == 31
    assert selection["development"] == 22
    assert selection["holdout"] == 9
    assert selection["original_match"] == 26
    assert selection["original_mismatch"] == 5
    frozen = prereg["qualification"]
    qmap = frozen["qualified_map"]
    assert set(qmap) == set(ids)
    assert frozen["qualified_count"] == sum(bool(v["qualified"]) for v in qmap.values()) == 4
    assert frozen["unqualified_count"] == 27


def test_scored_fixture_retains_all31_case_ids_and_frozen_qualification():
    # Run only after the preregistered control sample has been frozen and the
    # full symmetric replay is built; no result-dependent selection is allowed.
    assert RESULT_FIXTURE.exists(), "build the all31 replay only after controls are frozen"
    payload = json.loads(gzip.decompress(RESULT_FIXTURE.read_bytes()))
    cases = payload["cases"]
    prereg = _population_prereg()
    expected_ids = set(prereg["selection"]["all31_case_ids"])
    qmap = prereg["qualification"]["qualified_map"]
    assert len(cases) == 31
    assert {row["case_id"] for row in cases} == expected_ids
    assert len({row["case_id"] for row in cases}) == 31
    assert all(type(row["qualified"]) is bool for row in cases)
    assert sum(bool(row["qualified"]) for row in cases) == 4
    assert all(row["qualified"] is bool(qmap[row["case_id"]]["qualified"])
               for row in cases)
    assert sum(row["original_match_status"] == "MATCH" for row in cases) == 26
    assert sum(row["original_match_status"] == "MISMATCH" for row in cases) == 5
    assert all(row["flip_direction"] in {"NONE", "MATCH_TO_MISMATCH",
                                         "MISMATCH_TO_MATCH", "UNKNOWN"}
               for row in cases)


def test_partial_inventory_and_partial_outgoing_are_summed_without_subset_search():
    detect = replay.detect_outgoing
    account = replay.account_survivors
    before = _snapshot(100)
    after = _snapshot(101, [_force(1, units=[0, 2] + [0] * 8)])
    detection = detect(before, after, 10, 2, offset=0)
    result = account(2, [0, 5] + [0] * 8, 2, [0, 3] + [0] * 8, detection)
    assert result["status"] == "EXACT"
    assert result["observed_only_status"] == "EXACT"
    assert result["observed_inventory_plus_outgoing"] == [0, 5] + [0] * 8


def test_oversized_known_outgoing_is_not_clipped_or_filtered_by_vector_equality():
    before = _snapshot(100)
    after = _snapshot(101, [_force(1, units=[0, 7] + [0] * 8)])
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    result = replay.account_survivors(2, [0, 5] + [0] * 8, 2,
                                      [0, 1] + [0] * 8, detection)
    assert result["compatible_outgoing_sum"] == [0, 7] + [0] * 8
    assert result["observed_inventory_plus_outgoing"] == [0, 8] + [0] * 8
    assert result["status"] == "MISMATCH"


@pytest.mark.parametrize("unknown_field", ["source", "owner", "units"])
def test_unknown_stale_endpoint_owner_or_vector_cannot_become_known_zero(unknown_field):
    args = {"source_knowledge": "KNOWN", "owner_knowledge": "KNOWN",
            "units_knowledge": "KNOWN"}
    args[f"{unknown_field}_knowledge"] = "UNKNOWN"
    before = _snapshot(100)
    after = _snapshot(101, [_force(1, units=[0, 1] + [0] * 8, **args)])
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    assert detection["status"] == "UNKNOWN"
    result = replay.account_survivors(2, [0, 3] + [0] * 8, 2,
                                      [0, 1] + [0] * 8, detection)
    assert result["status"] == "UNKNOWN"


def test_incomplete_census_and_before_newness_ambiguity_are_unknown():
    before = _snapshot(100, [_force(1, source_knowledge="UNKNOWN", units=[0, 1] + [0] * 8)])
    after = _snapshot(101, [_force(2, source_knowledge="UNKNOWN", units=[0, 1] + [0] * 8)],
                      coverage="PLAYER_VISIBLE_PARTIAL")
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    assert detection["status"] == "UNKNOWN"
    assert detection["possible_alias_count"] > 0


def test_scope_requires_all_four_known_components_and_u16_consecutive_ticks():
    before = _snapshot(65535)
    after = _snapshot(0)
    assert replay.detect_outgoing(before, after, 10, 2, offset=0)["status"] in {
        "NO", "UNKNOWN"}
    empty_scope_before = _snapshot(10, scope=(None, None, None, None))
    empty_scope_after = _snapshot(11, scope=(None, None, None, None))
    assert replay.detect_outgoing(empty_scope_before, empty_scope_after,
                                  10, 2, offset=0)["status"] == "UNKNOWN"
    gap = _snapshot(12)
    assert replay.detect_outgoing(_snapshot(10), gap, 10, 2,
                                  offset=0)["status"] == "UNKNOWN"


def test_wrong_scope_or_nonconsecutive_edge_cannot_be_reported_as_yes():
    before = _snapshot(100)
    after = _snapshot(101, [_force(1, units=[0, 1] + [0] * 8)],
                      scope=("other-doc", "match", 2, 0))
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    assert detection["status"] == "UNKNOWN"
    assert detection["time_scope_valid"] is False


def test_before_unknown_destination_same_vector_marks_first_appearance_uncertain():
    units = [0, 2] + [0] * 8
    before = _snapshot(100, [_force("before", units=units,
                                    destination_knowledge="UNKNOWN")])
    after = _snapshot(101, [_force("after", units=units)])
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    assert detection["first_appearance_uncertain"] is True
    assert detection["before_unknown_destination_aliases"]
    assert detection["status"] == "YES"
    assert detection["complete"] is False
    accounted = replay.account_survivors(2, units, 2, [0] * 10, detection)
    assert accounted["status"] == "UNKNOWN"


def test_before_signature_multiplicity_is_subtracted_and_persistent_ids_do_not_multiply():
    units = [0, 2] + [0] * 8
    before = _snapshot(100, [_force("old-id", units=units)])
    after = _snapshot(101, [_force("changed-observer-id", units=units),
                            _force("simultaneous-copy", units=units)])
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    assert detection["compatible_count"] == 1
    assert detection["compatible_sum"] == units


def test_aggregate_outgoing_can_exceed_single_typed_count_limit_without_clipping():
    vector = [0, 200] + [0] * 8
    before = _snapshot(100)
    after = _snapshot(101, [_force("a", units=vector), _force("b", units=vector)])
    detection = replay.detect_outgoing(before, after, 10, 2, offset=0)
    result = replay.account_survivors(2, [0, 255] + [0] * 8, 2,
                                      [0, 100] + [0] * 8, detection)
    assert detection["compatible_count"] == 2
    assert detection["compatible_sum"] == [0, 400] + [0] * 8
    assert result["observed_inventory_plus_outgoing"] == [0, 500] + [0] * 8
    assert result["status"] == "MISMATCH"


def test_offset_zero_is_primary_and_later_offsets_cannot_rescue_it():
    case = {"case_id": "synthetic", "cohort": "capture", "split": "development",
            "target_id": 10, "evaluable": True,
            "raw_formula_match_arrival": False,
            "prediction": {"owner": 2, "vector": [0, 5] + [0] * 8},
            "observed_arrival": {"owner": 2, "vector": [0] * 10}}
    snapshots = {
        "before": _snapshot(100),
        "offset_0": _snapshot(101),
        "offset_1": _snapshot(102, [_force("later", units=[0, 5] + [0] * 8)]),
        "offset_2": _snapshot(103, [_force("later2", units=[0, 5] + [0] * 8)]),
    }
    result = replay.analyze_case(case, snapshots)
    assert result["outgoing_by_offset"]["0"]["offset"] == 0
    assert result["continuation_accounting_status"] != "EXACT"
    assert result["outgoing_by_offset"]["1"]["status"] == "YES"
    assert result["outgoing_by_offset"]["2"]["status"] == "NO"


def test_bidirectional_outcome_flips_are_retained_and_unknown_is_not_a_flip():
    def row(cid, old_match, primary_status, qualified=True):
        case = {"case_id": cid, "cohort": "capture", "split": "development",
                "target_id": 10, "evaluable": qualified,
                "raw_formula_match_arrival": old_match,
                "prediction": {"owner": 2, "vector": [0, 5] + [0] * 8},
                "observed_arrival": {"owner": 2, "vector": [0] * 10}}
        before = _snapshot(100)
        if primary_status == "EXACT":
            offset0 = _snapshot(101, [_force("new", units=[0, 5] + [0] * 8)])
        else:
            offset0 = _snapshot(101)
        if primary_status == "UNKNOWN":
            offset0["provenance"]["coverage"] = "PARTIAL"
        snapshots = {"before": before, "offset_0": offset0,
                     "offset_1": _snapshot(102), "offset_2": _snapshot(103)}
        return replay.analyze_case(case, snapshots)
    rows = [row("match-to-mismatch", True, "MISMATCH"),
            row("mismatch-to-match", False, "EXACT"),
            row("unknown", True, "UNKNOWN")]
    assert [item["flip_direction"] for item in rows] == [
        "MATCH_TO_MISMATCH", "MISMATCH_TO_MATCH", "UNKNOWN"]


def test_decision_hierarchy_prefers_falsification_then_hard_stop_information():
    controls_pass = {"A": {"selected": 100, "YES": 0, "UNKNOWN": 0},
                     "B": {"decoy_available_N": 50, "decoy": {"YES": 0, "UNKNOWN": 0}},
                     "overall_controls_pass": True}
    mismatch = {"continuation_accounting_status": "MISMATCH",
                "continuation_accounting": {"complete": True, "owner_match": True}}
    exact = {"continuation_accounting_status": "EXACT",
             "continuation_accounting": {"complete": True, "owner_match": True}}
    falsified_cases = [{"case_id": "qualified-raw-and-aware-mismatch", "qualified": True,
                        "original_match_status": "MISMATCH", "flip_direction": "NONE",
                        "raw_formula_status": "SCORED", "raw_formula_match_arrival": False,
                        "owner_match_arrival": True, "vector_match_arrival": False,
                        **mismatch},
                       {"case_id": "qualified-owner-contradiction", "qualified": True,
                        "original_match_status": "MATCH", "flip_direction": "MATCH_TO_MISMATCH",
                        "raw_formula_status": "SCORED", "raw_formula_match_arrival": True,
                        "owner_match_arrival": True, "vector_match_arrival": True,
                        **mismatch},
                       {"case_id": "unqualified-match-flip", "qualified": False,
                        "original_match_status": "MATCH", "flip_direction": "MATCH_TO_MISMATCH",
                        "raw_formula_status": "SCORED", "raw_formula_match_arrival": True,
                        "owner_match_arrival": True, "vector_match_arrival": True,
                        **mismatch}]
    falsified = replay.decide_outcome({"cases": falsified_cases}, controls_pass)
    assert falsified["outcome"] == "FORMULA_FALSIFIED"
    # A known flip on an unqualified case does not falsify formula, but it must
    # prevent support because the symmetric 26-MATCH preservation requirement fails.
    unqualified_only = [{"case_id": "unqualified-match-flip", "qualified": False,
        "original_match_status": "MATCH", "flip_direction": "MATCH_TO_MISMATCH",
        "raw_formula_status": "SCORED", "raw_formula_match_arrival": True,
        "owner_match_arrival": True, "vector_match_arrival": True, **mismatch}]
    assert replay.decide_outcome({"cases": unqualified_only}, controls_pass)["outcome"] == \
        "INSUFFICIENT_INFORMATION"
    supported_cases = [
        *[{"case_id": f"m{i}", "qualified": False, "original_match_status": "MISMATCH",
           "flip_direction": "MISMATCH_TO_MATCH", **exact} for i in range(4)],
        {"case_id": "m5", "qualified": False, "original_match_status": "MISMATCH",
         "flip_direction": "NONE", "continuation_accounting_status": "UNKNOWN",
         "continuation_accounting": {"complete": False, "owner_match": True}},
        *[{"case_id": f"q{i}", "qualified": True, "original_match_status": "MATCH",
           "flip_direction": "NONE", **exact} for i in range(4)],
    ]
    assert replay.decide_outcome({"cases": supported_cases}, controls_pass)["outcome"] == \
        "FORMULA_DIAGNOSTICALLY_SUPPORTED"
    with_unqualified_flip = supported_cases + [{"case_id": "u", "qualified": False,
        "original_match_status": "MATCH", "flip_direction": "MATCH_TO_MISMATCH",
        "raw_formula_status": "SCORED", "raw_formula_match_arrival": True,
        "owner_match_arrival": True, "vector_match_arrival": True, **mismatch}]
    result = replay.decide_outcome({"cases": with_unqualified_flip}, controls_pass)
    assert result["outcome"] == "INSUFFICIENT_INFORMATION"
    assert result["qualified_fully_known_counterexample_count"] == 0
    assert replay.decide_outcome({"cases": supported_cases}, {"A": {"selected": 0,
        "YES": 0, "UNKNOWN": 0}, "B": {"decoy_available_N": 0,
        "decoy": {"YES": 0, "UNKNOWN": 0}}, "overall_controls_pass": False})["outcome"] == \
        "INSUFFICIENT_INFORMATION"
    contradictory_controls = {"A": {"selected": 100, "YES": 11, "UNKNOWN": 0},
        "B": {"decoy_available_N": 50, "decoy": {"YES": 0, "UNKNOWN": 0}},
        "overall_controls_pass": True}
    assert replay.decide_outcome({"cases": supported_cases}, contradictory_controls)["outcome"] == \
        "INSUFFICIENT_INFORMATION"
    assert replay.decide_outcome({"cases": supported_cases}, controls_pass,
                                 definition_revisions_used=2)["outcome"] == \
        "INSUFFICIENT_INFORMATION"
    assert replay.decide_outcome({"cases": supported_cases}, controls_pass,
                                 expired=True)["outcome"] == "INSUFFICIENT_INFORMATION"
