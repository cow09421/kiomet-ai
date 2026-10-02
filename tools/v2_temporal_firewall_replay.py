"""Replay audited force-birth cases with a strict birth-time inference firewall.

This is a bounded analysis of retained snapshots. It does not collect live data.
The inferred launch is built from exactly the pre-birth and birth observations;
future observations are scored only after the frozen birth transition.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import UnsupportedState, from_canonical, step
import v2_external_action_replay as prior

AUDIT_PATH = ROOT / "docs/V2_M2A_TRAJECTORY_AUDIT.json"
TRAJECTORIES_PATH = ROOT / "docs/V2_M2A_TRAJECTORIES.json"
DEFAULT_OUTPUT = ROOT / "runtime/research/v2/temporal-firewall-candidate.json"
POST_BIRTH_TICKS = 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", *args],
            cwd=ROOT, check=True, capture_output=True, text=True).stdout.rstrip("\r\n")
    status = run("status", "--porcelain", "--untracked-files=all")
    return {"head": run("rev-parse", "HEAD"), "dirty": bool(status),
            "dirty_paths": [line[3:] for line in status.splitlines() if len(line) >= 4]}


def infer_birth_action(before_raw: dict[str, Any], birth_raw: dict[str, Any],
                       before_canonical: Any, birth_canonical: Any) -> dict[str, Any]:
    """Infer an action from the one permitted adjacent pair, never future rows."""
    actions, reason, proofs = prior._classify_transition(
        before_raw, birth_raw, before_canonical, birth_canonical)
    if reason or len(actions) != 1:
        births, birth_reason = prior._birth_candidates(before_raw, birth_raw)
        return {"status": "AMBIGUOUS" if births else "IMPOSSIBLE",
                "grade": "C", "reason": reason or birth_reason or "ACTION_NOT_UNIQUE",
                "source_conservation": proofs, "frozen_actions": []}
    action = actions[0]
    frozen = {"owner": action["owner"], "source": action["source"],
              "destination": action["destination"], "units": list(action["units"]),
              "player": action["player"], "terminal": None}
    return {"status": "UNIQUE", "grade": "B",
            "reason": "UNIQUE_ACTION_PARAMETERS_FROM_PRE_BIRTH_AND_BIRTH_PAIR",
            "birth_sequence": birth_raw.get("sequence"),
            "birth_world_sequence": birth_canonical.tick.value,
            "before_sequence": before_raw.get("sequence"),
            "source_visible": True,
            "source": action["source"], "owner": action["owner"],
            "current_visible_segment_target": action["destination"],
            "unit_vector": list(action["units"]),
            "source_conservation": proofs,
            "frozen_actions": [frozen],
            "manual_model_assumptions": {
                "terminal": None,
                "terminal_route": "UNKNOWN; no future route used to infer the action",
                "fuel": "existing manual Launch model initialization (150) is an assumption, not an observed input",
                "server_application_tick": "UNKNOWN; birth tick is first observation, not server time"}}


def _value(item: Any) -> Any:
    return item.get("value") if isinstance(item, dict) and "value" in item else None


def _rows(record: dict[str, Any], field: str) -> list[dict[str, Any]] | None:
    raw = record.get(field)
    values = raw if field == "towers" else _value(raw)
    return values if isinstance(values, list) and all(isinstance(x, dict) for x in values) else None


def _id_map(rows: list[dict[str, Any]] | None) -> dict[Any, dict[str, Any]] | None:
    if rows is None:
        return None
    result = {}
    for row in rows:
        raw_ident = row.get("id")
        ident = raw_ident if type(raw_ident) in (int, str) else _value(raw_ident)
        if ident is None or ident in result:
            return None
        result[ident] = row
    return result


def _units(row: dict[str, Any]) -> dict[int, int] | None:
    values = _value(row.get("units"))
    counts = values.get("counts") if isinstance(values, dict) else None
    if not isinstance(counts, list):
        return None
    result = {}
    for pair in counts:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or pair[0] in result):
            return None
        result[pair[0]] = pair[1]
    return result


def _decision_metrics(predicted: Any, observed: Any,
                      destination_id: int | None) -> dict[str, Any]:
    pred = {t.id: t for t in predicted.towers}
    obs = {t.id: t for t in observed.towers}
    if pred.keys() != obs.keys():
        return {"ownership_correctness": "UNKNOWN_TOWER_SET_MISMATCH",
                "remaining_units_l1_error": None,
                "target_owner_agreement": None,
                "capture_result_correct": None,
                "capture_result_eligible": False}
    owner_pairs = [(pred[k].owner, obs[k].owner) for k in pred]
    ownership = (all(type(a) is int and type(b) is int for a, b in owner_pairs) and
                 all(a == b for a, b in owner_pairs))
    unit_error = sum(abs(a - b) for key in pred for a, b in zip(pred[key].units, obs[key].units))
    target_agreement = None
    if destination_id in pred:
        target_agreement = pred[destination_id].owner == obs[destination_id].owner
    return {"ownership_correctness": ownership,
            "remaining_units_l1_error": unit_error,
            "target_owner_agreement": target_agreement,
            "capture_result_correct": None,
            "capture_result_eligible": False,
            "eta_tick_error": "UNKNOWN_SIM_FORCE_ETA_NOT_EXPOSED"}


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def classify_future_transition(before_raw: dict[str, Any], after_raw: dict[str, Any],
                              before_canonical: Any = None, after_canonical: Any = None) -> dict[str, Any]:
    """Multi-label visible-change patterns; causal labels require stronger evidence."""
    tags: set[str] = set()
    unknown = []
    changed_fields = []
    before_towers = _id_map(_rows(before_raw, "towers"))
    after_towers = _id_map(_rows(after_raw, "towers"))
    before_forces = _id_map(_rows(before_raw, "forces"))
    after_forces = _id_map(_rows(after_raw, "forces"))
    if None in (before_towers, after_towers, before_forces, after_forces):
        unknown.append("visible tower or force identity set incomplete")
    unit_increase = False
    unit_decrease = False
    unit_changed_ids = set()
    if before_towers is not None and after_towers is not None:
        common = before_towers.keys() & after_towers.keys()
        if before_towers.keys() != after_towers.keys():
            unknown.append("visible tower identity set changed")
        ownership_changed = set()
        for ident in common:
            b, a = before_towers[ident], after_towers[ident]
            for field in ("owner", "relation"):
                bv, av = _value(b.get(field)), _value(a.get(field))
                if bv is None or av is None:
                    unknown.append(f"tower {field} unknown")
                elif bv != av:
                    tags.add("OWNERSHIP_RELATION_CHANGE")
                    ownership_changed.add(ident)
                    changed_fields.append(f"tower[{ident}].{field}")
            bline, aline = _value(b.get("supply_line_present")), _value(a.get("supply_line_present"))
            if bline is not None and aline is not None and bline != aline:
                tags.add("SUPPLY_LINE_RELATED")
                changed_fields.append(f"tower[{ident}].supply_line_present")
            bu, au = _units(b), _units(a)
            if bu is None or au is None:
                unknown.append("tower unit vector unknown")
            elif bu != au:
                changed_fields.append(f"tower[{ident}].units")
                unit_changed_ids.add(ident)
                unit_increase |= any(au.get(k, 0) > bu.get(k, 0) for k in set(bu) | set(au))
                unit_decrease |= any(au.get(k, 0) < bu.get(k, 0) for k in set(bu) | set(au))
        if ownership_changed and any(
            _value(before_towers[k].get("relation")) != "SELF" and
            _value(after_towers[k].get("relation")) == "SELF" for k in ownership_changed):
            tags.add("CAPTURE_PATTERN")
    removed_forces = []
    if before_forces is not None and after_forces is not None:
        added, removed = after_forces.keys() - before_forces.keys(), before_forces.keys() - after_forces.keys()
        if added:
            for ident in added:
                if _value(after_forces[ident].get("confidence")) == "NEW_TRACK":
                    tags.add("LAUNCH_FORCE_BIRTH_PATTERN")
                else:
                    unknown.append("new force lacks reliable birth identity")
        for ident in removed:
            row = before_forces[ident]
            removed_forces.append((_value(row.get("source")), _value(row.get("destination"))))
        for ident in before_forces.keys() & after_forces.keys():
            b, a = before_forces[ident], after_forces[ident]
            bp, ap = _value(b.get("progress")), _value(a.get("progress"))
            if bp is not None and ap is not None and bp != ap:
                tags.add("MOVEMENT")
                changed_fields.append(f"force[{ident}].progress")
            elif bp is None or ap is None:
                unknown.append("force progress unknown")
            if _units(b) != _units(a):
                tags.add("FORCE_UNIT_VECTOR_CHANGE_PATTERN")
                changed_fields.append(f"force[{ident}].units")
            if (_value(b.get("source")), _value(b.get("destination"))) != (
                    _value(a.get("source")), _value(a.get("destination"))):
                tags.add("FORCE_SEGMENT_CHANGE_PATTERN")
                changed_fields.append(f"force[{ident}].segment")
    for _source, destination in removed_forces:
        if destination is not None and before_towers is not None and after_towers is not None and destination in before_towers and destination in after_towers:
            if _units(before_towers[destination]) != _units(after_towers[destination]):
                tags.add("ARRIVAL_PATTERN")
                relation = _value(after_towers[destination].get("relation"))
                if relation == "SELF" and unit_increase:
                    tags.add("FRIENDLY_REINFORCEMENT_PATTERN")
            else:
                tags.add("FORCE_DISAPPEARANCE_PATTERN")
                unknown.append("force disappearance alone does not prove arrival")
        else:
            tags.add("FORCE_DISAPPEARANCE_PATTERN")
            unknown.append("force disappeared without a visible destination comparison")
    if unit_increase or unit_decrease:
        production_verified = False
        if before_canonical is not None and after_canonical is not None:
            try:
                before_state = from_canonical(before_canonical)
                predicted = step(before_state)
                observed = from_canonical(after_canonical)
                expected_units = {t.id: t.units for t in predicted.towers}
                observed_units = {t.id: t.units for t in observed.towers}
                previous_units = {t.id: t.units for t in before_state.towers}
                production_verified = (expected_units == observed_units and
                    any(previous_units.get(i) != expected_units.get(i) for i in expected_units))
            except UnsupportedState:
                production_verified = False
        if production_verified:
            tags.add("PRODUCTION")
        else:
            unknown.append("tower unit change lacks exact deterministic no-action explanation")
    if tags == {"MOVEMENT"}:
        tags.add("MOVEMENT_ONLY")
    if not tags and not unknown:
        tags.add("STABLE")
    if unknown:
        tags.add("UNKNOWN")
    return {"event_tags": sorted(tags), "overlapping_tags": sorted(tags),
            "changed_fields": sorted(set(changed_fields)),
            "unknown_reasons": list(dict.fromkeys(unknown))}


def _scope(canonical: Any) -> tuple[Any, Any, Any]:
    return canonical.document_id, canonical.match_id.value, canonical.player_id.value


def simulate_continuous(start_canonical: Any, rows: list[tuple[dict[str, Any], Any]],
                        birth_index: int, frozen_actions: list[dict[str, Any]],
                        requested_total_ticks: int) -> dict[str, Any]:
    """Advance from the original start; skip scoring at the hindsight birth tick."""
    state = from_canonical(start_canonical)
    first_divergence = None
    refusal = None
    growth = []
    scored = 0
    clean_horizon = 0
    still_clean = True
    for transition_index in range(1, requested_total_ticks + 1):
        if transition_index >= len(rows):
            refusal = {"tick_index_from_start": transition_index, "reason": "OBSERVATION_GAP"}
            break
        before_raw, before_can = rows[transition_index - 1]
        after_raw, after_can = rows[transition_index]
        if ((after_can.tick.value - before_can.tick.value) & 0xFFFF) != 1:
            refusal = {"tick_index_from_start": transition_index, "reason": "NONCONSECUTIVE_WORLD_TICK"}
            break
        if _scope(before_can) != _scope(after_can) or _scope(after_can)[1] is None:
            refusal = {"tick_index_from_start": transition_index, "reason": "DOCUMENT_MATCH_PLAYER_SCOPE_CHANGED"}
            break
        if transition_index < birth_index:
            try:
                state = step(state)
            except UnsupportedState as exc:
                refusal = {"tick_index_from_start": transition_index,
                           "reason": "SIMULATOR_UNSUPPORTED_BEFORE_BIRTH:" + str(exc).split(":")[0]}
                break
            continue
        if transition_index == birth_index:
            try:
                state = prior._apply_injected_step(state, frozen_actions)
            except UnsupportedState as exc:
                refusal = {"tick_index_from_start": transition_index,
                           "reason": "MANUAL_MODEL_BIRTH_STEP_UNSUPPORTED:" + str(exc).split(":")[0]}
                break
            continue  # The birth tick is an inference observation, never scored.
        future_births, future_birth_error = prior._birth_candidates(before_raw, after_raw)
        if future_births or future_birth_error:
            refusal = {"tick_index_from_start": transition_index,
                       "world_sequence": after_can.tick.value,
                       "reason": "UNINFERRED_FUTURE_FORCE_BIRTH",
                       "detail": future_birth_error or "visible new force appears after firewall"}
            break
        try:
            observed = from_canonical(after_can)
        except UnsupportedState as exc:
            refusal = {"tick_index_from_start": transition_index,
                       "reason": "OBSERVED_STATE_UNSUPPORTED:" + str(exc).split(":")[0]}
            break
        try:
            predicted = step(state)
        except UnsupportedState as exc:
            refusal = {"tick_index_from_start": transition_index,
                       "world_sequence": after_can.tick.value,
                       "reason": "SIMULATOR_UNSUPPORTED:" + str(exc).split(":")[0]}
            break
        error = prior._error_summary(predicted, observed)
        destination_id = frozen_actions[0].get("destination") if frozen_actions else None
        decision = _decision_metrics(predicted, observed, destination_id)
        scored += 1
        growth.append({"tick_index_from_start": transition_index,
                       "future_tick_offset_from_birth": transition_index - birth_index,
                       "world_sequence": after_can.tick.value,
                       "sequence": after_raw.get("sequence"), **error,
                       "decision_metrics": decision})
        if not error["matches"]:
            if first_divergence is None:
                first_divergence = {"tick_index_from_start": transition_index,
                    "future_tick_offset_from_birth": transition_index - birth_index,
                    "world_sequence": after_can.tick.value,
                    "sequence": after_raw.get("sequence"), "fields": error["first_differences"]}
            still_clean = False
        elif still_clean:
            clean_horizon += 1
        state = predicted
    birth_sample = getattr(rows[birth_index][1], "sampled_at_ms", None) if birth_index < len(rows) else None
    clean_sample = (getattr(rows[birth_index + clean_horizon][1], "sampled_at_ms", None)
                    if birth_index + clean_horizon < len(rows) else None)
    clean_observation_span = ((clean_sample - birth_sample) / 1000 if type(clean_sample) is int and
                     type(birth_sample) is int and clean_sample >= birth_sample else None)
    return {"scoring_starts_at": "T_birth+1",
            "birth_tick_scored": False,
            "requested_post_birth_ticks": POST_BIRTH_TICKS,
            "scored_future_ticks": scored,
            "full_post_birth_horizon": scored == POST_BIRTH_TICKS and refusal is None,
            "first_future_divergence": first_divergence,
            "first_refusal": refusal,
            "longest_initial_no_divergence_horizon_ticks": clean_horizon,
            "longest_initial_no_divergence_host_observation_span_seconds": clean_observation_span,
            "longest_initial_no_divergence_nominal_seconds": clean_horizon * 0.25,
            "error_growth": growth,
            "continuous_prediction_no_reset": True,
            "conditional_post_birth_forecast_ticks": scored,
            "independent_known_causal_input_ticks": 0,
            "strict_predictive_eligibility": False,
            "strict_predictive_ineligibility_reason": "no independently authenticated causal input or Grade-A action ledger; conditional held-out forecast comparisons remain valid",
            "terminal_fuel_limit": "unknown route/fuel are manual-model assumptions; they do not exclude future ticks before the simulator actually requires those mechanics"}


def _pre_birth_cause(case_rows: list[tuple[dict[str, Any], Any]], birth_index: int,
                     source: int | None) -> dict[str, Any]:
    before_raw, _ = case_rows[birth_index - 1]
    towers = prior._raw_towers(before_raw)
    tower = towers.get(source) if towers is not None and source is not None else None
    line_fact = tower.get("supply_line_present") if tower else None
    line = (_value(line_fact) if isinstance(line_fact, dict) and line_fact.get("knowledge") == "OBSERVED"
            else None)
    prior_births = []
    for offset in range(1, birth_index):
        births, reason = prior._birth_candidates(case_rows[offset - 1][0], case_rows[offset][0])
        if reason:
            continue
        for birth in births:
            if birth["source"] == source:
                prior_births.append({"offset": offset, "world_sequence": case_rows[offset][1].tick.value})
    intervals = [((prior_births[i]["world_sequence"] - prior_births[i-1]["world_sequence"]) & 0xFFFF)
                 for i in range(1, len(prior_births))]
    periodic = ("YES" if len(prior_births) >= 3 and intervals and len(set(intervals)) == 1
                else "UNKNOWN")
    plausible_internal = (True if line is True or periodic == "YES" else
                          False if line is False and periodic == "NO" else None)
    # A short/no-birth retained window cannot prove no periodic behavior. A
    # unique action shape still does not prove which mechanism initiated it.
    cause = "AMBIGUOUS" if source is not None else "UNKNOWN"
    return {"supply_line_present_before_birth": "YES" if line is True else "NO" if line is False else "UNKNOWN",
            "source_visible": ("YES" if tower and isinstance(tower.get("visibility"), dict) and
                               tower["visibility"].get("value") is True and tower["visibility"].get("knowledge") == "OBSERVED"
                               else "NO" if tower and isinstance(tower.get("visibility"), dict) and
                               tower["visibility"].get("value") is False and tower["visibility"].get("knowledge") == "OBSERVED"
                               else "UNKNOWN"),
            "known_prior_births_from_same_source": prior_births,
            "prior_births_observed_in_retained_short_window": prior_births,
            "prior_periodic_birth_from_same_source": periodic,
            "known_relay_relationship": "UNKNOWN",
            "independent_ui_action_evidence": "NO",
            "other_player_visible_action_evidence": "UNKNOWN",
            "internal_supply_event_plausible": plausible_internal,
            "cause_classification": cause,
            "cause_note": "Birth causality is separate from later simulator stop reasons; snapshots do not prove the initiator."}


def replay_case(case: dict[str, Any], rows: list[tuple[dict[str, Any], Any]], index: int) -> dict[str, Any]:
    start_sequence = case["trajectory_start_sequence"]
    start_idx = next((i for i, (raw, _) in enumerate(rows)
                      if raw.get("sequence") == start_sequence), None)
    result = {"case_id": f"{case['cohort']}:{start_sequence}:{case['mismatch_sequence']}", "case_index": index,
        "trajectory_start_sequence": start_sequence,
        "audit_mismatch_sequence_used_for_case_identity_only": case["mismatch_sequence"],
        "formal_credit": 0, "temporal_firewall_grade": "C",
        "action_inference": {"status": "IMPOSSIBLE", "grade": "C", "reason": "NOT_RUN"},
        "future_forecast": None, "future_event_classification": [],
        "first_future_divergence": None, "first_refusal": None}
    if start_idx is None:
        result["first_refusal"] = {"reason": "AUDIT_START_NOT_RETAINED"}
        return result
    mismatch_idx = next((i for i, (raw, _) in enumerate(rows)
                         if raw.get("sequence") == case["mismatch_sequence"]), None)
    if mismatch_idx is None or mismatch_idx <= start_idx:
        result["first_refusal"] = {"reason": "AUDIT_BIRTH_PAIR_NOT_RETAINED"}
        return result
    birth_index = mismatch_idx - start_idx
    window = rows[start_idx:]
    birth_pair_before = rows[mismatch_idx - 1]
    birth_pair_after = rows[mismatch_idx]
    inference = infer_birth_action(birth_pair_before[0], birth_pair_after[0],
                                   birth_pair_before[1], birth_pair_after[1])
    result["T_birth"] = {"world_sequence": birth_pair_after[1].tick.value,
                         "observation_sequence": birth_pair_after[0].get("sequence"),
                         "offset_from_start_ticks": birth_index}
    result["action_inference"] = inference
    result["temporal_firewall_grade"] = inference["grade"]
    result["source_unit_delta_and_conservation"] = inference.get("source_conservation", [])
    result["conservation"] = ("PASS" if inference["status"] == "UNIQUE" and
        inference.get("source_conservation") and all(p.get("grade_b_conservation_pass") is True
        for p in inference["source_conservation"]) else "UNKNOWN")
    result["action_parameters_available_at_firewall"] = {
        key: inference.get(key) for key in ("source", "owner", "current_visible_segment_target", "unit_vector")}
    source = inference.get("source")
    result["pre_birth_cause"] = _pre_birth_cause(window, birth_index, source)
    required_total = max(20, birth_index + POST_BIRTH_TICKS)
    result["required_total_ticks_from_start"] = required_total
    result["required_post_birth_scoring_ticks"] = POST_BIRTH_TICKS
    result["scorable_future_ticks_start"] = "T_birth+1"
    endpoint_rows = window[:required_total + 1]
    result["available_total_ticks_from_start"] = max(0, len(endpoint_rows) - 1)
    for j in range(birth_index + 1, min(len(endpoint_rows), required_total + 1)):
        before_raw, before_can = endpoint_rows[j - 1]
        after_raw, after_can = endpoint_rows[j]
        classification = classify_future_transition(before_raw, after_raw,
            endpoint_rows[j-1][1], after_can)
        classification.update({"future_tick_offset_from_birth": j - birth_index,
            "world_sequence": after_can.tick.value, "observation_sequence": after_raw.get("sequence")})
        result["future_event_classification"].append(classification)
    if inference["status"] != "UNIQUE":
        result["first_refusal"] = {"reason": "ACTION_INFERENCE_NOT_UNIQUE", "detail": inference["reason"]}
        return result
    replay_rows = endpoint_rows
    forecast = simulate_continuous(rows[start_idx][1], replay_rows,
                                   birth_index, inference["frozen_actions"], required_total)
    # Use the untrimmed selected rows so observation-gap detection retains its denominator.
    result["future_forecast"] = forecast
    result["first_future_divergence"] = forecast["first_future_divergence"]
    result["first_refusal"] = forecast["first_refusal"]
    result["temporal_firewall_grade"] = "B"
    return result


def run_replay(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    trajectories = json.loads(TRAJECTORIES_PATH.read_text(encoding="utf-8"))
    cases = audit.get("failures")
    if not isinstance(cases, list) or len(cases) != 13:
        raise ValueError("expected exactly 13 audited mismatch identities")
    path_cases: dict[Path, list[tuple[int, dict[str, Any]]]] = {}
    for i, case in enumerate(cases, 1):
        path = ROOT / "runtime/research/v2" / Path(case["before"]["file"]).name
        path_cases.setdefault(path, []).append((i, case))
    windows = {}
    snapshot_hashes = {}
    for path, specs in path_cases.items():
        selected, digest = prior._collect_case_windows(path, specs, POST_BIRTH_TICKS)
        windows.update(selected)
        snapshot_hashes[path.relative_to(ROOT).as_posix()] = digest
    audit_hashes = audit.get("source_sha256", {})
    cohorts = {x.get("cohort"): x for x in trajectories.get("cohorts", [])}
    checks = []
    for case in cases:
        rel, cohort = case["before"]["file"], case["cohort"]
        actual = snapshot_hashes.get(rel.replace("\\", "/"))
        audit_hash = audit_hashes.get(rel)
        trajectory_hash = cohorts.get(cohort, {}).get("raw_sha256")
        checks.append({"cohort": cohort, "path": rel,
            "matches_audit_hash": actual is not None and actual == audit_hash,
            "matches_trajectory_hash": actual is not None and actual == trajectory_hash})
    integrity = all(c["matches_audit_hash"] and c["matches_trajectory_hash"] for c in checks)
    case_results = []
    for index, case in enumerate(cases, 1):
        if not integrity:
            case_results.append({"case_id": f"{case['cohort']}:{case['trajectory_start_sequence']}:{case['mismatch_sequence']}", "case_index": index,
                "temporal_firewall_grade": "C", "formal_credit": 0,
                "first_refusal": {"reason": "SNAPSHOT_HASH_MISMATCH"}})
            continue
        case_results.append(replay_case(case, windows.get(index, []), index))
    event_counts = collections.Counter()
    unscored_event_counts = collections.Counter()
    for case in case_results:
        forecast = case.get("future_forecast") or {}
        scored_offsets = {row["future_tick_offset_from_birth"] for row in forecast.get("error_growth", [])}
        for tick in case.get("future_event_classification", []):
            target = event_counts if tick["future_tick_offset_from_birth"] in scored_offsets else unscored_event_counts
            target.update(tick["event_tags"])
    horizons = [(c.get("future_forecast") or {}).get("longest_initial_no_divergence_horizon_ticks")
        for c in case_results if (c.get("future_forecast") or {}).get("longest_initial_no_divergence_horizon_ticks") is not None]
    horizon_observation_spans = [(c.get("future_forecast") or {}).get("longest_initial_no_divergence_host_observation_span_seconds")
        for c in case_results if (c.get("future_forecast") or {}).get("longest_initial_no_divergence_host_observation_span_seconds") is not None]
    horizon_nominal_seconds = [(c.get("future_forecast") or {}).get("longest_initial_no_divergence_nominal_seconds")
        for c in case_results if (c.get("future_forecast") or {}).get("longest_initial_no_divergence_nominal_seconds") is not None]
    core_sources = sorted((ROOT / "src/kiomet_ai/v2").rglob("*.py"))
    source_paths = [AUDIT_PATH, TRAJECTORIES_PATH, Path(__file__).resolve(),
                    Path(prior.__file__).resolve(), *core_sources, *path_cases]
    source_hashes = {p.relative_to(ROOT).as_posix(): _sha256(p) for p in source_paths}
    forecast_ticks = sum((c.get("future_forecast") or {}).get("scored_future_ticks", 0) for c in case_results)
    result = {"status": "CANDIDATE_TEMPORAL_FIREWALL_DIAGNOSTIC" if integrity else "SNAPSHOT_HASH_MISMATCH_FAIL_CLOSED",
        "analysis_version": "temporal-firewall-replay-v1",
        "question": "What out-of-sample post-birth forecast evidence remains when action inference sees only the pre-birth/birth pair?",
        "method": {"case_selection": "audit supplies 13 cohort/start/mismatch identities only; no audit action parameters are consumed",
            "inference_callable_inputs": ["before_raw", "birth_raw", "before_canonical", "birth_canonical"],
            "action_inference_source_boundary": "only adjacent pre-birth and T_birth observations",
            "continuous_replay": "from original trajectory start without resets; apply frozen inferred action at T_birth; do not score T_birth; score from T_birth+1",
            "primary_horizon": "max(start+20 ticks, T_birth+20 ticks)",
            "later_uninferred_birth": "stop before injecting or scoring that transition; preserve it as first refusal",
            "terminal_fuel": "manual-model launch assumptions only; terminal route and observed fuel unknown",
            "strict_predictive_eligibility": "NO_AUTHENTICATED_CAUSAL_INPUT_OR_GRADE_A_LEDGER; this does not invalidate conditional held-out comparisons",
            "terminal_fuel_limit": "unknown route/fuel do not exclude a future tick before the simulator actually requires those mechanics"},
        "source_provenance": {"snapshots_match_audit_and_trajectory_hashes": integrity,
            "snapshot_checks": checks, "current_core_manifest_scope": "all src/kiomet_ai/v2/**/*.py"},
        "head_dirty": _git_state(),
        "cases": case_results,
        "counts": {"independent_cases": len(case_results),
            "unique_action_inference": sum(c.get("action_inference", {}).get("status") == "UNIQUE" for c in case_results),
            "ambiguous_action_inference": sum(c.get("action_inference", {}).get("status") == "AMBIGUOUS" for c in case_results),
            "impossible_action_inference": sum(c.get("action_inference", {}).get("status") == "IMPOSSIBLE" for c in case_results),
            "conditional_post_birth_forecast_ticks": forecast_ticks,
            "independent_known_causal_input_ticks": 0,
            "cases_with_future_evidence": sum(bool((c.get("future_forecast") or {}).get("scored_future_ticks")) for c in case_results),
            "full_post_birth_horizons": sum((c.get("future_forecast") or {}).get("full_post_birth_horizon") is True for c in case_results)},
        "event_tag_counts_overlapping_not_independent_scored_ticks": dict(sorted(event_counts.items())),
        "event_tag_counts_unscored_observed_ticks": dict(sorted(unscored_event_counts.items())),
        "horizon_stats_ticks": {"count": len(horizons),
            "median": _percentile(horizons, 0.5),
            "p25": _percentile(horizons, 0.25),
            "p75": _percentile(horizons, 0.75),
            "max": max(horizons) if horizons else None},
        "horizon_stats_host_observation_span_seconds": {"count": len(horizon_observation_spans),
            "median": _percentile(horizon_observation_spans, 0.5),
            "p25": _percentile(horizon_observation_spans, 0.25),
            "p75": _percentile(horizon_observation_spans, 0.75),
            "max": max(horizon_observation_spans) if horizon_observation_spans else None},
        "horizon_stats_nominal_seconds": {"count": len(horizon_nominal_seconds),
            "tick_duration_seconds": 0.25,
            "median": _percentile(horizon_nominal_seconds, 0.5),
            "p25": _percentile(horizon_nominal_seconds, 0.25),
            "p75": _percentile(horizon_nominal_seconds, 0.75),
            "max": max(horizon_nominal_seconds) if horizon_nominal_seconds else None},
        "replay_verdict": "INSUFFICIENT EVIDENCE",
        "decision_metrics": {"ownership_correctness": "reported per tick only where exact owner fields are determinable; otherwise UNKNOWN",
            "remaining_units_error": "reported through exact state signature comparisons; no summary without determinable states",
            "ETA_tick_error": "UNKNOWN unless one-to-one visible force identity and ETA exist on both sides",
            "capture_result": "event tags only; no terminal result inferred",
            "action_legality": "birth-pair direct adjacency checks only; terminal path legality UNKNOWN"},
        "formal_credit": 0, "source_sha256": source_hashes,
        "tool_sha256": _sha256(Path(__file__).resolve())}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_replay(args.output)
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "event_tag_counts": result["event_tag_counts_overlapping_not_independent_scored_ticks"],
                      "horizon_stats_ticks": result["horizon_stats_ticks"],
                      "formal_credit": result["formal_credit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
