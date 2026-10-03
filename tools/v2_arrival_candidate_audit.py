"""Read-only candidate inventory for ordinary arrivals in pinned snapshots.

This emits observational candidates only. It does not invoke the simulator or
promote a candidate to formal event evidence.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COHORTS = ("03d032d57e5b", "7d56a775bc4c", "85391858b5d8",
           "b1f7f9416e92", "daf86d0544b7", "fe678ebb30ce")
OUT = ROOT / "runtime/research/v2/arrival-candidate-audit.json"
VERSION = "arrival-candidate-audit-v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fact(row, key):
    f = row.get(key)
    if not isinstance(f, dict) or f.get("knowledge") not in ("OBSERVED", "DERIVED"):
        return None
    return f.get("value")


def vector(row, key):
    v = fact(row, key)
    if not isinstance(v, dict) or not isinstance(v.get("counts"), list):
        return None
    out = {}
    for pair in v["counts"]:
        if (not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                or type(pair[1]) is not int or pair[0] in out or not 0 <= pair[0] < 10
                or not 0 <= pair[1] <= 255):
            return None
        out[pair[0]] = pair[1]
    if set(out) != set(range(10)):
        return None
    return tuple(out[i] for i in range(10))


def indexed(rows, keep_ids=None, id_key="id"):
    result = {}
    for r in rows:
        ident = r.get(id_key) if type(r.get(id_key)) is int else None
        if ident is not None and (keep_ids is None or ident in keep_ids) and fact(r, "visibility") is True:
            result[ident] = r
    return result


def observation(raw):
    t = fact(raw, "tick")
    fs, ts = raw.get("forces"), raw.get("towers")
    if (type(t) is not int or not isinstance(fs, dict) or fs.get("knowledge") != "OBSERVED"
            or not isinstance(fs.get("value"), list) or not isinstance(ts, list)
            or not isinstance(raw.get("document_id"), str)
            or not isinstance(fact(raw, "match_id"), str)
            or type(fact(raw, "player_id")) is not int):
        return None
    # This recorder pins completeness as a top-level enum string.
    coverage = raw.get("coverage")
    complete = coverage == "PLAYER_VISIBLE_COMPLETE"
    cv = fact(raw, "coverage")
    if isinstance(cv, dict):
        complete = (cv.get("forces") == "PLAYER_VISIBLE_COMPLETE" or
                    cv.get("force_set") == "PLAYER_VISIBLE_COMPLETE")
    if not complete:
        return None
    forces = fs["value"]
    endpoint_ids = {fact(f, k) for f in forces if isinstance(f, dict)
                    for k in ("source", "destination") if type(fact(f, k)) is int}
    return {"tick": t, "forces": forces, "towers": indexed(ts, endpoint_ids),
            "scope": (raw["document_id"], fact(raw, "match_id"), fact(raw, "player_id")),
            "sequence": raw.get("sequence")}


def current_identity(r):
    owner, source, target, units = (fact(r, "owner"), fact(r, "source"),
                                    fact(r, "destination"), vector(r, "units"))
    if type(owner) is not int or type(source) is not int or type(target) is not int or units is None:
        return None
    return (owner, source, target, units)


def pair_candidates(cohort, before, after, following):
    b_forces = [f for f in before["forces"] if fact(f, "visibility") is True]
    a_forces = [f for f in after["forces"] if fact(f, "visibility") is True]
    next_forces = [f for f in following["forces"] if fact(f, "visibility") is True]
    b_towers, a_towers, n_towers = before["towers"], after["towers"], following["towers"]
    signatures = collections.Counter(current_identity(f) for f in b_forces)
    after_signatures = collections.Counter(current_identity(f) for f in a_forces)
    # A destination with any other inbound force in the same before snapshot is ambiguous.
    inbound_count = collections.Counter(fact(f, "destination") for f in b_forces
        if type(fact(f, "destination")) is int)
    candidates = []
    for f in b_forces:
        sig = current_identity(f)
        if sig is None or signatures[sig] != 1 or after_signatures[sig] != 0:
            continue
        owner, source, dest, units = sig
        if source not in b_towers or dest not in b_towers or dest not in a_towers or dest not in n_towers:
            continue
        if inbound_count[dest] != 1:
            continue
        old, updated, next_state = b_towers[dest], a_towers[dest], n_towers[dest]
        old_owner, old_units = fact(old, "owner"), vector(old, "units")
        new_owner, new_units = fact(updated, "owner"), vector(updated, "units")
        next_owner, next_units = fact(next_state, "owner"), vector(next_state, "units")
        if old_units is None or new_units is None or next_units is None or type(new_owner) is not int:
            continue
        if old_owner == 0 and not any(old_units):
            kind = "NEUTRAL_CAPTURE_BOUNDARY_CANDIDATE"
            expected_owner = owner
        elif type(old_owner) is int and old_owner == owner and owner != 0:
            kind = ("SELF_REINFORCEMENT_CANDIDATE" if owner == before["scope"][2]
                    else "NONSELF_SAME_OWNER_REINFORCEMENT_CANDIDATE")
            expected_owner = owner
        else:
            continue
        if new_owner != expected_owner or new_units == old_units:
            continue
        raw_id = fact(f, "id")
        after_ids = {fact(x, "id") for x in a_forces if fact(x, "id") is not None}
        exact_arrival_delta = all(old_units[i] + units[i] == new_units[i] for i in range(10))
        candidates.append({
            "kind": kind, "cohort": cohort, "document_id": before["scope"][0],
            "match_id": before["scope"][1], "player_id": before["scope"][2],
            "before_sequence": before["sequence"], "arrival_observation_sequence": after["sequence"],
            "next_observation_sequence": following["sequence"],
            "before_tick": before["tick"], "arrival_observation_tick": after["tick"],
            "next_observation_tick": following["tick"], "source_tower": source,
            "target_tower": dest, "force_owner": owner, "target_owner_before": old_owner,
            "target_owner_after": new_owner, "target_owner_next_tick": next_owner,
            "force_units": list(units), "target_units_before": list(old_units),
            "target_units_after": list(new_units), "target_units_next_tick": list(next_units),
            "target_delta_equals_force_vector_without_overflow": exact_arrival_delta,
            "target_delta_by_unit": [new_units[i] - old_units[i] for i in range(10)],
            "force_observer_id_before_only_supplemental": raw_id,
            "force_id_absent_after": raw_id not in after_ids if raw_id is not None else None,
            "arrival_is_not_proven_by_id_alone": True,
            "before_force_signature_unique": True, "no_other_visible_inbound_force_before": True,
            "force_absent_by_visible_owner_route_vector_signature_after": True,
            "arrival_tick_window": [before["tick"] + 1, after["tick"]],
            "tick_step_exact": (after["tick"] - before["tick"]) % 65536 == 1
                and (following["tick"] - after["tick"]) % 65536 == 1,
            "target_state_change_at_arrival_observation": True,
            "target_expected_owner_still_next_tick": next_owner == expected_owner,
            "target_units_observed_next_tick": True,
            "near_formal_boundary_candidate": exact_arrival_delta and next_owner == expected_owner,
            "ownership_after_arrival": next_owner,
            "remaining_units_after_arrival": next_units,
            "source_units_before": vector(b_towers[source], "units"),
            "source_units_arrival_observation": (vector(a_towers[source], "units")
                if source in a_towers else None),
            "caveats": ["ordinary status candidate only; simultaneous world causes may remain",
                        "no server application tick", "no action intent linkage",
                        "observer track ID is endpoint-dependent and supplemental only",
                        "event transition does not prove complete downstream route/fuel semantics"],
            "formal_credit": 0,
        })
    return candidates


def party_neutral_boundary_candidates():
    path = ROOT / "runtime/research/v2/party-readiness-route-supported-2-20261002.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    states = [entry["state"] for entry in report["OBSERVED"] if isinstance(entry, dict)
              and isinstance(entry.get("state"), dict)]
    by_tick = {fact(s, "tick"): s for s in states if type(fact(s, "tick")) is int}
    before, after = by_tick.get(33), by_tick.get(34)
    if before is None or after is None:
        return [], {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                    "status": "REQUIRED_TICK_PAIR_UNAVAILABLE"}
    b_forces = fact(before, "forces")
    a_forces = fact(after, "forces")
    if not isinstance(b_forces, list) or not isinstance(a_forces, list):
        return [], {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                    "status": "FORCE_COLLECTION_UNAVAILABLE"}
    b_towers = indexed(before.get("towers", []))
    a_towers = indexed(after.get("towers", []))
    sig_counts = collections.Counter(current_identity(f) for f in b_forces)
    a_sigs = collections.Counter(current_identity(f) for f in a_forces)
    after_ids = {fact(f, "id") for f in a_forces if fact(f, "id") is not None}
    out = []
    for f in b_forces:
        sig = current_identity(f)
        if sig is None or sig_counts[sig] != 1 or a_sigs[sig] != 0:
            continue
        owner, source, dest, units = sig
        if source not in b_towers or dest not in b_towers or dest not in a_towers:
            continue
        old, new = b_towers[dest], a_towers[dest]
        old_owner, new_owner = fact(old, "owner"), fact(new, "owner")
        old_units, new_units = vector(old, "units"), vector(new, "units")
        if (old_owner != 0 or old_units is None or any(old_units) or
                new_owner != owner or new_units != units):
            continue
        out.append({"kind": "SELF_NEUTRAL_CAPTURE_BOUNDARY_CANDIDATE",
            "document_id": before.get("document_id"), "match_id": fact(before, "match_id"),
            "player_id": fact(before, "player_id"), "before_sequence": before.get("sequence"),
            "arrival_observation_sequence": after.get("sequence"), "next_observation_sequence": None,
            "before_tick": 33, "arrival_observation_tick": 34, "next_observation_tick": None,
            "source_tower": source, "target_tower": dest, "force_owner": owner,
            "target_owner_before": old_owner, "target_owner_after": new_owner,
            "target_units_before": list(old_units), "target_units_after": list(new_units),
            "force_units": list(units), "target_delta_equals_force_vector_without_overflow": True,
            "force_observer_id_before_only_supplemental": fact(f, "id"),
            "force_id_absent_after": fact(f, "id") not in after_ids,
            "arrival_is_not_proven_by_id_alone": True,
            "near_formal_boundary_candidate": False,
            "candidate_level": "OBSERVED_NEUTRAL_CAPTURE_BOUNDARY_WITHOUT_NEXT_TICK",
            "same_world_transition_group": "party-route-readiness:tick33-to34",
            "caveats": ["two neutral captures share one world transition and context",
                        "no next-tick corroboration (recording ends at tick 34)",
                        "route/terminal/fuel remain UNKNOWN", "formal credit 0"]})
    return out, {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                 "fixture_path": "tests/fixtures/v2/party-route-readiness-20261002/party-readiness-route-supported-2-20261002.json.gz",
                 "fixture_sha256": sha(ROOT / "tests/fixtures/v2/party-route-readiness-20261002/party-readiness-route-supported-2-20261002.json.gz"),
                 "status": report.get("VERDICT"), "formal_credit": report.get("formal_credit"),
                 "has_tick_35": 35 in by_tick, "same_context_simultaneous_boundaries": len(out)}


def path_fuel_sanity():
    path = ROOT / "tests/fixtures/v2/factorized-coverage-edge-audit.jsonl.gz"
    report_path = ROOT / "docs/V2_M2A_FACTORIZED_COVERAGE.json"
    rows = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    active = [x for x in rows if x.get("active") == "ACTIVE_KNOWN"]
    blocked = [x for x in active if x["all_blockers"]["unknown_path"]["status"] == "BLOCKED"]
    path_keys = {(x["cohort"], x["edge_index"]) for x in blocked}
    fuel_keys = {(x["cohort"], x["edge_index"]) for x in active
                 if x["all_blockers"]["fuel"]["status"] == "BLOCKED"}
    pidx = lambda x: {e.get("force_index") for e in x["all_blockers"]["unknown_path"]["evidence"]
                      if isinstance(e, dict) and e.get("reason") == "UNKNOWN_POST_ARRIVAL_PATH"}
    fidx = lambda x: {e.get("force_index") for e in x["all_blockers"]["fuel"]["evidence"]
                      if isinstance(e, dict) and e.get("reason") in ("UNKNOWN_ARRIVAL_FUEL", "EXPIRED_ARRIVAL")}
    same_force_sets = sum(pidx(x) == fidx(x) for x in blocked)
    p_reasons = collections.Counter(e.get("reason") for x in blocked
        for e in x["all_blockers"]["unknown_path"]["evidence"] if isinstance(e, dict) and e.get("reason"))
    f_reasons = collections.Counter(e.get("reason") for x in blocked
        for e in x["all_blockers"]["fuel"]["evidence"] if isinstance(e, dict) and e.get("reason"))
    return {"verdict": "DISTINCT_BUT_CORRELATED" if path_keys == fuel_keys and same_force_sets == len(blocked) else "REVIEW_REQUIRED",
        "fixture_path": path.relative_to(ROOT).as_posix(), "fixture_sha256": sha(path),
        "report_path": report_path.relative_to(ROOT).as_posix(), "report_sha256": sha(report_path),
        "active_known_edges": len(active), "unknown_path_blocked": len(path_keys),
        "fuel_blocked": len(fuel_keys), "intersection": len(path_keys & fuel_keys),
        "symmetric_difference": len(path_keys ^ fuel_keys), "same_implicated_force_indices": same_force_sets,
        "path_force_reason_occurrences": dict(p_reasons), "fuel_force_reason_occurrences": dict(f_reasons),
        "source_conditions": {"unknown_path": "current leg reaches arrival and force terminal continuation is not positively known (UNKNOWN_POST_ARRIVAL_PATH)",
            "fuel": "arrival fuel is unknown or expired (UNKNOWN_ARRIVAL_FUEL/EXPIRED_ARRIVAL), except the exact narrow fuel-irrelevant merge case"},
        "interpretation": "both are independently evaluated guards on the same arrival-reaching force; exact edge overlap is co-occurrence, not duplicate gate mapping"}


def run(out=OUT):
    coverage_path = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
    cov = json.loads(coverage_path.read_text(encoding="utf-8"))
    candidates, pins = [], {}
    per_cohort = {}
    for cohort in COHORTS:
        p = ROOT / f"runtime/research/v2/snapshots-{cohort}.jsonl"
        expected = next(v["expected_sha256"] for v in cov["inputs"]["raw_files"].values()
                        if v["cohort"] == cohort)
        actual = sha(p)
        if actual != expected:
            raise ValueError(f"SNAPSHOT_PIN_MISMATCH:{cohort}")
        pins[cohort] = actual
        rows = []
        with p.open("r", encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                row = observation(raw)
                if row is not None:
                    rows.append(row)
        unique = []
        seen = set()
        for row in rows:
            key = (*row["scope"], row["tick"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        found = []
        for i in range(len(unique) - 2):
            b, a, n = unique[i:i+3]
            if b["scope"] != a["scope"] or a["scope"] != n["scope"]:
                continue
            if (a["tick"] - b["tick"]) % 65536 != 1 or (n["tick"] - a["tick"]) % 65536 != 1:
                continue
            found.extend(pair_candidates(cohort, b, a, n))
        per_cohort[cohort] = {"visible_complete_rows": len(unique), "candidates": len(found),
                              "kinds": dict(collections.Counter(c["kind"] for c in found))}
        candidates.extend(found)
    party_candidates, party_meta = party_neutral_boundary_candidates()
    result = {
        "status": "CANDIDATE_INVENTORY_ONLY_NO_FORMAL_CREDIT",
        "analysis_version": VERSION, "head": subprocess.check_output(
            ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip(),
        "input_manifest": {"coverage_report": {"path": coverage_path.relative_to(ROOT).as_posix(),
            "sha256": sha(coverage_path)}, "snapshots": pins},
        "method": {"scope": "ordinary friendly reinforcement and empty-neutral arrival/capture boundary candidates only",
            "requires": "three contiguous pinned observations; unique pre-event owner/source/target/vector signature; exact one inbound force to target; missing post-event force by signature; observed destination owner and vector change; next-tick destination observation",
            "identity": "observer ID supplemental only; endpoint-dependent track IDs are not used as the arrival criterion",
            "disallowed": "no future route, hidden state, live data, simulator promotion, or historical accepted case reuse as new formal credit"},
        "candidate_total": len(candidates), "near_formal_boundary_count": sum(c["near_formal_boundary_candidate"] for c in candidates),
        "contexts": len({(c["document_id"], c["match_id"]) for c in candidates}),
        "by_kind": dict(collections.Counter(c["kind"] for c in candidates)),
        "required_5_case_goal_met": sum(c["near_formal_boundary_candidate"] for c in candidates) >= 5,
        "friendly_goal_2_met": sum(c["kind"] == "SELF_REINFORCEMENT_CANDIDATE" and
                                    c["near_formal_boundary_candidate"] for c in candidates) >= 2,
        "neutral_goal_2_met": False,
        "secondary_existing_audit_only_candidates": party_candidates,
        "secondary_party_audit": party_meta,
        "path_fuel_sanity": path_fuel_sanity(),
        "historical_accepted_capture": {"path": "docs/V2_M2A_CONTROLLED_CAPTURE_VALIDATION.json",
            "sha256": sha(ROOT / "docs/V2_M2A_CONTROLLED_CAPTURE_VALIDATION.json"),
            "status": "ONE_PREVIOUSLY_ACCEPTED_CASE_REGRESSION_ONLY_NOT_COUNTED_AS_NEW"},
        "ordinary_hypothesis_corpus": {"path": "runtime/research/v2/m2a-ordinary_hypothesis-transition-corpus.jsonl",
            "sha256": sha(ROOT / "runtime/research/v2/m2a-ordinary_hypothesis-transition-corpus.jsonl"),
            "arrival_labeled_edges": 4, "categories": {"ground_combat_arrival": 2,
                "ordinary_air_unit_combat_arrival": 2}, "distinct_cohorts": 2,
            "admitted_into_noncombat_count": 0, "reason": "hostile combat branch excluded; hypothesis corpus only"},
        "candidates": candidates, "formal_credit": 0,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({k: result[k] for k in ("status", "candidate_total", "contexts", "by_kind",
        "required_5_case_goal_met", "friendly_goal_2_met", "neutral_goal_2_met", "formal_credit")},
        ensure_ascii=False))
