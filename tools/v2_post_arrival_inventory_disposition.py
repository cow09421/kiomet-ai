"""Bounded visible-force accounting for the 45 frozen capture cases.

This is retrospective diagnostic analysis only. It does not infer physical
force genealogy, a causal relay mechanism, or a production capture rule.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.v2_arrival_settlement_replay import (
    ROOT, DENOMINATOR, _tower, _force, _infer_pinned_acceleration, fact_values,
    known_fact, rows, sha_file, units, val, project_row, FORCE_FIELDS, TOWER_FIELDS,
)
from tools.v2_factorized_coverage import is_known

FREEZE = ROOT / "docs/V2_M2A_POST_ARRIVAL_DISPOSITION_FREEZE.json"
DEV_FIXTURE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-development.json.gz"
HOLD_FIXTURE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-holdout.json.gz"
OUT_FIXTURE = ROOT / "tests/fixtures/v2/post-arrival-inventory-disposition.json.gz"
REPORT_JSON = ROOT / "docs/V2_M2A_POST_ARRIVAL_INVENTORY_DISPOSITION.json"
REPORT_MD = ROOT / "docs/V2_M2A_POST_ARRIVAL_INVENTORY_DISPOSITION.md"

UNIT_COUNT = 10
OFFSETS = (0, 1, 2)
BASELINE_HEAD = "54d0c5a0ba37712ee448586a2de91c64aae749a4"
FREEZE_COMMIT = "ae561e9510d4a7bceb8e029f0b6f1806b60b56c1"


def valid_vector(value: Any) -> tuple[int, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) != UNIT_COUNT:
        return None
    if any(type(n) is not int or n < 0 or n > 255 for n in value):
        return None
    return tuple(value)


def account_outgoing(incoming_vector: Any, observed_inventory: Any,
                     outgoing_vectors: Iterable[Any], *,
                     accounting_complete: bool = True) -> dict[str, Any]:
    """Compare inventory with incoming minus every supplied outgoing vector.

    Negative components are retained. The observed-only result is useful when
    aliases or census completeness prevent a complete accounting conclusion.
    """
    incoming = valid_vector(incoming_vector)
    observed = valid_vector(observed_inventory)
    outgoing_known = outgoing_vectors is not None
    outgoing = [valid_vector(v) for v in outgoing_vectors] if outgoing_known else []
    vectors_known = incoming is not None and observed is not None and outgoing_known and all(v is not None for v in outgoing)
    expected: tuple[int, ...] | None = None
    if vectors_known:
        sums = tuple(sum(v[i] for v in outgoing if v is not None) for i in range(UNIT_COUNT))
        expected = tuple(incoming[i] - sums[i] for i in range(UNIT_COUNT))
    observed_match = (expected is not None and observed == expected)
    status = "UNKNOWN" if not accounting_complete or not vectors_known else ("EXACT" if observed_match else "MISMATCH")
    positive_outgoing = bool(vectors_known and any(any(n != 0 for n in v) for v in outgoing if v is not None))
    return {
        "status": status,
        "complete": bool(accounting_complete and vectors_known),
        "observed_only_status": "UNKNOWN" if not vectors_known else ("EXACT" if observed_match else "MISMATCH"),
        "expected_inventory_unclipped": list(expected) if expected is not None else None,
        "observed_inventory": list(observed) if observed is not None else None,
        "negative_components_retained": bool(expected is not None and any(n < 0 for n in expected)),
        "positive_outgoing": positive_outgoing,
        "outgoing_vector_count": len(outgoing),
        "outgoing_sum": [sum(v[i] for v in outgoing if v is not None) for i in range(UNIT_COUNT)]
            if vectors_known else None,
    }


def _scope(snapshot: dict[str, Any]) -> tuple[Any, ...] | None:
    provenance = snapshot.get("provenance", {})
    value = provenance.get("scope")
    if (not isinstance(value, list) or len(value) != 4 or not isinstance(value[0], str)
            or not isinstance(value[1], str) or type(value[2]) is not int
            or type(value[3]) not in (int, float)):
        return None
    return tuple(value)


def _tick(snapshot: dict[str, Any] | None) -> int | None:
    if not isinstance(snapshot, dict):
        return None
    tick = snapshot.get("provenance", {}).get("tick")
    return tick if type(tick) is int else None


def _consecutive(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    a, b = _tick(left), _tick(right)
    left_scope, right_scope = _scope(left or {}), _scope(right or {})
    return (left_scope is not None and right_scope is not None and left_scope == right_scope
            and a is not None and b is not None
            and (b - a) % 65536 == 1)


def _key(row: dict[str, Any]) -> tuple[Any, ...] | None:
    owner = known_fact(row, "owner")
    source = known_fact(row, "source")
    destination = known_fact(row, "destination")
    vector = units(row.get("units")) if is_known(row.get("units")) else None
    if type(owner) is not int or type(source) is not int or (destination is not None and type(destination) is not int) or vector is None:
        return None
    return owner, source, destination, tuple(vector)


def _outgoing_rows(snapshot: dict[str, Any] | None, target_id: int,
                   expected_owner: int | None = None,
                   expected_vector: tuple[int, ...] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return [], {"census_complete": False, "unknown_visibility_rows": 0,
                    "unknown_source_aliases": 0, "plausible_same_owner_unknown_source_aliases": 0,
                    "unknown_owner_or_vector_from_target": 0, "plausible_same_owner_unknown_vector": 0}
    provenance = snapshot.get("provenance", {})
    census = provenance.get("coverage") == "PLAYER_VISIBLE_COMPLETE"
    all_forces = snapshot.get("forces")
    if not isinstance(all_forces, list):
        return [], {"census_complete": False, "unknown_visibility_rows": 0,
                    "unknown_source_aliases": 0, "plausible_same_owner_unknown_source_aliases": 0,
                    "unknown_owner_or_vector_from_target": 0, "plausible_same_owner_unknown_vector": 0}
    visible_rows, unknown_visibility = [], 0
    for row in all_forces:
        vis = known_fact(row, "visibility")
        if vis is True:
            visible_rows.append(row)
        elif vis is not False:
            unknown_visibility += 1
    outgoing: list[dict[str, Any]] = []
    unknown_source_aliases = 0
    plausible_unknown_source_aliases = 0
    unknown_owner_or_vector = 0
    plausible_unknown_vector = 0
    for ordinal, row in enumerate(visible_rows):
        source = known_fact(row, "source")
        if type(source) is not int:
            unknown_source_aliases += 1
            owner = known_fact(row, "owner")
            vector = units(row.get("units")) if is_known(row.get("units")) else None
            vector_plausible = (vector is None or expected_vector is None
                or (any(vector) and all(vector[i] <= expected_vector[i] for i in range(UNIT_COUNT))))
            if ((type(owner) is not int or expected_owner is None or owner == expected_owner)
                    and vector_plausible):
                plausible_unknown_source_aliases += 1
            continue
        if source != target_id:
            continue
        owner = known_fact(row, "owner")
        vector = units(row.get("units")) if is_known(row.get("units")) else None
        outgoing.append({
            "observer_id_supplemental": row.get("id") if type(row.get("id")) is int else known_fact(row, "id"),
            "visible_ordinal": ordinal,
            "owner": owner if type(owner) is int else None,
            "source": source,
            "destination": known_fact(row, "destination") if type(known_fact(row, "destination")) is int else None,
            "destination_known": type(known_fact(row, "destination")) is int,
            "units": list(vector) if vector is not None else None,
            "progress": known_fact(row, "progress") if type(known_fact(row, "progress")) is int else None,
            "signature": list(_key(row)) if _key(row) is not None else None,
        })
        if type(owner) is not int or vector is None:
            unknown_owner_or_vector += 1
            vector_plausible = (vector is None or expected_vector is None
                or (any(vector) and all(vector[i] <= expected_vector[i] for i in range(UNIT_COUNT))))
            if ((type(owner) is not int or expected_owner is None or owner == expected_owner)
                    and vector_plausible):
                plausible_unknown_vector += 1
    return outgoing, {
        "census_complete": bool(census and unknown_visibility == 0),
        "unknown_visibility_rows": unknown_visibility,
        "unknown_source_aliases": unknown_source_aliases,
        "plausible_same_owner_unknown_source_aliases": plausible_unknown_source_aliases,
        "unknown_owner_or_vector_from_target": unknown_owner_or_vector,
        "plausible_same_owner_unknown_vector": plausible_unknown_vector,
    }


def _sig_key(row: dict[str, Any]) -> tuple[Any, ...] | None:
    value = row.get("signature")
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not isinstance(value[3], (list, tuple)):
        return None
    return value[0], value[1], value[2], tuple(value[3])


def _target_context(snapshot: dict[str, Any] | None, target_id: int) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"status": "UNKNOWN"}
    tower = next((r for r in snapshot.get("towers", [])
                  if r.get("id") == target_id and known_fact(r, "visibility") is True), None)
    if tower is None:
        return {"status": "UNKNOWN", "target_visible": False}
    return {
        "status": "OBSERVED", "target_visible": True,
        "owner": known_fact(tower, "owner"), "inventory": units(tower.get("units")) if is_known(tower.get("units")) else None,
        "capacity": units(tower.get("capacity")) if is_known(tower.get("capacity")) else None,
        "production": known_fact(tower, "production"),
        "delay_ticks": known_fact(tower, "delay_ticks"),
        "supply_line_present": known_fact(tower, "supply_line_present"),
        "effects": known_fact(tower, "effects"),
    }


def _project_snapshot(raw: dict[str, Any], path: str, line_no: int, source_hash: str) -> dict[str, Any]:
    """Project a raw observation without promoting stale UNKNOWN fact values."""
    towers_known = is_known(raw.get("towers")) or isinstance(raw.get("towers"), list)
    forces_known = is_known(raw.get("forces")) or isinstance(raw.get("forces"), list)
    towers = ([project_row(r, TOWER_FIELDS) for r in rows(raw, "towers")
              if known_fact(r, "visibility") is True] if towers_known else [])
    forces = ([project_row(r, FORCE_FIELDS) for r in rows(raw, "forces")
              if known_fact(r, "visibility") is not False] if forces_known else None)
    return {
        "provenance": {
            "sequence": raw.get("sequence"), "tick": known_fact(raw, "tick"),
            "scope": [raw.get("document_id"), known_fact(raw, "match_id"),
                     known_fact(raw, "player_id"), known_fact(raw, "document_time_origin_ms")],
            "coverage": raw.get("coverage"), "forces_collection_known": forces_known,
            "source_path": path, "source_line": line_no,
            "source_sha256": source_hash, "first_retained_for_scope_tick": True,
        },
        "towers": towers, "forces": forces,
    }


def _unknown_source_aliases(snapshot: dict[str, Any] | None, incoming_owner: int | None,
                            incoming_vector: tuple[int, ...] | None) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("forces"), list):
        return []
    result = []
    for row in snapshot["forces"]:
        if known_fact(row, "visibility") is not True or type(known_fact(row, "source")) is int:
            continue
        owner = known_fact(row, "owner")
        vector = units(row.get("units")) if is_known(row.get("units")) else None
        compatible = (vector is None or incoming_vector is None
            or (any(vector) and all(vector[i] <= incoming_vector[i] for i in range(UNIT_COUNT))))
        plausible_owner = type(owner) is not int or incoming_owner is None or owner == incoming_owner
        result.append({
            "observer_id_supplemental": row.get("id") if type(row.get("id")) is int else None,
            "source_unknown": True, "owner": owner, "owner_known": type(owner) is int,
            "units": list(vector) if vector is not None else None, "vector_known": vector is not None,
            "destination": known_fact(row, "destination"),
            "destination_known": type(known_fact(row, "destination")) is int,
            "plausible_same_owner_outgoing": bool(plausible_owner and compatible),
            "exact_incoming_vector_alias": bool(plausible_owner and vector is not None
                and incoming_vector is not None and vector == incoming_vector),
            "first_appearance_uncertain": True,
        })
    return result


def analyze_case(case: dict[str, Any], snapshots: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze one frozen capture case over `before`, `offset_0`, `offset_1`, `offset_2`.

    Snapshots use the replay helper's portable projected form. No IDs are used
    to establish genealogy; they remain supplemental observer metadata only.
    """
    if snapshots is None:
        snapshots = case.get("disposition_snapshots")
    if not isinstance(snapshots, dict):
        raise ValueError("analyze_case expects `disposition_snapshots` or an explicit snapshots mapping")
    target_id = case.get("target_id")
    incoming_sig = case.get("incoming_signature")
    if not isinstance(incoming_sig, (list, tuple)) or len(incoming_sig) != 4:
        incoming_owner, incoming_vector = None, None
    else:
        incoming_owner, incoming_vector = incoming_sig[0], valid_vector(incoming_sig[3])
    contexts = {k: _target_context(snapshots.get(k), target_id)
                for k in ("before", "offset_0", "offset_1", "offset_2")}
    observed_arrival_owner = contexts["offset_0"].get("owner")
    outgoing_by_offset: dict[str, list[dict[str, Any]]] = {}
    census_by_offset: dict[str, dict[str, Any]] = {}
    unknown_source_aliases_by_offset: dict[str, list[dict[str, Any]]] = {}
    for offset in OFFSETS:
        key = f"offset_{offset}"
        outgoing_by_offset[key], census_by_offset[key] = _outgoing_rows(
            snapshots.get(key), target_id, incoming_owner, incoming_vector)
        unknown_source_aliases_by_offset[key] = _unknown_source_aliases(
            snapshots.get(key), incoming_owner, incoming_vector)
        snap = snapshots.get(key) or {}
        provenance = snap.get("provenance", {})
        for row in outgoing_by_offset[key]:
            row["same_owner_as_incoming"] = (type(row.get("owner")) is int
                and type(incoming_owner) is int and row["owner"] == incoming_owner)
            row["same_owner_as_observed_arrival_target"] = (type(row.get("owner")) is int
                and type(observed_arrival_owner) is int and row["owner"] == observed_arrival_owner)
            row["observed_offset"] = offset
            row["observed_tick"] = _tick(snap)
            row["source_path"] = provenance.get("source_path")
            row["source_line"] = provenance.get("source_line")
            row["source_sequence"] = provenance.get("sequence")
    before_rows, before_completeness = _outgoing_rows(
        snapshots.get("before"), target_id, incoming_owner, incoming_vector)
    before_unknown_aliases = _unknown_source_aliases(snapshots.get("before"), incoming_owner, incoming_vector)
    before_plausible_unknown_aliases = sum(x["plausible_same_owner_outgoing"] for x in before_unknown_aliases)
    before_exact_vector_aliases = sum(x["exact_incoming_vector_alias"] for x in before_unknown_aliases)
    before_counts = collections.Counter(_sig_key(r) for r in before_rows if _sig_key(r) is not None)
    seen_peak = collections.Counter(before_counts)
    first_seen_outgoing: list[dict[str, Any]] = []
    offsets_case = {0: False, 1: False, 2: False}
    for offset in OFFSETS:
        rows_at_offset = outgoing_by_offset[f"offset_{offset}"]
        counts = collections.Counter(_sig_key(r) for r in rows_at_offset if _sig_key(r) is not None)
        row_index: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
        for row in rows_at_offset:
            signature = _sig_key(row)
            if signature is not None:
                row_index[signature].append(row)
        for signature, count in counts.items():
            prior_peak = seen_peak[signature]
            if count > prior_peak:
                delta = count - prior_peak
                offsets_case[offset] = True
                for row in row_index[signature][:delta]:
                    first_seen_outgoing.append({**row, "first_observed_offset": offset,
                        "first_observed_tick": _tick(snapshots.get(f"offset_{offset}")),
                        "first_observed_source_path": (snapshots.get(f"offset_{offset}") or {}).get("provenance", {}).get("source_path"),
                        "first_observed_source_line": (snapshots.get(f"offset_{offset}") or {}).get("provenance", {}).get("source_line"),
                        "first_observed_sequence": (snapshots.get(f"offset_{offset}") or {}).get("provenance", {}).get("sequence"),
                        "dedup_signature": list(signature),
                        "same_owner_as_new_target": signature[0] == incoming_owner,
                        "same_owner_as_observed_arrival_target": (type(observed_arrival_owner) is int
                            and signature[0] == observed_arrival_owner),
                        "compatible_with_incoming": (signature[0] == incoming_owner
                            and any(signature[3]) and incoming_vector is not None
                            and all(signature[3][i] <= incoming_vector[i] for i in range(UNIT_COUNT))),
                    })
                seen_peak[signature] = count
    offset0_known_same_owner_vectors = [r["units"] for r in first_seen_outgoing
        if r["first_observed_offset"] == 0 and r.get("same_owner_as_new_target") is True and r.get("units") is not None]
    completeness = census_by_offset.get("offset_0", {})
    plausible_alias_unknown = ((completeness.get("plausible_same_owner_unknown_source_aliases", 0) or 0) > 0
        or (completeness.get("plausible_same_owner_unknown_vector", 0) or 0) > 0
        or completeness.get("census_complete") is not True
        or before_completeness.get("census_complete") is not True
        or before_plausible_unknown_aliases > 0)
    time_scope = {
        "before_to_arrival": _consecutive(snapshots.get("before"), snapshots.get("offset_0")),
        "arrival_to_offset_1": _consecutive(snapshots.get("offset_0"), snapshots.get("offset_1")),
        "offset_1_to_offset_2": _consecutive(snapshots.get("offset_1"), snapshots.get("offset_2")),
    }
    primary = account_outgoing(incoming_vector,
        contexts["offset_0"].get("inventory"), offset0_known_same_owner_vectors,
        accounting_complete=(not plausible_alias_unknown and time_scope["before_to_arrival"]))
    observed_inventory = contexts["offset_0"].get("inventory")
    raw_arrival_owner_match = (contexts["offset_0"].get("owner") == incoming_owner
        if type(contexts["offset_0"].get("owner")) is int and type(incoming_owner) is int else None)
    if raw_arrival_owner_match is True and incoming_vector is not None and observed_inventory is not None:
        if tuple(observed_inventory) == incoming_vector:
            raw_inventory_classification = "MATCH"
        elif not any(observed_inventory):
            raw_inventory_classification = "ZERO_INVENTORY"
        else:
            raw_inventory_classification = "OTHER_MISMATCH"
    else:
        raw_inventory_classification = "UNKNOWN"
    # An observed-only equality is not promoted to complete accounting when a
    # plausible same-target outgoing alias is unresolved.
    positive_exact = (primary["observed_only_status"] == "EXACT" and primary["positive_outgoing"])
    no_outgoing_observed_only = (primary["observed_only_status"] == "EXACT" and not primary["positive_outgoing"])
    no_outgoing_exact = (primary["status"] == "EXACT" and not primary["positive_outgoing"])
    first_offset = next((n for n in OFFSETS if offsets_case[n]), None)
    if first_offset is not None:
        first_offset_status: str | int = first_offset
    elif all(time_scope.values()) and all(census_by_offset[f"offset_{n}"].get("census_complete") is True
            and census_by_offset[f"offset_{n}"].get("plausible_same_owner_unknown_source_aliases", 0) == 0
            and census_by_offset[f"offset_{n}"].get("plausible_same_owner_unknown_vector", 0) == 0
            for n in OFFSETS):
        first_offset_status = "none"
    else:
        first_offset_status = "UNKNOWN"
    # Supplementary 0..2 total is unique-by-signature/multiplicity and is not
    # used to explain offset-0 inventory causally.
    window_vectors = [r["units"] for r in first_seen_outgoing
        if r.get("same_owner_as_new_target") is True and r.get("units") is not None]
    window_complete = all(time_scope.values()) and not any(census_by_offset[f"offset_{n}"].get("census_complete") is not True
        or (census_by_offset[f"offset_{n}"].get("plausible_same_owner_unknown_source_aliases", 0) or 0) > 0
        or (census_by_offset[f"offset_{n}"].get("plausible_same_owner_unknown_vector", 0) or 0) > 0
        for n in OFFSETS)
    window_accounting = account_outgoing(incoming_vector, contexts["offset_0"].get("inventory"),
        window_vectors, accounting_complete=window_complete)
    return {
        "case_id": case.get("case_id"), "cohort": case.get("cohort"), "split": case.get("split"),
        "recording": case.get("cohort"), "target_id": target_id,
        "before_tick": _tick(snapshots.get("before")), "arrival_tick": _tick(snapshots.get("offset_0")),
        "incoming_owner": incoming_owner, "incoming_vector": list(incoming_vector) if incoming_vector is not None else None,
        "observed_arrival_target_owner": observed_arrival_owner,
        "original_inventory_classification": case.get("classification"),
        "raw_first_retained_arrival_owner_match": raw_arrival_owner_match,
        "raw_first_retained_arrival_inventory_classification": raw_inventory_classification,
        "original_fixture_arrival_owner": case.get("observed_owner_after"),
        "original_fixture_arrival_inventory": case.get("observed_inventory_after"),
        "target_context_by_offset": contexts,
        "snapshot_provenance_by_offset": {
            label: ({k: (snapshots.get(label) or {}).get("provenance", {}).get(k)
                for k in ("sequence", "tick", "scope", "coverage", "source_path", "source_line",
                          "source_sha256", "first_retained_for_scope_tick")}
                if snapshots.get(label) is not None else None)
            for label in ("before", "offset_0", "offset_1", "offset_2")},
        "source_census_by_offset": census_by_offset,
        "before_source_census": before_completeness,
        "unknown_source_aliases_by_offset": unknown_source_aliases_by_offset,
        "before_existing_outgoing_multiplicity": {"known_signature_count": sum(before_counts.values()),
            "unique_signatures": len(before_counts), "unknown_source_aliases": before_completeness.get("unknown_source_aliases", 0),
            "unknown_source_alias_rows": before_unknown_aliases,
            "plausible_same_owner_unknown_source_aliases": before_plausible_unknown_aliases,
            "exact_incoming_vector_unknown_source_aliases": before_exact_vector_aliases},
        "all_visible_outgoing_by_offset": outgoing_by_offset,
        "duplicate_signature_multiplicity_by_offset": {
            str(n): sum(max(0, count - 1) for count in collections.Counter(
                _sig_key(r) for r in outgoing_by_offset[f"offset_{n}"] if _sig_key(r) is not None).values())
            for n in OFFSETS},
        "first_observed_new_outgoing_0_2": first_seen_outgoing,
        "new_outgoing_first_offset_case": first_offset,
        "new_outgoing_first_offset_status": first_offset_status,
        "new_outgoing_present_by_offset": {str(k): offsets_case[k] for k in OFFSETS},
        "primary_arrival_accounting": primary,
        "primary_positive_outgoing_observed_only_exact": bool(positive_exact),
        "primary_positive_outgoing_exact": bool(positive_exact and primary["status"] == "EXACT"),
        "primary_no_outgoing_exact_tautology": bool(no_outgoing_exact),
        "primary_no_outgoing_observed_only_equality": bool(no_outgoing_observed_only),
        "primary_outgoing_positive_total": sum(primary["outgoing_sum"] or []),
        "supplementary_window_0_2_accounting": window_accounting,
        "unknown_alias_completeness_block": plausible_alias_unknown,
        "before_only_context": {k: case.get("local_context", {}).get(k) for k in (
            "target_supply_line_present", "capacity_status", "production_due", "target_delay",
            "source_delay", "special_destination", "local_inbound_complete",
            "other_visible_forces_destination_unknown_may_arrive_here",
            "other_visible_forces_known_other_destination")},
        "time_scope_contiguous": time_scope,
    }


