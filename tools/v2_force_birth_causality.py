"""Bounded read-only causality review for the 13 audited force births.

For each case this reads the raw recording only through the first visible
NEW_TRACK/progress-zero observation at the audited birth world tick. It writes
an explicitly candidate-only JSON receipt; it does not run the game or tests.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import UnsupportedState, from_canonical, step

AUDIT = ROOT / "docs/V2_M2A_TRAJECTORY_AUDIT.json"
TRAJECTORIES = ROOT / "docs/V2_M2A_TRAJECTORIES.json"
REPLAY = ROOT / "runtime/research/v2/external-action-replay-candidate.json"
OUTPUT = ROOT / "runtime/research/v2/force-birth-causality-candidate.json"
VERSION = "force-birth-causality-candidate-v1.0"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value(row: Any, key: str) -> Any:
    value = row.get(key) if isinstance(row, dict) else None
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _knowledge(row: Any, key: str) -> Any:
    value = row.get(key) if isinstance(row, dict) else None
    return value.get("knowledge") if isinstance(value, dict) else None


def _force_rows(state: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    box = state.get("forces") if isinstance(state, dict) else None
    rows = box.get("value") if isinstance(box, dict) else None
    return rows if isinstance(rows, list) else None


def _visible(force: dict[str, Any]) -> bool:
    return _value(force, "visibility") is True and _knowledge(force, "visibility") == "OBSERVED"


def _vector(fact: Any) -> list[int] | None:
    counts = _value({"x": fact}, "x")
    counts = counts.get("counts") if isinstance(counts, dict) else None
    if not isinstance(counts, list):
        return None
    by_index: dict[int, int] = {}
    for pair in counts:
        if (not isinstance(pair, list) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or pair[0] in by_index):
            return None
        by_index[pair[0]] = pair[1]
    return [by_index[i] for i in range(10)] if set(by_index) == set(range(10)) else None


def _tower_vector(tower: dict[str, Any] | None, field: str) -> list[int] | None:
    return _vector(tower.get(field)) if isinstance(tower, dict) else None


def _scope(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("document_id"), _value(row, "match_id"), _value(row, "player_id")


def _same_source_births(state: dict[str, Any], prior_ids: set[str], source: int) -> list[dict[str, Any]]:
    result = []
    for force in _force_rows(state) or []:
        ident = _value(force, "id")
        if (_value(force, "source") == source and _value(force, "confidence") == "NEW_TRACK" and
                _value(force, "progress") == 0 and isinstance(ident, str) and ident not in prior_ids and
                _visible(force)):
            result.append(force)
    return result


def _read_prefix(case: dict[str, Any], path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return first-per-tick prebirth rows plus the first reliable birth row; stop at T."""
    target_tick = case["after"]["world_tick"]
    target_sequence = case["after"]["sequence"]
    source = case["observed_new_force"]["source"]
    destination = case["observed_new_force"]["destination"]
    first_rows: list[dict[str, Any]] = []
    last_tick: Any = object()
    birth_state = None
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            tick = _value(row, "tick")
            if type(tick) is not int:
                continue
            first_for_tick = tick != last_tick
            if first_for_tick:
                first_rows.append(row)
                last_tick = tick
            if tick != target_tick:
                continue
            prev = next((r for r in reversed(first_rows[:-1])
                         if _value(r, "tick") == ((target_tick - 1) & 0xFFFF)), None)
            prior_ids = {_value(f, "id") for f in (_force_rows(prev) or []) if _value(f, "id")} if prev else set()
            matches = [f for f in (_force_rows(row) or [])
                       if _value(f, "source") == source and _value(f, "destination") == destination and
                       _value(f, "confidence") == "NEW_TRACK" and _value(f, "progress") == 0 and
                       isinstance(_value(f, "id"), str) and _value(f, "id") not in prior_ids and _visible(f)]
            if matches:
                birth_state = row
                break
            if row.get("sequence") == target_sequence:
                break
    return first_rows, birth_state


