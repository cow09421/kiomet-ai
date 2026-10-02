"""Finite replay of audited V2 external-force births as injected actions.

Grade-B actions are inferred from adjacent visible snapshots plus same-tick
no-action source inventory deltas. They are diagnostic inputs, never Grade-A
provenance. No observed after-state is used to modify a simulator prediction.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import Launch, Scenario, UnsupportedState, from_canonical, step
from v2_sim_differential import signature

AUDIT_PATH = ROOT / "docs/V2_M2A_TRAJECTORY_AUDIT.json"
TRAJECTORIES_PATH = ROOT / "docs/V2_M2A_TRAJECTORIES.json"
DEFAULT_OUTPUT = ROOT / "runtime/research/v2/external-action-replay-candidate.json"
HORIZON_TICKS = 20


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", *args],
                              cwd=ROOT, check=True, capture_output=True, text=True).stdout.rstrip("\r\n")
    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain", "--untracked-files=all")
    paths = [line[3:] for line in status.splitlines() if len(line) >= 4]
    return {"head": head, "dirty": bool(status), "dirty_paths": paths}


def _fact_value(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) and "value" in fact else None


def _observed_visible(raw: dict[str, Any]) -> bool:
    visibility = raw.get("visibility")
    return (isinstance(visibility, dict) and visibility.get("value") is True and
            visibility.get("knowledge") == "OBSERVED")


def _raw_towers(record: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = record.get("towers")
    if not isinstance(rows, list):
        raise ValueError("RAW_TOWERS_UNAVAILABLE")
    result = {}
    for tower in rows:
        if not isinstance(tower, dict) or type(tower.get("id")) is not int:
            raise ValueError("RAW_TOWER_ID_INVALID")
        if tower["id"] in result:
            raise ValueError("RAW_TOWER_ID_DUPLICATE")
        result[tower["id"]] = tower
    return result


def _tower_units(raw_tower: dict[str, Any]) -> tuple[int, ...] | None:
    unit_fact = raw_tower.get("units")
    counts = _fact_value(unit_fact)
    pairs = counts.get("counts") if isinstance(counts, dict) else None
    if not isinstance(pairs, list):
        return None
    by_index = {}
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or not 0 <= pair[1] <= 255):
            return None
        if pair[0] in by_index:
            return None
        by_index[pair[0]] = pair[1]
    if set(by_index) != set(range(10)):
        return None
    return tuple(by_index[i] for i in range(10))


def _force_rows(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    forces = record.get("forces")
    rows = _fact_value(forces)
    return rows if isinstance(rows, list) and all(isinstance(r, dict) for r in rows) else None


def _birth_candidates(before_raw: dict[str, Any], after_raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    before_rows, after_rows = _force_rows(before_raw), _force_rows(after_raw)
    if before_rows is None or after_rows is None:
        return [], "FORCE_SET_UNAVAILABLE"
    before_ids = set()
    for force in before_rows:
        ident = _fact_value(force.get("id"))
        if not isinstance(ident, str) or not ident:
            return [], "BEFORE_FORCE_OBSERVER_ID_UNAVAILABLE"
        if ident in before_ids:
            return [], "DUPLICATE_BEFORE_FORCE_OBSERVER_ID"
        before_ids.add(ident)
    candidates = []
    seen_after_ids = set()
    for position, force in enumerate(after_rows):
        ident = _fact_value(force.get("id"))
        if not isinstance(ident, str) or not ident:
            return [], "AFTER_FORCE_OBSERVER_ID_UNAVAILABLE"
        if ident in seen_after_ids:
            return [], "DUPLICATE_AFTER_FORCE_OBSERVER_ID"
        seen_after_ids.add(ident)
        confidence = _fact_value(force.get("confidence"))
        visibility = force.get("visibility")
        if not _observed_visible(force):
            return [], "FORCE_VISIBILITY_NOT_OBSERVED"
        if ident in before_ids:
            if confidence == "NEW_TRACK":
                return [], "EXISTING_ID_MARKED_NEW_TRACK"
            continue
        if confidence != "NEW_TRACK":
            # New identities without the observer's explicit new-track marker
            # are ambiguous continuations, not inferred actions.
            return [], "NEW_FORCE_LACKS_NEW_TRACK_MARKER"
        progress = _fact_value(force.get("progress"))
        units_raw = _fact_value(force.get("units"))
        pairs = units_raw.get("counts") if isinstance(units_raw, dict) else None
        if not isinstance(pairs, list):
            return [], "NEW_FORCE_UNITS_UNAVAILABLE"
        by_index = {}
        for pair in pairs:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                    type(pair[0]) is not int or type(pair[1]) is not int or pair[1] < 0 or pair[0] in by_index):
                return [], "NEW_FORCE_UNITS_INVALID"
            by_index[pair[0]] = pair[1]
        if set(by_index) != set(range(10)):
            return [], "NEW_FORCE_VECTOR_INCOMPLETE"
        if any(count > 255 for count in by_index.values()):
            return [], "NEW_FORCE_U8_COUNT_OUT_OF_RANGE"
        unit_vector = tuple(by_index[i] for i in range(10))
        reported_count = _fact_value(force.get("unit_count"))
        if type(reported_count) is not int or reported_count != sum(unit_vector):
            return [], "NEW_FORCE_UNIT_COUNT_INCONSISTENT"
        if (type(progress) is not int or progress != 0 or not any(unit_vector)):
            return [], "NEW_FORCE_NOT_PROGRESS_ZERO_OR_EMPTY"
        owner = _fact_value(force.get("owner"))
        source = _fact_value(force.get("source"))
        destination = _fact_value(force.get("destination"))
        relation = _fact_value(force.get("relation"))
        if type(owner) is not int or owner <= 0 or type(source) is not int or type(destination) is not int:
            return [], "NEW_FORCE_ENDPOINT_OR_OWNER_UNKNOWN"
        if relation is not None and not isinstance(relation, str):
            return [], "NEW_FORCE_RELATION_INVALID"
        candidates.append({"snapshot_birth_order": position, "owner": owner,
                           "source": source, "destination": destination,
                           "units": unit_vector, "relation": relation,
                           "observer_identity_new": True, "progress_zero": True})
    if len(after_rows) > len(before_rows) and not candidates:
        return [], "FORCE_COUNT_INCREASE_WITHOUT_VERIFIABLE_NEW_TRACK"
    return candidates, None


def _tower_int(raw: dict[str, Any], field: str) -> int | None:
    value = _fact_value(raw.get(field))
    return value if type(value) is int else None


def _tower_morale(raw: dict[str, Any]) -> bool | None:
    effects = _fact_value(raw.get("effects"))
    if not isinstance(effects, list):
        return None
    values = {}
    for item in effects:
        if (not isinstance(item, (list, tuple)) or len(item) != 2 or
                not isinstance(item[0], str) or type(item[1]) is not bool or item[0] in values):
            return None
        values[item[0]] = item[1]
    if set(values) != {"MORALE_BOOST"}:
        return None
    return values["MORALE_BOOST"]


def _exact_launch_actions(before_raw: dict[str, Any], after_raw: dict[str, Any],
                          before_state: Any, no_action_after: Any,
                          births: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str | None, list[dict[str, Any]]]:
    """Grade B only if each source's full deterministic inventory delta is explained."""
    if not births:
        return [], None, []
    before_towers = _raw_towers(before_raw)
    after_towers = _raw_towers(after_raw)
    observed_model = {t.id: t for t in before_state.towers}
    deterministic = {t.id: t for t in no_action_after.towers}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for birth in births:
        grouped.setdefault(birth["source"], []).append(birth)
    proof_rows = []
    for source, source_births in grouped.items():
        raw_before, raw_after = before_towers.get(source), after_towers.get(source)
        model_before, model_after = observed_model.get(source), deterministic.get(source)
        if raw_before is None or raw_after is None or model_before is None or model_after is None:
            return None, "SOURCE_TOWER_UNAVAILABLE", proof_rows
        if not _observed_visible(raw_before) or not _observed_visible(raw_after):
            return None, "SOURCE_TOWER_VISIBILITY_NOT_OBSERVED", proof_rows
        before_units = _tower_units(raw_before)
        raw_after_units = _tower_units(raw_after)
        if before_units is None or raw_after_units is None:
            return None, "SOURCE_UNIT_VECTOR_UNKNOWN", proof_rows
        after_owner, after_kind = _tower_int(raw_after, "owner"), _tower_int(raw_after, "tower_type")
        before_owner, before_kind = _tower_int(raw_before, "owner"), _tower_int(raw_before, "tower_type")
        before_morale, after_morale = _tower_morale(raw_before), _tower_morale(raw_after)
        if (before_owner is None or after_owner is None or before_kind is None or after_kind is None or
                before_morale is None or after_morale is None or
                before_owner != after_owner or before_owner != model_before.owner or
                after_owner != model_after.owner or before_kind != after_kind or
                before_kind != model_before.kind or after_kind != model_after.kind or
                before_morale != after_morale or before_morale != model_before.morale or
                after_morale != model_after.morale):
            return None, "SOURCE_OWNER_TYPE_OR_MORALE_CHANGED", proof_rows
        if any(b["owner"] != after_owner for b in source_births):
            return None, "SOURCE_OWNER_DOES_NOT_MATCH_FORCE_OWNER", proof_rows
        expected = [0] * 10
        for birth in source_births:
            for i, count in enumerate(birth["units"]):
                expected[i] += count
        raw_delta = tuple(before_units[i] - raw_after_units[i] for i in range(10))
        model_delta = tuple(model_after.units[i] - raw_after_units[i] for i in range(10))
        exact_model_conservation = model_delta == tuple(expected)
        proof_rows.append({"source": source, "birth_count": len(source_births),
                           "raw_before_to_observed_after_source_delta": list(raw_delta),
                           "deterministic_no_action_to_observed_source_delta": list(model_delta),
                           "aggregate_new_force_units": expected,
                           "grade_b_conservation_pass": exact_model_conservation})
        if not exact_model_conservation:
            return None, "SOURCE_DELTA_DOES_NOT_EXACTLY_MATCH_BIRTHS", proof_rows
        if source not in observed_model or any(b["destination"] not in observed_model for b in source_births):
            return None, "ACTION_ENDPOINT_NOT_IN_VISIBLE_TOWER_SET", proof_rows
        tower = observed_model[source]
        for birth in source_births:
            destination_before = before_towers.get(birth["destination"])
            destination_after = after_towers.get(birth["destination"])
            if (destination_before is None or destination_after is None or
                    not _observed_visible(destination_before) or not _observed_visible(destination_after)):
                return None, "DESTINATION_TOWER_VISIBILITY_NOT_OBSERVED", proof_rows
            if birth["destination"] not in tower.neighbors:
                return None, "ACTION_DESTINATION_NOT_VISIBLE_NEIGHBOR", proof_rows
    # Preserve observed snapshot-local birth order. Current step API separates
    # player and opponent queues; mixed-owner interleaving cannot be represented.
    owners_in_order = []
    player = before_state.player
    for birth in births:
        bucket = "player" if birth["owner"] == player else "opponent"
        if not owners_in_order or owners_in_order[-1] != bucket:
            owners_in_order.append(bucket)
    if len(owners_in_order) > 1:
        return None, "MIXED_OWNER_BIRTH_ORDER_NOT_REPRESENTABLE_BY_STEP_API", proof_rows
    actions = []
    for birth in births:
        actions.append({**birth, "evidence_grade": "B",
                        "terminal": None,
                        "fuel_assumption": "manual-DeployForce model initializes fuel=150; not observed or independently authenticated"})
    return actions, None, proof_rows


