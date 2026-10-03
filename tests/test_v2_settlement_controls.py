import copy
import gzip
import json
from pathlib import Path

import pytest

from tools.v2_settlement_negative_controls import (
    REPLAY,
    before_capture_eligibility,
    build_report,
    isolated_terminal_known_case,
    synthetic_public_mutations,
    _set_fact,
)


def development_cases():
    with gzip.open(REPLAY, "rt", encoding="utf-8") as stream:
        return json.load(stream)["cases"]


def clean_capture_candidate():
    cases = development_cases()
    return next(case for case in cases
                if case.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                and case["case_id"] == "fe678ebb30ce:1584:0")


def test_actual_development_close_invalid_capture_cases_are_all_refused():
    report = build_report()
    assert report["actual_case_count"] >= 10
    assert report["production_gate_passed"] is False
    assert report["this_control_pack_holdout_outcomes_accessed"] is False
    assert report["negative_control_total"] == 28
    assert report["negative_control_rejected"] == 28
    assert report["false_admissions"] == 0
    assert all("TERMINAL_NOT_KNOWN_TRUE_BEFORE" in row["refusals"]
               for row in report["actual_development_close_invalid_cases"])
    assert any("INBOUND_DESTINATION_UNKNOWN" in row["refusals"]
               for row in report["actual_development_close_invalid_cases"])
    assert any("CAPACITY_UNKNOWN_OR_CLIPPING_CONTEXT" in row["refusals"]
               for row in report["actual_development_close_invalid_cases"])


def test_synthetic_terminal_known_before_snapshot_is_only_positive_control():
    case = clean_capture_candidate()
    original = before_capture_eligibility(case)
    assert "TERMINAL_NOT_KNOWN_TRUE_BEFORE" in original["reasons"]
    positive = isolated_terminal_known_case(case)
    assert before_capture_eligibility(positive)["eligible"] is True


def test_frozen_ground_overflow_allowance_is_not_overrejected():
    case = isolated_terminal_known_case(clean_capture_candidate())
    before = case["snapshots"]["before"]
    target = next(t for t in before["towers"] if t["id"] == case["target_id"])
    incoming = next(f for f in before["forces"]
                    if f["source"].get("value") == case["incoming_signature"][1]
                    and f["destination"].get("value") == case["target_id"])
    _set_fact(target, "capacity", {"counts": [[i, 0 if i != 5 else 2] for i in range(10)]})
    _set_fact(incoming, "units", {"counts": [[i, 0 if i != 5 else 12] for i in range(10)]})
    case["incoming_signature"][3] = [0, 0, 0, 0, 0, 12, 0, 0, 0, 0]
    result = before_capture_eligibility(case)
    assert "CAPACITY_WOULD_CHANGE_FROZEN_VECTOR" not in result["reasons"]
    assert "CAPACITY_UNKNOWN_OR_CLIPPING_CONTEXT" not in result["reasons"]
    assert result["eligible"] is True


@pytest.mark.parametrize("name,case,expected", synthetic_public_mutations(clean_capture_candidate()))
def test_public_before_input_mutations_are_refused(name, case, expected):
    result = before_capture_eligibility(case)
    assert result["eligible"] is False, name
    assert expected in result["reasons"], (name, result["reasons"])


def test_post_arrival_force_absence_cannot_admit_unknown_terminal():
    case = copy.deepcopy(clean_capture_candidate())
    before_result = before_capture_eligibility(case)
    case["post_arrival_force_status"] = {"t_plus_1": "DISAPPEARED", "t_plus_2": "DISAPPEARED"}
    case["snapshots"]["arrival"] = copy.deepcopy(case["snapshots"]["before"])
    case["snapshots"]["arrival"]["forces"] = []
    case["snapshots"]["following"] = copy.deepcopy(case["snapshots"]["before"])
    case["snapshots"]["following"]["forces"] = []
    after_result = before_capture_eligibility(case)
    assert before_result == after_result
    assert "TERMINAL_NOT_KNOWN_TRUE_BEFORE" in after_result["reasons"]


def test_after_snapshots_cannot_change_before_only_owner_or_inventory_eligibility():
    case = isolated_terminal_known_case(clean_capture_candidate())
    before_result = before_capture_eligibility(case)
    for snapshot_name in ("arrival", "following"):
        snapshot = copy.deepcopy(case["snapshots"]["before"])
        target = next(t for t in snapshot["towers"] if t["id"] == case["target_id"])
        target["owner"] = {"value": 99, "knowledge": "OBSERVED", "source": "test", "observed_at_ms": 2}
        target["units"] = {"value": {"counts": [[i, 1 if i == 5 else 0] for i in range(10)]},
                           "knowledge": "OBSERVED", "source": "test", "observed_at_ms": 2}
        case["snapshots"][snapshot_name] = snapshot
    assert before_capture_eligibility(case) == before_result


def test_targeted_actual_cases_are_prearrival_only_records():
    report = build_report()
    for row in report["actual_development_close_invalid_cases"]:
        assert row["terminal_before"] is None
        assert "classification" not in row
        assert "observed_owner_after" not in row
        assert "post_arrival_force_status" not in row

