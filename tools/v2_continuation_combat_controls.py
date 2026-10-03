"""Outcome-free selection and passive scoring of preregistered continuation controls.

Selection is deliberately separable from scoring: ``select`` writes and freezes
the A/B identities without importing or invoking the continuation detector.
``score`` consumes that frozen plan and the sibling replay's shared detector.
This is retrospective diagnostics only; it does not change production or credit.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_PREREG.json"
DENOMINATOR = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
EDGE_AUDIT = ROOT / "tests/fixtures/v2/arrival-factor-edge-audit.jsonl.gz"
DEV_FIXTURE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-development.json.gz"
HOLDOUT_FIXTURE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-holdout.json.gz"
SELECTION = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_CONTROL_SELECTION.json"
CONTROLS_FIXTURE = ROOT / "tests/fixtures/v2/continuation-combat-controls.json.gz"
CONTROLS_REPORT = ROOT / "docs/V2_M2A_CONTINUATION_COMBAT_CONTROLS.json"
NONCOMBAT_BRANCHES = {"EMPTY_NEUTRAL_CAPTURE", "SAME_OWNER_REINFORCEMENT"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rank_key(salt: str, group: str, cohort: str, before_sequence: int,
             target_id: int) -> str:
    raw = f"{salt}|{group}|{cohort}|{before_sequence}|{target_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def fact(row: dict[str, Any], name: str) -> Any:
    item = row.get(name)
    if isinstance(item, dict) and "value" in item:
        if item.get("knowledge") not in ("OBSERVED", "DERIVED"):
            return None
        return item.get("value")
    return item


def typed_units(row: dict[str, Any]) -> list[int] | None:
    value = fact(row, "units")
    if isinstance(value, dict):
        value = value.get("counts")
        if isinstance(value, list):
            try:
                pairs = {int(unit): int(count) for unit, count in value}
                value = [pairs.get(i) for i in range(10)]
            except (TypeError, ValueError):
                return None
    if (not isinstance(value, (list, tuple)) or len(value) != 10 or
            any(type(n) is not int or n < 0 for n in value)):
        return None
    return list(value)


def is_ordinary_tower(row: dict[str, Any], *, owner: int | None = None,
                      positive: bool = True) -> bool:
    if fact(row, "visibility") is not True:
        return False
    row_owner = fact(row, "owner")
    units = typed_units(row)
    tower_type = fact(row, "tower_type")
    if type(row_owner) is not int or row_owner <= 0 or (owner is not None and row_owner != owner):
        return False
    if type(tower_type) is not int or units is None:
        return False
    if any(units[6:]) or (positive and not any(units)):
        return False
    return True


def visible_rows(snapshot: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    value = snapshot.get(collection)
    if isinstance(value, dict):
        value = fact(snapshot, collection)
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def certify_no_due_inbound(snapshot: dict[str, Any], target_id: int) -> tuple[bool, str]:
    """Fail closed unless the complete before census has known routes away from target.

    A force addressed to the target is conservatively treated as possibly due;
    any unresolved destination is UNKNOWN. A known different destination
    excludes an arrival to this tower on the sampled current-leg edge.
    """
    if snapshot.get("provenance", {}).get("coverage") != "PLAYER_VISIBLE_COMPLETE":
        return False, "INCOMPLETE_VISIBLE_CENSUS"
    for collection in ("towers", "forces"):
        for index, row in enumerate(visible_rows(snapshot, collection)):
            if fact(row, "visibility") is not True:
                return False, f"{collection.upper()}_{index}_VISIBILITY_UNKNOWN"
    forces = visible_rows(snapshot, "forces")
    for index, force in enumerate(forces):
        if fact(force, "visibility") is not True:
            continue
        destination = fact(force, "destination")
        if type(destination) is not int:
            return False, f"FORCE_{index}_DESTINATION_UNKNOWN"
        if destination == target_id:
            return False, f"FORCE_{index}_MAY_ARRIVE_TARGET"
    return True, "COMPLETE_BEFORE_FORCE_ROUTES_EXCLUDE_TARGET"


def known_edge_identity(before_raw: dict[str, Any], after_raw: dict[str, Any]) -> tuple[bool, int | None]:
    """Require explicit, complete scope and consecutive known ticks."""
    def known_scope(raw: dict[str, Any]) -> tuple[Any, ...] | None:
        values = (raw.get("document_id"), fact(raw, "match_id"),
                  fact(raw, "player_id"), fact(raw, "document_time_origin_ms"))
        if (not isinstance(values[0], str) or not values[0] or
                not isinstance(values[1], str) or not values[1] or
                type(values[2]) is not int or type(values[3]) not in (int, float)):
            return None
        return values
    scope_before, scope_after = known_scope(before_raw), known_scope(after_raw)
    tick_before, tick_after = fact(before_raw, "tick"), fact(after_raw, "tick")
    if (scope_before is None or scope_after is None or scope_before != scope_after or
            type(tick_before) is not int or type(tick_after) is not int or
            (tick_after - tick_before) % 65536 != 1):
        return False, None
    return True, tick_before


def _build_a_pool(salt: str, denominator: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, str]]:
    """Stream audit-referenced edge pairs and retain only eligible candidate metadata."""
    edges_by_cohort: dict[str, list[dict[str, Any]]] = {}
    with gzip.open(EDGE_AUDIT, "rt", encoding="utf-8") as f:
        for line in f:
            edge = json.loads(line)
            lines = edge.get("lines")
            if isinstance(lines, list) and len(lines) == 2 and all(type(x) is int for x in lines):
                edges_by_cohort.setdefault(edge["cohort"], []).append(edge)
    files = {metadata["cohort"]: (ROOT / Path(rel.replace("\\", "/")), metadata["expected_sha256"])
             for rel, metadata in denominator["inputs"]["raw_files"].items()}
    path_by_cohort = {cohort: path.relative_to(ROOT).as_posix() for cohort, (path, _) in files.items()}
    a_pool: dict[str, dict[str, Any]] = {}
    rejects: dict[str, int] = {}
    hashes: dict[str, str] = {EDGE_AUDIT.relative_to(ROOT).as_posix(): sha256(EDGE_AUDIT)}

    for cohort, edges in edges_by_cohort.items():
        if cohort not in files:
            continue
        path, expected = files[cohort]
        line_to_edges: dict[int, list[int]] = {}
        remaining: dict[int, int] = {}
        for index, edge in enumerate(edges):
            before_line, after_line = edge["lines"]
            line_to_edges.setdefault(before_line, []).append(index)
            line_to_edges.setdefault(after_line, []).append(index)
            remaining[before_line] = remaining.get(before_line, 0) + 1
            remaining[after_line] = remaining.get(after_line, 0) + 1
        cache: dict[int, dict[str, Any]] = {}
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for line_no, raw_line in enumerate(stream, 1):
                h.update(raw_line)
                for edge_index in line_to_edges.get(line_no, ()):
                    if line_no not in cache:
                        cache[line_no] = json.loads(raw_line)
                    edge = edges[edge_index]
                    before_line, after_line = edge["lines"]
                    if before_line not in cache or after_line not in cache:
                        continue
                    before_raw, after_raw = cache[before_line], cache[after_line]
                    valid_edge, tick_before = known_edge_identity(before_raw, after_raw)
                    if not valid_edge:
                        rejects["NONCONSECUTIVE_OR_SCOPE_GAP"] = rejects.get("NONCONSECUTIVE_OR_SCOPE_GAP", 0) + 1
                    else:
                        before = _context(before_raw, cohort, before_line, path_by_cohort[cohort], expected)
                        if before["provenance"].get("coverage") != "PLAYER_VISIBLE_COMPLETE":
                            rejects["INCOMPLETE_VISIBLE_CENSUS"] = rejects.get("INCOMPLETE_VISIBLE_CENSUS", 0) + 1
                        else:
                            seen_target_ids: set[int] = set()
                            for tower in visible_rows(before, "towers"):
                                ident = tower.get("id")
                                if type(ident) is not int or ident in seen_target_ids:
                                    continue
                                seen_target_ids.add(ident)
                                if not is_ordinary_tower(tower):
                                    continue
                                no_due, reason = certify_no_due_inbound(before, ident)
                                if not no_due:
                                    rejects[reason] = rejects.get(reason, 0) + 1
                                    continue
                                sequence = before["provenance"].get("sequence")
                                if type(sequence) is not int:
                                    rejects["BEFORE_SEQUENCE_UNKNOWN"] = rejects.get("BEFORE_SEQUENCE_UNKNOWN", 0) + 1
                                    continue
                                scope = tuple(before["provenance"].get("scope", []))
                                key = json.dumps([scope, tick_before, ident], separators=(",", ":"))
                                candidate = {
                                    "cohort": cohort, "split": edge.get("split"), "target_id": ident,
                                    "before_sequence": sequence, "before_tick": tick_before,
                                    "arrival_sequence": after_raw.get("sequence"),
                                    "arrival_tick": fact(after_raw, "tick"),
                                    "before_line": before_line, "arrival_line": after_line,
                                    "source_path": path_by_cohort[cohort], "source_sha256": expected,
                                    "audit_edge_index": edge.get("edge_index"),
                                    "coverage": before["provenance"].get("coverage"),
                                    "no_due_inbound_basis": reason,
                                    "rank": rank_key(salt, "A", cohort, sequence, ident),
                                }
                                old = a_pool.get(key)
                                if old is None or candidate["rank"] < old["rank"]:
                                    a_pool[key] = candidate
                    remaining[before_line] -= 1
                    remaining[after_line] -= 1
                    for old_line in (before_line, after_line):
                        if remaining.get(old_line, 0) <= 0:
                            cache.pop(old_line, None)
        actual = h.hexdigest()
        if actual != expected:
            raise RuntimeError(f"raw hash mismatch for {cohort}: {actual} != {expected}")
        hashes[path.relative_to(ROOT).as_posix()] = actual
    return a_pool, rejects, hashes


def _context(raw: dict[str, Any], cohort: str, line_no: int,
             source_path: str, source_hash: str) -> dict[str, Any]:
    # Reuse the established raw-to-visible projection, not the result scorer.
    from tools.v2_arrival_settlement_replay import full_context, raw_tick, raw_scope
    context = full_context(raw)
    # The standard projection intentionally includes only visible entities. For
    # this control, an unknown collection/visibility must also downgrade census
    # completeness so it cannot be mistaken for an empty visible set.
    raw_forces = raw.get("forces")
    if isinstance(raw_forces, dict):
        if raw_forces.get("knowledge") not in ("OBSERVED", "DERIVED"):
            context["provenance"]["coverage"] = "PLAYER_VISIBLE_INCOMPLETE"
        raw_forces = raw_forces.get("value")
    for collection in ("towers", "forces"):
        rows = raw.get(collection)
        if collection == "forces" and isinstance(rows, dict):
            rows = rows.get("value")
        if isinstance(rows, list) and any(
                not isinstance(item.get("visibility"), dict) or
                item["visibility"].get("knowledge") not in ("OBSERVED", "DERIVED") or
                type(item["visibility"].get("value")) is not bool
                for item in rows if isinstance(item, dict)):
            context["provenance"]["coverage"] = "PLAYER_VISIBLE_INCOMPLETE"
    context["provenance"].update({"source_path": source_path,
                                  "source_sha256": source_hash,
                                  "line": line_no,
                                  "sequence": raw.get("sequence"),
                                  "tick": raw_tick(raw),
                                  "scope": list(raw_scope(raw))})
    return context


def _load_b_pool() -> tuple[list[dict[str, Any]], dict[str, str]]:
    cases: list[dict[str, Any]] = []
    hashes = {}
    for path in (DEV_FIXTURE, HOLDOUT_FIXTURE):
        hashes[path.relative_to(ROOT).as_posix()] = sha256(path)
        payload = json.loads(gzip.decompress(path.read_bytes()))
        for case in payload.get("cases", []):
            if (case.get("boundary", {}).get("status") != "SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN" or
                    case.get("branch_candidate") not in NONCOMBAT_BRANCHES):
                continue
            before = case.get("snapshots", {}).get("before", {})
            arrival = case.get("snapshots", {}).get("arrival", {})
            bp = before.get("provenance", {})
            ap = arrival.get("provenance", {})
            if (not before or not arrival or bp.get("scope") != ap.get("scope") or
                    (ap.get("tick") - bp.get("tick", -1)) % 65536 != 1):
                continue
            # Retain source frames in memory for decoy choice and subsequent scoring.
            case["_control_before"] = before
            case["_control_after"] = arrival
            cases.append(case)
    return cases, hashes


def _choose_decoy(case: dict[str, Any]) -> tuple[int | None, str]:
    before = case["_control_before"]
    target_id = case.get("target_id")
    incoming = case.get("incoming_signature")
    incoming_owner = incoming[0] if isinstance(incoming, list) and len(incoming) == 4 else None
    if type(incoming_owner) is not int or incoming_owner <= 0:
        return None, "UNKNOWN_INCOMING_OWNER"
    towers = {r.get("id"): r for r in visible_rows(before, "towers") if type(r.get("id")) is int}
    target = towers.get(target_id)
    if target is None:
        return None, "TARGET_NOT_VISIBLE_BEFORE"
    neighbors = fact(target, "neighbors")
    neighbor_ids = [n for n in neighbors if type(n) is int] if isinstance(neighbors, list) else []
    neighbor_ids.sort(key=lambda ident: (rank_key(json.loads(PREREG.read_text(encoding="utf-8"))["controls"]["seed_salt"], "B-DECOY", case["cohort"], before["provenance"]["sequence"], ident), ident))
    ranked = []
    for ident, tower in towers.items():
        if ident == target_id or not is_ordinary_tower(tower, owner=incoming_owner):
            continue
        clear, _ = certify_no_due_inbound(before, ident)
        if clear:
            method = "OBSERVED_NEIGHBOR" if ident in neighbor_ids else "OTHER_VISIBLE"
            # Neighbor preference is primary, then preregistered salted ordering.
            ranked.append((0 if method == "OBSERVED_NEIGHBOR" else 1,
                           rank_key(json.loads(PREREG.read_text(encoding="utf-8"))["controls"]["seed_salt"], "B-DECOY", case["cohort"], before["provenance"]["sequence"], ident), ident, method))
    if not ranked:
        return None, "NO_CERTIFIED_SAME_OWNER_DECOY"
    _, _, ident, method = min(ranked)
    return ident, method


def build_selection_plan(path: Path = SELECTION) -> dict[str, Any]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    salt = prereg["controls"]["seed_salt"]
    denominator = json.loads(DENOMINATOR.read_text(encoding="utf-8"))
    a_pool, a_rejects, raw_hashes = _build_a_pool(salt, denominator)

    a_selected = sorted(a_pool.values(), key=lambda x: (x["rank"], x["cohort"], x["before_sequence"], x["target_id"]))[:100]
    b_cases, b_hashes = _load_b_pool()
    b_hashes.update(raw_hashes)
    b_ranked = []
    b_no_decoy = 0
    for case in b_cases:
        before = case["_control_before"]
        sequence = before.get("provenance", {}).get("sequence")
        target_id = case.get("target_id")
        if type(sequence) is not int or type(target_id) is not int:
            continue
        decoy_id, method = _choose_decoy(case)
        if decoy_id is None:
            b_no_decoy += 1
        b_ranked.append({
            "case_id": case["case_id"], "cohort": case["cohort"], "split": case["split"],
            "branch_candidate": case["branch_candidate"], "before_sequence": sequence,
            "before_tick": before.get("provenance", {}).get("tick"),
            "target_id": target_id, "decoy_target_id": decoy_id,
            "decoy_method": method,
            "source_path": before.get("provenance", {}).get("source_path"),
            "source_sha256": before.get("provenance", {}).get("source_sha256"),
            "rank": rank_key(salt, "B", case["cohort"], sequence, target_id),
        })
    b_selected = sorted(b_ranked, key=lambda x: (x["rank"], x["case_id"]))[:50]
    source_manifest = {
        PREREG.relative_to(ROOT).as_posix(): sha256(PREREG),
        DENOMINATOR.relative_to(ROOT).as_posix(): sha256(DENOMINATOR),
        **raw_hashes, **b_hashes,
    }
    plan = {
        "version": "continuation-combat-control-selection-v1",
        "selection_status": "FROZEN_BEFORE_DETECTOR_SCORING",
        "prereg_path": PREREG.relative_to(ROOT).as_posix(),
        "prereg_sha256": sha256(PREREG),
        "seed_salt": salt,
        "rank_rule": "SHA256(seed_salt|group|cohort|before_sequence|target_id), ascending; no detector or outcome fields used",
        "A": {"target_N": 100, "candidate_pool": len(a_pool), "selected_N": len(a_selected),
              "eligible_nonarrival_controls": a_selected, "exclusion_counts": a_rejects},
        "B": {"target_N": 50, "candidate_pool": len(b_ranked), "supported_noncombat_population_expected": 264,
              "selected_N": len(b_selected), "unavailable_decoy_count_in_full_pool": b_no_decoy,
              "selected_cases": b_selected},
        "source_manifest_sha256": source_manifest,
        "selection_scope": "Retrospective old corpus; candidate selection uses before-only tower/force fields and pinned edge identity. This plan freezes sample identities before importing or calling the outgoing detector.",
    }
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return plan


def _snapshot_from_raw(cohort: str, line_no: int, path: str,
                       source_hash: str) -> dict[str, Any]:
    rel = path.replace("/", "\\")
    raw_path = ROOT / Path(path)
    with raw_path.open("rb") as stream:
        for index, line in enumerate(stream, 1):
            if index == line_no:
                raw = json.loads(line)
                return _context(raw, cohort, line_no, path, source_hash)
    raise RuntimeError(f"missing raw line {path}:{line_no}")


def _score_a_controls(selected_rows: list[dict[str, Any]], detect_outgoing: Any) -> list[dict[str, Any]]:
    """Score selected A rows in one streaming pass per pinned raw source."""
    grouped: dict[str, dict[tuple[int, int], list[dict[str, Any]]]] = {}
    for selected in selected_rows:
        pair = (selected["before_line"], selected["arrival_line"])
        grouped.setdefault(selected["cohort"], {}).setdefault(pair, []).append(selected)
    result: list[dict[str, Any]] = []
    for cohort, pairs in grouped.items():
        path = ROOT / Path(next(iter(pairs.values()))[0]["source_path"])
        expected = next(iter(pairs.values()))[0]["source_sha256"]
        by_line: dict[int, list[tuple[int, int]]] = {}
        ref_count: dict[int, int] = {}
        for pair in pairs:
            for line_no in set(pair):
                by_line.setdefault(line_no, []).append(pair)
                ref_count[line_no] = ref_count.get(line_no, 0) + 1
        cached: dict[int, dict[str, Any]] = {}
        completed: set[tuple[int, int]] = set()
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for line_no, raw_line in enumerate(stream, 1):
                h.update(raw_line)
                if line_no not in by_line:
                    continue
                cached[line_no] = json.loads(raw_line)
                for pair in by_line[line_no]:
                    if pair in completed or pair[0] not in cached or pair[1] not in cached:
                        continue
                    before = _context(cached[pair[0]], cohort, pair[0], path.relative_to(ROOT).as_posix(), expected)
                    after = _context(cached[pair[1]], cohort, pair[1], path.relative_to(ROOT).as_posix(), expected)
                    for selected in pairs[pair]:
                        target_after = [r for r in visible_rows(after, "towers") if r.get("id") == selected["target_id"]]
                        post_owner = fact(target_after[0], "owner") if len(target_after) == 1 else None
                        detection = detect_outgoing(before, after, selected["target_id"], post_owner, offset=0)
                        result.append({**selected, "outgoing_status": detection.get("status", "UNKNOWN"),
                                       "detection": detection})
                    completed.add(pair)
                    for old_line in set(pair):
                        ref_count[old_line] -= 1
                        if ref_count[old_line] <= 0:
                            cached.pop(old_line, None)
        actual = h.hexdigest()
        if actual != expected:
            raise RuntimeError(f"A scoring raw source changed during pass: {cohort}")
        if len(completed) != len(pairs):
            raise RuntimeError(f"selected A pair missing from raw source: {cohort}")
    return result


def run_controls(selection_path: Path = SELECTION) -> dict[str, Any]:
    """Score only frozen controls through the shared combat detector API."""
    from tools.v2_continuation_combat_replay import detect_outgoing
    detector_path = ROOT / "tools/v2_continuation_combat_replay.py"
    detector_hash = sha256(detector_path)
    plan = json.loads(selection_path.read_text(encoding="utf-8"))
    if plan.get("selection_status") != "FROZEN_BEFORE_DETECTOR_SCORING":
        raise RuntimeError("selection plan is not frozen")
    for rel, expected in plan.get("source_manifest_sha256", {}).items():
        actual = sha256(ROOT / rel)
        if actual != expected:
            raise RuntimeError(f"frozen selection source changed before scoring: {rel}")
    a_cases = _score_a_controls(plan["A"]["eligible_nonarrival_controls"], detect_outgoing)

    b_pool, _ = _load_b_pool()
    by_id = {case["case_id"]: case for case in b_pool}
    b_cases = []
    for selected in plan["B"]["selected_cases"]:
        case = by_id.get(selected["case_id"])
        if case is None:
            raise RuntimeError(f"selected B case missing from pinned pool: {selected['case_id']}")
        before, after = case["_control_before"], case["_control_after"]
        target_rows = [r for r in visible_rows(after, "towers") if r.get("id") == selected["target_id"]]
        post_owner = fact(target_rows[0], "owner") if len(target_rows) == 1 else None
        actual = detect_outgoing(before, after, selected["target_id"], post_owner, offset=0)
        decoy_id = selected.get("decoy_target_id")
        decoy = None
        if type(decoy_id) is int:
            decoy_rows = [r for r in visible_rows(after, "towers") if r.get("id") == decoy_id]
            decoy_owner = fact(decoy_rows[0], "owner") if len(decoy_rows) == 1 else None
            decoy = detect_outgoing(before, after, decoy_id, decoy_owner, offset=0)
        b_cases.append({**selected,
                        "actual_target_outgoing_status": actual.get("status", "UNKNOWN"),
                        "decoy_outgoing_status": decoy.get("status", "UNKNOWN") if decoy else "UNKNOWN",
                        "actual_target_detection": actual, "decoy_detection": decoy})
    a_statuses = [r["outgoing_status"] for r in a_cases]
    b_decoys = [r for r in b_cases if r["decoy_detection"] is not None]
    b_missing_decoy = sum(r["decoy_detection"] is None for r in b_cases)
    yes_a = sum(x == "YES" for x in a_statuses)
    unk_a = sum(x == "UNKNOWN" for x in a_statuses)
    yes_b = sum(r["decoy_outgoing_status"] == "YES" for r in b_decoys)
    unk_b = sum(r["decoy_outgoing_status"] == "UNKNOWN" for r in b_decoys)
    a_upper = (yes_a + unk_a) / len(a_cases) if a_cases else None
    b_upper = (yes_b + unk_b) / len(b_decoys) if b_decoys else None
    report = {
        "version": "continuation-combat-controls-v1",
        "status": "RETROSPECTIVE_CONTROL_DIAGNOSTIC_ONLY",
        "production_credit": 0,
        "qualification_credit": 0,
        "selection_plan_sha256": sha256(selection_path),
        "A": {"selected": len(a_cases), "known_positive": yes_a, "unknown": unk_a,
              "eligible_N": len(a_cases), "YES": yes_a,
              "NO": sum(x == "NO" for x in a_statuses), "UNKNOWN": unk_a,
              "conservative_yes_plus_unknown_upper_rate": a_upper,
              "known_positive_rate": yes_a / len(a_cases) if a_cases else None,
              "gate_pass": bool(len(a_cases) >= 90 and a_upper is not None and a_upper <= .10 and
                                 (yes_a / len(a_cases) if a_cases else 1) <= .10),
              "cases": a_cases},
        "B": {"selected_N": len(b_cases), "actual_target": {
                  "YES": sum(r["actual_target_outgoing_status"] == "YES" for r in b_cases),
                  "NO": sum(r["actual_target_outgoing_status"] == "NO" for r in b_cases),
                  "UNKNOWN": sum(r["actual_target_outgoing_status"] == "UNKNOWN" for r in b_cases)},
              "available_decoys": len(b_decoys), "known_positive_pairs": yes_b,
              "unknown_pairs": unk_b, "selected_cases_without_decoy": b_missing_decoy,
              "decoy_available_N": len(b_decoys), "decoy": {
                  "YES": yes_b, "NO": sum(r["decoy_outgoing_status"] == "NO" for r in b_decoys),
                  "UNKNOWN": unk_b, "conservative_yes_plus_unknown_upper_rate": b_upper,
                  "known_positive_rate": yes_b / len(b_decoys) if b_decoys else None,
                  "gate_pass": bool(len(b_decoys) >= 20 and b_upper is not None and b_upper <= .10 and
                                     (yes_b / len(b_decoys) if b_decoys else 1) <= .10)},
              "cases": b_cases},
        "overall_controls_pass": bool(len(a_cases) >= 90 and a_upper is not None and a_upper <= .10 and
            (yes_a / len(a_cases) if a_cases else 1) <= .10 and len(b_decoys) >= 20 and
            b_upper is not None and b_upper <= .10 and
            (yes_b / len(b_decoys) if b_decoys else 1) <= .10),
        "source_manifest_sha256": {**{path: sha256(ROOT / path) for path in plan["source_manifest_sha256"]},
            "tools/v2_continuation_combat_controls.py": sha256(Path(__file__)),
            "tools/v2_continuation_combat_replay.py": sha256(ROOT / "tools/v2_continuation_combat_replay.py")},
    }
    if sha256(detector_path) != detector_hash:
        raise RuntimeError("shared detector source changed during control scoring")
    report["shared_detector_source_sha256"] = detector_hash
    CONTROLS_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    CONTROLS_FIXTURE.write_bytes(gzip.compress(json.dumps({"A": a_cases, "B": b_cases},
        ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    CONTROLS_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("select", "score"))
    args = parser.parse_args()
    if args.command == "select":
        print(json.dumps(build_selection_plan(), ensure_ascii=False))
    else:
        print(json.dumps(run_controls(), ensure_ascii=False))


if __name__ == "__main__":
    main()
