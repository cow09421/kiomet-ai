"""Analysis-only before-state capture eligibility negative controls.

This module recognizes the frozen provisional-capture premises. It does not
predict a settlement vector, alter simulator state, score holdout, or grant
production eligibility.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from kiomet_ai.v2.sim.step import phase
from tools.v2_arrival_settlement_replay import local_context

REPLAY = ROOT / "tests/fixtures/v2/arrival-settlement-replay-development.json.gz"
PREMISE_FREEZE = ROOT / "docs/V2_M2A_SETTLEMENT_PREMISE_FREEZE.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fact_value(row: Any, key: str) -> Any:
    fact = row.get(key) if isinstance(row, dict) else None
    if not isinstance(fact, dict) or fact.get("knowledge") not in ("OBSERVED", "DERIVED"):
        return None
    return fact.get("value")


def _vector(row: Any, key: str) -> tuple[int, ...] | None:
    fact = row.get(key) if isinstance(row, dict) else None
    if not isinstance(fact, dict) or fact.get("knowledge") not in ("OBSERVED", "DERIVED"):
        return None
    value = fact.get("value")
    if isinstance(value, dict):
        pairs = value.get("counts")
        if not isinstance(pairs, list) or len(pairs) != 10:
            return None
        try:
            table = {pair[0]: pair[1] for pair in pairs if isinstance(pair, list) and len(pair) == 2}
        except (TypeError, IndexError):
            return None
        if set(table) != set(range(10)):
            return None
        result = tuple(table[i] for i in range(10))
    elif isinstance(value, list) and len(value) == 10:
        result = tuple(value)
    else:
        return None
    if any(type(n) is not int or not 0 <= n <= 255 for n in result):
        return None
    return result


def _towers(before: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    found: dict[int, list[dict[str, Any]]] = {}
    for row in before.get("towers", []):
        if isinstance(row, dict) and type(row.get("id")) is int:
            found.setdefault(row["id"], []).append(row)
    return found


def _before_snapshot(case: dict[str, Any]) -> dict[str, Any] | None:
    snapshots = case.get("snapshots")
    if not isinstance(snapshots, dict):
        return None
    value = snapshots.get("before", snapshots.get("t_minus_1"))
    return value if isinstance(value, dict) else None


def _find_incoming_force(before: dict[str, Any], case: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    sig = case.get("incoming_signature")
    if not isinstance(sig, (list, tuple)) or len(sig) != 4:
        return None, 0
    _, source_id, target_id, _ = sig
    matches = []
    for force in before.get("forces", []):
        if not isinstance(force, dict):
            continue
        if (_fact_value(force, "source") == source_id
                and _fact_value(force, "destination") == target_id):
            matches.append(force)
    return (matches[0], len(matches)) if len(matches) == 1 else (None, len(matches))


def before_capture_eligibility(case: dict[str, Any]) -> dict[str, Any]:
    """Return before-only premise blockers; never consult post-arrival fields."""
    reasons: list[str] = []
    before = _before_snapshot(case)
    if not isinstance(before, dict):
        return {"eligible": False, "reasons": ["BEFORE_SNAPSHOT_MISSING"]}
    provenance = before.get("provenance", {})
    scope = provenance.get("scope") if isinstance(provenance, dict) else None
    if (provenance.get("coverage") != "PLAYER_VISIBLE_COMPLETE"
            or not isinstance(scope, list) or len(scope) != 4
            or not all(scope[:3]) or type(provenance.get("tick")) is not int
            or type(provenance.get("sequence")) is not int):
        reasons.append("UNKNOWN_BEFORE_SCOPE")

    boundary = case.get("boundary")
    if (not isinstance(boundary, dict)
            or boundary.get("status") not in ("SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN",
                                               "ARRIVAL_REACHED_SUPPORTED_BOUNDARY")
            or boundary.get("branch") != "CAPTURE_REQUIRED"):
        reasons.append("NO_SUPPORTED_CAPTURE_BOUNDARY")

    sig = case.get("incoming_signature")
    source_id = sig[1] if isinstance(sig, (list, tuple)) and len(sig) == 4 else None
    target_id = case.get("target_id")
    if type(source_id) is not int or type(target_id) is not int:
        reasons.append("UNKNOWN_ENDPOINT_ID")
    indexed = _towers(before)
    sources = indexed.get(source_id, []) if type(source_id) is int else []
    targets = indexed.get(target_id, []) if type(target_id) is int else []
    if len(sources) != 1:
        reasons.append("SOURCE_NOT_UNIQUE_VISIBLE")
    if len(targets) != 1:
        reasons.append("TARGET_NOT_UNIQUE_VISIBLE")
    source = sources[0] if len(sources) == 1 else None
    target = targets[0] if len(targets) == 1 else None

    target_owner = _fact_value(target, "owner")
    if target_owner is None:
        reasons.append("TARGET_OWNER_UNKNOWN")
    elif type(target_owner) is not int or target_owner != 0:
        reasons.append("TARGET_NOT_NEUTRAL")
    target_units = _vector(target, "units")
    if target_units is None:
        reasons.append("TARGET_INVENTORY_UNKNOWN_OR_INVALID")
    elif any(target_units):
        reasons.append("TARGET_DEFENDED_OR_NONEMPTY")

    local = local_context(case)
    if local.get("local_inbound_complete") is not True:
        reasons.append("INBOUND_SCOPE_UNKNOWN")
    if local.get("other_visible_forces_destination_unknown_may_arrive_here", 0):
        reasons.append("INBOUND_DESTINATION_UNKNOWN")
    if local.get("visible_inbound_count_known") != 1:
        reasons.append("MULTIPLE_VISIBLE_INBOUND")

    source_delay = _fact_value(source, "delay_ticks")
    target_delay = _fact_value(target, "delay_ticks")
    if source_delay is None:
        reasons.append("SOURCE_DELAY_UNKNOWN")
    elif type(source_delay) is not int or source_delay != 0:
        reasons.append("SOURCE_DELAY_ACTIVE_OR_INVALID")
    if target_delay is None:
        reasons.append("TARGET_DELAY_UNKNOWN")
    elif type(target_delay) is not int or target_delay != 0:
        reasons.append("TARGET_DELAY_ACTIVE_OR_INVALID")

    incoming, matching_count = _find_incoming_force(before, case)
    if matching_count != 1 or incoming is None:
        reasons.append("INCOMING_FORCE_NOT_UNIQUE")
    incoming_owner = _fact_value(incoming, "owner")
    if incoming_owner is None:
        reasons.append("INCOMING_OWNER_UNKNOWN")
    elif type(incoming_owner) is not int or incoming_owner <= 0:
        reasons.append("INCOMING_OWNER_NONNEUTRAL_REQUIRED")
    incoming_units = _vector(incoming, "units")
    if incoming_units is None:
        reasons.append("INCOMING_INVENTORY_UNKNOWN_OR_INVALID")
    else:
        if any(incoming_units[6:]):
            reasons.append("SPECIAL_OR_RULER_INCOMING_VECTOR")
        if not any(incoming_units[1:6]):
            reasons.append("NONCLAIMING_INCOMING_VECTOR")

    if local.get("special_destination") is not False:
        reasons.append("SPECIAL_DESTINATION_OR_UNKNOWN")
    if local.get("capacity_status") not in ("WITHIN_NORMAL_CAPACITY", "WITHIN_PINNED_GROUND_OVERFLOW"):
        reasons.append("CAPACITY_UNKNOWN_OR_CLIPPING_CONTEXT")
    capacity = _vector(target, "capacity")
    if capacity is None:
        reasons.append("CAPACITY_UNKNOWN_OR_INVALID")
    elif incoming_units is not None and target_units is not None:
        totals = [target_units[i] + incoming_units[i] for i in range(10)]
        if any(totals[i] > capacity[i] + (5 if i == 4 else 10 if i == 5 else 0)
               for i in range(10)):
            reasons.append("CAPACITY_WOULD_CHANGE_FROZEN_VECTOR")

    target_supply = _fact_value(target, "supply_line_present")
    if target_supply is True:
        reasons.append("ACTIVE_LOCAL_RELAY")

    tick = provenance.get("tick") if isinstance(provenance, dict) else None
    if (type(tick) is int and type(target_id) is int and target is not None
            and target_owner == 0 and target_units == (0,) * 10):
        # The pinned step says neutral towers do not add production. Preserve an
        # explicit due check in case a future neutral production source appears.
        due = False
        production_rows = _fact_value(target, "production")
        if production_rows is None:
            reasons.append("TARGET_PRODUCTION_UNKNOWN")
        else:
            for unit, period in production_rows:
                if type(unit) is not int or type(period) is not int or period <= 0:
                    reasons.append("TARGET_PRODUCTION_INVALID")
                    continue
                if phase((tick + 1) & 65535, target_id) % period == 0:
                    due = True
        if due:
            reasons.append("TARGET_PRODUCTION_DUE")

    terminal = _fact_value(incoming, "terminal")
    if terminal is not True:
        reasons.append("TERMINAL_NOT_KNOWN_TRUE_BEFORE")
    fuel = _fact_value(incoming, "fuel")
    if fuel is not None and (type(fuel) is not int or fuel <= 0):
        reasons.append("KNOWN_EXPIRED_OR_INVALID_ARRIVAL_FUEL")

    # Deduplicate while preserving readable guard order.
    reasons = list(dict.fromkeys(reasons))
    return {"eligible": not reasons, "reasons": reasons,
            "before_only": True, "local_context": local,
            "target_owner_before": target_owner,
            "target_inventory_before": list(target_units) if target_units is not None else None,
            "incoming_owner_before": incoming_owner,
            "incoming_vector_before": list(incoming_units) if incoming_units is not None else None,
            "terminal_before": terminal,
            "source_id": source_id, "target_id": target_id}


def _known_fact(value: Any) -> dict[str, Any]:
    return {"value": value, "knowledge": "OBSERVED", "source": "negative-control mutation",
            "observed_at_ms": 1}


def isolated_terminal_known_case(case: dict[str, Any]) -> dict[str, Any]:
    """Create a test-only positive baseline by changing only before terminal."""
    result = copy.deepcopy(case)
    before = _before_snapshot(result)
    incoming, count = _find_incoming_force(before, result) if before is not None else (None, 0)
    if count != 1 or incoming is None:
        raise ValueError("cannot isolate terminal premise without one unique incoming force")
    incoming["terminal"] = _known_fact(True)
    return result


def _set_fact(row: dict[str, Any], key: str, value: Any, knowledge: str = "OBSERVED") -> None:
    row[key] = {"value": value, "knowledge": knowledge, "source": "negative-control mutation",
                "observed_at_ms": 1 if knowledge != "UNKNOWN" else None}


def synthetic_public_mutations(case: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Independent public-input mutations, each based on the same eligible case."""
    base = isolated_terminal_known_case(case)
    before = _before_snapshot(base)
    target = next(t for t in before["towers"] if t["id"] == base["target_id"])
    source_id = base["incoming_signature"][1]
    source = next(t for t in before["towers"] if t["id"] == source_id)
    force, _ = _find_incoming_force(before, base)
    mutations: list[tuple[str, dict[str, Any], str]] = []

    def clone(name: str, expected: str) -> tuple[str, dict[str, Any], str]:
        return name, copy.deepcopy(base), expected

    def set_incoming_units(case: dict[str, Any], values: list[int]) -> None:
        incoming_row, count = _find_incoming_force(case["snapshots"]["before"], case)
        if count != 1 or incoming_row is None:
            raise ValueError("cannot mutate a non-unique before incoming force")
        _set_fact(incoming_row, "units", {"counts": [[i, values[i]] for i in range(10)]})
        case["incoming_signature"][3] = list(values)

    c = clone("defended_neutral", "TARGET_DEFENDED_OR_NONEMPTY")
    _set_fact(next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"]),
              "units", {"counts": [[i, 1 if i == 5 else 0] for i in range(10)]})
    mutations.append(c)

    c = clone("multiple_inbound", "MULTIPLE_VISIBLE_INBOUND")
    f = copy.deepcopy(next(f for f in c[1]["snapshots"]["before"]["forces"]
                           if _fact_value(f, "source") == source_id
                           and _fact_value(f, "destination") == base["target_id"]))
    _set_fact(f, "owner", 17)
    _set_fact(f, "source", source_id + 1)
    f["id"] = _known_fact("negative-control-second-force")
    c[1]["snapshots"]["before"]["forces"].append(f)
    mutations.append(c)

    for label, field, value, expected in (
        ("source_delay_active", "source", 1, "SOURCE_DELAY_ACTIVE_OR_INVALID"),
        ("target_delay_active", "target", 1, "TARGET_DELAY_ACTIVE_OR_INVALID"),
        ("source_delay_unknown", "source", None, "SOURCE_DELAY_UNKNOWN"),
        ("target_delay_unknown", "target", None, "TARGET_DELAY_UNKNOWN"),
    ):
        c = clone(label, expected)
        row = next(t for t in c[1]["snapshots"]["before"]["towers"]
                   if t["id"] == (source_id if field == "source" else base["target_id"]))
        _set_fact(row, "delay_ticks", value, "UNKNOWN" if value is None else "OBSERVED")
        mutations.append(c)

    c = clone("special_incoming", "SPECIAL_OR_RULER_INCOMING_VECTOR")
    set_incoming_units(c[1], [0, 0, 0, 0, 0, 3, 1, 0, 0, 0])
    mutations.append(c)

    c = clone("hostile_occupied_target", "TARGET_NOT_NEUTRAL")
    row = next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"])
    _set_fact(row, "owner", 17)
    _set_fact(row, "relation", "ENEMY")
    mutations.append(c)

    c = clone("active_local_relay", "ACTIVE_LOCAL_RELAY")
    row = next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"])
    _set_fact(row, "supply_line_present", True)
    mutations.append(c)

    c = clone("terminal_unknown", "TERMINAL_NOT_KNOWN_TRUE_BEFORE")
    row, _ = _find_incoming_force(c[1]["snapshots"]["before"], c[1])
    row.pop("terminal", None)
    mutations.append(c)

    c = clone("wrong_target_inventory", "TARGET_DEFENDED_OR_NONEMPTY")
    row = next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"])
    _set_fact(row, "units", {"counts": [[i, 2 if i == 5 else 0] for i in range(10)]})
    mutations.append(c)

    c = clone("capacity_too_small", "CAPACITY_WOULD_CHANGE_FROZEN_VECTOR")
    row = next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"])
    _set_fact(row, "capacity", {"counts": [[i, 2 if i == 5 else (15 if i == 0 else (1 if i == 4 else (1 if i == 9 else 0))) ] for i in range(10)]})
    set_incoming_units(c[1], [0, 0, 0, 0, 0, 13, 0, 0, 0, 0])
    mutations.append(c)

    c = clone("target_owner_unknown", "TARGET_OWNER_UNKNOWN")
    row = next(t for t in c[1]["snapshots"]["before"]["towers"] if t["id"] == base["target_id"])
    _set_fact(row, "owner", None, "UNKNOWN")
    mutations.append(c)

    c = clone("incoming_owner_unknown", "INCOMING_OWNER_UNKNOWN")
    row, _ = _find_incoming_force(c[1]["snapshots"]["before"], c[1])
    _set_fact(row, "owner", None, "UNKNOWN")
    mutations.append(c)

    c = clone("inbound_scope_partial", "UNKNOWN_BEFORE_SCOPE")
    c[1]["snapshots"]["before"]["provenance"]["coverage"] = "PARTIAL"
    mutations.append(c)

    c = clone("unknown_inbound_destination", "INBOUND_DESTINATION_UNKNOWN")
    row = copy.deepcopy(force)
    _set_fact(row, "owner", 17)
    _set_fact(row, "source", source_id + 2)
    _set_fact(row, "destination", None, "UNKNOWN")
    row["id"] = _known_fact("negative-control-unknown-destination-force")
    c[1]["snapshots"]["before"]["forces"].append(row)
    mutations.append(c)

    c = clone("no_capture_boundary", "NO_SUPPORTED_CAPTURE_BOUNDARY")
    c[1]["boundary"]["branch"] = "COMBAT_REQUIRED"
    mutations.append(c)

    c = clone("known_expired_fuel", "KNOWN_EXPIRED_OR_INVALID_ARRIVAL_FUEL")
    row, _ = _find_incoming_force(c[1]["snapshots"]["before"], c[1])
    _set_fact(row, "fuel", 0)
    mutations.append(c)

    # The names themselves are the reviewable independent public mutations.
    return mutations


