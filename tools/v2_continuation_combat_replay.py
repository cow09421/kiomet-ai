"""Retrospective, continuation-aware replay of the frozen 31 combat cases.

This module only analyzes already recorded, player-visible snapshots. It does
not change the frozen formula, qualification, production, or live behavior.
"""
from __future__ import annotations

import collections
from datetime import datetime, timezone
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.v2_post_arrival_inventory_disposition import _project_snapshot  # noqa: E402
from tools.v2_combat_passive_replay import score_case  # noqa: E402
from tools.v2_factorized_coverage import is_known  # noqa: E402

PREREG = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_PREREG.json"
OLD_REPORT = ROOT / "docs/V2_M2A_COMBAT_PASSIVE_REPLAY.json"
OLD_FIXTURE = ROOT / "tests/fixtures/v2/combat-passive-replay.json.gz"
SETTLEMENT_DEV = ROOT / "tests/fixtures/v2/arrival-settlement-replay-development.json.gz"
SETTLEMENT_HOLD = ROOT / "tests/fixtures/v2/arrival-settlement-replay-holdout.json.gz"
FORMULA_SOURCE = ROOT / "src/kiomet_ai/v2/sim/combat.py"
OUTPUT_JSON = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_REPLAY.json"
OUTPUT_MD = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_REPLAY.md"
OUTPUT_FIXTURE = ROOT / "tests/fixtures/v2/continuation-aware-combat-replay.json.gz"
UNIT_COUNT = 10
PREVIOUSLY_INSPECTED = "YES"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fact_value(row: Any, name: str) -> Any:
    wrapper = row.get(name) if isinstance(row, dict) else None
    if (not isinstance(wrapper, dict)
            or wrapper.get("knowledge") not in {"OBSERVED", "DERIVED", "KNOWN"}
            or wrapper.get("value") is None):
        return None
    return wrapper["value"]


def _vector(fact_or_vector: Any, *, maximum: int | None = 255) -> tuple[int, ...] | None:
    if isinstance(fact_or_vector, dict):
        if (fact_or_vector.get("knowledge") not in {"OBSERVED", "DERIVED", "KNOWN"}
                or fact_or_vector.get("value") is None):
            return None
        value = fact_or_vector.get("value")
    else:
        value = fact_or_vector
    if isinstance(value, dict) and isinstance(value.get("counts"), list):
        counts = [0] * UNIT_COUNT
        seen: set[int] = set()
        for pair in value["counts"]:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return None
            kind, count = pair
            if type(kind) is not int or type(count) is not int or not 0 <= kind < UNIT_COUNT or kind in seen:
                return None
            if count < 0 or (maximum is not None and count > maximum):
                return None
            seen.add(kind)
            counts[kind] = count
        value = counts
    if (not isinstance(value, (list, tuple)) or len(value) != UNIT_COUNT
            or any(type(n) is not int or n < 0 or (maximum is not None and n > maximum) for n in value)):
        return None
    return tuple(value)


def _valid_scope(snapshot: Any) -> tuple[Any, ...] | None:
    if not isinstance(snapshot, dict):
        return None
    value = snapshot.get("provenance", {}).get("scope")
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or not isinstance(value[0], str) or not isinstance(value[1], str)
            or type(value[2]) is not int or type(value[3]) not in (int, float)):
        return None
    return tuple(value)


def _tick(snapshot: Any) -> int | None:
    value = snapshot.get("provenance", {}).get("tick") if isinstance(snapshot, dict) else None
    return value if type(value) is int else None


def _tower_in(snapshot: Any, target_id: int) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("towers"), list):
        return None
    return next((row for row in snapshot["towers"]
        if isinstance(row, dict) and row.get("id") == target_id
        and ("visibility" not in row or _fact_value(row, "visibility") is True)), None)


def _time_scope_valid(before: Any, after: Any, offset: int) -> bool:
    left_scope, right_scope = _valid_scope(before), _valid_scope(after)
    left_tick, right_tick = _tick(before), _tick(after)
    return (left_scope is not None and left_scope == right_scope
            and left_tick is not None and right_tick is not None
            and (right_tick - left_tick) % 65536 == 1 + offset)


def _visible_states(snapshot: Any) -> tuple[list[dict[str, Any]], int, bool]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("forces"), list):
        return [], 0, False
    rows: list[dict[str, Any]] = []
    unknown_visibility = 0
    for row in snapshot["forces"]:
        if not isinstance(row, dict):
            unknown_visibility += 1
            continue
        visibility = _fact_value(row, "visibility")
        if visibility is True:
            rows.append(row)
        elif visibility is not False:
            unknown_visibility += 1
    complete = (snapshot.get("provenance", {}).get("coverage") == "PLAYER_VISIBLE_COMPLETE"
                and unknown_visibility == 0)
    return rows, unknown_visibility, complete


def _signature(row: dict[str, Any]) -> tuple[Any, ...] | None:
    owner, source = _fact_value(row, "owner"), _fact_value(row, "source")
    dest = _fact_value(row, "destination")
    vector = _vector(row.get("units"))
    if type(owner) is not int or type(source) is not int or (dest is not None and type(dest) is not int) or vector is None:
        return None
    return owner, source, dest, vector


