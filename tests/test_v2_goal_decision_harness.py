"""Independent checks for the frozen Goal006 DEV reference pack.

This suite is intentionally not run until the parent freezes the reference
fixture, evaluator, and source manifest together.
"""
from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tools.v2_goal_decision_harness import (
    Action,
    admit_case,
    evaluate,
    run_policy,
    visible_state,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "v2_goal_decision_harness_dev.json"
@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def case_rows(pack: dict) -> list[dict]:
    return pack["cases"]


def _tower_row(rows: tuple, tower_id: int) -> tuple:
    return next(row for row in rows if row[0] == tower_id)


def _sample(result: dict, check: dict):
    if check["sample"] == "result":
        return result
    if check["sample"] == "horizon":
        rows = result["final_towers"]
        tower = next(row for row in rows if row[0] == check["id"])
        return {"owner": tower[2], "soldier": tower[3][5], "ruler": tower[3][9]}
    if check["sample"] == "tick":
        trace = next(row for row in result["trace"] if row["tick"] == check["tick"])
        if check["entity"] == "tower":
            owner = dict(trace["tower_owners"])[check["id"]]
            units = dict(trace["tower_units"])[check["id"]]
            return {"owner": owner, "soldier": units[5], "ruler": units[9]}
    raise AssertionError(f"unsupported hand-reference check: {check}")


def _check_reference(result: dict, check: dict) -> object:
    sample = _sample(result, check)
    if check["sample"] == "result":
        if check["field"] == "alive":
            alive = result["alive"]
            actual = alive.get(check["owner"], alive.get(str(check["owner"])))
        else:
            actual = sample[check["field"]]
    else:
        actual = sample[check["field"]]
    assert actual == check["equals"], (
        f"hand-derived reference mismatch: {check}; got {actual!r}"
    )
    return actual


def test_reference_pack_has_exactly_two_predeclared_cases_per_stratum(case_rows: list[dict]) -> None:
    assert len(case_rows) == 12
    counts: dict[str, int] = {}
    ids = set()
    for row in case_rows:
        case = row["case"]
        assert case["case_id"] not in ids
        ids.add(case["case_id"])
        counts[case["stratum"]] = counts.get(case["stratum"], 0) + 1
        assert case["horizon_ticks"] == 120
        assert len(row["reference"]["actions"]) >= 2
        for item in row["reference"]["actions"]:
            assert item["event_tick"] is not None
            assert set(item["expected"]) == {"checks"}
            assert item["expected"]["checks"]
    assert counts == {
        "S1_expansion": 2,
        "S2_contested_expansion": 2,
        "S3_threat_defense": 2,
        "S4_reinforcement": 2,
        "S5_combat_risk": 2,
        "S6_uncertainty": 2,
    }


def test_reference_pack_binds_prereg_and_full_source_bundle(pack: dict) -> None:
    assert pack["prereg_id"] == "goal-006"
    assert pack["prereg_commit"] == "51e80db38a73c226fb644363a01095fcadb88889"
    assert pack["source_envelope_commit"] == "44c79a2"
    assert len(pack["source_manifest"]) == 15
    assert set(pack["source_refs"]) == {
        "clock", "road_and_tower_identity", "tower_capacity_and_generation",
        "chunk_update_and_arrival", "combat", "ruler_loss_to_terminal",
    }


def test_all_predeclared_reference_cases_are_supported(case_rows: list[dict]) -> None:
    for row in case_rows:
        # Only the scenario mapping reaches the public admission boundary.
        admission = admit_case(row["case"])
        assert admission["status"] == "SUPPORTED", (row["case"]["case_id"], admission)


def test_reference_choices_are_legal_and_match_hand_checkpoints(case_rows: list[dict]) -> None:
    for row in case_rows:
        case = row["case"]
        menu = {
            json.dumps(action.as_dict(), sort_keys=True)
            for action in visible_state(case).legal_choices
        }
        signatures = []
        for reference in row["reference"]["actions"]:
            choice = reference["choice"]
            assert json.dumps(choice, sort_keys=True) in menu, (case["case_id"], choice)
            result = evaluate(case, choice)
            assert result["status"] == "EVALUATED", (case["case_id"], result)
            for check in reference["expected"]["checks"]:
                _check_reference(result, check)
            signatures.append((result["terminal"], tuple(sorted(result["alive"].items())),
                               result["final_towers"]))
        assert len(set(signatures)) >= 2, (
            case["case_id"], "predeclared legal choices lack different checked outcomes"
        )


def test_paired_sixth_stratum_has_the_same_visible_state(case_rows: list[dict]) -> None:
    rows = [row for row in case_rows if row["case"]["stratum"] == "S6_uncertainty"]
    assert len(rows) == 2
    first, second = (row["case"] for row in rows)
    assert first["future_opponents"] != second["future_opponents"]
    assert first["towers"] == second["towers"]
    assert first["forces"] == second["forces"]
    assert first["start_tick"] == second["start_tick"]
    assert visible_state(first) == visible_state(second)
    view = visible_state(first)
    assert not hasattr(view, "case_id")
    assert not hasattr(view, "stratum")
    assert not hasattr(view, "future_opponents")
    assert not hasattr(view, "alive")
    assert view.tick == 0


def test_policy_inputs_and_choice_are_identical_across_the_latent_pair(case_rows: list[dict]) -> None:
    rows = [row for row in case_rows if row["case"]["stratum"] == "S6_uncertainty"]
    observed = []

    def fixed_visible_policy(view, legal_choices):
        observed.append((view, legal_choices))
        return next(choice for choice in legal_choices if choice.kind == "WAIT")

    outcomes = [run_policy(row["case"], fixed_visible_policy) for row in rows]
    assert len(observed) == 2
    assert observed[0] == observed[1]
    assert outcomes[0]["policy_input"] == outcomes[1]["policy_input"]
    assert outcomes[0]["policy_choice"] == outcomes[1]["policy_choice"] == {"kind": "WAIT"}


def test_complete_legal_menu_keeps_the_opposing_edge_choice(case_rows: list[dict]) -> None:
    row = next(row for row in case_rows
               if row["case"]["case_id"] == "g006-s3-ruler-threat-immediate")
    case = row["case"]
    assert admit_case(case)["status"] == "SUPPORTED"
    core_id = next(t["id"] for t in case["towers"] if t["xy"] == [1, 1])
    hostile_source_id = next(t["id"] for t in case["towers"] if t["xy"] == [1, 2])
    assert Action("DEPLOY", core_id, hostile_source_id) in visible_state(case).legal_choices


def _invalid_cases(case_rows: list[dict]) -> list[tuple[str, dict]]:
    ordinary = next(copy.deepcopy(row["case"]) for row in case_rows
                    if row["case"]["case_id"] == "g006-s1-expansion-village")
    contested = next(copy.deepcopy(row["case"]) for row in case_rows
                     if row["case"]["case_id"] == "g006-s2-contested-neutral-slow-own")
    threat = next(copy.deepcopy(row["case"]) for row in case_rows
                  if row["case"]["case_id"] == "g006-s3-ruler-threat-immediate")
    bad: list[tuple[str, dict]] = []

    c = copy.deepcopy(ordinary); c["horizon_ticks"] = 119; bad.append(("wrong horizon", c))
    c = copy.deepcopy(ordinary); c["player"] = 2; bad.append(("unsupported player", c))
    c = copy.deepcopy(ordinary); c["closed_by_construction"] = False; bad.append(("open world", c))
    c = copy.deepcopy(ordinary); c["alive"].pop("1"); bad.append(("missing alive owner", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["visible"] = False; bad.append(("incomplete visibility", c))
    c = copy.deepcopy(ordinary); c["towers"][1]["units"][9] = 1; bad.append(("duplicate player ruler", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["units"][9] = 0; bad.append(("missing alive player's ruler", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["xy"] = [16, 10]; bad.append(("cross chunk", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["supply"] = True; bad.append(("supply line", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["units"] = [0] * 9; bad.append(("short typed vector", c))
    c = copy.deepcopy(ordinary); c["towers"][0]["units"][1] = 1; bad.append(("unsupported tower unit", c))
    c = copy.deepcopy(ordinary); c["towers"][1]["kind"] = 255; bad.append(("unsupported tower type", c))
    c = copy.deepcopy(ordinary); c["towers"].append(copy.deepcopy(c["towers"][0])); bad.append(("duplicate tower id", c))
    c = copy.deepcopy(ordinary); c["forces"] = [{"owner": 2, "src": 17, "dst": 1, "units": [0]*10, "progress": 0, "fuel": 150, "visible": True}]; bad.append(("empty force composition", c))
    c = copy.deepcopy(ordinary); c["forces"] = [{"owner": 2, "src": 17, "dst": 1, "units": [0,1,0,0,0,1,0,0,0,0], "progress": 0, "fuel": 150, "visible": True}]; bad.append(("unsupported force unit", c))
    c = copy.deepcopy(ordinary); c["forces"] = [{"owner": 2, "src": 17, "dst": 1, "units": [0,0,0,0,0,1,0,0,0,0], "progress": 256, "fuel": 150, "visible": True}]; bad.append(("out-of-range progress", c))
    c = copy.deepcopy(contested); c["future_opponents"][0]["at_tick"] = c["start_tick"]; bad.append(("not future action", c))
    c = copy.deepcopy(contested); c["future_opponents"][0]["units"] = [0]*10; bad.append(("script overrides normal inventory", c))
    c = copy.deepcopy(contested); c["future_opponents"][0]["target"] = 99999; bad.append(("unknown scripted target", c))
    c = copy.deepcopy(threat); c["forces"][0]["units"][6] = 1; bad.append(("unsupported incoming force unit", c))
    return bad


def test_unsafe_and_unsupported_admission_controls_are_refused(case_rows: list[dict]) -> None:
    controls = _invalid_cases(case_rows)
    assert len(controls) >= 12
    for label, case in controls:
        admission = admit_case(case)
        assert admission["status"] == "UNSUPPORTED", (label, admission)


def test_visible_policy_view_is_detached_and_does_not_expose_reference_or_scripts(case_rows: list[dict]) -> None:
    row = next(row for row in case_rows if row["case"]["stratum"] == "S6_uncertainty")
    case = copy.deepcopy(row["case"])
    view = visible_state(case)
    before_towers = view.towers
    before_forces = view.forces
    case["towers"].clear()
    case["future_opponents"].clear()
    assert view.towers == before_towers
    assert view.forces == before_forces
    assert isinstance(view.towers, tuple)
    assert isinstance(view.forces, tuple)
    assert isinstance(view.legal_choices, tuple)
    with pytest.raises(FrozenInstanceError):
        view.tick = 99
