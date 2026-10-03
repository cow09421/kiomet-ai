"""Strict, read-only verifier for one captured official-UI action.

The verifier deliberately returns UNKNOWN whenever the persisted visible record
cannot exclude a competing cause.  UI delivery and CANDIDATE_MATCHED are inputs,
never acceptance evidence by themselves.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CLIENT_SHA256 = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"


def _fact(obj: Any) -> tuple[Any, bool]:
    if isinstance(obj, dict) and "knowledge" in obj:
        return obj.get("value"), obj.get("knowledge") in {"OBSERVED", "DERIVED"} and obj.get("value") is not None
    return None, False


def _v(obj: Any) -> Any:
    value, known = _fact(obj)
    return value if known else None


def _units(obj: Any) -> dict[int, int] | None:
    raw = _v(obj)
    if not isinstance(raw, dict):
        return None
    pairs = raw.get("counts")
    if not isinstance(pairs, list):
        return None
    out: dict[int, int] = {}
    for pair in pairs:
        if (not isinstance(pair, list) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or
                pair[0] not in range(10) or pair[0] in out or pair[1] < 0):
            return None
        out[pair[0]] = pair[1]
    return out if set(out) == set(range(10)) else None


def _vec_equal(a: dict[int, int], b: dict[int, int]) -> bool:
    return len(a) == len(b) == 10 and all(a[k] == b[k] for k in range(10))


def _sum_vec(vectors: list[dict[int, int]]) -> dict[int, int]:
    return {k: sum(v[k] for v in vectors) for k in range(10)}


def _scope(state: dict[str, Any]) -> tuple[Any, ...] | None:
    match, mk = _fact(state.get("match_id"))
    player, pk = _fact(state.get("player_id"))
    life, lk = _fact(state.get("lifecycle"))
    doc = state.get("document_id")
    if not (mk and pk and lk and isinstance(doc, str) and doc and isinstance(match, str) and match and type(player) is int and player > 0 and life == "IN_MATCH"):
        return None
    return doc, match, player, life


def _tower(state: dict[str, Any], ident: Any) -> dict[str, Any] | None:
    rows = state.get("towers")
    if not isinstance(rows, list):
        return None
    matches = [r for r in rows if isinstance(r, dict) and r.get("id") == ident]
    if len(matches) != 1:
        return None
    tower = matches[0]
    visible, known = _fact(tower.get("visibility"))
    return tower if known and visible is True else None


def _forces(state: dict[str, Any]) -> list[dict[str, Any]] | None:
    rows = _v(state.get("forces"))
    if not isinstance(rows, list):
        return None
    if any(not isinstance(r, dict) for r in rows):
        return None
    ids = [_v(r.get("id")) for r in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        return None
    if any(not (_fact(r.get("visibility"))[1] and _v(r.get("visibility")) is True) for r in rows):
        return None
    return rows


def _known_production_none(tower: dict[str, Any], intended: set[int]) -> bool | None:
    """True proves no listed production for intended mobile types; None is unknown."""
    prod = _v(tower.get("production"))
    if not isinstance(prod, list):
        return None
    for entry in prod:
        if not isinstance(entry, list) or len(entry) != 2 or type(entry[0]) is not int:
            return None
        if entry[0] in intended:
            return False
    return True


def verify_case(records: list[dict[str, Any]], *, command_index: int = 1) -> dict[str, Any]:
    """Verify one action from JSONL records; report SUCCESS only on full evidence."""
    def one(kind: str) -> list[dict[str, Any]]:
        return [r for r in records if r.get("kind") == kind and r.get("command_index", 1) == command_index]

    reasons: list[str] = []
    befores, intents, uis, results = one("BEFORE_INTENT"), one("ACTION_INTENT"), one("UI_ACTION_RESULT"), one("COMMAND_RESULT")
    after_rows = one("AFTER_DISTINCT_TICK")
    if len(befores) != 1 or len(intents) != 1 or len(uis) != 1 or len(results) != 1:
        return {"status": "UNKNOWN", "reasons": ["REQUIRED_RECORD_MISSING_OR_DUPLICATED"]}
    before = befores[0].get("state")
    intent, ui, result = intents[0], uis[0], results[0]
    if not isinstance(before, dict):
        return {"status": "UNKNOWN", "reasons": ["BEFORE_INTENT_STATE_MISSING"]}
    intent_id = intent.get("intent_id")
    ordered = [records.index(x) for x in (befores[0], intents[0], uis[0])]
    after_positions = [records.index(x) for x in after_rows]
    result_pos = records.index(results[0])
    if ordered != sorted(ordered) or any(i <= ordered[-1] for i in after_positions) or result_pos <= max(after_positions, default=ordered[-1]):
        reasons.append("DURABLE_RECORD_ORDER_INVALID")
    if not intent_id or ui.get("intent_id") != intent_id:
        reasons.append("UI_RESULT_INTENT_MISMATCH")
    if ui.get("ui_delivery_status") != "SUCCESS":
        reasons.append("UI_DELIVERY_NOT_SUCCESS")
    down, up = ui.get("mouse_down_host_monotonic_ms"), ui.get("mouse_up_host_monotonic_ms")
    if type(down) is not int or type(up) is not int or up < down:
        reasons.append("UI_GESTURE_TIMESTAMPS_UNKNOWN_OR_INVALID")
    if (intent.get("input_method") != "official Playwright page mouse" or
            intent.get("intended_action") != "ALL_CURRENT_DEPLOYABLE" or
            intent.get("selected_tower_none_confirmed") is not True):
        reasons.append("ACTION_INTENT_NOT_PINNED_OFFICIAL_GESTURE")
    assoc = result.get("action_ledger_association")
    if isinstance(assoc, dict) and assoc.get("status") == "CANDIDATE_MATCHED":
        # Kept as diagnostic only. All checks below are independent.
        pass

    source_id = (intent.get("source") or {}).get("tower_id")
    dest_id = (intent.get("destination") or {}).get("tower_id")
    player = intent.get("player_id")
    raw_vector = intent.get("intended_unit_vector")
    incoming: dict[int, int] = {k: 0 for k in range(10)}
    seen_units: set[int] = set()
    if isinstance(raw_vector, list):
        for p in raw_vector:
            if not isinstance(p, list) or len(p) != 2 or type(p[0]) is not int or type(p[1]) is not int or p[0] not in range(6) or p[1] <= 0 or p[0] in seen_units:
                incoming = {}
                break
            incoming[p[0]] = p[1]
            seen_units.add(p[0])
    if not incoming or not seen_units:
        reasons.append("INTENDED_VECTOR_UNKNOWN_OR_INVALID")
    intended_types = {k for k, value in incoming.items() if value > 0}

    states = [before]
    for row in after_rows:
        obs = row.get("observation")
        st = obs.get("state") if isinstance(obs, dict) else None
        if not isinstance(st, dict):
            reasons.append("AFTER_TICK_STATE_MISSING_OR_MALFORMED")
            continue
        states.append(st)
    base_scope = _scope(before)
    base_tick = _v(before.get("tick"))
    if base_scope is None or type(base_tick) is not int:
        reasons.append("BEFORE_EPOCH_OR_TICK_UNKNOWN")
    ticks = [_v(s.get("tick")) for s in states]
    client_sha = before.get("client_sha256")
    if client_sha != CLIENT_SHA256:
        reasons.append("CLIENT_BUILD_NOT_FROZEN_PIN")
    if len(states) < 3:
        reasons.append("FIXED_TWO_TICK_WINDOW_INCOMPLETE")
    for i, state in enumerate(states):
        if _scope(state) != base_scope or type(ticks[i]) is not int:
            reasons.append("EPOCH_OR_TICK_UNKNOWN_OR_CHANGED")
            break
        if i and ticks[i] != ((ticks[i - 1] + 1) & 0xFFFF):
            reasons.append("NONCONSECUTIVE_WORLD_TICKS")
            break
        if _forces(state) is None:
            reasons.append("FORCE_CENSUS_INCOMPLETE_OR_AMBIGUOUS")
            break
        if state.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
            reasons.append("VISIBLE_CENSUS_NOT_COMPLETE")
            break
        if _v(state.get("source_mode")) != "NETWORK":
            reasons.append("WORLD_SOURCE_MODE_NOT_NETWORK")
            break
        if not before.get("client_sha256") or state.get("client_sha256") != before.get("client_sha256"):
            reasons.append("CLIENT_BUILD_IDENTITY_CHANGED_OR_UNKNOWN")
            break
        if state.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
            reasons.append("VISIBLE_CENSUS_NOT_COMPLETE")
            break
        if _v(state.get("source_mode")) != "NETWORK":
            reasons.append("WORLD_SOURCE_MODE_NOT_NETWORK")
            break
        if not client_sha or state.get("client_sha256") != client_sha:
            reasons.append("CLIENT_BUILD_IDENTITY_CHANGED_OR_UNKNOWN")
            break

    if base_scope is not None and (
            intent.get("document_id") != base_scope[0] or
            (intent.get("match_epoch") or {}).get("document_id") != base_scope[0] or
            (intent.get("match_epoch") or {}).get("match_id") != base_scope[1] or
            intent.get("player_id") != base_scope[2] or
            (intent.get("match_epoch") or {}).get("player_id") != base_scope[2] or
            (intent.get("match_epoch") or {}).get("lifecycle") != base_scope[3] or
            intent.get("world_sequence") != base_tick):
        reasons.append("INTENT_EPOCH_OR_BEFORE_TICK_MISMATCH")
    if intent.get("client_sha256") != before.get("client_sha256"):
        reasons.append("INTENT_CLIENT_BUILD_MISMATCH")
    before_record = befores[0]
    route = before_record.get("before_only_route_certificate")
    if not isinstance(route, dict) or route.get("qualified") is not True or route.get("scope") != "BEFORE_SNAPSHOT_ONLY":
        reasons.append("BEFORE_ROUTE_CERTIFICATE_NOT_QUALIFIED")
    if (before_record.get("source") != source_id or before_record.get("destination") != dest_id or
            (before_record.get("BEFORE") or {}).get("source") != source_id or
            (before_record.get("BEFORE") or {}).get("destination") != dest_id or
            before_record.get("tick") != base_tick):
        reasons.append("ACTION_ENDPOINTS_DO_NOT_MATCH_BEFORE_INTENT")

    before_source, before_dest = _tower(before, source_id), _tower(before, dest_id)
    if before_source is None or before_dest is None:
        reasons.append("BEFORE_ENDPOINT_MISSING_OR_DUPLICATED")
    prior_ids = intent.get("prior_force_ids")
    before_forces = _forces(before)
    if not isinstance(prior_ids, list) or before_forces is None or set(prior_ids) != {_v(f.get("id")) for f in before_forces}:
        reasons.append("PRIOR_FORCE_SET_NOT_EXACT")
    if before_source is not None:
        pre_deployable = _units(before_source.get("deployable"))
        if _v(before_source.get("owner")) != player or pre_deployable is None or not _vec_equal(pre_deployable, incoming):
            reasons.append("BEFORE_SOURCE_NOT_OWN_OR_ALL_CURRENT_DEPLOYABLE_MISMATCH")
        if _v(before_source.get("tower_type")) != (intent.get("source") or {}).get("tower_type"):
            reasons.append("SOURCE_TYPE_DIFFERS_FROM_ACTION_INTENT")
    if before_dest is not None and _v(before_dest.get("tower_type")) != (intent.get("destination") or {}).get("tower_type"):
        reasons.append("DESTINATION_TYPE_DIFFERS_FROM_ACTION_INTENT")
    if intent.get("pre_action_source_supply_line_present") is not False:
        reasons.append("SOURCE_SUPPLY_LINE_NOT_KNOWN_ABSENT")
    if intent.get("preexisting_visible_inbound_force_to_source") is not False:
        reasons.append("PREEXISTING_SOURCE_INBOUND_NOT_KNOWN_ABSENT")
    if not result.get("supply_line_guard_passed"):
        reasons.append("ROUTE_SUPPLY_LINE_GUARD_NOT_CONFIRMED")

    # Exact, unique NEW_TRACK route; reject any unknown endpoint alias as a competitor.
    candidate_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    ambiguous_alias = False
    for offset, state in enumerate(states[1:], 1):
        force_rows = _forces(state)
        if force_rows is None:
            continue
        for force in force_rows:
            ident, owner = _v(force.get("id")), _v(force.get("owner"))
            src, dst = _v(force.get("source")), _v(force.get("destination"))
            if src is None or dst is None:
                if owner in (None, player):
                    ambiguous_alias = True
                continue
            if src == source_id and dst == dest_id and owner == player and ident not in (prior_ids or []):
                candidate_by_id.setdefault(ident, (offset, force))
    candidates = list(candidate_by_id.values())
    if ambiguous_alias:
        reasons.append("UNKNOWN_ENDPOINT_OWN_FORCE_ALIAS")
    if len(candidates) != 1:
        reasons.append("NEW_OWN_FORCE_NOT_UNIQUE")
    if len(candidates) == 1 and candidates[0][0] not in (1, 2):
        reasons.append("BIRTH_OUTSIDE_FIXED_TWO_TICK_WINDOW")
    birth_state = states[candidates[0][0]] if len(candidates) == 1 else None
    birth = candidates[0][1] if len(candidates) == 1 else None
    if birth is not None:
        if _v(birth.get("confidence")) != "NEW_TRACK" or _v(birth.get("progress")) != 0:
            reasons.append("FORCE_BIRTH_NOT_CONFIRMED_NEW_TRACK_AT_ZERO")
        birth_vector = _units(birth.get("units"))
        if birth_vector is None or not _vec_equal(birth_vector, incoming):
            reasons.append("BIRTH_VECTOR_DIFFERS_OR_UNKNOWN")
        # Must remain same known force through the fixed two-tick window, then disappear on arrival.
        for later in states[candidates[0][0] + 1:]:
            rows = _forces(later)
            if rows is not None:
                matches = [f for f in rows if _v(f.get("id")) == _v(birth.get("id"))]
                if len(matches) > 1:
                    reasons.append("FORCE_ID_MULTIPLICITY")
                if matches:
                    c = matches[0]
                    if (_v(c.get("confidence")) != "UNIQUE_CONTINUATION" or
                            _v(c.get("owner")) != _v(birth.get("owner")) or
                            _v(c.get("source")) != _v(birth.get("source")) or
                            _v(c.get("destination")) != _v(birth.get("destination")) or
                            not _vec_equal(_units(c.get("units")) or {}, _units(birth.get("units")) or {})):
                        reasons.append("FORCE_CONTINUATION_NOT_UNIQUE_OR_STABLE")

    # Source conservation at the birth frame, plus no competing incoming or production.
    if birth_state is not None and before_source is not None:
        source_at_birth = _tower(birth_state, source_id)
        pre_vec, post_vec = _units(before_source.get("units")), _units(source_at_birth.get("units")) if source_at_birth else None
        if pre_vec is None or post_vec is None or birth is None:
            reasons.append("SOURCE_INVENTORY_UNKNOWN")
        else:
            delta = {k: pre_vec[k] - post_vec[k] for k in range(10)}
            if any(v < 0 for v in delta.values()) or not _vec_equal(delta, {**{k: 0 for k in range(10)}, **incoming}):
                reasons.append("SOURCE_DEPLETION_DOES_NOT_EQUAL_BIRTH_VECTOR")
        for state in states[:candidates[0][0] + 1]:
            row = _tower(state, source_id)
            if row is None or _v(row.get("supply_line_present")) is not False:
                reasons.append("SOURCE_SUPPLY_LINE_NOT_ABSENT_THROUGH_BIRTH")
                break
        if before_forces is not None:
            for state in states[:candidates[0][0] + 1]:
                rows = _forces(state)
                if rows is None or any(_v(f.get("destination")) in (source_id, None) for f in rows):
                    reasons.append("SOURCE_INBOUND_COMPETITOR_PRESENT_OR_UNKNOWN")
                    break
        source_contexts = []
        source_capacities = []
        for state in states[:candidates[0][0] + 1]:
            tower = _tower(state, source_id)
            if tower is None or _known_production_none(tower, intended_types) is not True:
                reasons.append("SOURCE_PRODUCTION_COULD_EXPLAIN_BIRTH")
                break
            if any(_v(tower.get(k)) is None for k in ("tower_type", "owner", "delay_ticks", "effects")):
                reasons.append("SOURCE_GENERATION_CONTEXT_UNKNOWN")
                break
            source_contexts.append(tower)
            capacity = _units(tower.get("capacity"))
            if capacity is None:
                reasons.append("SOURCE_CAPACITY_UNKNOWN")
                break
            source_capacities.append(capacity)
        if len(source_capacities) > 1 and any(not _vec_equal(source_capacities[0], row) for row in source_capacities[1:]):
            reasons.append("SOURCE_CAPACITY_CHANGED_DURING_BIRTH")
        if len(source_contexts) > 1 and any(
                _v(source_contexts[0].get(k)) != _v(row.get(k))
                for row in source_contexts[1:] for k in ("tower_type", "owner", "delay_ticks", "effects")):
            reasons.append("SOURCE_GENERATION_CONTEXT_CHANGED")
    else:
        reasons.append("SOURCE_BIRTH_SNAPSHOT_UNAVAILABLE")

    # Destination cue is necessary but never sufficient: independently require exact inventory delta,
    # no intended-type production, no competing plausible inbound, and force disappearance.
    cue = result.get("arrival_cue")
    cue_tick = cue.get("tick") if isinstance(cue, dict) else None
    arrival_index = next((i for i, s in enumerate(states[1:], 1) if _v(s.get("tick")) == cue_tick), None)
    if arrival_index is None or not isinstance(cue, dict):
        reasons.append("DESTINATION_ARRIVAL_CUE_NOT_BOUND_TO_SNAPSHOT")
    else:
        if len(states) < 3 or (len(candidates) == 1 and arrival_index <= candidates[0][0]):
            reasons.append("ARRIVAL_NOT_AFTER_BIRTH_IN_COMPLETE_WINDOW")
        if len(candidates) == 1:
            birth_idx = candidates[0][0]
            for index in range(birth_idx + 1, arrival_index):
                rows_between = _forces(states[index])
                selected = _v(birth.get("id")) if birth else None
                same = [f for f in (rows_between or []) if _v(f.get("id")) == selected]
                if (rows_between is None or len(same) != 1 or
                        _v(same[0].get("confidence")) != "UNIQUE_CONTINUATION" or
                        _v(same[0].get("owner")) != player or
                        _v(same[0].get("source")) != source_id or
                        _v(same[0].get("destination")) != dest_id or
                        not _vec_equal(_units(same[0].get("units")) or {}, incoming)):
                    reasons.append("FORCE_CONTINUATION_GAP_OR_AMBIGUITY_BEFORE_ARRIVAL")
                    break
        arrival = states[arrival_index]
        if cue.get("basis") != "visible endpoint change and matching force absent":
            reasons.append("ARRIVAL_CUE_BASIS_NOT_RECOGNIZED")
        dest_before = _tower(before, dest_id)
        dest_after = _tower(arrival, dest_id)
        old_inv = _units(dest_before.get("units")) if dest_before else None
        new_inv = _units(dest_after.get("units")) if dest_after else None
        if old_inv is None or new_inv is None:
            reasons.append("DESTINATION_INVENTORY_UNKNOWN")
        else:
            observed_delta = {k: new_inv[k] - old_inv[k] for k in range(10)}
            if any(v < 0 for v in observed_delta.values()) or not _vec_equal(observed_delta, {**{k: 0 for k in range(10)}, **incoming}):
                reasons.append("DESTINATION_DELTA_NOT_EXACTLY_INTENDED_VECTOR")
        if dest_after is None or _v(dest_after.get("owner")) != player:
            reasons.append("DESTINATION_OWNER_NOT_CONFIRMED")
        if dest_before is not None and dest_after is not None:
            dest_contexts = []
            for state in states[:arrival_index + 1]:
                tower = _tower(state, dest_id)
                if tower is None or _known_production_none(tower, intended_types) is not True:
                    reasons.append("DESTINATION_PRODUCTION_COULD_EXPLAIN_INVENTORY_CHANGE")
                    break
                if any(_v(tower.get(k)) is None for k in ("tower_type", "owner", "delay_ticks", "effects")):
                    reasons.append("DESTINATION_GENERATION_CONTEXT_UNKNOWN")
                    break
                dest_contexts.append(tower)
            if len(dest_contexts) > 1 and any(
                    _v(dest_contexts[0].get(k)) != _v(row.get(k))
                    for row in dest_contexts[1:] for k in ("tower_type", "delay_ticks", "effects")):
                reasons.append("DESTINATION_GENERATION_CONTEXT_CHANGED")
            for state in states[:arrival_index + 1]:
                tower = _tower(state, dest_id)
                if tower is None or _v(tower.get("supply_line_present")) is not False:
                    reasons.append("DESTINATION_SUPPLY_LINE_NOT_KNOWN_ABSENT")
                    break
        rows = _forces(arrival)
        if rows is None or (birth is not None and any(_v(f.get("id")) == _v(birth.get("id")) for f in rows)):
            reasons.append("MATCHED_FORCE_NOT_KNOWN_DISAPPEARED_AT_ARRIVAL")
        if rows is not None:
            for state in states[:arrival_index + 1]:
                for force in (_forces(state) or []):
                    owner, src, dst, vec = _v(force.get("owner")), _v(force.get("source")), _v(force.get("destination")), _units(force.get("units"))
                    selected_id = _v(birth.get("id")) if birth is not None else None
                    if _v(force.get("id")) == selected_id:
                        continue
                    if dst == dest_id or dst is None:
                        reasons.append("COMPETING_OR_UNKNOWN_DESTINATION_INBOUND")
                        break
                if "COMPETING_OR_UNKNOWN_DESTINATION_INBOUND" in reasons:
                    break

    # Deduplicate diagnostics while preserving order.
    reasons = list(dict.fromkeys(reasons))
    return {"status": "SUCCESS" if not reasons else "UNKNOWN", "reasons": reasons,
            "intent_id": intent_id, "source_id": source_id, "destination_id": dest_id,
            "ticks": ticks, "candidate_force_id": _v(birth.get("id")) if birth else None,
            "candidate_birth_offset": candidates[0][0] if len(candidates) == 1 else None,
            "arrival_cue_tick": cue_tick,
            "association_status_diagnostic_only": assoc.get("status") if isinstance(assoc, dict) else None}


def verify_paths(report_path: Path, event_path: Path | None = None) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if event_path is not None:
        path = event_path
    else:
        event_rel = Path(report.get("event_file", ""))
        repo_root = Path(__file__).resolve().parents[1]
        choices = [event_rel] if event_rel.is_absolute() else [repo_root / event_rel, report_path.parent / event_rel]
        path = next((candidate for candidate in choices if candidate.is_file()), choices[0])
    if not path.is_file():
        return {"status": "UNKNOWN", "reasons": ["EVENT_FILE_MISSING"]}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return verify_case(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="controlled-transition report JSON")
    parser.add_argument("--events", type=Path, help="optional JSONL event file override")
    args = parser.parse_args(argv)
    result = verify_paths(args.report, args.events)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