def _case(case: dict[str, Any], index: int, path: Path,
          replay_case: dict[str, Any], tick_ms: float) -> dict[str, Any]:
    first_rows, birth = _read_prefix(case, path)
    target = case["after"]["world_tick"]
    prior_rows = [r for r in first_rows if 0 < ((target - _value(r, "tick")) & 0xFFFF) < 32768]
    previous = prior_rows[-1] if prior_rows else None
    source, destination = case["observed_new_force"]["source"], case["observed_new_force"]["destination"]
    if birth is None or previous is None:
        return {"case_index": index, "cohort": case["cohort"], "T_birth_world_tick": target,
                "classification": "UNKNOWN", "temporal_firewall_grade": "C", "formal_credit": 0,
                "reason": "NO_RELIABLE_BIRTH_OR_COMPLETE_PREBIRTH_TICK_AT_CUTOFF"}

    before_tower = next((t for t in previous.get("towers", []) if t.get("id") == source), None)
    birth_tower = next((t for t in birth.get("towers", []) if t.get("id") == source), None)
    before_units, birth_units = _tower_vector(before_tower, "units"), _tower_vector(birth_tower, "units")
    birth_forces = [f for f in (_force_rows(birth) or [])
                    if _value(f, "source") == source and _value(f, "destination") == destination and
                    _value(f, "confidence") == "NEW_TRACK" and _value(f, "progress") == 0 and _visible(f)]
    newborn = birth_forces[0] if len(birth_forces) == 1 else None
    newborn_units = _vector(newborn.get("units")) if newborn else None
    raw_delta = [a - b for a, b in zip(before_units, birth_units)] if before_units and birth_units else None
    consecutive = (_value(birth, "tick") - _value(previous, "tick")) % 65536 == 1
    scope_complete = (_scope(previous) == _scope(birth) and
                      previous.get("coverage") == "PLAYER_VISIBLE_COMPLETE" and
                      birth.get("coverage") == "PLAYER_VISIBLE_COMPLETE")

    prior_births = []
    for pre, cur in zip(prior_rows[:-1], prior_rows[1:]):
        if (pre.get("coverage") != "PLAYER_VISIBLE_COMPLETE" or cur.get("coverage") != "PLAYER_VISIBLE_COMPLETE" or
                _scope(pre) != _scope(cur) or (_value(cur, "tick") - _value(pre, "tick")) % 65536 != 1):
            continue
        old_ids = {_value(f, "id") for f in (_force_rows(pre) or []) if _value(f, "id")}
        for force in _same_source_births(cur, old_ids, source):
            prior_births.append({"world_tick": _value(cur, "tick"), "owner": _value(force, "owner"),
                "destination": _value(force, "destination"), "unit_vector": _vector(force.get("units")),
                "progress": _value(force, "progress")})
    prior_ticks = [x["world_tick"] for x in prior_births]
    intervals = [(prior_ticks[i] - prior_ticks[i-1]) & 0xFFFF for i in range(1, len(prior_ticks))]
    periodicity = ("REPEATED_EQUAL_INTERVALS" if len(intervals) >= 2 and len(set(intervals)) == 1 else
                   "IRREGULAR_PRIOR_INTERVALS" if len(intervals) >= 2 else "UNKNOWN_TOO_FEW_PRIOR_INTERVALS")

    inbound = []
    for force in _force_rows(previous) or []:
        if _value(force, "destination") == source and _visible(force):
            inbound.append({"owner": _value(force, "owner"), "source": _value(force, "source"),
                "destination": _value(force, "destination"), "progress": _value(force, "progress"),
                "eta_ms": _value(force, "eta_ms"), "eta_knowledge": _knowledge(force, "eta_ms"),
                "unit_vector": _vector(force.get("units")), "confidence": _value(force, "confidence")})

    next_sequence = (_value(previous, "tick") + 1) & 0xFFFF
    phase_offset = ((source >> 4) & 4095) + ((source >> 20) << 8)
    phase_clock = (next_sequence + phase_offset) & 0xFFFF
    production = _value(before_tower, "production") if before_tower else None
    due = ([{"unit": p[0], "period_ticks": p[1]} for p in production
            if isinstance(p, list) and len(p) == 2 and type(p[0]) is int and type(p[1]) is int and
            p[1] > 0 and phase_clock % p[1] == 0] if isinstance(production, list) else [])
    capacity_obj = _value(before_tower, "capacity") if before_tower else None
    capacity_counts = capacity_obj.get("counts") if isinstance(capacity_obj, dict) else None
    capmap = {p[0]: p[1] for p in capacity_counts or [] if isinstance(p, list) and len(p) == 2}
    capacity = [capmap.get(i) for i in range(10)] if set(capmap) == set(range(10)) else None
    overcap = ([{"unit": i, "units": n, "capacity": capmap.get(i)} for i, n in enumerate(before_units or [])
                if i in capmap and n > capmap[i]])
    overflow_due = bool(phase_clock % 120 == 0 and overcap)

    source_step = {"status": "UNKNOWN", "reason": None, "source_units_after_no_action": None,
                   "source_delta_before_to_no_action": None}
    try:
        model_before = from_canonical(state_from_dict(previous))
        model_after = step(model_before)
        sim_tower = next((t for t in model_after.towers if t.id == source), None)
        if sim_tower is not None:
            source_step = {"status": "PASS", "reason": None,
                "source_units_after_no_action": list(sim_tower.units),
                "source_delta_before_to_no_action": [x-y for x, y in zip(before_units, sim_tower.units)]}
    except UnsupportedState as exc:
        source_step["status"], source_step["reason"] = "UNSUPPORTED", str(exc).split(":")[0]
    except Exception as exc:
        source_step["status"], source_step["reason"] = "ERROR", type(exc).__name__
    production_effects = []
    for item in due:
        unit = item["unit"]
        before_count = before_units[unit] if before_units and unit < 10 else None
        after_count = source_step["source_units_after_no_action"][unit] if source_step["source_units_after_no_action"] else None
        cap = capacity[unit] if capacity and unit < 10 else None
        effect = ("UNKNOWN_NO_LOCAL_STEP" if before_count is None or after_count is None else
                  "DUE_BUT_AT_CAPACITY_NO_UNIT_GENERATED" if cap is not None and before_count >= cap and after_count == before_count else
                  "NO_NET_GENERATION_IN_LOCAL_STEP" if after_count == before_count else
                  "LOCAL_STEP_CHANGED_INVENTORY")
        production_effects.append({**item, "prebirth_units": before_count, "capacity": cap,
                                   "no_action_units_at_T": after_count, "effect": effect})

    proof = next((r for r in replay_case.get("source_conservation", []) if r.get("source") == source), None)
    conservation = (raw_delta == newborn_units and source_step["status"] == "PASS" and
                    not any(source_step["source_delta_before_to_no_action"] or []))
    recorder, owner = _value(birth, "player_id"), _value(newborn, "owner") if newborn else None
    source_fields = [k for k in (before_tower or {}) if any(s in k.lower() for s in ("supply", "line", "relay", "route"))]
    if not source_fields:
        supply = "UNKNOWN_NOT_RETAINED"
    else:
        supply = "FIELD_PRESENT_VALUE_REQUIRES_REVIEW"
    arrival = ("NO_VISIBLE_INBOUND_FORCE_IN_COMPLETE_PREBIRTH_FORCE_SET" if not inbound else
               "POSSIBLE_WITHIN_ONE_TICK_BY_DERIVED_ETA" if any(type(x["eta_ms"]) is int and x["eta_ms"] <= tick_ms for x in inbound) else
               "UNKNOWN_INBOUND_ARRIVAL_TIME" if any(type(x["eta_ms"]) is not int for x in inbound) else
               "INBOUND_PRESENT_ETA_EXCEEDS_ONE_TICK")
    classification = "AMBIGUOUS" if newborn and scope_complete and before_units and birth_units else "UNKNOWN"
    return {"case_index": index, "cohort": case["cohort"], "snapshot_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "T_birth_world_tick": _value(birth, "tick"), "T_birth_sequence": birth.get("sequence"),
        "audit_after_sequence": case["after"]["sequence"], "audit_before_sequence": case["before"]["sequence"],
        "analysis_prebirth_first_per_tick_sequence": previous.get("sequence"),
        "temporal_cutoff": "No later world tick parsed for this case.",
        "scope": {"document_id": birth.get("document_id"), "match_id": _value(birth, "match_id"),
                  "player_id": recorder, "force_owner": owner, "recorded_player_is_force_owner": owner == recorder},
        "source": {"tower_id": source, "destination_tower_id": destination,
            "visible_before_birth": bool(before_tower and _value(before_tower, "visibility") is True and _knowledge(before_tower, "visibility") == "OBSERVED"),
            "visible_at_birth": bool(birth_tower and _value(birth_tower, "visibility") is True and _knowledge(birth_tower, "visibility") == "OBSERVED"),
            "owner_before": _value(before_tower, "owner") if before_tower else None,
            "owner_at_birth": _value(birth_tower, "owner") if birth_tower else None,
            "birth_owner_matches_source_owner": owner == _value(before_tower, "owner") == _value(birth_tower, "owner"),
            "tower_type_before": _value(before_tower, "tower_type") if before_tower else None,
            "units_before_birth": before_units, "units_at_birth": birth_units,
            "capacity_before_birth": capacity, "raw_before_minus_birth_units": raw_delta,
            "raw_unit_removal_equals_new_force_vector": raw_delta == newborn_units if raw_delta is not None and newborn_units is not None else None,
            "production_periods_before_birth": production, "local_phase_clock_at_T": phase_clock,
            "production_periods_due_at_T_by_local_phase_rule": due,
            "production_due_effects_by_local_no_action_step": production_effects,
            "owned_overflow_units_before_birth": overcap,
            "owned_overflow_cleanup_due_at_T_by_local_rule": overflow_due,
            "supply_line_presence_before_birth": supply, "retained_source_supply_route_relay_fields": source_fields,
            "no_action_source_step": source_step,
            "source_inventory_conservation_status": "PASS_SOURCE_REMOVAL_EQUALS_BIRTH_AND_LOCAL_NO_ACTION_SOURCE_DELTA_IS_ZERO; CAUSE_NOT_IDENTIFIED" if conservation else "UNKNOWN_OR_NOT_EXACT",
            "external_replay_source_conservation": ({k: proof.get(k) for k in ("raw_before_to_observed_after_source_delta", "deterministic_no_action_to_observed_source_delta", "aggregate_new_force_units", "grade_b_conservation_pass")} if proof else None)},
        "new_force": {"reliable_birth_found": bool(newborn), "count_for_exact_pair": len(birth_forces),
            "owner": owner, "unit_vector": newborn_units, "progress": _value(newborn, "progress") if newborn else None,
            "confidence": _value(newborn, "confidence") if newborn else None, "visible_observed": _visible(newborn) if newborn else False},
        "prebirth_inbound_forces_to_source": inbound,
        "prebirth_inbound_arrival_assessment": {"status": arrival, "world_tick_duration_ms": tick_ms,
            "basis": "Immediate prebirth current-segment/progress and observer-derived ETA only; not a server arrival guarantee."},
        "prior_same_source_newborns_before_T": prior_births, "prior_same_source_birth_ticks": prior_ticks,
        "prior_interbirth_tick_intervals": intervals, "periodicity_assessment": periodicity,
        "route_relay_assessment": "UNKNOWN: retained force snapshots expose current segment only; source rows contain no supply-line/route/relay field",
        "action_evidence": {"case_scoped_ACTION_INTENT": "NOT_FOUND_IN_RETAINED_RUNTIME_RECORDS",
            "case_scoped_UI_ACTION_RESULT": "NOT_FOUND_IN_RETAINED_RUNTIME_RECORDS",
            "other_player_action": "NOT_OBSERVED_OR_ATTRIBUTED"},
        "action_inference": "AMBIGUOUS_NO_UNIQUE_CAUSAL_INPUT_AT_CUTOFF" if classification == "AMBIGUOUS" else "IMPOSSIBLE_FROM_AVAILABLE_CUTOFF_DATA",
        "temporal_firewall_grade": "C", "classification": classification,
        "classification_reason": "Reliable birth and source-unit accounting are consistent, but no case-scoped pre-action/UI provenance exists and supply-line/route/relay input is unknown." if classification == "AMBIGUOUS" else "Birth/source evidence incomplete at cutoff.",
        "formal_credit": 0}


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    trajectory = json.loads(TRAJECTORIES.read_text(encoding="utf-8"))
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    by_case = {(x.get("cohort"), x.get("mismatch_sequence")): x for x in replay.get("cases", [])}
    cohort_hashes = {x.get("cohort"): x.get("raw_sha256") for x in trajectory.get("cohorts", [])}
    case_results, snapshot_hashes = [], {}
    for index, case in enumerate(audit.get("failures", []), 1):
        rel = case["before"]["file"]
        snapshot = ROOT / "runtime/research/v2" / Path(rel).name
        snapshot_hashes[rel] = _sha(snapshot)
        case_results.append(_case(case, index, snapshot,
            by_case.get((case["cohort"], case["mismatch_sequence"]), {}),
            float(trajectory.get("tick_duration_ms", 250.0))))
    checks = []
    for rel, digest in sorted(snapshot_hashes.items()):
        cohort = next(x["cohort"] for x in audit["failures"] if x["before"]["file"] == rel)
        checks.append({"path": rel, "sha256": digest,
            "audit_sha256_matches": audit.get("source_sha256", {}).get(rel) == digest,
            "trajectory_cohort_sha256_matches": cohort_hashes.get(cohort) == digest})
    ledger_files = []
    for path in (ROOT / "runtime/research/v2").rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "ACTION_INTENT" in text or "UI_ACTION_RESULT" in text:
                ledger_files.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    git = subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", "status", "--short", "--untracked-files=all"],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout.rstrip()
    head = subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout.rstrip()
    sources = [AUDIT, TRAJECTORIES, REPLAY, ROOT / "src/kiomet_ai/v2/sim/step.py",
               ROOT / "docs/V2_M2A_LAUNCH_RULE.md", Path(__file__).resolve()]
    result = {"status": "CANDIDATE_PARTIAL_NO_CAUSAL_CREDIT", "analysis_version": VERSION,
        "formal_credit": 0,
        "classification_counts": {kind: sum(c["classification"] == kind for c in case_results)
            for kind in ("LIKELY_EXTERNAL_PLAYER_ACTION", "LIKELY_INTERNAL_SUPPLY_EVENT", "AMBIGUOUS", "UNKNOWN")},
        "fixed_method": {"temporal_firewall": "Per case, parse no world sequence later than T_birth; use the first reliable visible matching NEW_TRACK/progress-zero observation within the audited birth tick.",
            "prebirth_baseline": "First retained observation in the immediately previous distinct world tick; same document/match/player scope and complete coverage required.",
            "source_conservation": "Report raw pre-minus-birth vector and local deterministic no-action source counterfactual; consistency does not identify the actor or exclude unmodeled supply-line dispatch.",
            "supply_rule": "Only explicit prebirth fields/observations count; missing supply-line/route/relay values stay UNKNOWN.",
            "prior_periodicity": "Only complete same-scope consecutive first-per-tick births strictly before current T; require at least two prior intervals exactly equal before claiming periodicity.",
            "external_action_threshold": "Case-linked durable ACTION_INTENT/UI_ACTION_RESULT plus unique pair birth and vector consistency; none retained for these cases.",
            "internal_supply_threshold": "Known prebirth supply-line/relay input plus prior repeated equal intervals and vector-consistent event; none meets this threshold.",
            "inbound_arrival": "Only immediate prebirth inbound force rows, progress and observer-derived ETA versus report tick duration; derived ETA is not server authority.",
            "production_overflow": "Compute source local phase/production and overflow opportunity at T; compare local no-action inventory effects. This does not prove supply-line absence."},
        "source_scope": {"git_head": head, "dirty": bool(git), "dirty_paths": [x[3:] for x in git.splitlines() if len(x) >= 4],
            "data_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): _sha(p) for p in sources},
            "snapshot_checks": checks, "tick_duration_ms": trajectory.get("tick_duration_ms"),
            "case_scoped_action_ledger_files_found": ledger_files,
            "temporal_access": "Full-file SHA-256 is recorded for provenance; each case parser stops at its first reliable birth observation in T_birth and does not parse a later tick."},
        "cases": case_results,
        "summary_evidence": {"reliable_force_births": sum(c["new_force"]["reliable_birth_found"] for c in case_results),
            "source_removal_equals_birth_vector": sum(c["source"]["raw_unit_removal_equals_new_force_vector"] is True for c in case_results),
            "local_no_action_source_step_zero_delta": sum(c["source"]["no_action_source_step"]["status"] == "PASS" and not any(c["source"]["no_action_source_step"]["source_delta_before_to_no_action"] or []) for c in case_results),
            "source_owned_by_recorded_player": sum(c["scope"]["recorded_player_is_force_owner"] for c in case_results),
            "source_supply_line_route_unknown": sum(c["source"]["supply_line_presence_before_birth"] == "UNKNOWN_NOT_RETAINED" for c in case_results),
            "visible_prebirth_inbound_force_cases": sum(bool(c["prebirth_inbound_forces_to_source"]) for c in case_results),
            "overflow_cleanup_due_cases": sum(c["source"]["owned_overflow_cleanup_due_at_T_by_local_rule"] for c in case_results),
            "production_due_cases": sum(bool(c["source"]["production_periods_due_at_T_by_local_phase_rule"]) for c in case_results)},
        "limitations": ["No case-linked ACTION_INTENT/UI_ACTION_RESULT found in retained runtime records; this does not prove no human input occurred.",
            "Old snapshots do not retain source supply-line/route/relay values; current force segments expose only the current leg.",
            "Exact source removal and local no-action conservation are compatible with a manual launch and an unmodeled automatic dispatch.",
            "No case is classified likely external or likely internal without positive causal input evidence."]}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(OUTPUT.relative_to(ROOT)), "cases": len(case_results),
        "classification_counts": result["classification_counts"], "summary_evidence": result["summary_evidence"],
        "all_snapshot_pins_match": all(x["audit_sha256_matches"] and x["trajectory_cohort_sha256_matches"] for x in checks),
        "analysis_script_sha256": _sha(Path(__file__).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
