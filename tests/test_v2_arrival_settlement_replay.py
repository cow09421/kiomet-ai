import gzip
import json
from pathlib import Path

from tools.v2_arrival_settlement_replay import consecutive_scope, normalized_signature


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/v2"


def split_fixture(name):
    path = FIXTURE_DIR / f"arrival-settlement-replay-{name}.json.gz"
    return json.loads(gzip.decompress(path.read_bytes()))


def test_v2_settlement_population_retains_all_known_due_rows_and_exclusions():
    dev, hold = split_fixture("development"), split_fixture("holdout")
    assert len(dev["cases"]) == 312
    assert len(hold["cases"]) == 101
    all_cases = dev["cases"] + hold["cases"]
    assert len(all_cases) == 413
    supported = [c for c in all_cases if c["boundary"]["status"] == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"]
    excluded = [c for c in all_cases if c["boundary"]["status"] != "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"]
    assert len(supported) == 295
    assert len(excluded) == 118
    assert sum(c["branch_candidate"] == "EMPTY_NEUTRAL_CAPTURE" and c["classification"] != "UNSCORABLE"
               for c in all_cases) == 45
    assert sum(c["branch_candidate"] == "SAME_OWNER_REINFORCEMENT" and c["classification"] != "UNSCORABLE"
               for c in all_cases) == 219


def test_v2_arrival_counterexample_remains_scored_despite_continuation_uncertainty():
    case = next(c for c in split_fixture("development")["cases"]
                if c["case_id"] == "03d032d57e5b:187:0")
    assert case["boundary"]["status"] == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"
    assert case["branch_candidate"] == "EMPTY_NEUTRAL_CAPTURE"
    assert case["classification"] == "MISMATCH"
    assert case["first_mismatch_field"] == "inventory_after"
    assert case["predicted_owner_after"] == case["observed_owner_after"] == 10
    assert case["observed_inventory_after"] == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert case["post_arrival_force_status"]["t_plus_1"] == "TRANSFORMED"
    assert case["post_arrival_force_status"]["t_plus_2"] == "TRANSFORMED"
    assert case["observed_owner_following"] == 10
    assert case["observed_inventory_following"] == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def test_v2_t_plus_2_status_requires_contiguous_same_scope_observations():
    cases = split_fixture("development")["cases"] + split_fixture("holdout")["cases"]
    for case in cases:
        snaps = case["snapshots"]
        if case["contiguous_t_plus_2_complete"]:
            assert consecutive_scope(snaps["before"], snaps["arrival"])
            assert consecutive_scope(snaps["arrival"], snaps["following"])
        else:
            assert case["post_arrival_force_status"]["t_plus_2"] == "UNKNOWN"
    a = {"provenance": {"scope": ["doc", "match", 1, 1.0], "tick": 9}}
    b = {"provenance": {"scope": ["doc", "match", 1, 1.0], "tick": 11}}
    c = {"provenance": {"scope": ["doc", "other", 1, 1.0], "tick": 10}}
    assert not consecutive_scope(a, b)
    assert not consecutive_scope(a, c)


def test_v2_force_signature_normalizes_json_vectors_without_observer_ids():
    signature = [10, 13828326, 13893863, [0, 0, 0, 0, 0, 5, 0, 0, 0, 0]]
    assert normalized_signature(signature) == (10, 13828326, 13893863, (0, 0, 0, 0, 0, 5, 0, 0, 0, 0))
    assert normalized_signature([10, 13828326, 13893863, None]) is None


def test_v2_terminal_revision_is_before_only_and_does_not_relabel_original_scores():
    dev, hold = split_fixture("development"), split_fixture("holdout")
    all_cases = dev["cases"] + hold["cases"]
    assert sum(c["classification"] == "MATCH" for c in all_cases) == 29
    assert sum(c["classification"] == "MISMATCH" for c in all_cases) == 235
    assert sum(c["classification"] == "UNSCORABLE" for c in all_cases) == 149
    assert all(c["local_context"]["final_frozen_eligibility"]["capture"] is False for c in all_cases)
    assert all(c["local_context"]["final_frozen_eligibility"]["reinforcement"] is False for c in all_cases)
    counterexamples = [c for c in all_cases if c["classification"] == "MISMATCH"
                       and c["post_arrival_force_status"]["t_plus_1"] in ("TRANSFORMED", "AMBIGUOUS")]
    assert counterexamples


def test_v2_no_terminal_proxy_summary_reports_capture_subset_scores():
    report = json.loads((ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json").read_text())
    for split_name in ("development", "holdout"):
        detail = report["splits"][split_name]["naive_scores_within_eligibility"]["eligibility_without_terminal_proxy"]["capture"]
        cases = [c for c in split_fixture(split_name)["cases"]
                 if c["local_context"]["eligibility_without_terminal_proxy"]["capture"]]
        assert detail["cases"] == len(cases)
        assert detail["match"] == sum(c["classification"] == "MATCH" for c in cases)
        assert detail["mismatch"] == sum(c["classification"] == "MISMATCH" for c in cases)
    dev = report["splits"]["development"]["naive_scores_within_eligibility"]["eligibility_without_terminal_proxy"]["capture"]
    hold = report["splits"]["holdout"]["naive_scores_within_eligibility"]["eligibility_without_terminal_proxy"]["capture"]
    assert (dev["cases"], dev["match"], dev["mismatch"]) == (8, 2, 6)
    assert (hold["cases"], hold["match"], hold["mismatch"]) == (11, 5, 6)


def test_v2_historical_live_and_prior_grade_b_contexts_stay_separate():
    report = json.loads((ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json").read_text())
    live = report["separate_previous_context"]
    assert live["not_in_413_population"] is True
    assert live["not_holdout"] is True
    assert (live["raw_observations"], live["unique_scope_tick_states"], live["known_due_candidates"]) == (175, 81, 4)
    assert live["arrival_owner_and_inventory_exact_matches"] == 4
    grade_b = report["previously_accepted_grade_b_context"]
    assert grade_b["previously_accepted_grade_b_count"] == grade_b["mapped_count"] == 8
    assert grade_b["formal_credit"] == 0
    assert all(row["mapping_status"] == "MATCHED" and row["formal_credit"] == 0 for row in grade_b["cases"])