def _target_source_rows(snapshot: Any, target_id: int, post_owner: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    visible_rows, unknown_visibility, census_complete = _visible_states(snapshot)
    matching: list[dict[str, Any]] = []
    unknown_source_aliases: list[dict[str, Any]] = []
    unknown_owner_or_vector: list[dict[str, Any]] = []
    for ordinal, row in enumerate(visible_rows):
        source = _fact_value(row, "source")
        owner = _fact_value(row, "owner")
        vector = _vector(row.get("units"))
        if type(source) is not int:
            # No survivor-budget filter: any potentially same-owner positive
            # force with unknown source can alias the target route.
            if (type(owner) is not int or owner == post_owner) and (vector is None or any(vector)):
                unknown_source_aliases.append({
                    "observer_id_supplemental": _fact_value(row, "id"),
                    "owner": owner, "vector": list(vector) if vector is not None else None,
                    "destination": _fact_value(row, "destination"),
                    "first_appearance_uncertain": True,
                })
            continue
        if source != target_id:
            continue
        matching.append({
            "observer_id_supplemental": _fact_value(row, "id"),
            "visible_ordinal": ordinal,
            "owner": owner if type(owner) is int else None,
            "source": source,
            "destination": _fact_value(row, "destination"),
            "destination_known": type(_fact_value(row, "destination")) is int,
            "vector": list(vector) if vector is not None else None,
            "signature": list(_signature(row)) if _signature(row) is not None else None,
            "owner_known": type(owner) is int,
            "vector_known": vector is not None,
        })
        if type(owner) != int or vector is None:
            if (type(owner) is not int or owner == post_owner) and (vector is None or any(vector)):
                unknown_owner_or_vector.append(matching[-1])
    return matching, {
        "census_complete": census_complete,
        "unknown_visibility_rows": unknown_visibility,
        "unknown_source_aliases": unknown_source_aliases,
        "unknown_owner_or_vector_from_target": unknown_owner_or_vector,
    }


def detect_outgoing(before: dict[str, Any], after: dict[str, Any], target_id: int,
                    observed_post_owner: int, *, offset: int = 0,
                    previous_snapshots: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Detect new same-tick outgoing signatures without survivor-budget filtering.

    `offset=0` is primary arrival; offsets 1 and 2 are exploratory. Signature
    multiplicity (owner/source/destination/vector) is compared with before and
    the peak multiplicity in previous observations. Observer IDs are ignored.
    """
    if offset not in (0, 1, 2):
        raise ValueError("offset must be 0, 1, or 2")
    after_rows, after_quality = _target_source_rows(after, target_id, observed_post_owner)
    before_rows, before_quality = _target_source_rows(before, target_id, observed_post_owner)
    before_endpoint_aliases = [row for row in before_rows
        if row["owner"] == observed_post_owner and row["vector"] is not None
        and any(row["vector"]) and not row["destination_known"]]

    peak: collections.Counter[tuple[Any, ...]] = collections.Counter()
    snapshots = [before, *list(previous_snapshots)]
    previous_qualities = []
    timing_valid = _time_scope_valid(before, after, offset)
    for index, snap in enumerate(snapshots):
        snap_rows, snap_quality = _target_source_rows(snap, target_id, observed_post_owner)
        if index > 0:
            previous_qualities.append(snap_quality)
        rows, _, _ = _visible_states(snap)
        counts: collections.Counter[tuple[Any, ...]] = collections.Counter()
        for row in rows:
            if _fact_value(row, "source") == target_id:
                sig = _signature(row)
                if sig is not None:
                    counts[sig] += 1
        for sig, count in counts.items():
            peak[sig] = max(peak[sig], count)
        if index > 0:
            timing_valid = timing_valid and _time_scope_valid(snapshots[index - 1], snap, 0)
    if len(snapshots) > 1:
        timing_valid = timing_valid and _time_scope_valid(snapshots[-1], after, 0)

    after_counts: collections.Counter[tuple[Any, ...]] = collections.Counter()
    after_by_sig: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in after_rows:
        signature = tuple(row["signature"]) if row.get("signature") is not None else None
        if signature is not None:
            after_counts[signature] += 1
            after_by_sig[signature].append(row)

    new_rows: list[dict[str, Any]] = []
    seen_peak = peak.copy()
    for signature, count in after_counts.items():
        delta = max(0, count - peak[signature])
        if delta:
            new_rows.extend(after_by_sig[signature][:delta])
        seen_peak[signature] = max(seen_peak[signature], count)

    compatible: list[dict[str, Any]] = []
    wrong_owner: list[dict[str, Any]] = []
    zero_vector: list[dict[str, Any]] = []
    unverified_time: list[dict[str, Any]] = []
    for row in new_rows:
        if not timing_valid:
            unverified_time.append(row)
        elif row["owner"] != observed_post_owner:
            wrong_owner.append(row)
        elif row["vector"] is None:
            continue
        elif not any(row["vector"]):
            zero_vector.append(row)
        else:
            compatible.append(row)
    vector_sum = [sum(row["vector"][i] for row in compatible) for i in range(UNIT_COUNT)]

    all_qualities = [before_quality, *previous_qualities, after_quality]
    plausible_unknown = (sum(len(q["unknown_source_aliases"])
        + len(q["unknown_owner_or_vector_from_target"]) for q in all_qualities)
        + len(before_endpoint_aliases))
    complete = bool(timing_valid and all(q["census_complete"] for q in all_qualities)
                    and type(observed_post_owner) is int and not plausible_unknown)
    if compatible and timing_valid:
        status = "YES"
    elif plausible_unknown or not complete or not timing_valid:
        status = "UNKNOWN"
    else:
        status = "NO"
    return {
        "offset": offset,
        "status": status,
        "complete": complete,
        "time_scope_valid": timing_valid,
        "before_tick": _tick(before), "after_tick": _tick(after),
        "scope": list(_valid_scope(after)) if _valid_scope(after) is not None else None,
        "source_census_before": before_quality,
        "source_census_after": after_quality,
        "all_target_source_rows": after_rows,
        "new_signature_multiplicity": len(new_rows),
        "compatible_outgoing": compatible,
        "compatible_count": len(compatible),
        "compatible_sum": vector_sum,
        "known_wrong_owner_rows": wrong_owner,
        "zero_vector_rows": zero_vector,
        "unverified_time_rows": unverified_time,
        "possible_alias_count": plausible_unknown,
        "before_unknown_destination_aliases": before_endpoint_aliases,
        "first_appearance_uncertain": bool(before_endpoint_aliases),
        "signature_rule": "owner/source/destination/typed-vector multiplicity; observer ID excluded",
    }


def account_survivors(predicted_owner: Any, predicted_survivor_vector: Any,
                      observed_owner: Any, observed_inventory: Any,
                      detection: dict[str, Any]) -> dict[str, Any]:
    """Compare survivor prediction with inventory plus all detected outgoing."""
    predicted = _vector(predicted_survivor_vector)
    inventory = _vector(observed_inventory)
    owner_known = type(predicted_owner) is int and type(observed_owner) is int
    owner_match = owner_known and predicted_owner == observed_owner
    outgoing = detection.get("compatible_sum")
    outgoing_vector = _vector(outgoing, maximum=None)
    expected = None
    if inventory is not None and outgoing_vector is not None:
        expected = [inventory[i] + outgoing_vector[i] for i in range(UNIT_COUNT)]
    vectors_known = predicted is not None and expected is not None
    observed_only = ("UNKNOWN" if not vectors_known else
                     "EXACT" if list(predicted) == expected else "MISMATCH")
    if not owner_known:
        status = "UNKNOWN"
    elif not vectors_known or detection.get("complete") is not True:
        status = "UNKNOWN"
    elif not owner_match:
        status = "MISMATCH"
    else:
        status = "EXACT" if list(predicted) == expected else "MISMATCH"
    return {
        "status": status,
        "complete": bool(status in ("EXACT", "MISMATCH") and detection.get("complete") is True and owner_known),
        "owner_match": owner_match if owner_known else None,
        "predicted_owner": predicted_owner if type(predicted_owner) is int else None,
        "observed_owner": observed_owner if type(observed_owner) is int else None,
        "predicted_survivor_vector": list(predicted) if predicted is not None else None,
        "observed_inventory": list(inventory) if inventory is not None else None,
        "compatible_outgoing_sum": list(outgoing_vector) if outgoing_vector is not None else None,
        "observed_inventory_plus_outgoing": expected,
        "observed_only_status": observed_only,
    }


def analyze_case(case: dict[str, Any], snapshots: dict[str, Any] | None = None,
                 qualified: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the identical continuation accounting to one frozen old case."""
    snapshots = snapshots or case.get("continuation_snapshots")
    if not isinstance(snapshots, dict):
        raise ValueError("analyze_case needs before/offset_0/offset_1/offset_2 snapshots")
    original = "MATCH" if case.get("raw_formula_match_arrival") is True else "MISMATCH"
    prediction = case.get("prediction") or {}
    observed = case.get("observed_arrival") or {}
    qual = qualified or {}
    dets: dict[int, dict[str, Any]] = {}
    accounts: dict[int, dict[str, Any]] = {}
    prior: list[dict[str, Any]] = []
    arrival_tower = _tower_in(snapshots.get("offset_0"), case["target_id"])
    post_owner = _fact_value(arrival_tower, "owner") if arrival_tower else None
    observed_inventory_after = _vector(arrival_tower.get("units")) if arrival_tower else None
    for offset in (0, 1, 2):
        snap = snapshots.get(f"offset_{offset}")
        detection = detect_outgoing(snapshots.get("before"), snap, case["target_id"],
            post_owner, offset=offset, previous_snapshots=prior)
        dets[offset] = detection
        target = _tower_in(snap, case["target_id"])
        inventory = _vector(target.get("units")) if target is not None else None
        accounts[offset] = account_survivors(prediction.get("owner"), prediction.get("vector"),
            _fact_value(target, "owner") if target else None,
            inventory, detection)
        if isinstance(snap, dict):
            prior.append(snap)
    aware = accounts[0]
    if aware["status"] == "UNKNOWN" or aware["complete"] is not True:
        flip = "UNKNOWN"
    elif original == "MISMATCH" and aware["status"] == "EXACT":
        flip = "MISMATCH_TO_MATCH"
    elif original == "MATCH" and aware["status"] == "MISMATCH":
        flip = "MATCH_TO_MISMATCH"
    else:
        flip = "NONE"
    qualification = {"qualified": bool(qual.get("qualified", case.get("evaluable", False))),
                     "blockers": list(qual.get("blockers", case.get("evaluability_blockers", [])))}
    return {
        "case_id": case["case_id"], "recording_context": case.get("cohort"),
        "cohort": case.get("cohort"), "split": case.get("split"),
        "original_match_status": original, "qualified": qualification["qualified"],
        "qualification_blockers": qualification["blockers"],
        "hostility_known": case.get("pair_relation_status") == "KNOWN_HOSTILE",
        "inbound_complete": case.get("contamination", {}).get("multiple_inbound") is False,
        "predicted_post_combat_owner": prediction.get("owner"),
        "predicted_survivor_vector": prediction.get("vector"),
        "observed_owner_after": post_owner,
        "observed_inventory_after": list(observed_inventory_after) if observed_inventory_after is not None else None,
        "previous_projection_observed_arrival": observed,
        "offset0_matches_previous_observed": (post_owner == observed.get("owner")
            and list(observed_inventory_after) == observed.get("vector")
            if observed_inventory_after is not None else None),
        "raw_formula_status": case.get("raw_formula_status"),
        "raw_formula_match_arrival": case.get("raw_formula_match_arrival"),
        "owner_match_arrival": case.get("owner_match_arrival"),
        "vector_match_arrival": case.get("vector_match_arrival"),
        "same_tick_compatible_outgoing_count": dets[0]["compatible_count"],
        "same_tick_outgoing_sum": dets[0]["compatible_sum"],
        "same_tick_outgoing_status": dets[0]["status"],
        "continuation_accounting_status": aware["status"],
        "continuation_accounting": aware,
        "outgoing_by_offset": {str(k): dets[k] for k in dets},
        "exploratory_accounting_by_offset": {str(k): accounts[k] for k in accounts if k > 0},
        "flip_direction": flip,
        "timeline_provenance": {k: (snapshots.get(k) or {}).get("provenance")
                                 for k in ("before", "offset_0", "offset_1", "offset_2")},
    }


def _control_state(controls: dict[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    a = controls.get("A", {})
    b = controls.get("B", {})
    n_a = a.get("eligible_N", a.get("selected", a.get("n")))
    pos_a = a.get("YES", a.get("known_positive", a.get("positive")))
    unk_a = a.get("UNKNOWN", a.get("unknown"))
    if any(type(value) is not int or value < 0 for value in (n_a, pos_a, unk_a)):
        blockers.append("CONTROL_A_COUNTS_MISSING_OR_INVALID")
    elif n_a < 90:
        blockers.append("CONTROL_A_N_LT_90")
    elif (pos_a + unk_a) / n_a > 0.10:
        blockers.append("CONTROL_A_POSITIVE_PLUS_UNKNOWN_GT_10_PERCENT")
    if type(pos_a) is int and type(n_a) is int and n_a > 0 and pos_a / n_a > 0.10:
        blockers.append("CONTROL_A_KNOWN_POSITIVES_GT_10_PERCENT")
    decoy = b.get("decoy", {})
    n_b = b.get("decoy_available_N", b.get("available_decoys", b.get("available", b.get("n"))))
    pos_b = decoy.get("YES", b.get("known_positive_pairs", b.get("known_positive", b.get("positive"))))
    unk_b = decoy.get("UNKNOWN", b.get("unknown_pairs", b.get("unknown")))
    if any(type(value) is not int or value < 0 for value in (n_b, pos_b, unk_b)):
        blockers.append("CONTROL_B_COUNTS_MISSING_OR_INVALID")
    elif n_b < 20:
        blockers.append("CONTROL_B_AVAILABLE_LT_20")
    elif (pos_b + unk_b) / n_b > 0.10:
        blockers.append("CONTROL_B_POSITIVE_PLUS_UNKNOWN_GT_10_PERCENT")
    if type(pos_b) is int and type(n_b) is int and n_b > 0 and pos_b / n_b > 0.10:
        blockers.append("CONTROL_B_KNOWN_POSITIVES_GT_10_PERCENT")
    if controls.get("overall_controls_pass") is False:
        blockers.append("CONTROL_REPORT_OVERALL_GATE_FAILED")
    return not blockers, blockers


def decide_outcome(report: dict[str, Any], controls: dict[str, Any], *,
                   definition_revisions_used: int = 0,
                   prohibited_information_needed: bool = False,
                   expired: bool = False) -> dict[str, Any]:
    """Apply the preregistered hard stops, falsification-first three-way gate."""
    passed_controls, control_blockers = _control_state(controls)
    hard_stops = []
    if not passed_controls:
        hard_stops.extend(control_blockers)
    if definition_revisions_used > 1:
        hard_stops.append("SECOND_COMPATIBLE_DEFINITION_REVISION")
    if prohibited_information_needed:
        hard_stops.append("PROHIBITED_INFORMATION_NEEDED")
    if expired:
        hard_stops.append("HARD_DEADLINE_EXPIRED")
    cases = report.get("cases", [])
    qualified = [row for row in cases if row.get("qualified")]
    raw_known_mismatch = lambda row: (row.get("raw_formula_status") == "SCORED"
        and row.get("owner_match_arrival") is not None
        and row.get("vector_match_arrival") is not None
        and row.get("raw_formula_match_arrival") is False)
    def aware_mismatch_known(row: dict[str, Any]) -> bool:
        accounting = row.get("continuation_accounting", {})
        # The frozen unknown policy requires all relevant accounting inputs to
        # be complete even when the owner comparison itself is known.
        return (row.get("continuation_accounting_status") == "MISMATCH"
                and accounting.get("complete") is True
                and accounting.get("owner_match") in (True, False))
    known_residuals = [row for row in qualified
        if aware_mismatch_known(row) and raw_known_mismatch(row)]
    original_match_flips = [row for row in qualified if row.get("original_match_status") == "MATCH"
                            and row.get("flip_direction") == "MATCH_TO_MISMATCH"
                            and aware_mismatch_known(row)]
    falsified = bool(known_residuals or original_match_flips)
    mismatches = [row for row in cases if row.get("original_match_status") == "MISMATCH"]
    mismatch_rescues = sum(row.get("continuation_accounting_status") == "EXACT" and
        row.get("continuation_accounting", {}).get("complete") is True for row in mismatches)
    support = (len(mismatches) == 5 and mismatch_rescues >= 4
        and not [row for row in cases if row.get("original_match_status") == "MATCH"
                 and row.get("flip_direction") == "MATCH_TO_MISMATCH"
                 and aware_mismatch_known(row)]
        and not known_residuals
        and len(qualified) == 4 and all(row.get("continuation_accounting_status") == "EXACT"
            and row.get("continuation_accounting", {}).get("complete") is True for row in qualified)
        and passed_controls and definition_revisions_used <= 1)
    if hard_stops:
        outcome = "INSUFFICIENT_INFORMATION"
    elif falsified:
        outcome = "FORMULA_FALSIFIED"
    elif support:
        outcome = "FORMULA_DIAGNOSTICALLY_SUPPORTED"
    else:
        outcome = "INSUFFICIENT_INFORMATION"
    return {
        "outcome": outcome, "allowed_outcomes": ["FORMULA_FALSIFIED",
            "FORMULA_DIAGNOSTICALLY_SUPPORTED", "INSUFFICIENT_INFORMATION"],
        "hard_stop_blockers": hard_stops, "controls_pass": passed_controls,
        "control_blockers": control_blockers,
        "qualified_fully_known_counterexample_count": len(known_residuals),
        "qualified_fully_known_counterexample_cases": [x["case_id"] for x in known_residuals],
        "original_match_true_mismatch_count": len(original_match_flips),
        "original_match_true_mismatch_cases": [x["case_id"] for x in original_match_flips],
        "original_mismatch_count": len(mismatches), "original_mismatch_rescued_count": mismatch_rescues,
        "qualified_count": len(qualified),
        "formal_credit_change": 0, "new_grade_a": 0, "new_grade_b": 0,
        "certified_combat": False, "production_change": False,
    }


def _verify_receipts(prereg: dict[str, Any]) -> dict[str, Any]:
    formula_hash = sha256(FORMULA_SOURCE)
    if formula_hash != prereg["formula"]["source_sha256"]:
        raise ValueError("current combat formula does not match the preregistered frozen hash")
    paths = prereg["source_sha256"]
    receipts = {}
    for rel, expected in paths.items():
        path = ROOT / rel
        actual = sha256(path)
        receipts[rel] = {"expected_sha256": expected, "actual_sha256": actual,
                         "matches": actual == expected}
    bad = [path for path, item in receipts.items() if not item["matches"]]
    if bad:
        raise ValueError(f"frozen prereg source hash mismatch before scoring: {bad}")
    return receipts


def _load_old_and_projected(prereg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = json.loads(gzip.decompress(OLD_FIXTURE.read_bytes()))
    old_cases = payload["cases"]
    wanted_ids = prereg["selection"]["all31_case_ids"]
    if len(old_cases) != 31 or {row["case_id"] for row in old_cases} != set(wanted_ids):
        raise ValueError("prior passive replay no longer maps the frozen all31 selection exactly")
    projected_rows = []
    for path in (SETTLEMENT_DEV, SETTLEMENT_HOLD):
        raw = json.loads(gzip.decompress(path.read_bytes()))
        projected_rows.extend(raw["cases"])
    by_id: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in projected_rows:
        if row.get("case_id") in set(wanted_ids):
            by_id[row["case_id"]].append(row)
    if any(len(by_id.get(case_id, [])) != 1 for case_id in wanted_ids):
        raise ValueError("projected before/arrival timeline is not a unique mapping for all31")
    return old_cases, {case_id: by_id[case_id][0] for case_id in wanted_ids}


def _extract_raw_snapshots(projected_cases: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Stream the six pinned raw files, preserving missing exact ticks as UNKNOWN."""
    receipt = json.loads((ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json").read_text(encoding="utf-8"))
    manifest = receipt.get("raw_source_hashes")
    if not isinstance(manifest, dict) or len(manifest) != 6:
        raise ValueError("pinned settlement receipt must contain all six raw source files")
    wanted: dict[str, dict[tuple[tuple[Any, ...], int], list[tuple[str, str]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    selected: dict[str, dict[str, Any]] = {row["case_id"]: {} for row in projected_cases}
    for case in projected_cases:
        before = case.get("snapshots", {}).get("before", {})
        scope = before.get("provenance", {}).get("scope")
        if not isinstance(scope, list) or len(scope) != 4:
            raise ValueError(f"missing frozen full scope for {case['case_id']}")
        arrival_tick = case.get("arrival_tick")
        before_tick = case.get("before_tick")
        if type(arrival_tick) is not int or type(before_tick) is not int:
            raise ValueError(f"missing pinned tick for {case['case_id']}")
        path = case.get("source_path", "").replace("\\", "/")
        for label, tick in (("before", before_tick),
                            *((f"offset_{offset}", (arrival_tick + offset) % 65536)
                              for offset in (0, 1, 2))):
            wanted[path][(tuple(scope), tick)].append((case["case_id"], label))

    raw_hash_receipts: dict[str, Any] = {}
    for manifest_path, item in manifest.items():
        rel = manifest_path.replace("\\", "/")
        path = ROOT / rel
        targets = wanted.get(rel, {})
        selected_keys: set[tuple[tuple[Any, ...], int]] = set()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for line_no, line in enumerate(stream, 1):
                digest.update(line)
                if not targets:
                    continue
                raw = json.loads(line)
                scope = (raw.get("document_id"),
                         _fact_value(raw, "match_id"),
                         _fact_value(raw, "player_id"),
                         _fact_value(raw, "document_time_origin_ms"))
                tick = _fact_value(raw, "tick")
                if type(tick) is not int:
                    continue
                key = (scope, tick)
                if key not in targets or key in selected_keys:
                    continue
                selected_keys.add(key)
                snapshot = _project_snapshot(raw, rel, line_no, item["expected_sha256"])
                for case_id, label in targets[key]:
                    selected[case_id][label] = snapshot
        actual = digest.hexdigest()
        expected = item.get("expected_sha256")
        raw_hash_receipts[rel] = {"expected_sha256": expected, "actual_sha256": actual,
            "receipt_actual_sha256": item.get("actual_sha256"),
            "matches": actual == expected == item.get("actual_sha256")
                and item.get("matches_manifest") is True}
        if not raw_hash_receipts[rel]["matches"]:
            raise ValueError(f"pinned raw source hash mismatch: {rel}")
    missing = [{"case_id": case_id, "snapshot": label}
        for case_id, states in selected.items()
        for label in ("before", "offset_0", "offset_1", "offset_2")
        if label not in states]
    return selected, {"raw_sources": raw_hash_receipts, "missing_exact_snapshots": missing}


def build_case_rows(*, extraction: dict[str, dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract exact raw snapshots and score all31 symmetrically.

    Calling this performs the replay and should only occur after the committed
    preregistration and independent-control selection freeze.
    """
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    receipts = _verify_receipts(prereg)
    old_cases, projected = _load_old_and_projected(prereg)
    if extraction is None:
        extracted, raw_hashes = _extract_raw_snapshots(list(projected.values()))
    else:
        extracted, raw_hashes = extraction, {}
    qual_map = prereg["qualification"]["qualified_map"]
    rows = []
    for case in old_cases:
        cid = case["case_id"]
        pcase = projected[cid]
        snaps = extracted[cid]
        snapshots = {"before": snaps.get("before"),
            "offset_0": snaps.get("offset_0"), "offset_1": snaps.get("offset_1"), "offset_2": snaps.get("offset_2")}
        map_entry = qual_map[cid]
        rescored = score_case(pcase)
        if (rescored.get("prediction") != case.get("prediction")
                or rescored.get("raw_formula_match_arrival") != case.get("raw_formula_match_arrival")
                or rescored.get("evaluable") != case.get("evaluable")
                or rescored.get("evaluability_blockers") != case.get("evaluability_blockers")
                or bool(rescored.get("evaluable")) != bool(map_entry["qualified"])):
            raise ValueError(f"frozen qualification changed for {cid}")
        offset0_tower = _tower_in(snapshots.get("offset_0"), case["target_id"])
        offset0_owner = _fact_value(offset0_tower, "owner") if offset0_tower else None
        offset0_inventory = _vector(offset0_tower.get("units")) if offset0_tower else None
        if offset0_tower is not None and offset0_owner is not None and offset0_inventory is not None:
            if offset0_owner != case.get("observed_arrival", {}).get("owner") or list(offset0_inventory) != case.get("observed_arrival", {}).get("vector"):
                raise ValueError(f"exact offset0 target projection disagrees with prior arrival observation: {cid}")
        row = analyze_case(case, snapshots, map_entry)
        row["frozen_rescore_assertions"] = {
            "prediction_unchanged": rescored.get("prediction") == case.get("prediction"),
            "raw_match_unchanged": rescored.get("raw_formula_match_arrival") == case.get("raw_formula_match_arrival"),
            "qualification_unchanged": rescored.get("evaluable") == case.get("evaluable") == map_entry.get("qualified"),
            "evaluability_blockers_unchanged": rescored.get("evaluability_blockers") == case.get("evaluability_blockers"),
            "offset0_matches_previous_observed": row.get("offset0_matches_previous_observed"),
        }
        row["case_source"] = {
            "settlement_source_path": pcase.get("source_path"),
            "settlement_source_sha256": pcase.get("source_sha256"),
            "input_scope_consecutive": pcase.get("scope_consecutive_before_to_arrival"),
            "audit_sequences": pcase.get("audit_sequences"),
            "snapshot_sources": {key: value.get("provenance") for key, value in snapshots.items()},
        }
        rows.append(row)
    if {x["case_id"] for x in rows} != set(prereg["selection"]["all31_case_ids"]):
        raise ValueError("case selection changed")
    return rows, {"prereg_receipts": receipts, "raw_snapshot_hashes": raw_hashes,
                  "old_case_count": len(old_cases), "projected_case_count": len(projected)}


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for split in ("development", "holdout", "total"):
        group = cases if split == "total" else [c for c in cases if c["split"] == split]
        result[split] = {
            "cases": len(group),
            "original_match": sum(c["original_match_status"] == "MATCH" for c in group),
            "original_mismatch": sum(c["original_match_status"] == "MISMATCH" for c in group),
            "qualified": sum(c["qualified"] for c in group),
            "unqualified": sum(not c["qualified"] for c in group),
            "outgoing_status": dict(collections.Counter(c["same_tick_outgoing_status"] for c in group)),
            "accounting_status": dict(collections.Counter(c["continuation_accounting_status"] for c in group)),
            "qualified_accounting_status": dict(collections.Counter(
                c["continuation_accounting_status"] for c in group if c["qualified"])),
            "observed_only_accounting_status": dict(collections.Counter(
                c["continuation_accounting"]["observed_only_status"] for c in group)),
            "flips": dict(collections.Counter(c["flip_direction"] for c in group)),
        }
    return result


def build_report(controls: dict[str, Any], *, definition_revisions_used: int = 0,
                 prohibited_information_needed: bool = False, expired: bool | None = None) -> dict[str, Any]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if expired is None:
        deadline = datetime.fromisoformat(prereg["deadline_utc"].replace("Z", "+00:00"))
        expired = datetime.now(timezone.utc) >= deadline
    rows, provenance = build_case_rows()
    outcome = decide_outcome({"cases": rows}, controls,
        definition_revisions_used=definition_revisions_used,
        prohibited_information_needed=prohibited_information_needed, expired=expired)
    summary = _aggregate(rows)
    # Fixed-denominator assertions make accidental cohort narrowing a hard error.
    if (summary["total"]["cases"] != 31 or summary["total"]["original_match"] != 26
            or summary["total"]["original_mismatch"] != 5
            or summary["total"]["qualified"] != 4
            or summary["development"]["cases"] != 22 or summary["holdout"]["cases"] != 9):
        raise ValueError("the frozen 31/26/5/4 and 22/9 primary denominator changed")
    flip_total = collections.Counter(c["flip_direction"] for c in rows)
    cross = {status: {outgoing: sum(c["original_match_status"] == status
            and c["same_tick_outgoing_status"] == outgoing for c in rows)
        for outgoing in ("YES", "NO", "UNKNOWN")}
        for status in ("MATCH", "MISMATCH")}
    flips = {key: flip_total.get(key, 0) for key in
             ("NONE", "MATCH_TO_MISMATCH", "MISMATCH_TO_MATCH", "UNKNOWN")}
    owner_proxy = {
        "correct": sum(c.get("owner_match_arrival") is True for c in rows),
        "compared": sum(c.get("owner_match_arrival") is not None for c in rows),
        "incorrect": sum(c.get("owner_match_arrival") is False for c in rows),
    }
    report = {
        "version": "continuation-aware-combat-replay-v1",
        "prereg": {"path": PREREG.relative_to(ROOT).as_posix(),
            "sha256": sha256(PREREG), "baseline_head": prereg["baseline_head"],
            "formula_sha256": prereg["formula"]["source_sha256"]},
        "previously_inspected": {"status": PREVIOUSLY_INSPECTED,
            "basis": "All31 previously had generic arrival/following force-status inspection. Only the5 nonzero attacker-survivor cases (precisely the original mismatches) entered the old source=target/new-leg scan and already had NEW_LEG_COMPATIBLE_OWNER_AND_SURVIVOR_VECTOR. The remaining26 had route/alias inspection, not exhaustive outgoing accounting. Independence is therefore reduced, especially for the5 mismatch explanations.",
            "generic_status_inspected": 31, "explicit_new_leg_scan_cases": 5,
            "prior_complete_outgoing_accounting_all31": False,
            "source": "tools/v2_combat_passive_replay.py:_observed_force_status_detail"},
        "population": {"cases": 31, "development": 22, "holdout": 9,
            "original_match": 26, "original_mismatch": 5,
            "qualified": 4, "unqualified": 27,
            "selection_rule": prereg["selection"]["rule"]},
        "formula": {"name": "fight_ordinary", "source": "src/kiomet_ai/v2/sim/combat.py",
            "source_sha256": sha256(FORMULA_SOURCE), "pinned_sha256": prereg["formula"]["source_sha256"],
            "formula_or_production_changed": False},
        "qualification": prereg["qualification"],
        "continuation_accounting_definition": prereg["continuation_accounting"],
        "compatible_outgoing_definition": prereg["compatible_outgoing"],
        "unknown_policy": prereg["unknown_policy"],
        "controls": controls,
        "summary_by_split": summary,
        "same_tick_outgoing_2x2": cross,
        "flip_counts": flips,
        "existing_owner_proxy_accuracy": owner_proxy,
        "cases": rows,
        "decision": outcome,
        "formal_credit_change": 0, "grade_a_change": 0, "grade_b_change": 0,
        "certified_combat": False, "owner_only_production_rule": False,
        "provenance": provenance,
        "shared_detector_source_sha256": sha256(Path(__file__)),
        "limits": prereg["limits"],
        "prospective_recording_spec": "To be finalized separately after this retrospective outcome; no recording started.",
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary_by_split"]
    decision = report["decision"]
    lines = [
        "# Continuation-aware passive combat replay", "",
        f"**Outcome: {decision['outcome']}**. This retrospective reanalysis adds no Grade A/B, formal Combat, or certification credit and changes neither formula nor production.", "",
        f"All {report['population']['cases']} frozen cases were retained: {report['population']['original_match']} original MATCH / {report['population']['original_mismatch']} original MISMATCH; qualification remains {report['population']['qualified']} / {report['population']['unqualified']}. Original development/holdout split remains 22/9.", "",
        f"The earlier passive replay had already inspected per-case post-arrival force visibility: **PREVIOUSLY_INSPECTED = {report['previously_inspected']['status']}**. This makes the current replay retrospective and not independent evidence.", "",
        "## Primary same-tick continuation accounting", "",
        "Primary uses only offset 0: predicted survivor vector must equal observed target inventory plus every newly observed compatible same-tick outgoing vector, with predicted owner matching observed post-combat owner. Partial retained inventory and multiple outgoing forces are included; oversized vectors remain counterexamples. Offsets +1/+2 are exploratory only.", "",
        f"Same-tick outgoing status 2×2: `{json.dumps(report['same_tick_outgoing_2x2'], sort_keys=True)}`.",
        f"Flip counts: `{json.dumps(report['flip_counts'], sort_keys=True)}`.",
        f"Qualified cases with known residual counterexample: {decision['qualified_fully_known_counterexample_count']}; original MATCH cases truly flipped to MISMATCH: {decision['original_match_true_mismatch_count']}.", "",
        "## Controls and limits", "",
        "A and B controls use the shared detector and preregistered deterministic sampling. A positive actual-target outgoing in a noncombat event is reported separately from false pairing on its non-arriving decoy.",
        f"Control gate passed: {decision['controls_pass']}; blockers: `{json.dumps(decision['control_blockers'])}`.", "",
        "The JSON artifact includes all 31 case rows, original status and split, unchanged qualification, predicted/observed vectors and owner, outgoing counts/sums, unknown/observed-only accounting, per-offset exploratory data, scope/tick provenance, flip direction, controls, and source hash receipts.", "",
        "## Next prospective recording", "",
        "A separate prospective passive recording specification can be finalized after this outcome. No broad recording run, live combat, production change, formula edit, owner-only production rule, or evidence-credit increase occurred.", "",
    ]
    return "\n".join(lines)


def write_report(report: dict[str, Any]) -> None:
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(report), encoding="utf-8")
    fixture_data = {"version": report["version"], "population": report["population"],
                    "summary_by_split": report["summary_by_split"], "cases": report["cases"]}
    compressed = gzip.compress(json.dumps(fixture_data, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8"), compresslevel=9, mtime=0)
    OUTPUT_FIXTURE.write_bytes(compressed)


if __name__ == "__main__":
    controls = json.loads((ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_CONTROLS.json").read_text(encoding="utf-8"))
    if controls.get("shared_detector_source_sha256") != sha256(Path(__file__)):
        raise SystemExit("Controls must be scored with this exact shared detector source before replay.")
    report = build_report(controls)
    write_report(report)
    print(json.dumps({"outcome": report["decision"]["outcome"],
                      "population": report["population"], "flips": report["flip_counts"]}))