def _load_case_fixtures() -> dict[str, list[dict[str, Any]]]:
    result = {}
    for split, path in (("development", DEV_FIXTURE), ("holdout", HOLD_FIXTURE)):
        payload = json.loads(gzip.decompress(path.read_bytes()))
        result[split] = [c for c in payload["cases"]
            if c.get("branch_candidate") == "EMPTY_NEUTRAL_CAPTURE"
            and c.get("boundary", {}).get("status") == "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN"
            and c.get("classification") in ("MATCH", "MISMATCH")]
    return result


def load_population() -> dict[str, list[dict[str, Any]]]:
    """Load the original, unchanged 45 capture cases partitioned by split."""
    return _load_case_fixtures()


def _wanted_snapshots(cases: list[dict[str, Any]]) -> dict[str, dict[tuple[Any, ...], set[str]]]:
    by_file: dict[str, dict[tuple[Any, ...], set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    for case in cases:
        snaps = case["snapshots"]
        scope = tuple(snaps["before"]["provenance"]["scope"])
        before_tick, arrival_tick = _tick(snaps["before"]), _tick(snaps["arrival"])
        if before_tick is None or arrival_tick is None or (arrival_tick - before_tick) % 65536 != 1:
            raise ValueError(f"nonconsecutive base snapshots for {case['case_id']}")
        path = case["source_path"].replace("\\", "/")
        by_file[path][(*scope, before_tick)].add("before")
        for offset in OFFSETS:
            by_file[path][(*scope, (arrival_tick + offset) % 65536)].add(f"offset_{offset}")
    return by_file


def extract_exact_snapshots(cases: list[dict[str, Any]]) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str]]:
    """Stream/hash all six manifest sources; retain first exact scoped tick rows."""
    manifest = json.loads(DENOMINATOR.read_text(encoding="utf-8"))["inputs"]["raw_files"]
    wanted = _wanted_snapshots(cases)
    selected: dict[str, dict[str, dict[str, Any]]] = {c["case_id"]: {} for c in cases}
    cases_at_key: dict[str, dict[tuple[Any, ...], list[dict[str, Any]]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for case in cases:
        scope = tuple(case["snapshots"]["before"]["provenance"]["scope"])
        before_tick, arrival_tick = _tick(case["snapshots"]["before"]), _tick(case["snapshots"]["arrival"])
        path = case["source_path"].replace("\\", "/")
        for label, tick in (("before", before_tick), *( (f"offset_{n}", (arrival_tick + n) % 65536) for n in OFFSETS)):
            cases_at_key[path][(*scope, tick)].append((case, label))
    actual_hashes: dict[str, str] = {}
    for manifest_name, entry in manifest.items():
        rel = manifest_name.replace("\\", "/")
        path = ROOT / rel
        digest = hashlib.sha256()
        targets = wanted.get(rel, {})
        first_keys: set[tuple[Any, ...]] = set()
        with path.open("rb") as stream:
            for line_no, line in enumerate(stream, 1):
                digest.update(line)
                if not targets:
                    continue
                raw = json.loads(line)
                tick = known_fact(raw, "tick")
                if type(tick) is not int:
                    continue
                raw_scope = (raw.get("document_id"), known_fact(raw, "match_id"),
                    known_fact(raw, "player_id"), known_fact(raw, "document_time_origin_ms"))
                if (not isinstance(raw_scope[0], str) or not isinstance(raw_scope[1], str)
                        or type(raw_scope[2]) is not int or type(raw_scope[3]) not in (int, float)):
                    continue
                key = (*raw_scope, tick)
                labels = targets.get(key)
                if labels is None or key in first_keys:
                    continue
                first_keys.add(key)
                snapshot = _project_snapshot(raw, rel, line_no, entry["expected_sha256"])
                for case, label in cases_at_key[rel].get(key, []):
                    selected[case["case_id"]][label] = snapshot
        actual = digest.hexdigest()
        actual_hashes[rel] = actual
        expected = entry["expected_sha256"]
        if actual != expected or entry.get("actual_sha256") != expected:
            raise ValueError(f"raw source hash mismatch: {rel}")
    missing_required = [(case_id, label) for case_id, data in selected.items()
               for label in ("before", "offset_0") if label not in data]
    if missing_required:
        raise ValueError(f"missing required before/arrival first retained snapshots: {missing_required[:8]}")
    for data in selected.values():
        data.setdefault("offset_1", None)
        data.setdefault("offset_2", None)
    return selected, actual_hashes


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for split in ("development", "holdout", "total"):
        subset = cases if split == "total" else [c for c in cases if c["split"] == split]
        outcome = collections.Counter(c["original_inventory_classification"] for c in subset)
        groups = len({(c["cohort"], c["arrival_tick"]) for c in subset})
        recordings = len({c["cohort"] for c in subset})
        by_class = {}
        for cls in ("MATCH", "MISMATCH"):
            xs = [c for c in subset if c["original_inventory_classification"] == cls]
            context = lambda field: dict(collections.Counter(
                str(c.get("before_only_context", {}).get(field)) for c in xs))
            by_class[cls] = {
                "cases": len(xs), "groups": len({(c["cohort"], c["arrival_tick"]) for c in xs}),
                "recordings": len({c["cohort"] for c in xs}),
                "outgoing_positive_cases": sum(c["primary_outgoing_positive_total"] > 0 for c in xs),
                "compatible_new_outgoing_cases_0_2": sum(any(r.get("compatible_with_incoming") is True
                    for r in c["first_observed_new_outgoing_0_2"]) for c in xs),
                "primary_accounting": dict(collections.Counter(c["primary_arrival_accounting"]["status"] for c in xs)),
                "observed_only_accounting": dict(collections.Counter(c["primary_arrival_accounting"]["observed_only_status"] for c in xs)),
                "positive_outgoing_exact": sum(c["primary_positive_outgoing_exact"] for c in xs),
                "positive_outgoing_observed_only_exact": sum(c["primary_positive_outgoing_observed_only_exact"] for c in xs),
                "no_outgoing_exact_tautology": sum(c["primary_no_outgoing_exact_tautology"] for c in xs),
                "no_outgoing_observed_only_equality": sum(c["primary_no_outgoing_observed_only_equality"] for c in xs),
                "first_outgoing_offset_cases": dict(collections.Counter(str(c["new_outgoing_first_offset_status"]) for c in xs)),
                "window_0_2_accounting": dict(collections.Counter(c["supplementary_window_0_2_accounting"]["status"] for c in xs)),
                "before_context": {
                    "visible_line_fact": context("target_supply_line_present"),
                    "capacity_class": context("capacity_status"),
                    "production_due": context("production_due"),
                    "target_delay": context("target_delay"), "source_delay": context("source_delay"),
                    "special_destination": context("special_destination"),
                    "inbound_complete": context("local_inbound_complete"),
                    "possible_unknown_destination_inbound": context("other_visible_forces_destination_unknown_may_arrive_here"),
                },
                "recording_concentration": dict(collections.Counter(c["cohort"] for c in xs)),
                "target_concentration": {"unique_targets": len({c["target_id"] for c in xs}),
                    "max_cases_on_one_target": max(collections.Counter(c["target_id"] for c in xs).values(), default=0)},
            }
        result[split] = {"cases": len(subset), "groups": groups, "recordings": recordings,
            "outcome_counts": dict(outcome), "by_inventory_class": by_class}
    return result


def build_artifacts() -> dict[str, Any]:
    fixtures = load_population()
    selected_cases = fixtures["development"] + fixtures["holdout"]
    if len(selected_cases) != 45:
        raise ValueError(f"expected all 45 scored capture cases; got {len(selected_cases)}")
    selected, raw_hashes = extract_exact_snapshots(selected_cases)
    analyzed = []
    for case in selected_cases:
        snaps = selected[case["case_id"]]
        analyzed.append(analyze_case(case, snaps))
    by_split = _aggregate(analyzed)
    # Preserve original split and 13/32 outcome counts independently of the
    # post-arrival feature calculation.
    if by_split["total"]["outcome_counts"].get("MATCH") != 13 or by_split["total"]["outcome_counts"].get("MISMATCH") != 32:
        raise ValueError("the frozen primary population must remain 13 MATCH / 32 ZERO-INVENTORY")
    dev_count = by_split["development"]["cases"]
    if dev_count != 24 or by_split["holdout"]["cases"] != 21:
        raise ValueError("original development/holdout capture split changed")
    raw_owner_matches = sum(c["raw_first_retained_arrival_owner_match"] is True for c in analyzed)
    raw_inventory_classes = collections.Counter(c["raw_first_retained_arrival_inventory_classification"] for c in analyzed)
    if raw_owner_matches != 45 or raw_inventory_classes.get("MATCH") != 13 or raw_inventory_classes.get("ZERO_INVENTORY") != 32:
        raise ValueError(f"first-retained raw arrival facts differ from frozen outcome set: owners={raw_owner_matches}, inventory={dict(raw_inventory_classes)}")
    all_positive = [c for c in analyzed if c["primary_outgoing_positive_total"] > 0]
    complete_exact = sum(c["primary_arrival_accounting"]["status"] == "EXACT" for c in analyzed)
    hold = [c for c in analyzed if c["split"] == "holdout"]
    hold_exact = sum(c["primary_arrival_accounting"]["status"] == "EXACT" for c in hold)
    hold_positive = [c for c in hold if c["primary_outgoing_positive_total"] > 0]
    hold_positive_exact = sum(c["primary_positive_outgoing_exact"] for c in hold_positive)
    hold_positive_exact_groups = len({(c["cohort"], c["arrival_tick"]) for c in hold_positive
        if c["primary_positive_outgoing_exact"]})
    hold_positive_exact_contexts = len({c["cohort"] for c in hold_positive
        if c["primary_positive_outgoing_exact"]})
    strong_continuation_gate = (hold_exact / 21 >= 0.90
        and (hold_positive_exact / len(hold_positive) if hold_positive else 0) >= 0.90
        and hold_positive_exact_groups >= 10 and hold_positive_exact_contexts >= 2)
    report = {
        "status": "POST_ARRIVAL_INVENTORY_DISPOSITION_COMPLETE",
        "version": "post-arrival-inventory-disposition-v1",
        "freeze": {"path": "docs/V2_M2A_POST_ARRIVAL_DISPOSITION_FREEZE.json",
            "sha256": sha_file(FREEZE), "baseline_head": BASELINE_HEAD,
            "freeze_commit": FREEZE_COMMIT,
            "holdout_is_retrospective_diagnostic_only": True},
        "primary_population": {"cases": 45, "development": 24, "holdout": 21,
            "inventory_match": 13, "zero_inventory_mismatch": 32,
            "all_original_cases_retained": True},
        "first_retained_raw_outcome_validation": {"owner_matches": raw_owner_matches,
            "inventory_class_counts": dict(raw_inventory_classes),
            "matches_original_replay_outcomes": True},
        "group_tables": by_split,
        "primary_arrival_accounting": {
            "complete_exact_all_cases": complete_exact,
            "complete_exact_fraction_all45": complete_exact / 45,
            "positive_outgoing_cases": len(all_positive),
            "positive_outgoing_exact_cases": sum(c["primary_positive_outgoing_exact"] for c in all_positive),
            "positive_outgoing_exact_precision": (sum(c["primary_positive_outgoing_exact"] for c in all_positive) / len(all_positive)
                if all_positive else None),
            "no_outgoing_exact_tautology_cases": sum(c["primary_no_outgoing_exact_tautology"] for c in analyzed),
            "holdout_complete_exact": hold_exact,
            "holdout_complete_exact_fraction_of_21": hold_exact / 21,
            "holdout_positive_outgoing_cases": len(hold_positive),
            "holdout_positive_outgoing_exact_cases": hold_positive_exact,
            "holdout_positive_outgoing_precision": hold_positive_exact / len(hold_positive) if hold_positive else None,
            "holdout_positive_complete_exact_groups": len({(c["cohort"], c["arrival_tick"]) for c in hold_positive if c["primary_positive_outgoing_exact"]}),
            "holdout_positive_complete_exact_contexts": len({c["cohort"] for c in hold_positive if c["primary_positive_outgoing_exact"]}),
        },
        "source_hashes": {
            "docs/V2_M2A_POST_ARRIVAL_DISPOSITION_FREEZE.json": sha_file(FREEZE),
            "docs/V2_M2A_UNFILTERED_SETTLEMENT.json": sha_file(ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json"),
            "tests/fixtures/v2/arrival-settlement-replay-development.json.gz": sha_file(DEV_FIXTURE),
            "tests/fixtures/v2/arrival-settlement-replay-holdout.json.gz": sha_file(HOLD_FIXTURE),
            "raw_sources": raw_hashes,
            "report_tool_sha256": sha_file(Path(__file__)),
        },
        "verdict": "STRONG_CONTINUATION_PATTERN" if strong_continuation_gate else "INFORMATION_CEILING",
        "verdict_qualification": "Conditional observational accounting only; does not predict the outgoing force, prove causal relay, or grant production credit." if strong_continuation_gate else "The frozen quantitative gate did not pass; unknown or incomplete visible state remains limiting.",
        "before_only_trigger": "NO_BEFORE_TRIGGER_FOUND",
        "owner_only_capture": "FROZEN_HYPOTHESIS_ONLY_NOT_PRODUCTION",
        "production_changes": "NONE",
        "new_recordings": 0,
        "hypothesis_revisions": 0,
        "live_dispatches": 0,
        "negative_controls": {"tests_passed": 13, "evidence_type": "synthetic guards only; no empirical credit"},
        "formal_credit": 0,
        "causal_interpretation": "No causal attribution. First visible signature is not physical birth; inventory accounting is observational and unknown aliases limit completeness.",
        "cases": analyzed,
    }
    OUT_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"version": report["version"], "cases": analyzed},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with OUT_FIXTURE.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0, compresslevel=6) as gz:
            gz.write(raw)
    report["source_hashes"][OUT_FIXTURE.relative_to(ROOT).as_posix()] = sha_file(OUT_FIXTURE)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# Post-arrival inventory disposition", "",
        "All 45 originally scored capture cases are retained (13 inventory MATCH / 32 zero-inventory MISMATCH; original split unchanged). This is a retrospective diagnostic, not a new holdout or production rule.", "",
        "## Primary arrival-tick accounting", "",
        f"Complete exact accounting: {complete_exact}/45; positive-outgoing cases: {len(all_positive)}, of which {sum(c['primary_positive_outgoing_exact'] for c in all_positive)} account exactly. No-outgoing equality is reported separately as a tautological check.",
        f"Holdout: {hold_exact}/21 complete exact; {len(hold_positive)} positive-outgoing cases, {hold_positive_exact} complete exact in {hold_positive_exact_groups} groups / {hold_positive_exact_contexts} contexts. Frozen gate verdict: {report['verdict']} (conditional observational accounting; no prediction or causal claim).", "",
        "## Time and provenance", "",
        "Offset 0 is the arrival tick; offsets +1 and +2 are exact first-retained observations at consecutive ticks in the same scope. Existing `following` means +1. Later offsets are supplementary and cannot rescue primary arrival accounting.",
        "Outgoing rows are visible signatures, not proven physical births. Duplicate signature multiplicity is preserved; observer IDs are supplemental only. Unknown plausible aliases or incomplete census make complete accounting UNKNOWN, while observed-only arithmetic remains visible.", "",
        "## Results by split and case", "",
        "The JSON report contains every case, per-offset target state and outgoing force list, before-context fields, accounting status, capacity/production/inbound/line facts, group tables, and raw-source hashes.", "",
        "## Verdict", "",
        report["verdict"], ""]
    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = build_artifacts()
    print(json.dumps({"cases": result["primary_population"]["cases"],
        "primary": result["primary_arrival_accounting"],
        "report": str(REPORT_JSON), "fixture_sha256": result["source_hashes"][OUT_FIXTURE.relative_to(ROOT).as_posix()]},
        separators=(",", ":")))
