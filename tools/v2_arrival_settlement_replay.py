"""Unfiltered, split-aware replay of all pinned due-arrival opportunities.

The fixture preserves candidate rows even when the current-leg boundary is
excluded. Holdout inputs are materialized but never scored until the caller
explicitly requests that split after freezing premises.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tools.v2_factorized_coverage import _tower, _force, _infer_pinned_acceleration, val, is_known, units
from kiomet_ai.v2.sim import UnsupportedState, ordinary_arrival_boundary
from kiomet_ai.v2.sim.step import phase
from kiomet_ai.v2.observe.forces import motion
from kiomet_ai.v2.state import Units

DENOMINATOR = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
FREEZE = ROOT / "docs/V2_M2A_SETTLEMENT_RULE_FREEZE.json"
EDGE_AUDIT = ROOT / "tests/fixtures/v2/arrival-factor-edge-audit.jsonl.gz"
EDGE_AUDIT_DECOMPRESSED_SHA = ""
COHORTS = {
    "03d032d57e5b": "development", "7d56a775bc4c": "holdout",
    "85391858b5d8": "holdout", "b1f7f9416e92": "holdout",
    "daf86d0544b7": "development", "fe678ebb30ce": "development",
}
SPLIT_ORDER = ("development", "holdout")
VECTORS = ("owner", "source", "destination", "units", "progress", "accelerated", "fuel", "terminal")
TOWER_FIELDS = ("id", "visibility", "owner", "relation", "tower_type", "units", "capacity", "production",
                "neighbors", "position", "delay_ticks", "effects", "supply_line_present")
FORCE_FIELDS = ("id", "owner", "relation", "source", "destination", "units", "progress",
                "accelerated", "eta_ms", "fuel", "terminal", "visibility")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha_gzip_payload(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def project_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: row.get(name) for name in fields if name in row}


def fact_values(row: dict[str, Any], key: str) -> Any:
    return val(row.get(key))


def raw_scope(raw: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (raw.get("document_id"), fact_values(raw, "match_id"),
            fact_values(raw, "player_id"), fact_values(raw, "document_time_origin_ms"))


def raw_tick(raw: dict[str, Any]) -> int | None:
    tick = fact_values(raw, "tick")
    return tick if type(tick) is int else None


def rows(raw: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    value = raw.get(collection)
    if collection == "forces" and isinstance(value, dict):
        value = val(value)
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def visible(row: dict[str, Any]) -> bool:
    return fact_values(row, "visibility") is True


def full_context(raw: dict[str, Any]) -> dict[str, Any]:
    towers = [project_row(r, TOWER_FIELDS) for r in rows(raw, "towers") if visible(r)]
    forces = [project_row(r, FORCE_FIELDS) for r in rows(raw, "forces") if visible(r)]
    return {"provenance": {"sequence": raw.get("sequence"), "tick": raw_tick(raw),
                           "scope": list(raw_scope(raw)), "coverage": raw.get("coverage"),
                           "source_mode": raw.get("source_mode")},
            "towers": towers, "forces": forces}


def visible_index(raw: dict[str, Any], key: str) -> dict[int, dict[str, Any]]:
    return {r["id"]: r for r in rows(raw, key)
            if visible(r) and type(r.get("id")) is int}


def force_signature(row: dict[str, Any]) -> tuple[Any, ...] | None:
    owner, src, dst, vector = (fact_values(row, "owner"), fact_values(row, "source"),
                               fact_values(row, "destination"), units(row.get("units")))
    if type(owner) is not int or type(src) is not int or type(dst) is not int or vector is None:
        return None
    return owner, src, dst, vector


def normalized_signature(value: Any) -> tuple[Any, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not isinstance(value[3], (list, tuple)):
        return None
    return value[0], value[1], value[2], tuple(value[3])


def consecutive_scope(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    lp, rp = left.get("provenance", {}), right.get("provenance", {})
    lt, rt = lp.get("tick"), rp.get("tick")
    return (lp.get("scope") == rp.get("scope") and type(lt) is int and type(rt) is int
            and (rt - lt) % 65536 == 1)


def scope_known_before(snapshot: dict[str, Any]) -> bool:
    scope = snapshot.get("provenance", {}).get("scope")
    return (isinstance(scope, list) and len(scope) == 4 and isinstance(scope[0], str)
            and isinstance(scope[1], str) and type(scope[2]) is int
            and isinstance(scope[3], (int, float)))


def force_status(case: dict[str, Any], tick_name: str) -> str:
    snapshot = case["snapshots"].get(tick_name)
    if snapshot is None:
        return "UNKNOWN"
    sig = normalized_signature(case["incoming_signature"])
    if sig is None:
        return "UNKNOWN"
    fs = snapshot["forces"]
    if snapshot["provenance"].get("coverage") != "PLAYER_VISIBLE_COMPLETE":
        return "UNKNOWN"
    sigs = [force_signature(row) for row in fs]
    exact = [x for x in sigs if x == sig]
    if len(exact) == 1:
        return "CONTINUES"
    if len(exact) > 1:
        return "AMBIGUOUS"
    transformed = [x for x in sigs if x is not None and x[0] == sig[0]
                   and x[1] == case["target_id"] and type(x[2]) is int and x[3] == sig[3]]
    if len(transformed) == 1:
        return "TRANSFORMED"
    if len(transformed) > 1:
        return "AMBIGUOUS"
    for row, row_sig in zip(fs, sigs):
        if row_sig is None and (known_fact(row, "owner") in (None, sig[0])
                                or units(row.get("units")) in (None, sig[3])):
            return "AMBIGUOUS"
        if (case.get("attacker_id_supplemental") is not None
                and fact_values(row, "id") == case["attacker_id_supplemental"]):
            return "AMBIGUOUS"
    # The signature absence is based on the complete visible collection. The
    # observer ID is deliberately ignored as evidence of identity continuity.
    return "DISAPPEARED"


def known_fact(row: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(row, dict) or not is_known(row.get(key)):
        return None
    return val(row.get(key))


def local_context(case: dict[str, Any]) -> dict[str, Any]:
    before = case["snapshots"]["before"]
    target_id, attacker_sig = case["target_id"], normalized_signature(case["incoming_signature"])
    target = visible_index(before, "towers").get(target_id)
    all_forces = [r for r in rows(before, "forces") if visible(r)]
    unrelated = 0
    unresolved = 0
    target_inbound = 0
    incoming_signature_count = 0
    for r in all_forces:
        if attacker_sig is not None and force_signature(r) == attacker_sig:
            incoming_signature_count += 1
            continue
        dst = known_fact(r, "destination")
        if type(dst) is int and dst != target_id:
            unrelated += 1
        elif type(dst) is int and dst == target_id:
            target_inbound += 1
        else:
            unresolved += 1
    source = visible_index(before, "towers").get(attacker_sig[1]) if attacker_sig is not None else None
    out = {"visible_inbound_count_known": target_inbound + 1,
           "incoming_signature_unique_before": incoming_signature_count == 1,
           "other_visible_forces_known_other_destination": unrelated,
           "other_visible_forces_destination_unknown_may_arrive_here": unresolved,
           "local_inbound_complete": unresolved == 0,
           "target_owner_before": known_fact(target, "owner"),
           "target_inventory_before": units(target.get("units")) if target else None,
           "target_capacity": units(target.get("capacity")) if target else None,
           "target_production": known_fact(target, "production"),
           "target_delay": known_fact(target, "delay_ticks"),
           "target_supply_line_present": known_fact(target, "supply_line_present"),
           "target_effects": known_fact(target, "effects"),
           "source_delay": known_fact(source, "delay_ticks"),
           "incoming_terminal": known_fact(case.get("incoming_raw_fact"), "terminal"),
           "incoming_fuel": known_fact(case.get("incoming_raw_fact"), "fuel"),
           "incoming_accelerated": known_fact(case.get("incoming_raw_fact"), "accelerated"),
           "special_destination": None,
           "capacity_status": "UNKNOWN",
           "production_due": None,
           "relay_fact": "UNKNOWN"}
    owner = attacker_sig[0] if attacker_sig is not None else None
    incoming = attacker_sig[3] if attacker_sig is not None else None
    defenders = out["target_inventory_before"]
    cap = out["target_capacity"]
    if defenders is not None and incoming is not None:
        out["special_destination"] = any(defenders[6:]) or any(incoming[6:])
    if defenders is not None and cap is not None and incoming is not None:
        totals = tuple(defenders[i] + incoming[i] for i in range(10))
        if all(totals[i] <= cap[i] for i in range(10)):
            out["capacity_status"] = "WITHIN_NORMAL_CAPACITY"
        elif (all(totals[i] <= cap[i] for i in range(10) if i not in (4, 5))
              and totals[4] <= cap[4] + 5 and totals[5] <= cap[5] + 10):
            out["capacity_status"] = "WITHIN_PINNED_GROUND_OVERFLOW"
        else:
            out["capacity_status"] = "CLIPPING_OR_CAPACITY_AMBIGUITY"
    if target is not None and out["target_supply_line_present"] is not None:
        out["relay_fact"] = "LOCAL_RELAY_INTERACTION" if out["target_supply_line_present"] else "NO_VISIBLE_LOCAL_RELAY"
    if target is not None and out["target_production"] is not None and out["target_owner_before"] == 0:
        out["production_due"] = False
    elif (target is not None and out["target_production"] is not None
          and out["target_owner_before"] is not None and defenders is not None and cap is not None):
        arrival_tick = case["audit_ticks"][1]
        out["production_due"] = any(period > 0 and phase(arrival_tick, target_id) % period == 0
                                     and defenders is not None and defenders[unit] < cap[unit]
                                     for unit, period in out["target_production"])
    out["before_only_hard_premises"] = {
        "known_target_owner_inventory": out["target_owner_before"] is not None and defenders is not None,
        "known_incoming_vector": incoming is not None,
        "no_unresolved_relevant_inbound": unresolved == 0 and target_inbound == 0,
        "no_active_delay": out["target_delay"] == 0,
        "no_special_destination": out["special_destination"] is False,
        "no_production_due": out["production_due"] is False,
        "no_confirmed_local_relay": out["target_supply_line_present"] is not True,
        "no_capacity_context": out["capacity_status"] in ("WITHIN_NORMAL_CAPACITY", "WITHIN_PINNED_GROUND_OVERFLOW"),
        "incoming_signature_unique_before": out["incoming_signature_unique_before"],
        "incoming_terminal_known_true": out["incoming_terminal"] is True,
        "incoming_fuel_known": out["incoming_fuel"] is not None,
    }
    ordinary_vector = incoming is not None and not any(incoming[6:])
    current_boundary = case["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"
    common = (current_boundary and scope_known_before(before)
              and incoming is not None and out["incoming_signature_unique_before"] and ordinary_vector
              and out["local_inbound_complete"] and target_inbound == 0
              and out["target_delay"] == 0 and out["source_delay"] == 0
              and out["special_destination"] is False and out["target_capacity"] is not None
              and out["capacity_status"] in ("WITHIN_NORMAL_CAPACITY", "WITHIN_PINNED_GROUND_OVERFLOW"))
    known_expired_fuel = (type(out["incoming_fuel"]) is int and out["incoming_fuel"] <= 0)
    out["eligibility_without_terminal_proxy"] = {
        "capture": bool(common and out["target_owner_before"] == 0 and defenders is not None
                        and not any(defenders) and out["target_supply_line_present"] is not True
                        and not known_expired_fuel),
        "reinforcement": bool(common and out["target_owner_before"] == owner and owner not in (None, 0)
                               and out["target_supply_line_present"] is False
                               and out["production_due"] is False),
    }
    out["final_frozen_eligibility"] = {
        "capture": bool(out["eligibility_without_terminal_proxy"]["capture"]
                        and out["incoming_terminal"] is True),
        "reinforcement": bool(out["eligibility_without_terminal_proxy"]["reinforcement"]
                               and out["incoming_terminal"] is True),
    }
    towers = rows(before, "towers")
    forces = rows(before, "forces")
    strict_state_inputs = (bool(towers) and bool(forces)
        and all(_tower(row)[0] is not None for row in towers)
        and all(_force(row)[0] is not None and type(known_fact(row, "accelerated")) is bool
                for row in forces))
    out["strict_world_inputs_complete"] = strict_state_inputs
    out["strict_world_eligible"] = {
        "capture": bool(out["final_frozen_eligibility"]["capture"] and strict_state_inputs),
        "reinforcement": bool(out["final_frozen_eligibility"]["reinforcement"] and strict_state_inputs),
    }
    return out


def score_case(case: dict[str, Any]) -> None:
    before = case["snapshots"]["before"]
    after = case["snapshots"].get("arrival")
    boundary = case["boundary"]
    normalized = normalized_signature(case["incoming_signature"])
    incoming = normalized[3] if normalized is not None else None
    local = local_context(case)
    case["scope_consecutive_before_to_arrival"] = consecutive_scope(before, after)
    owner = normalized[0] if normalized is not None else None
    before_owner, before_units = local["target_owner_before"], local["target_inventory_before"]
    if before_owner == 0 and before_units is not None and not any(before_units) and owner not in (None, 0) and incoming is not None:
        branch = "EMPTY_NEUTRAL_CAPTURE"
        predicted_owner, predicted_units = owner, incoming
    elif before_owner == owner and owner not in (None, 0) and before_units is not None and incoming is not None:
        branch = "SAME_OWNER_REINFORCEMENT"
        predicted_owner = before_owner
        predicted_units = tuple(before_units[i] + incoming[i] for i in range(10))
    else:
        branch = "NO_NAIVE_SETTLEMENT_BRANCH"
        predicted_owner = predicted_units = None
    case["branch_candidate"] = branch
    case["predicted_owner_after"] = predicted_owner
    case["predicted_inventory_after"] = predicted_units
    case["local_context"] = local
    case["before_tick"] = case["snapshots"]["before"]["provenance"].get("tick")
    case["arrival_tick"] = case["snapshots"].get("arrival", {}).get("provenance", {}).get("tick")
    case["following_tick"] = (case["snapshots"].get("following", {}).get("provenance", {}).get("tick"))
    case["incoming_owner"] = owner
    case["incoming_vector"] = incoming
    case["target_owner_before"] = before_owner
    case["target_inventory_before"] = before_units
    case["visible_inbound_count"] = local["visible_inbound_count_known"]
    case["production_due"] = local["production_due"]
    case["visible_supply_relay_fact"] = local["relay_fact"]
    case["delay_state"] = local["target_delay"]
    case["special_destination"] = local["special_destination"]
    case["combat_applicability"] = "COMBAT_REQUIRED" if case["boundary"].get("branch") == "COMBAT_REQUIRED" else "NO_VISIBLE_HOSTILE_COMBAT_REQUIRED"
    case["capacity_status"] = local["capacity_status"]
    case["eligibility_without_terminal_proxy"] = local["eligibility_without_terminal_proxy"]
    case["final_frozen_eligibility"] = local["final_frozen_eligibility"]
    observed_target = visible_index(after, "towers").get(case["target_id"]) if after else None
    case["observed_owner_after"] = known_fact(observed_target, "owner")
    case["observed_inventory_after"] = units(observed_target.get("units")) if observed_target else None
    following = case["snapshots"].get("following")
    following_target = visible_index(following, "towers").get(case["target_id"]) if following else None
    case["observed_owner_following"] = known_fact(following_target, "owner")
    case["observed_inventory_following"] = units(following_target.get("units")) if following_target else None
    case["first_mismatch_field"] = None
    if (case["boundary"].get("status") != "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"
            or not case["scope_consecutive_before_to_arrival"]
            or predicted_owner is None or case["observed_owner_after"] is None
            or case["observed_inventory_after"] is None):
        case["classification"] = "UNSCORABLE"
    else:
        if predicted_owner != case["observed_owner_after"]:
            case["first_mismatch_field"] = "owner_after"
        elif predicted_units != case["observed_inventory_after"]:
            case["first_mismatch_field"] = "inventory_after"
        case["classification"] = "MISMATCH" if case["first_mismatch_field"] else "MATCH"
    case["post_arrival_force_status"] = {
        "t_plus_1": force_status(case, "arrival"),
        "t_plus_2": force_status(case, "following"),
    }
    case["observed_capacity_after"] = units(observed_target.get("capacity")) if observed_target else None
    case["after_capacity_context"] = ("AFTER_VECTOR_OVER_VISIBLE_CAPACITY" if
        observed_target and case["observed_inventory_after"] is not None
        and case["observed_capacity_after"] is not None and any(
            case["observed_inventory_after"][i] > case["observed_capacity_after"][i] for i in range(10))
        else "NO_VISIBLE_AFTER_OVERFLOW_OR_UNKNOWN")
    case["current_deposit_identifiability"] = (
        "UNKNOWN_CONTINUATION_OR_SAME_TICK_RELAUNCH" if
        case["post_arrival_force_status"]["t_plus_1"] in ("TRANSFORMED", "AMBIGUOUS")
        else "NOT_ESTABLISHED_BY_THIS_REPLAY")


def collect_candidates(split: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    with gzip.open(EDGE_AUDIT, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("split") != split or row.get("cohort") not in COHORTS:
                continue
            for ordinal, item in enumerate(row.get("factor_observations", {}).get("arrival", [])):
                boundary = item.get("current_leg_boundary")
                if boundary is None:
                    reason = item.get("boundary_exclusion")
                    # Older audit stores the exception as the first blocker.
                    blockers = row.get("all_blockers", {}).get("arrival", {})
                    force_index = next((e.get("force_index") for e in blockers.get("evidence", [])
                                        if isinstance(e, dict) and type(e.get("force_index")) is int), None)
                    force_index = item.get("force_index", force_index)
                    boundary = {"status": "EXCLUDED", "branch": "EXCLUDED", "exclusion": reason,
                                "force_index": force_index}
                else:
                    boundary = dict(boundary)
                    boundary["force_index"] = item.get("force_index")
                if type(boundary.get("force_index")) is not int:
                    # Movement observations carry alignment IDs but force rows are indexed only in
                    # the frozen source audit; recover by endpoint + signature when unique.
                    boundary["force_index"] = None
                lines = row["lines"]
                seqs = row["sequence"]
                ticks = row["ticks"]
                case_id = f"{row['cohort']}:{row['edge_index']}:{ordinal}"
                candidates.append({"case_id": case_id, "cohort": row["cohort"], "split": split,
                    "edge_index": row["edge_index"], "ordinal": ordinal, "raw_lines": lines,
                    "audit_sequences": seqs, "audit_ticks": ticks, "source": item.get("source"),
                    "target_id": item.get("destination"), "force_index": boundary.get("force_index"),
                    "boundary": boundary, "audit_item": item})
    return candidates


def raw_hash_expected(manifest: dict[str, Any], cohort: str) -> tuple[str, Path]:
    for name, data in manifest["inputs"]["raw_files"].items():
        if data["cohort"] == cohort:
            return data["expected_sha256"], ROOT / Path(name.replace("\\", "/"))
    raise RuntimeError(f"cohort missing from denominator manifest: {cohort}")


def snapshot_context(raw: dict[str, Any], path: Path, line: int, digest: str) -> dict[str, Any]:
    context = full_context(raw)
    context["provenance"].update({"source_path": path.relative_to(ROOT).as_posix(),
                                  "source_sha256": digest, "line": line,
                                  "sequence": raw.get("sequence"), "tick": raw_tick(raw)})
    return context


def project_split(split: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    manifest = json.loads(DENOMINATOR.read_text(encoding="utf-8"))
    candidates = collect_candidates(split)
    by_cohort: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for c in candidates: by_cohort[c["cohort"]].append(c)
    hashes: dict[str, str] = {}
    for cohort, cases in by_cohort.items():
        expected, path = raw_hash_expected(manifest, cohort)
        required_lines = {line for c in cases for line in c["raw_lines"]}
        # Index future observations by exact scope + u16 tick while streaming. The first raw
        # observation for a tick is retained, matching the denominator's duplicate policy.
        future_keys: set[tuple[tuple[Any, ...], int]] = set()
        for c in cases:
            scope = None
            # The scope is read from the exact t row later; target tick keys are provisionally
            # collected by tick and completed once that row is materialized.
            tick = c["audit_ticks"][1]
            future_keys.add((("__lineage__", c["case_id"]), (tick + 1) & 65535))
            future_keys.add((("__lineage__", c["case_id"]), (tick + 2) & 65535))
        selected: dict[int, dict[str, Any]] = {}
        h = hashlib.sha256()
        # One streaming pass verifies the full input hash and retains selected t-1/t lines.
        with path.open("rb") as f:
            for lineno, raw_line in enumerate(f, 1):
                h.update(raw_line)
                if lineno in required_lines:
                    selected[lineno] = json.loads(raw_line)
        actual = h.hexdigest()
        if actual != expected:
            raise RuntimeError(f"pinned raw hash mismatch for {cohort}: {actual} != {expected}")
        hashes[path.relative_to(ROOT).as_posix()] = actual
        # Preserve input tick t, arrival at t+1, and the contiguous following
        # observation at t+2. This is the force-status horizon in the freeze.
        future_specs: dict[tuple[tuple[Any, ...], int], list[tuple[dict[str, Any], str]]] = collections.defaultdict(list)
        for c in cases:
            raw_arrival = selected.get(c["raw_lines"][1])
            if raw_arrival is None:
                raise RuntimeError(f"missing selected arrival line: {c['case_id']}")
            tick = raw_tick(raw_arrival)
            if tick is None: continue
            scope = raw_scope(raw_arrival)
            future_specs[(scope, (tick + 1) & 65535)].append((c, "following"))
        future_lines: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
        # A second streaming pass is bounded and selects only requested first-per-tick rows.
        # Hash was already verified in the preceding full pass.
        remaining = set(future_specs)
        with path.open("rb") as f:
            for lineno, raw_line in enumerate(f, 1):
                if not remaining: break
                raw = json.loads(raw_line)
                tick = raw_tick(raw)
                key = (raw_scope(raw), tick) if tick is not None else None
                if key in remaining and all(lineno > c["raw_lines"][1] for c, _ in future_specs[key]):
                    for c, slot in future_specs[key]:
                        future_lines[(c["case_id"], slot)] = (lineno, raw)
                    remaining.remove(key)
        for c in cases:
            raw_before = selected[c["raw_lines"][0]]
            raw_t = selected[c["raw_lines"][1]]
            row_force = rows(raw_before, "forces")
            idx = c.get("force_index")
            def candidate_row(r: dict[str, Any]) -> bool:
                if (not visible(r) or fact_values(r, "source") != c["source"]
                        or fact_values(r, "destination") != c["target_id"]):
                    return False
                item = c.get("audit_item", {})
                expected_progress, speed = item.get("predicted_progress"), item.get("speed")
                progress = fact_values(r, "progress")
                return (type(expected_progress) is not int or type(speed) is not int
                        or type(progress) is int and progress + speed == expected_progress)
            force = row_force[idx] if type(idx) is int and idx < len(row_force) and candidate_row(row_force[idx]) else None
            # Validate every candidate by endpoint and frozen current-leg progress. Observer ID is
            # supplemental only and never breaks an ambiguous alignment.
            if force is None:
                matches = [r for r in row_force if candidate_row(r)]
                force = matches[0] if len(matches) == 1 else None
            if force is None:
                incoming_sig = [None, c["source"], c["target_id"], None]
            else:
                vec = units(force.get("units"))
                incoming_sig = [fact_values(force, "owner"), fact_values(force, "source"),
                                fact_values(force, "destination"), list(vec) if vec is not None else None]
            c["incoming_signature"] = incoming_sig
            c["force_id_supplemental"] = fact_values(force, "id") if force else None
            c["audit_ticks"] = [raw_tick(raw_before), raw_tick(raw_t)]
            c["incoming_raw_fact"] = force
            c["snapshots"] = {"before_raw": raw_before, "arrival_raw": raw_t}
            for slot in ("following",):
                pair = future_lines.get((c["case_id"], slot))
                if pair is not None:
                    line, raw = pair
                    c["snapshots"][slot] = raw
                else:
                    line, raw = None, None
                c.setdefault("provenance_lines", {})[slot] = line
            old_snapshots = c["snapshots"]
            c["snapshots"] = {
                "before": snapshot_context(old_snapshots["before_raw"], path, c["raw_lines"][0], actual),
                "arrival": snapshot_context(old_snapshots["arrival_raw"], path, c["raw_lines"][1], actual),
            }
            for slot in ("following",):
                if old_snapshots.get(slot) is not None:
                    c["snapshots"][slot] = snapshot_context(old_snapshots[slot], path,
                        c["provenance_lines"][slot], actual)
            # Provenance-aware contiguous tick check. Future observations are chosen from the same
            # scope; no t+2 status is accepted unless t+1 and t+2 both exist consecutively.
            p = c["snapshots"].get("before", {}).get("provenance", {})
            t1 = c["snapshots"].get("arrival", {}).get("provenance", {})
            t2 = c["snapshots"].get("following", {}).get("provenance", {})
            if not t1 or (t1.get("tick") - p.get("tick", -1)) % 65536 != 1:
                c["snapshots"].pop("arrival", None); c["snapshots"].pop("following", None)
            elif not t2 or (t2.get("tick") - t1.get("tick", -1)) % 65536 != 1:
                c["snapshots"].pop("following", None)
            c.pop("provenance_lines", None)
            c.pop("force_index", None)
            c.pop("audit_item", None)
            c.pop("raw_lines", None)
            c["target_id"] = c.pop("target_id")
            c["attacker_id_supplemental"] = c.pop("force_id_supplemental")
            c["source_path"] = path.relative_to(ROOT).as_posix()
            c["source_sha256"] = actual
            c["contiguous_t_plus_2_complete"] = "arrival" in c["snapshots"] and "following" in c["snapshots"]
    return candidates, hashes


def run(split: str, output_path: Path | None = None, score: bool = True) -> dict[str, Any]:
    candidates, input_hashes = project_split(split)
    if score:
        for case in candidates:
            score_case(case)
    else:
        for case in candidates:
            case.pop("boundary", None)
            case.pop("branch_candidate", None)
    out = output_path or ROOT / f"tests/fixtures/v2/arrival-settlement-replay-{split}.json.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps({"version": "unfiltered-arrival-settlement-replay-v1", "split": split,
        "source_hashes": input_hashes, "case_count": len(candidates), "cases": candidates},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with out.open("wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", filename="", mtime=0, compresslevel=6) as gz:
            gz.write(blob)
    counts = collections.Counter((c.get("branch_candidate"), c.get("classification")) for c in candidates)
    result = {"split": split, "case_count": len(candidates), "source_hashes": input_hashes,
            "fixture": out.relative_to(ROOT).as_posix(), "fixture_sha256": sha_file(out),
            "counts": {f"{branch}:{result}": n for (branch, result), n in sorted(counts.items())},
            "force_t_plus_1": dict(collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_1") for c in candidates)),
            "force_t_plus_2": dict(collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_2") for c in candidates))}
    if score:
        result["eligibility_without_terminal_proxy"] = {
            branch: sum(bool(c.get("local_context", {}).get("eligibility_without_terminal_proxy", {}).get(branch))
                        for c in candidates) for branch in ("capture", "reinforcement")}
        result["final_frozen_eligibility"] = {
            branch: sum(bool(c.get("local_context", {}).get("final_frozen_eligibility", {}).get(branch))
                        for c in candidates) for branch in ("capture", "reinforcement")}
        result["strict_world_eligible"] = {
            branch: sum(bool(c.get("local_context", {}).get("strict_world_eligible", {}).get(branch))
                        for c in candidates) for branch in ("capture", "reinforcement")}
    report_path = ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json"
    build_report_if_complete(report_path)
    return result


def rescore_existing_fixture(split: str) -> dict[str, Any]:
    path = ROOT / f"tests/fixtures/v2/arrival-settlement-replay-{split}.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    for case in payload["cases"]:
        score_case(case)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", filename="", mtime=0, compresslevel=6) as gz:
            gz.write(blob)
    cases = payload["cases"]
    counts = collections.Counter((c.get("branch_candidate"), c.get("classification")) for c in cases)
    result = {"split": split, "case_count": len(cases), "fixture": path.relative_to(ROOT).as_posix(),
        "fixture_sha256": sha_file(path), "counts": {f"{a}:{b}": n for (a, b), n in sorted(counts.items())},
        "eligibility_without_terminal_proxy": {b: sum(bool(c["local_context"]["eligibility_without_terminal_proxy"][b]) for c in cases)
            for b in ("capture", "reinforcement")},
        "final_frozen_eligibility": {b: sum(bool(c["local_context"]["final_frozen_eligibility"][b]) for c in cases)
            for b in ("capture", "reinforcement")}}
    build_report_if_complete(ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json")
    return result


def historical_live_scene_summary() -> dict[str, Any]:
    """Count every known ordinary due-arrival in the already captured live scene.

    This is a separate, previously seen context. It is not part of the pinned
    prospective holdout population and receives no formal credit.
    """
    path = ROOT / "tests/fixtures/v2/ordinary-arrival-scene-ae45ad53c1b4.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    observations = payload.get("observations", [])
    first_by_scope_tick: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in observations:
        if raw_tick(raw) is not None:
            first_by_scope_tick.setdefault((*raw_scope(raw), raw_tick(raw)), raw)
    ordered = sorted(first_by_scope_tick.values(), key=lambda r: (r.get("sequence", 0), raw_tick(r) or -1))
    next_observation = {}
    for left, right in zip(ordered, ordered[1:]):
        if raw_scope(left) == raw_scope(right) and (raw_tick(right) - raw_tick(left)) % 65536 == 1:
            next_observation[(*raw_scope(left), raw_tick(left))] = right
    by_key = {(*raw_scope(raw), raw_tick(raw)): raw for raw in ordered}
    rows_out = []
    exclusion_reasons: collections.Counter[str] = collections.Counter()
    branch_counts: collections.Counter[str] = collections.Counter()
    for before in ordered:
        key = (*raw_scope(before), raw_tick(before))
        arrival = next_observation.get(key)
        if arrival is None:
            continue
        towers = {}
        for row in rows(before, "towers"):
            if visible(row):
                tower, _ = _tower(row)
                if tower is not None:
                    towers[tower.id] = tower
        available, unavailable = [], []
        for index, row in enumerate(rows(before, "forces")):
            if not visible(row):
                continue
            force, _ = _force(row)
            if force is None:
                unavailable.append((index, row))
                continue
            force = _infer_pinned_acceleration(force, row, towers)
            if force.accelerated is None:
                unavailable.append((index, row))
            elif force.source in towers and force.destination in towers:
                available.append((index, row, force))
        following = next_observation.get((*raw_scope(arrival), raw_tick(arrival)))
        for index, row, force in available:
            source, target = towers[force.source], towers[force.destination]
            speed, required, _ = motion(Units(tuple(enumerate(force.units))), source.position,
                                        target.position, bool(force.accelerated), force.progress)
            if min(255, force.progress + speed) < required:
                continue
            try:
                boundary = ordinary_arrival_boundary(
                    force, source, target, raw_tick(before),
                    other_inbound=tuple(other[2] for other in available if other[0] != index),
                    inbound_context_complete=(not unavailable and is_known(before.get("forces"))
                        and before.get("coverage") == "PLAYER_VISIBLE_COMPLETE"), fixed_morale=True)
                status = "SUPPORTED" if boundary is not None else "NO_BOUNDARY"
                branch = boundary.branch if boundary is not None else None
            except UnsupportedState as exc:
                status, branch = "EXCLUDED", None
                exclusion_reasons[str(exc).split(":", 1)[0]] += 1
            branch_counts[f"{status}:{branch or 'NONE'}"] += 1
            before_target = visible_index(before, "towers").get(target.id)
            arrival_target = visible_index(arrival, "towers").get(target.id)
            following_target = visible_index(following, "towers").get(target.id) if following else None
            sig = (force.owner, force.source, force.destination, tuple(force.units))
            dummy = {"incoming_signature": sig, "target_id": target.id, "snapshots": {
                "arrival": full_context(arrival),
                "following": full_context(following) if following else None}}
            rows_out.append({
                "before_sequence": before.get("sequence"), "before_tick": raw_tick(before),
                "arrival_tick": raw_tick(arrival), "following_tick": raw_tick(following) if following else None,
                "source_id": force.source, "target_id": target.id, "branch": branch, "boundary_status": status,
                "incoming_owner": force.owner, "incoming_vector": list(force.units),
                "observed_arrival_owner": known_fact(arrival_target, "owner"),
                "observed_arrival_inventory": units(arrival_target.get("units")) if arrival_target else None,
                "observed_following_owner": known_fact(following_target, "owner"),
                "observed_following_inventory": units(following_target.get("units")) if following_target else None,
                "arrival_force_signature_status": force_status(dummy, "arrival"),
                "following_force_signature_status": force_status(dummy, "following"),
            })
    owner_vector_match = sum(r["observed_arrival_owner"] == r["incoming_owner"]
        and r["observed_arrival_inventory"] is not None
        and list(r["observed_arrival_inventory"]) == r["incoming_vector"] for r in rows_out)
    return {
        "fixture": path.relative_to(ROOT).as_posix(), "fixture_sha256": sha_file(path),
        "not_in_413_population": True, "not_holdout": True, "formal_credit": 0,
        "raw_observations": len(observations), "unique_scope_tick_states": len(ordered),
        "adjacent_scope_tick_pairs": len(next_observation), "known_due_candidates": len(rows_out),
        "branch_counts": dict(branch_counts), "excluded_reasons": dict(exclusion_reasons),
        "arrival_owner_and_inventory_exact_matches": owner_vector_match,
        "cases": rows_out,
    }


def prior_accepted_grade_b_summary(live_summary: dict[str, Any]) -> dict[str, Any]:
    """Attach current signature observations to the eight earlier accepted rows."""
    validation_path = ROOT / "docs/V2_M2A_ARRIVAL_BOUNDARY_VALIDATION.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    candidates = []
    for split in ("development", "holdout"):
        path = ROOT / f"tests/fixtures/v2/arrival-settlement-replay-{split}.json.gz"
        candidates.extend(json.loads(gzip.decompress(path.read_bytes()))["cases"])
    live_cases = live_summary["cases"]
    accepted_rows = []
    for old in validation.get("cases", []):
        if old.get("accepted_grade_b") is not True:
            continue
        cohort, tick = old.get("cohort"), old.get("tick")
        src, target = old.get("source"), old.get("target")
        if cohort == "live-ae45ad53c1b4":
            match = next((c for c in live_cases if c.get("before_tick") == tick
                          and c.get("source_id") == src and c.get("target_id") == target), None)
            source_type = "PREVIOUSLY_SEEN_LIVE_CONTEXT"
            details = match
        else:
            match = next((c for c in candidates if c.get("cohort") == cohort
                          and c.get("before_tick") == tick
                          and isinstance(c.get("incoming_signature"), list)
                          and c["incoming_signature"][1:3] == [src, target]), None)
            source_type = "PINNED_413_CONTEXT"
            details = None if match is None else {
                "case_id": match["case_id"], "classification": match.get("classification"),
                "branch_candidate": match.get("branch_candidate"),
                "arrival_force_signature_status": match.get("post_arrival_force_status", {}).get("t_plus_1"),
                "following_force_signature_status": match.get("post_arrival_force_status", {}).get("t_plus_2"),
                "observed_arrival_owner": match.get("observed_owner_after"),
                "observed_arrival_inventory": match.get("observed_inventory_after"),
                "observed_following_owner": match.get("observed_owner_following"),
                "observed_following_inventory": match.get("observed_inventory_following"),
            }
        if details is None:
            accepted_rows.append({"cohort": cohort, "before_tick": tick, "source_id": src,
                "target_id": target, "source_type": source_type, "mapping_status": "NOT_FOUND",
                "formal_credit": 0})
        else:
            if source_type == "PREVIOUSLY_SEEN_LIVE_CONTEXT":
                details = {k: details.get(k) for k in ("before_sequence", "before_tick", "arrival_tick",
                    "following_tick", "source_id", "target_id", "branch", "boundary_status",
                    "observed_arrival_owner", "observed_arrival_inventory", "observed_following_owner",
                    "observed_following_inventory", "arrival_force_signature_status",
                    "following_force_signature_status")}
            accepted_rows.append({"cohort": cohort, "before_tick": tick, "source_id": src,
                "target_id": target, "source_type": source_type, "mapping_status": "MATCHED",
                "current_observation": details, "formal_credit": 0})
    return {"source_report": validation_path.relative_to(ROOT).as_posix(),
        "source_sha256": sha_file(validation_path),
        "previously_accepted_grade_b_count": validation.get("accepted_grade_b_boundary_added"),
        "mapped_count": sum(x["mapping_status"] == "MATCHED" for x in accepted_rows),
        "independent_world_transition_groups": validation.get("independent_world_transition_groups"),
        "formal_credit": 0, "cases": accepted_rows}


def build_report_if_complete(report_path: Path) -> None:
    paths = {s: ROOT / f"tests/fixtures/v2/arrival-settlement-replay-{s}.json.gz"
             for s in ("development", "holdout")}
    if not all(p.exists() for p in paths.values()):
        return
    split_data = {s: json.loads(gzip.decompress(p.read_bytes())) for s, p in paths.items()}
    all_cases = [c for d in split_data.values() for c in d["cases"]]
    by_split: dict[str, Any] = {}
    for split, data in split_data.items():
        cases = data["cases"]
        boundary = collections.Counter("supported" if c["boundary"].get("status") ==
            "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN" else "excluded" for c in cases)
        branches = collections.Counter(c.get("branch_candidate") for c in cases)
        scores = collections.Counter((c.get("branch_candidate"), c.get("classification")) for c in cases)
        def elig(key: str, gate: str) -> dict[str, Any]:
            xs = [c for c in cases if c.get("local_context", {}).get(key, {}).get(gate)]
            return {"cases": len(xs), "groups": len({(c["cohort"], c.get("arrival_tick")) for c in xs}),
                    "recordings": len({c["cohort"] for c in xs})}
        force_t1 = collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_1") for c in cases)
        force_t2 = collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_2") for c in cases)
        residuals = {
            "production_due": sum(c.get("local_context", {}).get("production_due") is True for c in cases),
            "multiple_or_unresolved_inbound": sum(not c.get("local_context", {}).get("before_only_hard_premises", {}).get("no_unresolved_relevant_inbound") for c in cases),
            "active_delay": sum(c.get("local_context", {}).get("target_delay") not in (0, None) for c in cases),
            "special_destination": sum(c.get("local_context", {}).get("special_destination") is True for c in cases),
            "confirmed_local_relay": sum(c.get("local_context", {}).get("target_supply_line_present") is True for c in cases),
            "unknown_local_relay": sum(c.get("local_context", {}).get("target_supply_line_present") is None for c in cases),
            "capacity_clipping_or_ambiguity": sum(c.get("local_context", {}).get("capacity_status") == "CLIPPING_OR_CAPACITY_AMBIGUITY" for c in cases),
            "capacity_pinned_ground_overflow": sum(c.get("local_context", {}).get("capacity_status") == "WITHIN_PINNED_GROUND_OVERFLOW" for c in cases),
        }
        def eligible_score(gate: str, branch: str) -> dict[str, Any]:
            candidate_branch = {
                "capture": "EMPTY_NEUTRAL_CAPTURE",
                "reinforcement": "SAME_OWNER_REINFORCEMENT",
            }.get(branch)
            if candidate_branch is None:
                return {"cases": 0, "match": 0, "mismatch": 0, "unscorable": 0,
                        "accuracy_scored": None, "groups": 0, "recordings": 0}
            xs = [c for c in cases if c.get("branch_candidate") == candidate_branch
                  and c.get("local_context", {}).get(gate, {}).get(branch)]
            counts = collections.Counter(c.get("classification") for c in xs)
            return {"cases": len(xs), "match": counts["MATCH"], "mismatch": counts["MISMATCH"],
                    "unscorable": counts["UNSCORABLE"], "accuracy_scored": counts["MATCH"] / (counts["MATCH"] + counts["MISMATCH"])
                    if counts["MATCH"] + counts["MISMATCH"] else None,
                    "groups": len({(c["cohort"], c.get("arrival_tick")) for c in xs}),
                    "recordings": len({c["cohort"] for c in xs})}
        force_branch_status = {}
        for branch in ("EMPTY_NEUTRAL_CAPTURE", "SAME_OWNER_REINFORCEMENT", "NO_NAIVE_SETTLEMENT_BRANCH"):
            xs = [c for c in cases if c.get("branch_candidate") == branch
                  and c["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"]
            force_branch_status[branch] = {
                "t_plus_1": dict(collections.Counter(c["post_arrival_force_status"]["t_plus_1"] for c in xs)),
                "t_plus_2": dict(collections.Counter(c["post_arrival_force_status"]["t_plus_2"] for c in xs)),
            }
        by_split[split] = {
            "cases": len(cases), "boundary_supported": boundary["supported"], "boundary_excluded": boundary["excluded"],
            "branch_candidate_counts": dict(branches),
            "score_counts": {f"{a}:{b}": n for (a, b), n in sorted(scores.items())},
            "force_status_t_plus_1": dict(force_t1), "force_status_t_plus_2": dict(force_t2),
            "eligibility_without_terminal_proxy": {b: elig("eligibility_without_terminal_proxy", b) for b in ("capture", "reinforcement")},
            "final_frozen_eligibility": {b: elig("final_frozen_eligibility", b) for b in ("capture", "reinforcement")},
            "strict_world_eligible": {b: elig("strict_world_eligible", b) for b in ("capture", "reinforcement")},
            "naive_scores_within_eligibility": {
                gate: {b: eligible_score(gate, b) for b in ("capture", "reinforcement")}
                for gate in ("eligibility_without_terminal_proxy", "final_frozen_eligibility")},
            "force_status_supported_branch_cases": force_branch_status,
            "capacity_status_counts": dict(collections.Counter(c.get("local_context", {}).get("capacity_status") for c in cases)),
            "residuals": residuals,
        }
    naive = collections.Counter(c.get("classification") for c in all_cases)
    branch_naive = {}
    for branch in ("EMPTY_NEUTRAL_CAPTURE", "SAME_OWNER_REINFORCEMENT"):
        vals = collections.Counter(c.get("classification") for c in all_cases if c.get("branch_candidate") == branch)
        branch_naive[branch] = {"match": vals["MATCH"], "mismatch": vals["MISMATCH"],
                                "unscorable": vals["UNSCORABLE"],
                                "accuracy_scored": (vals["MATCH"] / (vals["MATCH"] + vals["MISMATCH"]))
                                    if vals["MATCH"] + vals["MISMATCH"] else None}
    manifest = json.loads(DENOMINATOR.read_text(encoding="utf-8"))
    edge_decompressed = sha_gzip_payload(EDGE_AUDIT)
    live_summary = historical_live_scene_summary()
    prior_grade_b = prior_accepted_grade_b_summary(live_summary)
    report = {
        "status": "UNFILTERED_REPLAY_COMPLETE",
        "version": "unfiltered-arrival-settlement-replay-v1",
        "freeze": {"initial_rule": "docs/V2_M2A_SETTLEMENT_RULE_FREEZE.json",
                   "initial_rule_sha256": sha_file(FREEZE),
                   "final_premise": "docs/V2_M2A_SETTLEMENT_PREMISE_FREEZE.json",
                   "final_premise_sha256": sha_file(ROOT / "docs/V2_M2A_SETTLEMENT_PREMISE_FREEZE.json"),
                   "holdout_scored_after_final_premise_freeze": True},
        "population": {"total_known_due_opportunities": len(all_cases),
                       "boundary_supported": sum(1 for c in all_cases if c["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"),
                       "boundary_excluded_retained": sum(1 for c in all_cases if c["boundary"].get("status") != "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"),
                       "supported_by_branch": {b: sum(1 for c in all_cases if c.get("branch_candidate") == b and c["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN")
                           for b in ("EMPTY_NEUTRAL_CAPTURE", "SAME_OWNER_REINFORCEMENT", "NO_NAIVE_SETTLEMENT_BRANCH")},
                       "raw_candidate_branch_counts_all_cases": dict(collections.Counter(c.get("branch_candidate") for c in all_cases))},
        "all_scoring": dict(naive), "branch_naive_scores": branch_naive,
        "all_413_force_status": {
            "t_plus_1": dict(collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_1") for c in all_cases)),
            "t_plus_2": dict(collections.Counter(c.get("post_arrival_force_status", {}).get("t_plus_2") for c in all_cases)),
        },
        "capture_owner_inventory_observations": {
            "supported_cases": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                                    and c["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"),
            "owner_after_matches_incoming": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                and c["classification"] != "UNSCORABLE" and c.get("observed_owner_after") == c.get("incoming_owner")),
            "observed_inventory_zero_after": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                and c["classification"] != "UNSCORABLE" and c.get("observed_inventory_after") == [0] * 10),
            "first_difference_counts": dict(collections.Counter(c.get("first_mismatch_field") for c in all_cases
                if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE" and c["classification"] == "MISMATCH")),
            "supported_inventory_mismatch_before_context": {
                "cases": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["boundary"].get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"
                    and c["classification"] == "MISMATCH"),
                "production_due_true": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("production_due") is True),
                "target_delay_nonzero": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("target_delay") not in (0, None)),
                "source_delay_nonzero": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("source_delay") not in (0, None)),
                "special_destination_true": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("special_destination") is True),
                "confirmed_local_relay_true": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("target_supply_line_present") is True),
                "local_relay_unknown": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("target_supply_line_present") is None),
                "possible_unknown_destination_inbound": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and (c.get("local_context", {}).get("other_visible_forces_destination_unknown_may_arrive_here") or 0) > 0),
                "incomplete_local_inbound_context": sum(1 for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH" and c.get("local_context", {}).get("local_inbound_complete") is not True),
                "capacity_status_counts": dict(collections.Counter(c.get("local_context", {}).get("capacity_status")
                    for c in all_cases if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
                    and c["classification"] == "MISMATCH")),
            },
        },
        "splits": by_split,
        "source_hashes": {**{p.relative_to(ROOT).as_posix(): sha_file(p) for p in paths.values()},
                          "docs/V2_M2A_COVERAGE_DENOMINATOR.json": sha_file(DENOMINATOR),
                          "tests/fixtures/v2/arrival-factor-edge-audit.jsonl.gz": sha_file(EDGE_AUDIT),
                          "arrival_factor_edge_audit_decompressed_sha256": edge_decompressed,
                          "tools/v2_arrival_settlement_replay.py": sha_file(Path(__file__))},
        "raw_source_hashes": manifest["inputs"]["raw_files"],
        "separate_previous_context": live_summary,
        "previously_accepted_grade_b_context": prior_grade_b,
        "interpretation": {
            "force_status": "Signature-level visibility only. TRANSFORMED means a unique same-owner/same-vector new leg starts at the prior target; it is continuation-compatible evidence, not physical force genealogy. Unknown plausible aliases remain AMBIGUOUS. DISAPPEARED means the original signature is absent from a complete visible collection, not proof of permanent consumption.",
            "settlement": "A capture owner transition with zero observed target inventory is a mismatch to the frozen owner+inventory capture rule. It remains in the score even when post-arrival force or downstream context is uncertain; current-deposit attribution is unresolved.",
            "eligibility": "The no-terminal-proxy and final frozen eligibility counts use before-only fields. Eligibility never filters original naive replay scores.",
        },
        "formal_credit": 0,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# Unfiltered arrival settlement replay", "",
          f"Population: {len(all_cases)} known due-arrival opportunities; {report['population']['boundary_supported']} supported boundaries and {report['population']['boundary_excluded_retained']} retained exclusions.", "",
          "## Original naive rule scores", "",
          f"Capture: {branch_naive['EMPTY_NEUTRAL_CAPTURE']['match']} match, {branch_naive['EMPTY_NEUTRAL_CAPTURE']['mismatch']} mismatch, {branch_naive['EMPTY_NEUTRAL_CAPTURE']['unscorable']} unscorable.",
          f"Reinforcement: {branch_naive['SAME_OWNER_REINFORCEMENT']['match']} match, {branch_naive['SAME_OWNER_REINFORCEMENT']['mismatch']} mismatch, {branch_naive['SAME_OWNER_REINFORCEMENT']['unscorable']} unscorable.", "",
          f"All {report['capture_owner_inventory_observations']['owner_after_matches_incoming']} supported captures show the incoming owner; {report['capture_owner_inventory_observations']['observed_inventory_zero_after']} show zero target inventory. Their before-context remains separately reported, including unknown relay/inbound facts and capacity status.", "",
          f"Before-only capture proxy: {sum(report['splits'][s]['naive_scores_within_eligibility']['eligibility_without_terminal_proxy']['capture']['cases'] for s in SPLIT_ORDER)} cases, {sum(report['splits'][s]['naive_scores_within_eligibility']['eligibility_without_terminal_proxy']['capture']['match'] for s in SPLIT_ORDER)} match and {sum(report['splits'][s]['naive_scores_within_eligibility']['eligibility_without_terminal_proxy']['capture']['mismatch'] for s in SPLIT_ORDER)} mismatch; final frozen terminal-true eligibility: {sum(report['splits'][s]['final_frozen_eligibility']['capture']['cases'] + report['splits'][s]['final_frozen_eligibility']['reinforcement']['cases'] for s in SPLIT_ORDER)} cases.", "",
          f"Separate previously seen live scene: {report['separate_previous_context']['raw_observations']} raw states / {report['separate_previous_context']['unique_scope_tick_states']} unique scope-tick states; {report['separate_previous_context']['known_due_candidates']} due opportunities, outside the 413 population and holdout.",
          f"Earlier accepted Grade B rows: {report['previously_accepted_grade_b_context']['mapped_count']} of {report['previously_accepted_grade_b_context']['previously_accepted_grade_b_count']} mapped for separate signature-status reporting; formal credit remains zero.", "",
          "Holdout was scored only after the final premise freeze. The before-only final eligibility counts and excluded boundary rows remain separate from the unfiltered score.", "",
          "Force status is signature-level visibility evidence; it does not prove physical force genealogy or permanent consumption.", "",
          f"Source hashes and per-split detail: [V2_M2A_UNFILTERED_SETTLEMENT.json](V2_M2A_UNFILTERED_SETTLEMENT.json).", ""]
    (ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--before-only", action="store_true", help="materialize split context without inspecting settlement outcomes")
    parser.add_argument("--rescore-fixture", action="store_true", help="recompute score/eligibility from an existing portable fixture")
    args = parser.parse_args()
    result = (rescore_existing_fixture(args.split) if args.rescore_fixture
              else run(args.split, score=not args.before_only))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