def build_report() -> dict[str, Any]:
    with gzip.open(REPLAY, "rt", encoding="utf-8") as stream:
        replay = json.load(stream)
    capture_cases = [c for c in replay["cases"] if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"]
    if len(capture_cases) != 24:
        raise RuntimeError(f"expected 24 unfiltered development capture candidates, got {len(capture_cases)}")
    control_ids = [
        "fe678ebb30ce:1584:0", "03d032d57e5b:187:0", "03d032d57e5b:232:0",
        "03d032d57e5b:268:0", "03d032d57e5b:400:0", "03d032d57e5b:991:0",
        "03d032d57e5b:1185:0", "03d032d57e5b:1209:0", "03d032d57e5b:1221:0",
        "daf86d0544b7:1492:0",
    ]
    by_id = {c["case_id"]: c for c in capture_cases}
    actual = []
    for case_id in control_ids:
        case = by_id[case_id]
        check = before_capture_eligibility(case)
        if check["eligible"]:
            raise RuntimeError(f"actual development control was admitted: {case_id}")
        actual.append({"case_id": case_id, "source": check["source_id"], "target": check["target_id"],
                       "tick": case["snapshots"]["before"]["provenance"]["tick"],
                       "target_owner_before": check["target_owner_before"],
                       "target_inventory_before": check["target_inventory_before"],
                       "terminal_before": check["terminal_before"], "refusals": check["reasons"]})
    positive_seed = by_id[control_ids[0]]
    positive = isolated_terminal_known_case(positive_seed)
    if not before_capture_eligibility(positive)["eligible"]:
        raise RuntimeError("isolated synthetic positive baseline does not satisfy frozen before premises")
    mutations = []
    for name, case, expected in synthetic_public_mutations(positive_seed):
        result = before_capture_eligibility(case)
        if result["eligible"] or expected not in result["reasons"]:
            raise RuntimeError(f"negative mutation {name} did not refuse on {expected}: {result['reasons']}")
        mutations.append({"name": name, "expected_refusal": expected, "actual_refusals": result["reasons"]})
    return {
        "version": "before-only-capture-negative-controls-v1",
        "scope": "analysis-only eligibility recognizer; no settlement prediction, production mutation, or holdout outcome access",
        "production_gate_passed": False,
        "this_control_pack_holdout_outcomes_accessed": False,
        "actual_development_close_invalid_cases": actual,
        "actual_case_count": len(actual),
        "actual_case_rejected_count": sum(not before_capture_eligibility(by_id[cid])["eligible"]
                                           for cid in control_ids),
        "synthetic_positive_baseline": {
            "source_case_id": positive_seed["case_id"],
            "only_change": "before-snapshot incoming Force terminal changed from unknown/missing to OBSERVED true",
            "eligible_under_frozen_before_premises": True,
            "outcome_fields_consulted": False
        },
        "public_input_mutations": mutations,
        "mutation_count": len(mutations),
        "mutation_rejected_count": sum(
            not before_capture_eligibility(case)["eligible"]
            for _, case, _ in synthetic_public_mutations(positive_seed)),
        "negative_control_total": len(actual) + len(mutations),
        "negative_control_rejected": (
            sum(not before_capture_eligibility(by_id[cid])["eligible"] for cid in control_ids)
            + sum(not before_capture_eligibility(case)["eligible"]
                  for _, case, _ in synthetic_public_mutations(positive_seed))),
        "false_admissions": sum(before_capture_eligibility(by_id[cid])["eligible"] for cid in control_ids)
        + sum(before_capture_eligibility(case)["eligible"]
              for _, case, _ in synthetic_public_mutations(positive_seed)),
        "review_guards": [
            "Use t_minus_1 endpoint/force facts only; never admit based on t/t+1 force absence or transformation.",
            "Terminal must be known true in the before snapshot; UNKNOWN is a hard refusal for exact inventory deposit.",
            "A local precondition violation remains a refusal even when a synthetic positive supplies terminal=true.",
            "This pack checks eligibility/refusal only; it does not mirror or verify the naive incoming-vector prediction."
        ],
        "source_manifest_sha256": {
            "development_replay_fixture": sha256(REPLAY),
            "premise_freeze": sha256(PREMISE_FREEZE),
            "replay_tool": sha256(ROOT / "tools/v2_arrival_settlement_replay.py"),
            "negative_controls_tool": sha256(Path(__file__)),
            "negative_controls_test": sha256(ROOT / "tests/test_v2_settlement_controls.py")
        }
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))

