"""Outcome-free sampling and honest-availability controls for continuation replay."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tools import v2_continuation_combat_controls as controls


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "docs" / "V2_M2A_CONTINUATION_COMBAT_CONTROL_SELECTION.json"
CONTROL_REPORT = ROOT / "docs" / "V2_M2A_CONTINUATION_COMBAT_CONTROLS.json"


def test_rank_key_is_stable_and_uses_only_preregistered_before_identity():
    salt = "kiomet-v2-continuation-combat-20261003-v1"
    group, cohort, sequence, target_id = "B", "context-a", 1234, 42
    expected = hashlib.sha256(
        f"{salt}|{group}|{cohort}|{sequence}|{target_id}".encode("utf-8")
    ).hexdigest()
    assert controls.rank_key(salt, group, cohort, sequence, target_id) == expected
    assert controls.rank_key(salt, group, cohort, sequence, target_id) == \
        controls.rank_key(salt, group, cohort, sequence, target_id)


def test_nonarrival_certification_fails_closed_on_unknown_destination_or_incomplete_census():
    before = {"provenance": {"coverage": "PLAYER_VISIBLE_COMPLETE"}, "forces": [
            {"visibility": True, "destination": {"value": 999, "knowledge": "OBSERVED"},
             "terminal": {"value": True, "knowledge": "OBSERVED"}}]}
    assert controls.certify_no_due_inbound(before, 10)[0] is True
    unknown = {"provenance": {"coverage": "PLAYER_VISIBLE_COMPLETE"}, "forces": [
        {"visibility": True, "destination": {"value": 999, "knowledge": "UNKNOWN"}}]}
    assert controls.certify_no_due_inbound(unknown, 10)[0] is False
    partial = {"provenance": {"coverage": "PLAYER_VISIBLE_PARTIAL"}, "forces": []}
    assert controls.certify_no_due_inbound(partial, 10)[0] is False


def test_pool_selection_is_invariant_to_after_outcome_fields(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "docs").mkdir()
    (project / "tests" / "fixtures" / "v2").mkdir(parents=True)
    prereg_path = project / "docs" / "prereg.json"
    prereg_path.write_bytes((ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_PREREG.json").read_bytes())
    denominator_path = project / "docs" / "denominator.json"
    raw_path = project / "raw.jsonl"
    edge_path = project / "tests" / "fixtures" / "v2" / "edges.jsonl.gz"
    selection_a, selection_b = project / "a.json", project / "b.json"

    def tower(ident, owner, units):
        return {"id": ident, "visibility": {"value": True, "knowledge": "OBSERVED"},
                "owner": {"value": owner, "knowledge": "OBSERVED"},
                "tower_type": {"value": 1, "knowledge": "OBSERVED"},
                "delay_ticks": {"value": 0, "knowledge": "OBSERVED"},
                "supply_line_present": {"value": False, "knowledge": "OBSERVED"},
                "units": {"value": {"counts": [[i, n] for i, n in enumerate(units)]},
                          "knowledge": "OBSERVED"},
                "neighbors": {"value": [20], "knowledge": "OBSERVED"}}

    def raw(tick, sequence, after_owner=2, after_unit=0, include_force=False):
        return {"document_id": "doc", "match_id": {"value": "match", "knowledge": "OBSERVED"},
            "player_id": {"value": 2, "knowledge": "OBSERVED"},
            "document_time_origin_ms": {"value": 0, "knowledge": "OBSERVED"},
            "tick": {"value": tick, "knowledge": "OBSERVED"}, "sequence": sequence,
            "after_owner": after_owner, "after_unit": after_unit, "include_force": include_force}

    def write_source(after_owner=2, after_unit=0, include_force=False):
        lines = [raw(100, 50), raw(101, 51, after_owner, after_unit, include_force)]
        raw_path.write_text("".join(json.dumps(row) + "\n" for row in lines), encoding="utf-8")
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        denominator_path.write_text(json.dumps({"inputs": {"raw_files": {
            "raw.jsonl": {"cohort": "ctx", "expected_sha256": digest}}}}),
            encoding="utf-8")
        with gzip.open(edge_path, "wt", encoding="utf-8") as stream:
            stream.write(json.dumps({"cohort": "ctx", "split": "development",
                "lines": [1, 2], "edge_index": 3}) + "\n")

    write_source()
    monkeypatch.setattr(controls, "ROOT", project)
    monkeypatch.setattr(controls, "PREREG", prereg_path)
    monkeypatch.setattr(controls, "DENOMINATOR", denominator_path)
    monkeypatch.setattr(controls, "EDGE_AUDIT", edge_path)

    def context(row, cohort, line, source_path, source_hash):
        target_owner = 1 if row["tick"]["value"] == 100 else row["after_owner"]
        target_unit = 1 if row["tick"]["value"] == 100 else row["after_unit"]
        forces = []
        if row.get("include_force"):
            forces = [{"visibility": {"value": True, "knowledge": "OBSERVED"},
                "owner": {"value": 2, "knowledge": "OBSERVED"},
                "source": {"value": 10, "knowledge": "OBSERVED"},
                "destination": {"value": 30, "knowledge": "OBSERVED"},
                "units": {"value": {"counts": [[1, 9]]}, "knowledge": "OBSERVED"}}]
        return {"provenance": {"scope": ["doc", "match", 2, 0],
            "tick": row["tick"]["value"], "sequence": row["sequence"],
            "coverage": "PLAYER_VISIBLE_COMPLETE"},
            "towers": [tower(10, target_owner, [0, target_unit] + [0] * 8),
                       tower(20, 2, [0, 2] + [0] * 8)], "forces": forces}
    monkeypatch.setattr(controls, "_context", context)

    before = {"provenance": {"scope": ["doc", "match", 2, 0],
        "sequence": 50, "tick": 100, "coverage": "PLAYER_VISIBLE_COMPLETE"},
        "towers": [tower(10, 1, [0, 1] + [0] * 8), tower(20, 2, [0, 2] + [0] * 8)],
        "forces": []}
    case = {"case_id": "b-case", "cohort": "ctx", "split": "development",
        "branch_candidate": "EMPTY_NEUTRAL_CAPTURE", "target_id": 10,
        "incoming_signature": [2, 7, 10, [0, 2] + [0] * 8],
        "_control_before": before, "_control_after": {}, "observed_owner_after": 2,
        "observed_inventory_after": [0, 0] + [0] * 8}
    b_holder = {"cases": [case]}
    monkeypatch.setattr(controls, "_load_b_pool", lambda: (b_holder["cases"], {}))

    first = controls.build_selection_plan(selection_a)
    first_refs = ([(x["cohort"], x["before_sequence"], x["target_id"], x["rank"])
                   for x in first["A"]["eligible_nonarrival_controls"]],
                  [(x["case_id"], x["target_id"], x["decoy_target_id"], x["rank"])
                   for x in first["B"]["selected_cases"]])
    # Keep scope, tick, sequences, and all before facts fixed; alter only post
    # owner/inventory and a newly observed outgoing force.
    write_source(after_owner=9, after_unit=12, include_force=True)
    case["observed_owner_after"] = 9
    case["observed_inventory_after"] = [0, 12] + [0] * 8
    case["_control_after"] = {"forces": [{"owner": 2, "source": 10,
        "destination": 30, "units": [0, 9] + [0] * 8}]}
    second = controls.build_selection_plan(selection_b)
    second_refs = ([(x["cohort"], x["before_sequence"], x["target_id"], x["rank"])
                    for x in second["A"]["eligible_nonarrival_controls"]],
                   [(x["case_id"], x["target_id"], x["decoy_target_id"], x["rank"])
                    for x in second["B"]["selected_cases"]])
    assert first_refs == second_refs


def test_frozen_control_plan_is_outcome_independent_and_has_distinct_b_decoys():
    assert SELECTION.exists(), "freeze the outcome-free A/B sample plan before scoring"
    plan = json.loads(SELECTION.read_text(encoding="utf-8"))
    prereg = json.loads((ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_PREREG.json").read_text(
        encoding="utf-8"))
    assert plan["selection_status"] == "FROZEN_BEFORE_DETECTOR_SCORING"
    assert plan["seed_salt"] == prereg["controls"]["seed_salt"]
    assert "no detector or outcome fields used" in plan["rank_rule"]
    a = plan["A"]["eligible_nonarrival_controls"]
    b = plan["B"]["selected_cases"]
    assert len(a) == plan["A"]["selected_N"] <= 100
    assert len(b) == plan["B"]["selected_N"] <= 50
    assert plan["B"]["supported_noncombat_population_expected"] == 264
    assert len({(x["cohort"], x["before_sequence"], x["target_id"]) for x in a}) == len(a)
    assert len({x["case_id"] for x in b}) == len(b)
    for row in a:
        assert row["rank"] == controls.rank_key(
            plan["seed_salt"], "A", row["cohort"], row["before_sequence"], row["target_id"])
        assert row["no_due_inbound_basis"] == "COMPLETE_BEFORE_FORCE_ROUTES_EXCLUDE_TARGET"
    for row in b:
        assert row["rank"] == controls.rank_key(
            plan["seed_salt"], "B", row["cohort"], row["before_sequence"], row["target_id"])
        assert row["decoy_target_id"] is None or row["decoy_target_id"] != row["target_id"]
    forbidden = {"outgoing_status", "actual_target_outgoing_status", "decoy_outgoing_status",
                 "continuation_accounting_status", "original_match_status"}
    assert not forbidden.intersection(plan)
    assert all(not forbidden.intersection(row) for row in a + b)


def test_scored_control_denominators_preserve_unknowns_and_noncombat_target_is_not_fp():
    assert CONTROL_REPORT.exists(), "score only after the selection plan is frozen"
    report = json.loads(CONTROL_REPORT.read_text(encoding="utf-8"))
    a = report["A"]
    b = report["B"]
    assert a["eligible_N"] == a["YES"] + a["NO"] + a["UNKNOWN"]
    assert a["conservative_yes_plus_unknown_upper_rate"] == \
        (a["YES"] + a["UNKNOWN"]) / a["eligible_N"] if a["eligible_N"] else None
    assert b["selected_N"] == len(b["cases"])
    assert b["actual_target"]["YES"] + b["actual_target"]["NO"] + \
        b["actual_target"]["UNKNOWN"] == b["selected_N"]
    assert b["decoy_available_N"] == sum(row["decoy_detection"] is not None for row in b["cases"])
    assert b["decoy"]["YES"] + b["decoy"]["NO"] + b["decoy"]["UNKNOWN"] == \
        b["decoy_available_N"]
    for row in b["cases"]:
        assert row["decoy_target_id"] is None or row["decoy_target_id"] != row["target_id"]
        if row["actual_target_outgoing_status"] == "YES":
            # A real continuation on a noncombat event target is reported as
            # actual-target presence; only a positive independent decoy is a mispair.
            assert row["decoy_outgoing_status"] in {"YES", "NO", "UNKNOWN"}