def _to_launch(action: dict[str, Any]) -> Launch:
    owner = None if action["owner"] == action["player"] else action["owner"]
    return Launch(action["source"], action["destination"], tuple(action["units"]),
                  owner=owner, terminal=None)


def _apply_injected_step(state: Any, actions: list[dict[str, Any]]) -> Any:
    player = state.player
    own = []
    opponent = []
    for item in actions:
        prepared = {**item, "player": player}
        launch = _to_launch(prepared)
        if item["owner"] == player:
            own.append(launch)
        else:
            opponent.append(launch)
    scenario = Scenario(opponent_launches=tuple(opponent))
    return step(state, tuple(own), scenario=scenario)


def _normalize(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _diff_paths(left: Any, right: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    if type(left) is not type(right):
        return [(path or "$", left, right)]
    if isinstance(left, dict):
        diffs = []
        for key in sorted(left.keys() | right.keys()):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                diffs.append((child, left.get(key), right.get(key)))
            else:
                diffs.extend(_diff_paths(left[key], right[key], child))
        return diffs
    if isinstance(left, list):
        if len(left) != len(right):
            return [(f"{path}.length", len(left), len(right))]
        diffs = []
        for i, (a, b) in enumerate(zip(left, right)):
            diffs.extend(_diff_paths(a, b, f"{path}[{i}]"))
        return diffs
    return [] if left == right else [(path or "$", left, right)]


def _error_summary(predicted: Any, observed: Any) -> dict[str, Any]:
    left, right = _normalize(signature(predicted)), _normalize(signature(observed))
    diffs = _diff_paths(left, right)
    top_level = sorted({path.split(".", 1)[0].split("[", 1)[0] for path, _, _ in diffs})
    numeric_delta = sum(abs(a - b) for _, a, b in diffs
                        if type(a) in (int, float) and type(b) in (int, float))
    return {"matches": not diffs,
            "differing_top_level_fields": top_level,
            "differing_leaf_count": len(diffs),
            "numeric_absolute_delta_sum": numeric_delta,
            "first_differences": [{"field": p, "predicted": a, "observed": b}
                                  for p, a, b in diffs[:12]]}


def _collect_case_windows(path: Path, case_specs: list[tuple[int, dict[str, Any]]],
                          minimum_horizon: int) -> tuple[dict[int, list[tuple[dict[str, Any], Any]]], str]:
    """Hash the full JSONL stream while retaining only audited 20–40 tick windows."""
    starts: dict[int, list[tuple[int, int]]] = {}
    windows: dict[int, list[tuple[dict[str, Any], Any]]] = {index: [] for index, _ in case_specs}
    lengths = {}
    for index, case in case_specs:
        starts.setdefault(case["trajectory_start_sequence"], []).append((index, case["comparison_ticks"]))
        lengths[index] = max(minimum_horizon, case["comparison_ticks"] + minimum_horizon)
    active: dict[int, tuple[int, int]] = {}
    digest = hashlib.sha256()
    previous_tick = object()
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            raw = json.loads(raw_line)
            tick_fact = raw.get("tick")
            tick = tick_fact.get("value") if isinstance(tick_fact, dict) else None
            if type(tick) is not int:
                continue
            if tick == previous_tick:
                continue  # Same first-observation-per-tick policy as trajectory audit.
            previous_tick = tick
            sequence = raw.get("sequence")
            if type(sequence) is int:
                for index, _offset in starts.get(sequence, []):
                    active[index] = (tick, lengths[index])
            selected = []
            expired = []
            for index, (start_tick, window_length) in active.items():
                elapsed = (tick - start_tick) & 65535
                if elapsed <= window_length:
                    selected.append(index)
                else:
                    expired.append(index)
            for index in expired:
                active.pop(index, None)
            if selected:
                canonical = state_from_dict(raw)
                for index in selected:
                    windows[index].append((raw, canonical))
    return windows, digest.hexdigest()


def _classify_transition(before_raw: dict[str, Any], after_raw: dict[str, Any],
                         before_canonical: Any, after_canonical: Any) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    births, reason = _birth_candidates(before_raw, after_raw)
    if reason:
        return [], reason, []
    if not births:
        return [], None, []
    before_scope = (before_canonical.document_id, before_canonical.match_id.value,
                    before_canonical.player_id.value)
    after_scope = (after_canonical.document_id, after_canonical.match_id.value,
                   after_canonical.player_id.value)
    if before_scope != after_scope or before_scope[1] is None or (after_canonical.tick.value-before_canonical.tick.value)%65536 != 1:
        return [], "TRANSITION_SCOPE_OR_TICK_INVALID", []
    try:
        before_state = from_canonical(before_canonical)
        no_action_after = step(before_state)
    except UnsupportedState as exc:
        return [], f"NO_ACTION_SOURCE_DELTA_UNAVAILABLE:{str(exc).split(':')[0]}", []
    actions, reason, proof = _exact_launch_actions(before_raw, after_raw, before_state,
                                                    no_action_after, births)
    if actions is not None:
        for action in actions:
            action["player"] = before_state.player
    return actions or [], reason, proof


def _run_branch(start_state: Any, tick_rows: list[tuple[dict[str, Any], Any]],
                transition_actions: list[dict[str, Any] | None], limit: int,
                inject: bool, requested_limit: int) -> dict[str, Any]:
    state = start_state
    comparisons = []
    first_divergence = None
    stop_reason = None
    actions_applied = 0
    horizon = 0
    for tick_index in range(1, limit + 1):
        before_raw, before_canonical = tick_rows[tick_index - 1]
        after_raw, after_canonical = tick_rows[tick_index]
        before_tick = before_canonical.tick.value
        after_tick = after_canonical.tick.value
        if (after_tick - before_tick) % 65536 != 1:
            stop_reason = "NONCONSECUTIVE_OBSERVATION_TICKS"
            break
        before_scope = (before_canonical.document_id, before_canonical.match_id.value,
                        before_canonical.player_id.value)
        after_scope = (after_canonical.document_id, after_canonical.match_id.value,
                       after_canonical.player_id.value)
        if before_scope != after_scope or before_scope[1] is None:
            stop_reason = "OBSERVATION_SCOPE_CHANGED"
            break
        try:
            observed_after = from_canonical(after_canonical)
        except UnsupportedState as exc:
            stop_reason = f"OBSERVED_STATE_UNSUPPORTED:{str(exc).split(':')[0]}"
            break
        action_rows = transition_actions[tick_index - 1] or [] if inject else []
        if inject and transition_actions[tick_index - 1] is None:
            stop_reason = "GRADE_C_EXTERNAL_ACTION_UNRESOLVED"
            break
        try:
            predicted = _apply_injected_step(state, action_rows) if action_rows else step(state)
        except UnsupportedState as exc:
            stop_reason = f"SIMULATOR_UNSUPPORTED:{str(exc).split(':')[0]}"
            break
        actions_applied += len(action_rows)
        error = _error_summary(predicted, observed_after)
        comparisons.append({"tick_index": tick_index,
                            "world_tick": observed_after.world_sequence,
                            "observed_sequence": after_raw.get("sequence"),
                            **error})
        if first_divergence is None and not error["matches"]:
            first_divergence = {"tick_index": tick_index,
                                "world_tick": observed_after.world_sequence,
                                "sequence": after_raw.get("sequence"),
                                "fields": error["first_differences"]}
        state = predicted
        horizon = tick_index
    if stop_reason is None and limit < requested_limit:
        stop_reason = "OBSERVATION_GAP"
    return {"status": "FULL_HORIZON" if horizon == requested_limit and stop_reason is None else "PARTIAL",
            "requested_ticks": requested_limit, "available_observation_ticks": limit,
            "simulated_and_compared_ticks": horizon,
            "actions_injected": actions_applied,
            "first_divergence": first_divergence,
            "error_growth": comparisons,
            "stop_reason": stop_reason,
            "full_trajectory_match": horizon == requested_limit and stop_reason is None and first_divergence is None}


def replay_case(audit_case: dict[str, Any], rows: list[tuple[dict[str, Any], Any]],
                audit_index: int, minimum_horizon: int = HORIZON_TICKS) -> dict[str, Any]:
    cohort = audit_case["cohort"]
    start_sequence = audit_case["trajectory_start_sequence"]
    mismatch_sequence = audit_case["mismatch_sequence"]
    start_index = next((i for i, (raw, _) in enumerate(rows)
                        if raw.get("sequence") == start_sequence), None)
    base = {"cohort": cohort, "case_index": audit_index,
            "trajectory_start_sequence": start_sequence,
            "mismatch_sequence": mismatch_sequence,
            "minimum_horizon_ticks": minimum_horizon,
            "formal_credit": 0,
            "action_evidence_grade": "C",
            "grade_c_reason": None,
            "actions": [], "source_conservation": [],
            "baseline_no_action": None, "injected_action_replay": None}
    if start_index is None:
        base["grade_c_reason"] = "AUDIT_START_SEQUENCE_NOT_FIRST_OBSERVATION_PER_TICK"
        base["baseline_no_action"] = {"status": "NOT_RUN_NO_EXACT_START", "simulated_and_compared_ticks": 0}
        base["injected_action_replay"] = {"status": "NOT_REPLAYABLE", "simulated_and_compared_ticks": 0,
                                          "stop_reason": base["grade_c_reason"]}
        return base
    mismatch_index = next((i for i, (raw, _) in enumerate(rows)
                           if raw.get("sequence") == mismatch_sequence), None)
    if mismatch_index is None or mismatch_index <= start_index:
        base["grade_c_reason"] = "AUDIT_MISMATCH_SEQUENCE_NOT_AFTER_START"
        base["baseline_no_action"] = {"status": "NOT_RUN_NO_AUDIT_MISMATCH_TICK", "simulated_and_compared_ticks": 0}
        base["injected_action_replay"] = {"status": "NOT_REPLAYABLE", "simulated_and_compared_ticks": 0,
                                          "stop_reason": base["grade_c_reason"]}
        return base
    original_mismatch_offset = mismatch_index - start_index
    if original_mismatch_offset != audit_case.get("comparison_ticks"):
        base["grade_c_reason"] = "AUDIT_MISMATCH_TICK_OFFSET_MISMATCH"
        base["baseline_no_action"] = {"status": "NOT_RUN_AUDIT_OFFSET_MISMATCH", "simulated_and_compared_ticks": 0}
        base["injected_action_replay"] = {"status": "NOT_REPLAYABLE", "simulated_and_compared_ticks": 0,
                                          "stop_reason": base["grade_c_reason"]}
        return base
    required_horizon = max(minimum_horizon, original_mismatch_offset + minimum_horizon)
    base["original_first_divergence_offset_ticks"] = original_mismatch_offset
    base["required_primary_horizon_ticks"] = required_horizon
    base["secondary_original_20_tick_horizon"] = minimum_horizon
    available = min(required_horizon, len(rows) - start_index - 1)
    if available <= 0:
        base["grade_c_reason"] = "NO_FOLLOWING_FIRST_PER_TICK_OBSERVATIONS"
        base["baseline_no_action"] = {"status": "NOT_RUN_NO_FOLLOWING_TICK", "simulated_and_compared_ticks": 0}
        base["injected_action_replay"] = {"status": "NOT_REPLAYABLE", "simulated_and_compared_ticks": 0,
                                          "stop_reason": base["grade_c_reason"]}
        return base
    tick_rows = rows[start_index:start_index + available + 1]
    try:
        start_state = from_canonical(tick_rows[0][1])
    except UnsupportedState as exc:
        reason = f"START_STATE_UNSUPPORTED:{str(exc).split(':')[0]}"
        base["grade_c_reason"] = reason
        base["baseline_no_action"] = {"status": "NOT_RUN_UNSUPPORTED_START", "simulated_and_compared_ticks": 0,
                                      "stop_reason": reason}
        base["injected_action_replay"] = {"status": "NOT_REPLAYABLE", "simulated_and_compared_ticks": 0,
                                          "stop_reason": reason}
        return base
    transition_actions: list[dict[str, Any] | None] = []
    all_proofs = []
    action_grade_at_mismatch = None
    c_reason = None
    event_rows = []
    for offset in range(1, len(tick_rows)):
        before_raw, before_canonical = tick_rows[offset - 1]
        after_raw, after_canonical = tick_rows[offset]
        births, birth_error = _birth_candidates(before_raw, after_raw)
        if birth_error:
            transition_actions.append(None)
            if birth_error:
                c_reason = c_reason or birth_error
            event_rows.append({"sequence": after_raw.get("sequence"), "grade": "C",
                               "reason": birth_error, "birth_count": 0})
            if after_raw.get("sequence") == mismatch_sequence:
                action_grade_at_mismatch = "C"
            continue
        if not births:
            transition_actions.append([])
            continue
        actions, reason, proof = _classify_transition(before_raw, after_raw,
                                                       before_canonical, after_canonical)
        all_proofs.extend(proof)
        if actions and reason is None:
            transition_actions.append(actions)
            event_rows.append({"sequence": after_raw.get("sequence"), "grade": "B",
                               "reason": "VISIBLE_BIRTH_AND_EXACT_NO_ACTION_SOURCE_CONSERVATION",
                               "birth_count": len(actions)})
            for action in actions:
                action["injected_at_sequence"] = after_raw.get("sequence")
                action["injected_at_world_tick"] = after_canonical.tick.value
                action["injection_offset_ticks_from_start"] = offset
            base["actions"].extend(actions)
            if after_raw.get("sequence") == mismatch_sequence:
                action_grade_at_mismatch = "B"
        else:
            transition_actions.append(None)
            c_reason = c_reason or reason or "EXTERNAL_BIRTH_NOT_PROVABLE"
            event_rows.append({"sequence": after_raw.get("sequence"), "grade": "C",
                               "reason": reason or "EXTERNAL_BIRTH_NOT_PROVABLE",
                               "birth_count": len(births)})
            if after_raw.get("sequence") == mismatch_sequence:
                action_grade_at_mismatch = "C"
    base["source_conservation"] = all_proofs
    base["external_birth_events"] = event_rows
    if action_grade_at_mismatch == "B":
        base["action_evidence_grade"] = "B"
    elif action_grade_at_mismatch == "C" or action_grade_at_mismatch is None:
        base["action_evidence_grade"] = "C"
    base["grade_c_reason"] = c_reason if base["action_evidence_grade"] == "C" else None
    # Each predicted branch advances from its own prior prediction. Raw canonical
    # observations are used only for comparison and independent action inference.
    replay_rows = tick_rows[:available + 1]
    transition_actions = transition_actions[:available]
    baseline = _run_branch(start_state, replay_rows, transition_actions, available,
                           inject=False, requested_limit=required_horizon)
    if action_grade_at_mismatch != "B":
        injected = {"status": "NOT_REPLAYABLE", "requested_ticks": required_horizon,
                    "available_observation_ticks": available, "simulated_and_compared_ticks": 0,
                    "actions_injected": 0, "first_divergence": None, "error_growth": [],
                    "stop_reason": c_reason or "NO_GRADE_B_ACTION_AT_AUDITED_MISMATCH",
                    "full_trajectory_match": False, "original_20_tick_secondary_full_match": False}
    else:
        injected = _run_branch(start_state, replay_rows, transition_actions, available,
                               inject=True, requested_limit=required_horizon)
    for branch in (baseline, injected):
        first20 = branch["error_growth"][:minimum_horizon]
        branch["original_20_tick_secondary_full_match"] = (
            len(first20) == minimum_horizon and all(item["matches"] for item in first20))
    base["baseline_no_action"] = baseline
    base["injected_action_replay"] = injected
    base["available_observation_ticks"] = available
    return base


def run_replay(output_path: Path = DEFAULT_OUTPUT, horizon: int = HORIZON_TICKS) -> dict[str, Any]:
    if horizon != HORIZON_TICKS:
        raise ValueError("MINIMUM_HORIZON_MUST_BE_20")
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    trajectory_report = json.loads(TRAJECTORIES_PATH.read_text(encoding="utf-8"))
    cases = audit.get("failures")
    if not isinstance(cases, list) or len(cases) != 13:
        raise ValueError("AUDIT_MUST_HAVE_13_FAILURES")
    path_cases: dict[Path, list[tuple[int, dict[str, Any]]]] = {}
    for i, case in enumerate(cases, 1):
        path = ROOT / "runtime/research/v2" / Path(case["before"]["file"]).name
        path_cases.setdefault(path, []).append((i, case))
    windows: dict[int, list[tuple[dict[str, Any], Any]]] = {}
    snapshot_hashes = {}
    for path, specs in path_cases.items():
        selected, digest = _collect_case_windows(path, specs, horizon)
        windows.update(selected)
        snapshot_hashes[path.relative_to(ROOT).as_posix()] = digest
    audit_expected = audit.get("source_sha256", {})
    trajectory_cohorts = {item.get("cohort"): item for item in trajectory_report.get("cohorts", [])}
    snapshot_integrity = []
    for case in cases:
        rel = case["before"]["file"]
        cohort = case["cohort"]
        actual = snapshot_hashes.get(rel)
        audit_expected_hash = audit_expected.get(rel)
        trajectory_expected_hash = trajectory_cohorts.get(cohort, {}).get("raw_sha256")
        snapshot_integrity.append({"cohort": cohort, "path": rel,
            "matches_audit_source_sha256": actual is not None and actual == audit_expected_hash,
            "matches_trajectory_report_raw_sha256": actual is not None and actual == trajectory_expected_hash,
            "all_required_hashes_match": actual is not None and actual == audit_expected_hash == trajectory_expected_hash})
    snapshots_verified = all(row["all_required_hashes_match"] for row in snapshot_integrity)
    replayed = []
    for i, case in enumerate(cases, 1):
        rows = windows.get(i, [])
        if snapshots_verified:
            replayed.append(replay_case(case, rows, i, horizon))
        else:
            replayed.append({"cohort": case["cohort"], "case_index": i,
                "trajectory_start_sequence": case["trajectory_start_sequence"],
                "mismatch_sequence": case["mismatch_sequence"], "action_evidence_grade": "C",
                "grade_c_reason": "SNAPSHOT_SOURCE_HASH_MISMATCH_FAIL_CLOSED", "formal_credit": 0,
                "actions": [], "baseline_no_action": {"status": "NOT_RUN_SOURCE_HASH_MISMATCH", "simulated_and_compared_ticks": 0},
                "injected_action_replay": {"status": "NOT_REPLAYABLE", "stop_reason": "SNAPSHOT_SOURCE_HASH_MISMATCH_FAIL_CLOSED",
                    "requested_ticks": None, "simulated_and_compared_ticks": 0, "full_trajectory_match": False}})
    grade_counts = collections.Counter(case["action_evidence_grade"] for case in replayed)
    full_matches = sum(case["injected_action_replay"].get("full_trajectory_match") is True for case in replayed)
    divergent = sum(case["injected_action_replay"].get("first_divergence") is not None for case in replayed)
    partial = sum(case["injected_action_replay"].get("status") == "PARTIAL" for case in replayed)
    nonreplayable = sum(case["injected_action_replay"].get("status") == "NOT_REPLAYABLE" for case in replayed)
    core_sources = sorted((ROOT / "src/kiomet_ai/v2").rglob("*.py"))
    sources = [AUDIT_PATH, TRAJECTORIES_PATH,
               ROOT / "tools/v2_sim_differential.py", ROOT / "tools/v2_sim_trajectories.py"] + core_sources + list(path_cases)
    source_hashes = {p.relative_to(ROOT).as_posix(): _sha256(p) for p in sources}
    audit_source_mismatches = []
    for rel, expected in audit_expected.items():
        path = ROOT / Path(rel)
        if path.is_file() and _sha256(path) != expected:
            audit_source_mismatches.append(rel)
    trajectory_manifest = trajectory_report.get("source_manifest", {})
    normalized_trajectory_manifest = {k.replace("\\", "/"): v for k, v in trajectory_manifest.items()}
    trajectory_core_mismatches = []
    for rel, expected in normalized_trajectory_manifest.items():
        path = ROOT / Path(rel)
        if path.is_file() and _sha256(path) != expected:
            trajectory_core_mismatches.append(rel)
    git = _git_state()
    result = {
        "status": "DIAGNOSTIC_NO_FORMAL_CREDIT" if snapshots_verified else "SNAPSHOT_PROVENANCE_MISMATCH_FAIL_CLOSED",
        "source_provenance": {"snapshot_sources_match_audit_and_trajectory_report": snapshots_verified,
            "snapshot_checks": snapshot_integrity,
            "audit_source_manifest_mismatches": audit_source_mismatches,
            "trajectory_core_manifest_mismatches": trajectory_core_mismatches,
            "core_manifest_scope": "all src/kiomet_ai/v2/**/*.py plus relevant differential and trajectory tools"},
        "question": "Do visible force births and exact source-unit conservation explain the audited first divergences when injected as external actions?",
        "window_policy": "Primary window runs through at least 20 ticks after the original first-divergence/action tick (20–40 total ticks). The original first 20 ticks are retained as a separate secondary full-match indicator. No intermediate reset; insufficient observed data is PARTIAL/OBSERVATION_GAP.",
        "total_cases": len(replayed),
        "grade_a": grade_counts["A"], "grade_b": grade_counts["B"], "grade_c": grade_counts["C"],
        "replayable_cases": sum(c["action_evidence_grade"] == "B" for c in replayed),
        "full_trajectory_matches_after_injection": full_matches,
        "first_divergence_still_exists_after_injection": divergent,
        "partial_or_unsupported": partial,
        "nonreplayable_grade_c": nonreplayable,
        "minimum_horizon_ticks": horizon,
        "maximum_required_horizon_ticks": max((c.get("required_primary_horizon_ticks", 0) for c in replayed), default=0),
        "model_assumptions": {
            "action_grade_b_is_inferred_not_pre_action_provenance": True,
            "launch_terminal": None,
            "launch_fuel": "The existing manual-DeployForce simulator path initializes fuel=150; this is a model assumption, not an observed or independently authenticated value. No result relies on it as evidence; terminal=None causes unknown post-arrival behavior to fail closed.",
            "action_timing": "Existing step applies launches after the current tick's deterministic simulation work.",
            "no_post_state_patch": True,
            "unknown_action_or_route": "Grade-C external births stop injected replay at that tick; terminal/route is never inferred from observed after-state.",
        },
        "classification": {
            "GRADE_A": "No pre-action ledger exists in retained snapshots; zero Grade-A actions.",
            "GRADE_B": "New observer id plus progress zero, visible source/destination/owner/full unit vector, and exact aggregate source-inventory conservation versus one deterministic no-action step; raw before-to-after source deltas also reported.",
            "GRADE_C": "Any missing/ambiguous/duplicate observer id, missing NEW_TRACK marker, non-observed visibility for force/source/destination, nonzero progress, incomplete/u8-invalid/inconsistent unit vector, unavailable deterministic source baseline, changing source owner/type/morale, inexact conservation, or unsupported action ordering remains UNKNOWN.",
        },
        "git": git,
        "test_scope": {"name": "13 audited intermediate trajectory mismatch replay", "minimum_ticks": horizon,
                       "primary_endpoint": "max(start+20 ticks, original first-divergence offset+20 ticks)",
                       "selection": "first retained observation per world tick; exact audit trajectory start sequence"},
        "result_counts": {"FULL_MATCH": full_matches, "DIVERGENCE": divergent,
                          "PARTIAL": partial, "GRADE_C_NOT_REPLAYABLE": nonreplayable},
        "formal_credit": 0,
        "pre_candidate_tool_attempts": [
            {"outcome": "INTERRUPTED_BEFORE_RESULT", "reason": "Initial all-snapshot retention exceeded the bounded-memory target; stopped before classifying cases."},
            {"outcome": "ABORTED_BEFORE_RESULT", "reason": "Finite-window draft raised NameError: snapshot_paths was not defined; fixed before candidate run."},
        ],
        "source_sha256": source_hashes,
        "tool_sha256": _sha256(Path(__file__).resolve()),
        "snapshot_first_per_tick_sha256": snapshot_hashes,
        "trajectory_report_status": trajectory_report.get("status"),
        "cases": replayed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--horizon", type=int, default=HORIZON_TICKS)
    args = parser.parse_args()
    result = run_replay(args.output, args.horizon)
    print(json.dumps({key: result[key] for key in (
        "status", "total_cases", "grade_a", "grade_b", "grade_c", "replayable_cases",
        "full_trajectory_matches_after_injection", "first_divergence_still_exists_after_injection",
        "partial_or_unsupported", "nonreplayable_grade_c", "formal_credit")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

