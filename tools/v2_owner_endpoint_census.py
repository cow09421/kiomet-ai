"""Bounded descriptive owner-by-endpoint census over accepted edge-before rows."""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

def owner_class(owner: dict[str, Any], relation: dict[str, Any], player_id: Any) -> str:
    """Use only internally consistent recorded owner/relation facts."""
    value, rel = owner.get("value"), relation.get("value")
    if relation.get("valid") and relation.get("knowledge") in ("OBSERVED", "DERIVED") and rel in OWNERS:
        if rel == "UNKNOWN_OWNER":
            return rel
        if rel == "SELF" and type(value) is int and type(player_id) is int and value != player_id:
            return "UNKNOWN_OWNER"
        if rel != "SELF" and type(value) is int and type(player_id) is int and value == player_id:
            return "UNKNOWN_OWNER"
        if rel == "NEUTRAL" and type(value) is int and value != 0:
            return "UNKNOWN_OWNER"
        return rel
    if type(value) is int and type(player_id) is int and player_id > 0:
        if value == player_id:
            return "SELF"
        if value == 0:
            return "NEUTRAL"
    return "UNKNOWN_OWNER"

COVERAGE = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
EDGE_GZIP = ROOT / "tests/fixtures/v2/coverage-denominator-edges.jsonl.gz"
DEFAULT_OUTPUT = ROOT / "runtime/research/v2/owner-endpoint-census-candidate.json"
OWNERS = ("SELF", "ALLY", "ENEMY", "NEUTRAL", "UNKNOWN_OWNER")
EXPECTED_EDGES = 13059
EXPECTED_INCIDENCES = 29450


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _git() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", *args],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.rstrip("\r\n")
    status = run("status", "--porcelain", "--untracked-files=all")
    return {"branch": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
            "dirty": bool(status), "dirty_paths": [x[3:] for x in status.splitlines() if len(x) >= 4]}


