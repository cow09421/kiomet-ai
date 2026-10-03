from __future__ import annotations

import gzip
import json
import pytest
from collections import Counter

from tools import v2_combat_passive_replay as replay


def test_formula_adapter_projects_attacker_victory_to_attacker_survivors():
    prediction = replay.project_fight(
        (0, 0, 0, 0, 2, 0, 0, 0, 0, 0), (0,) * 10, (255,) * 10,
        incoming_owner=2, target_owner=1, attacker_morale=False,
        defender_morale=False)

    assert prediction["winner"] == "ATTACKER"
    assert prediction["owner"] == 2
    assert prediction["vector"] == [0, 0, 0, 0, 2, 0, 0, 0, 0, 0]


def test_formula_adapter_projects_defender_victory_to_defender_survivors():
    prediction = replay.project_fight(
        (0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
        (0, 0, 0, 0, 0, 3, 0, 0, 0, 0), (255,) * 10,
        incoming_owner=2, target_owner=1, attacker_morale=False,
        defender_morale=True)

    assert prediction["winner"] == "DEFENDER"
    assert prediction["owner"] == 1
    assert prediction["vector"] == [0, 0, 0, 0, 0, 3, 0, 0, 0, 0]


def test_combat_morale_must_be_known_booleans():
    with pytest.raises(replay.UnsupportedState, match="UNKNOWN_COMBAT_MORALE"):
        replay.project_fight(
            (0, 0, 0, 0, 1, 0, 0, 0, 0, 0), (0,) * 10, (255,) * 10,
            incoming_owner=2, target_owner=1, attacker_morale=None,
            defender_morale=False)


def test_observed_match_keeps_missing_post_state_unknown():
    prediction = {"owner": 2, "vector": [0] * 10}
    assert replay.observed_match(prediction, None, None) is None
    assert replay.observed_match(prediction, 2, [0] * 10) is True
    assert replay.observed_match(prediction, 1, [0] * 10) is False


def test_contamination_blocks_evaluability_without_erasing_raw_scoring():
    assert replay.evaluability({
        "production": True, "aura": False, "multiple_inbound": False,
        "special": False, "pair_relation": False, "active_delay": False,
        "capacity_uncertainty": False, "continuity": False,
    }) == (False, ["PRODUCTION"])


def test_force_disappearance_requires_complete_census_confirmation():
    rows = [
        {"signature_match": False, "same_lineage_changed": False,
         "absence_confirmed": True},
        {"signature_match": False, "same_lineage_changed": False,
         "absence_confirmed": True},
    ]
    assert replay.classify_force_status(rows, complete=True) == "DISAPPEARED"
    assert replay.classify_force_status(rows, complete=False) == "UNKNOWN"
    rows[1]["absence_confirmed"] = None
    assert replay.classify_force_status(rows, complete=True) == "AMBIGUOUS"


def test_pair_relation_uses_existing_static_hostile_guard():
    assert replay.pair_relation_status(
        target_owner=4, incoming_owner=9, player_id=4,
        target_relation="SELF", incoming_relation="ENEMY") == "KNOWN_HOSTILE"
    assert replay.pair_relation_status(
        target_owner=9, incoming_owner=4, player_id=4,
        target_relation="ENEMY", incoming_relation="SELF") == "KNOWN_HOSTILE"
    assert replay.pair_relation_status(
        target_owner=0, incoming_owner=9, player_id=4,
        target_relation="NEUTRAL", incoming_relation="ENEMY") == "KNOWN_HOSTILE"
    assert replay.pair_relation_status(
        target_owner=9, incoming_owner=10, player_id=4,
        target_relation="ENEMY", incoming_relation="ENEMY") == "UNKNOWN_PAIR_RELATION"
    assert replay.pair_relation_status(
        target_owner=9, incoming_owner=9, player_id=4,
        target_relation="ENEMY", incoming_relation="ENEMY") == "NOT_HOSTILE_SAME_OWNER"


def test_unknown_endpoint_force_alias_keeps_continuation_ambiguous():
    fact = lambda value: {"value": value, "knowledge": "OBSERVED"}
    case = {
        "target_id": 10,
        "incoming_signature": [4, 8, 10, [0, 0, 0, 0, 0, 3, 0, 0, 0, 0]],
        "snapshots": {
            "arrival": {
                "provenance": {"coverage": "PLAYER_VISIBLE_COMPLETE"},
                "forces": [{"owner": fact(4), "units": fact({"counts": [[i, n] for i, n in enumerate(
                    [0, 0, 0, 0, 0, 3, 0, 0, 0, 0])]}), "source": fact(10)}],
            }
        },
    }
    prediction = {"attacker_survivors": [0, 0, 0, 0, 0, 3, 0, 0, 0, 0]}
    status, basis = replay._observed_force_status_detail(case, "arrival", prediction)
    assert status == "AMBIGUOUS"
    assert basis == "NEW_LEG_COMPATIBLE_OWNER_AND_SURVIVOR_VECTOR"


def test_unknown_pair_relation_blocks_local_evaluability():
    contamination = {
        "production": False, "aura": False, "multiple_inbound": False,
        "special": False, "pair_relation": True, "active_delay": False,
        "capacity_uncertainty": False, "continuity": False,
    }
    assert replay.evaluability(contamination) == (False, ["PAIR_RELATION"])


def test_current_combat_source_matches_the_frozen_hash():
    assert replay.assert_pinned_formula() == replay.PINNED_COMBAT_SHA256


def test_audit_loader_keeps_exact_31_combat_required_current_leg_cases():
    rows = replay.load_audit_population()

    assert len(rows) == 31
    assert len({row["case_id"] for row in rows}) == 31
    assert Counter((row["cohort"], row["split"]) for row in rows) == Counter({
        ("03d032d57e5b", "development"): 9,
        ("daf86d0544b7", "development"): 13,
        ("7d56a775bc4c", "holdout"): 9,
    })


def test_transition_corpus_loader_keeps_four_ground_and_air_candidates():
    rows = replay.load_transition_combat_population()

    assert len(rows) == 4
    assert Counter(category for row in rows for category in row["event_categories"]
                   if category in replay.COMBAT_EVENT_CATEGORIES) == Counter({
        "ground_combat_arrival": 2,
        "ordinary_air_unit_combat_arrival": 2,
    })


def test_scored_fixture_preserves_exact_population_and_partial_verdict():
    with gzip.open(replay.OUTPUT_FIXTURE, "rt", encoding="utf-8") as stream:
        report = json.load(stream)

    assert len(report["cases"]) == 31
    assert len({row["case_id"] for row in report["cases"]}) == 31
    assert report["summary"]["formula_scored"] == 31
    assert report["summary"]["arrival_owner_match"] == 31
    assert report["summary"]["arrival_exact_match"] == 26
    assert report["summary"]["evaluable"] == 4
    assert report["summary"]["evaluable_arrival_exact_match"] == 4
    assert report["verdict"]["status"] == "PARTIAL"
    assert report["verdict"]["production_promotion"] is False
    assert report["verdict"]["formula_tuning"] is False

    aliases = report["legacy_transition_corpus_cases"]
    assert len(aliases) == 4
    assert all(row["formula_scoring_reused_from_exact_raw_case"] for row in aliases)
    assert report["population"]["submitted_rows_including_aliases"] == 35
    assert report["population"]["union_unique_cases"] == 31
    assert report["population"]["legacy_new_unique_cases"] == 0


def test_report_markdown_uses_current_evaluable_count():
    markdown = replay.OUTPUT_MARKDOWN.read_text(encoding="utf-8")

    assert "(22 development, 9 holdout)" in markdown
    assert "The four clean cases do not meet" in markdown
    assert "The seven clean cases" not in markdown