def _fact(row: Any, key: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": None, "knowledge": "UNKNOWN", "valid": False}
    f = row.get(key)
    if not isinstance(f, dict) or not {"value", "knowledge", "source", "observed_at_ms"} <= f.keys():
        return {"value": None, "knowledge": "UNKNOWN", "valid": False}
    return {"value": f["value"], "knowledge": f["knowledge"], "valid": True}


def _known_int(f: dict[str, Any]) -> bool:
    return f.get("valid") is True and type(f.get("value")) is int and f.get("knowledge") in ("OBSERVED", "DERIVED")


def _endpoint_status(force: dict[str, Any], towers: dict[int, dict[str, Any]]) -> tuple[str, str]:
    fs, fd = _fact(force, "source"), _fact(force, "destination")
    ks, kd = _known_int(fs), _known_int(fd)
    pair = "BOTH_KNOWN" if ks and kd else "SOURCE_ONLY" if ks else "DESTINATION_ONLY" if kd else "BOTH_UNKNOWN"
    return ("KNOWN" if ks and kd else "UNKNOWN", pair)


def _tower_visible(towers: dict[int, dict[str, Any]], ident: Any) -> bool:
    if type(ident) is not int or ident not in towers:
        return False
    vis = _fact(towers[ident], "visibility")
    return vis["valid"] and vis["value"] is True and vis["knowledge"] in ("OBSERVED", "DERIVED")


def _init_counts() -> collections.Counter:
    return collections.Counter()


def _add(counter: collections.Counter, force: dict[str, Any], player: Any,
         gap_indexes: set[int], index: int, towers: dict[int, dict[str, Any]]) -> None:
    owner = owner_class(_fact(force, "owner"), _fact(force, "relation"), player)
    status, pair = _endpoint_status(force, towers)
    counter["total"] += 1
    counter[f"endpoint_{status.lower()}"] += 1
    counter[f"endpoint_pair_{pair.lower()}"] += 1
    source, dest = _fact(force, "source"), _fact(force, "destination")
    endpoint_values_known = status == "KNOWN"
    endpoint_towers_visible = endpoint_values_known and _tower_visible(towers, source["value"]) and _tower_visible(towers, dest["value"])
    gate_blocked = index in gap_indexes
    input_ready = endpoint_towers_visible and not gate_blocked
    counter["input_ready" if input_ready else "input_blocked"] += 1
    fields = {name: _fact(force, name) for name in
              ("owner", "relation", "source", "destination", "units", "unit_count", "progress")}
    leg_fields_known = all(_known_int(fields[name]) for name in ("source", "destination", "unit_count", "progress"))
    owner_known = fields["owner"]["valid"] and fields["owner"]["value"] is not None and fields["owner"]["knowledge"] in ("OBSERVED", "DERIVED")
    relation_known = fields["relation"]["valid"] and fields["relation"]["value"] in ("SELF", "ALLY", "ENEMY", "NEUTRAL") and fields["relation"]["knowledge"] in ("OBSERVED", "DERIVED")
    units = fields["units"]["value"]
    vector_known = fields["units"]["valid"] and fields["units"]["knowledge"] in ("OBSERVED", "DERIVED") and isinstance(units, dict) and isinstance(units.get("counts"), list)
    if vector_known:
        rows = units["counts"]
        vector_known = len(rows) == 10 and all(isinstance(x, list) and len(x) == 2 and type(x[0]) is int and type(x[1]) is int for x in rows)
        vector_known = vector_known and sum(x[1] for x in rows) == fields["unit_count"]["value"]
    leg_known = status == "KNOWN" and owner_known and relation_known and vector_known and leg_fields_known
    counter["current_leg_known" if leg_known else "current_leg_unknown"] += 1


def _summary(counter: collections.Counter) -> dict[str, Any]:
    total = counter["total"]
    keys = ("endpoint_known", "endpoint_unknown", "input_ready", "input_blocked", "current_leg_known", "current_leg_unknown")
    out: dict[str, Any] = {"total_records": total}
    for key in keys:
        n = counter[key]
        out[key] = {"count": n, "rate": n / total if total else None}
    out["endpoint_pair_counts"] = {k.removeprefix("endpoint_pair_").upper(): counter[k]
                                   for k in ("endpoint_pair_both_known", "endpoint_pair_source_only", "endpoint_pair_destination_only", "endpoint_pair_both_unknown")}
    return out


def build_report() -> dict[str, Any]:
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    edge_meta = coverage["edge_audit"]
    if edge_meta["rows"] != EXPECTED_EDGES or _sha(EDGE_GZIP) != edge_meta["sha256"]:
        raise RuntimeError("accepted edge fixture pin mismatch")
    raw_pins = coverage["inputs"]["raw_files"]
    cohort_meta = {x["cohort"]: x for x in coverage["cohorts"]}
    split_by_cohort = {k: v["split"] for k, v in cohort_meta.items()}
    edges: dict[str, dict[int, list[dict[str, Any]]]] = {c: collections.defaultdict(list) for c in split_by_cohort}
    # Validate all 13,059 rows and the decompressed pin while retaining only small edge metadata.
    h = hashlib.sha256()
    edge_count = 0
    with gzip.open(EDGE_GZIP, "rb") as stream:
        for line in stream:
            h.update(line)
            row = json.loads(line)
            if row.get("cohort") not in edges or row.get("before_line") is None:
                raise RuntimeError("malformed edge row")
            edges[row["cohort"]][row["before_line"]].append(row)
            edge_count += 1
    if edge_count != EXPECTED_EDGES or h.hexdigest() != edge_meta["decompressed_sha256"]:
        raise RuntimeError("edge count/decompressed pin mismatch")
    totals: dict[tuple[str, str], collections.Counter] = {(split, owner): _init_counts()
        for split in ("all", "development", "holdout") for owner in OWNERS}
    complete_totals: dict[tuple[str, str], collections.Counter] = {(split, owner): _init_counts()
        for split in ("all", "development", "holdout") for owner in OWNERS}
    per_cohort: dict[str, dict[str, collections.Counter]] = {c: {o: _init_counts() for o in OWNERS} for c in edges}
    complete_per_cohort: dict[str, dict[str, collections.Counter]] = {c: {o: _init_counts() for o in OWNERS} for c in edges}
    incidence_count = 0
    source_hashes: dict[str, str] = {}
    for cohort, line_edges in edges.items():
        rel = f"runtime/research/v2/snapshots-{cohort}.jsonl"
        raw_path = ROOT / rel
        expected = raw_pins[rel.replace("/", "\\")]["expected_sha256"]
        if _sha(raw_path) != expected:
            raise RuntimeError(f"raw snapshot pin mismatch: {cohort}")
        source_hashes[rel] = expected
        wanted = set(line_edges)
        terminal_line = max((row["after_line"] for rows in line_edges.values() for row in rows), default=0)
        max_line = max(max(wanted, default=0), terminal_line)
        with raw_path.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if line_no > max_line:
                    break
                if line_no not in wanted and line_no != terminal_line:
                    continue
                raw = json.loads(line)
                force_fact = raw.get("forces")
                forces = force_fact.get("value") if isinstance(force_fact, dict) else None
                if not isinstance(forces, list):
                    raise RuntimeError(f"malformed force list {cohort}:{line_no}")
                towers_list = raw.get("towers")
                towers = {t.get("id"): t for t in towers_list if isinstance(t, dict) and type(t.get("id")) is int} if isinstance(towers_list, list) else {}
                if line_no in wanted:
                  for edge in line_edges[line_no]:
                    # Endpoint readiness here is explicitly local to each force incidence.
                    gap_indexes: set[int] = set()
                    for gap in edge.get("control_readiness_gaps", []):
                        if isinstance(gap, str) and gap.startswith("force:"):
                            parts = gap.split(":")
                            if len(parts) == 3 and parts[1].isdigit() and parts[2] in {"source", "destination"}:
                                gap_indexes.add(int(parts[1]))
                    player = _fact(raw, "player_id")["value"]
                    for index, force in enumerate(forces):
                        if not isinstance(force, dict):
                            raise RuntimeError("malformed force record")
                        owner = owner_class(_fact(force, "owner"), _fact(force, "relation"), player)
                        _add(per_cohort[cohort][owner], force, player, gap_indexes, index, towers)
                        _add(totals[("all", owner)], force, player, gap_indexes, index, towers)
                        _add(totals[(split_by_cohort[cohort], owner)], force, player, gap_indexes, index, towers)
                        _add(complete_per_cohort[cohort][owner], force, player, gap_indexes, index, towers)
                        _add(complete_totals[("all", owner)], force, player, gap_indexes, index, towers)
                        _add(complete_totals[(split_by_cohort[cohort], owner)], force, player, gap_indexes, index, towers)
                        incidence_count += 1
                elif line_no == terminal_line:
                    player = _fact(raw, "player_id")["value"]
                    for index, force in enumerate(forces):
                        owner = owner_class(_fact(force, "owner"), _fact(force, "relation"), player)
                        _add(complete_per_cohort[cohort][owner], force, player, set(), index, towers)
                        _add(complete_totals[("all", owner)], force, player, set(), index, towers)
                        _add(complete_totals[(split_by_cohort[cohort], owner)], force, player, set(), index, towers)
    if incidence_count != EXPECTED_INCIDENCES:
        raise RuntimeError(f"edge-before force-incidence count changed: {incidence_count}")
    tool_path = Path(__file__).resolve()
    source_paths = [COVERAGE, ROOT / "tools/v2_endpoint_lineage.py", ROOT / "src/kiomet_ai/v2/control.py", ROOT / "src/kiomet_ai/v2/state.py"]
    totals_json = {scope: {owner: _summary(totals[(scope, owner)]) for owner in OWNERS}
                   for scope in ("all", "development", "holdout")}
    per_cohort_json = {c: {o: _summary(per_cohort[c][o]) for o in OWNERS} for c in sorted(per_cohort)}
    complete_totals_json = {scope: {owner: _summary(complete_totals[(scope, owner)]) for owner in OWNERS}
                   for scope in ("all", "development", "holdout")}
    complete_per_cohort_json = {c: {o: _summary(complete_per_cohort[c][o]) for o in OWNERS} for c in sorted(complete_per_cohort)}
    def rate(section: dict[str, Any], key: str) -> float | None:
        return section[key]["rate"]
    self_endpoint = rate(totals_json["all"]["SELF"], "endpoint_known")
    enemy_endpoint = rate(totals_json["all"]["ENEMY"], "endpoint_known")
    capture_validation_path = ROOT / "docs/V2_M2A_CONTROLLED_CAPTURE_VALIDATION.json"
    capture_record_path = ROOT / "runtime/research/v2/controlled-transition-77636cad4e97.jsonl"
    capture_fixture_path = ROOT / "tests/fixtures/v2/controlled-transition-77636cad4e97.jsonl.gz"
    capture_validation = json.loads(capture_validation_path.read_text(encoding="utf-8"))
    capture_event_hash = _sha(capture_record_path)
    capture_input = {"case": "accepted own UI drag -> one SELF force -> neutral empty tower arrival/capture",
        "validation_status": capture_validation["status"],
        "accepted_scope": capture_validation["scope"],
        "source": {"path": "14090505", "owner": 25, "relation": "SELF", "supply_line_present": False},
        "target": {"path": "14090504", "owner": 0, "relation": "NEUTRAL", "empty": True, "supply_line_present": False},
        "force": {"birth_tick": 65157, "owner": 25, "source": 14090505, "destination": 14090504,
            "birth_confidence": "NEW_TRACK", "birth_progress": 0, "units_match_recorded_typed_deployable": True,
            "same_unique_track_through_tick": 65185, "arrival_and_owner_change_tick": 65186},
        "evidence_layers": {
            "L0_preextractor_input": {"status": "UNKNOWN", "basis": "Durable BEFORE_INTENT and selection/hit-test records preserve UI intent and typed deployable, but the BEFORE_INTENT is prior to dispatch and explicitly records input_sent=false; no raw pre-extractor input payload is retained."},
            "L1_extractor_output": {"status": "UNKNOWN", "basis": "No separately retained extractor-stage object is paired with the canonical observation, so the L1 boundary is not independently evidenced."},
            "L2_canonical_gamestate": {"status": "PRESENT", "basis": "The retained AFTER_DISTINCT_TICK observation at tick 65185 contains the canonical GameState fields, including observed SELF owner/source/destination/units/progress."},
            "L3_serialization": {"status": "SERIALIZED_PRESENT_ROUNDTRIP_UNKNOWN", "basis": "Canonical state is retained as JSON in the recording; a paired explicit deserialize/reserialize boundary artifact is not recorded."},
            "L4_simulation_state": {"status": "CONDITIONAL_MAPPING_PRESENT", "basis": capture_validation["capture"]["simulation_input"]},
            "L5_readiness": {"status": "CANONICAL_ENDPOINT_FIELDS_READY; RECORDED_GLOBAL_READINESS_UNKNOWN", "basis": "Static reapplication of the pinned endpoint/control field gate to the saved tick-65185 canonical state finds both endpoints and no control_readiness_gaps. The accepted capture receipt does not store an independent global-readiness record for this tick; simulation mapping remains conditional on terminal/fuel premises."}},
        "credits": capture_validation["credit"],
        "saved_evidence": {"validation_path": str(capture_validation_path.relative_to(ROOT)).replace("\\", "/"),
            "validation_sha256": _sha(capture_validation_path), "recording_path": str(capture_record_path.relative_to(ROOT)).replace("\\", "/"),
            "recording_sha256": capture_event_hash, "fixture_path": str(capture_fixture_path.relative_to(ROOT)).replace("\\", "/"),
            "fixture_compressed_sha256": _sha(capture_fixture_path), "expected_recording_sha256": capture_validation["manifest"]["frozen_recording"]["sha256"]}}
    return {
        "status": "CANDIDATE_DESCRIPTIVE_CENSUS",
        "analysis_version": "owner-endpoint-census-v1",
        "universe": {"edge_rows": edge_count, "edge_before_force_record_incidences": incidence_count,
            "edge_gzip_sha256": _sha(EDGE_GZIP), "edge_decompressed_sha256": h.hexdigest(), "raw_snapshot_sha256": source_hashes,
            "cohorts": {c: split_by_cohort[c] for c in sorted(split_by_cohort)}},
        "method": {"unit": "one force-record incidence in each accepted distinct-observation edge's BEFORE snapshot; the same snapshot may contribute again when it is the before endpoint of another edge",
            "owner": "recorded relation when valid, with contradictions classified UNKNOWN_OWNER, using the frozen owner_class rule; otherwise only direct SELF/neutral facts qualify",
            "endpoint_known": "both source and destination are integer OBSERVED/DERIVED Facts; partial knownness is separately reported",
            "input_ready": "local endpoint readiness only: both endpoints resolve to positively visible towers and this exact force index has no source/destination readiness gap in the edge's before-state gate; not whole-state simulator readiness",
            "current_leg_known": "both endpoint Facts plus owner, relation, progress, unit_count, and a valid ten-type units vector whose sum equals unit_count are known; not a claim that motion/arrival is semantically simulated",
            "causality": "descriptive only; endpoint distributions do not identify why observation differs or prove pipeline loss/visibility policy"},
        "counts_by_scope": totals_json,
        "counts_by_cohort": per_cohort_json,
        "complete_retained_unique_observation_counts_by_scope": complete_totals_json,
        "complete_retained_unique_observation_counts_by_cohort": complete_per_cohort_json,
        "complete_retained_observation_universe": {"unique_first_observation_per_scope_tick_count": EXPECTED_EDGES + len(edges),
            "description": "Accepted 13,059 edge-before observations plus each cohort's final after observation; no duplicate scope/tick snapshots are added. This supplemental census prevents dropping the six terminal observations.",
            "terminal_rows_included": len(edges)},
        "comparison": {"self_endpoint_known_rate": self_endpoint, "enemy_endpoint_known_rate": enemy_endpoint,
            "self_minus_enemy_endpoint_known_rate": None if self_endpoint is None or enemy_endpoint is None else self_endpoint - enemy_endpoint,
            "supports_general_pipeline_loss_claim": False,
            "interpretation": "Descriptive SELF-vs-ENEMY endpoint distribution only; a difference may motivate observation-policy hypotheses but does not establish pipeline-loss cause."},
        "historical_accepted_ui_capture": capture_input,
        "provenance": {"coverage_json_sha256": _sha(COVERAGE), "source_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): _sha(p) for p in source_paths},
            "tool_sha256": _sha(tool_path), "git": _git()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output),
        "records": report["universe"]["edge_before_force_record_incidences"],
        "self_endpoint_known_rate": report["comparison"]["self_endpoint_known_rate"],
        "enemy_endpoint_known_rate": report["comparison"]["enemy_endpoint_known_rate"],
        "tool_sha256": report["provenance"]["tool_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
