"""Before-only enemy current-leg derivation diagnostic on pinned recordings.

No position/direction is imputed. Direct endpoints remain direct; a known
current endpoint may expose an adjacency candidate set, never a unique route
without a proved Force/topology rule.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DENOMINATOR = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
LINEAGE = ROOT / "tests/fixtures/v2/endpoint-lineage-entities.jsonl.gz"
DEFAULT_REPORT = ROOT / "runtime/research/v2/enemy-current-leg-candidate.json"
DEFAULT_AUDIT = ROOT / "runtime/research/v2/enemy-current-leg-audit.jsonl.gz"
DEV = ("fe678ebb30ce", "03d032d57e5b", "daf86d0544b7")
HOLDOUT = ("85391858b5d8", "7d56a775bc4c", "b1f7f9416e92")
ORDER = DEV + HOLDOUT
DIRECT_PROVENANCE = "current segment endpoint intersect current observed towers"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def value(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) else None


def known(fact: Any) -> bool:
    return isinstance(fact, dict) and fact.get("knowledge") != "UNKNOWN" and fact.get("value") is not None


def owner_class(force: dict[str, Any], player_id: Any) -> str:
    relation = value(force.get("relation")) if known(force.get("relation")) else None
    if relation in ("SELF", "ALLY", "ENEMY", "NEUTRAL"):
        return relation
    owner = value(force.get("owner")) if known(force.get("owner")) else None
    if type(owner) is int and owner == 0:
        return "NEUTRAL"
    if type(owner) is int and type(player_id) is int and owner == player_id:
        return "SELF"
    return "UNKNOWN_OWNER"


def _endpoint_is_current_visible(force: dict[str, Any], key: str) -> bool:
    fact = force.get(key)
    if not known(fact) or type(value(fact)) is not int:
        return False
    provenance = fact.get("source", "")
    return isinstance(provenance, str) and DIRECT_PROVENANCE in provenance


def classify_current_leg(force: dict[str, Any], towers: dict[int, dict[str, Any]],
                         player_id: Any = None) -> dict[str, Any]:
    """Classify only t-visible endpoint/graph inputs; candidate is never unique."""
    source_known = known(force.get("source")) and type(value(force.get("source"))) is int
    target_known = known(force.get("destination")) and type(value(force.get("destination"))) is int
    source = value(force.get("source")) if source_known else None
    target = value(force.get("destination")) if target_known else None
    source_provenance_ok = _endpoint_is_current_visible(force, "source")
    target_provenance_ok = _endpoint_is_current_visible(force, "destination")
    direct = source_known and target_known
    candidates: list[int] = []
    candidate_basis = None
    if direct:
        classification = "DIRECT_ENDPOINT"
        reason = "both endpoints are present in this t-visible Force record; no derivation performed"
    elif source_known and source_provenance_ok:
        tower = towers.get(source)
        neighbors_fact = tower.get("neighbors") if tower else None
        if known(neighbors_fact) and isinstance(value(neighbors_fact), list):
            candidates = sorted({x for x in value(neighbors_fact) if type(x) is int and x in towers and x != source})
            candidate_basis = "currently visible neighbors of current-visible source"
        classification = "CANDIDATE_SET" if candidates else "UNAVAILABLE"
        reason = ("adjacency supplies candidates only; no proved force-route/topology rule permits unique selection"
                  if candidates else "no current visible adjacent candidate list is available")
    elif target_known and target_provenance_ok:
        tower = towers.get(target)
        neighbors_fact = tower.get("neighbors") if tower else None
        if known(neighbors_fact) and isinstance(value(neighbors_fact), list):
            candidates = sorted({x for x in value(neighbors_fact) if type(x) is int and x in towers and x != target})
            candidate_basis = "currently visible neighbors of current-visible destination"
        classification = "CANDIDATE_SET" if candidates else "UNAVAILABLE"
        reason = ("adjacency supplies candidates only; no proved force-route/topology rule permits unique selection"
                  if candidates else "no current visible adjacent candidate list is available")
    else:
        classification = "UNAVAILABLE"
        reason = "canonical Force has no visible position/direction; progress without a current endpoint anchor does not determine a leg"
    progress_known = known(force.get("progress")) and type(value(force.get("progress"))) is int
    progress = value(force.get("progress")) if progress_known else None
    if direct:
        motion_state = "CURRENT_LEG_DIRECTLY_OBSERVED"
    elif progress == 0:
        motion_state = "ZERO_PROGRESS_NOT_STATIONARY_EVIDENCE"
    elif progress_known:
        motion_state = "UNKNOWN_MOTION_NO_FORCE_POSITION_OR_DIRECTION"
    else:
        motion_state = "UNKNOWN_MOTION_PROGRESS_UNAVAILABLE"
    return {
        "classification": classification,
        "source": source,
        "target": target,
        "candidate_targets_or_sources": candidates,
        "candidate_basis": candidate_basis,
        "reason": reason,
        "motion_state": motion_state,
        "progress": progress,
        "progress_known": progress_known,
        "source_provenance": force.get("source", {}).get("source") if isinstance(force.get("source"), dict) else None,
        "destination_provenance": force.get("destination", {}).get("source") if isinstance(force.get("destination"), dict) else None,
        "position_field_present": "position" in force,
        "direction_field_present": "direction" in force,
        "owner_class": owner_class(force, player_id),
        "direct_endpoint": direct,
    }


def _identity_reliable(force: dict[str, Any], force_rows: list[Any], raw: dict[str, Any]) -> bool:
    ident = force.get("id")
    if not isinstance(ident, dict) or ident.get("knowledge") != "DERIVED" or not isinstance(value(ident), str) or not value(ident):
        return False
    if value(force.get("visibility")) is not True or value(force.get("confidence")) not in ("NEW_TRACK", "UNIQUE_CONTINUATION"):
        return False
    if (not isinstance(raw.get("document_id"), str) or not raw.get("document_id")
        or not isinstance(value(raw.get("match_id")), str) or not value(raw.get("match_id"))
        or type(value(raw.get("player_id"))) is not int or value(raw.get("player_id")) <= 0):
        return False
    return sum(1 for row in force_rows if isinstance(row, dict) and value(row.get("id")) == value(ident)) == 1


def _summarize(counts: dict[str, collections.Counter]) -> dict[str, Any]:
    output = {}
    for split, by_owner in counts.items():
        output[split] = {}
        for owner in ("SELF", "ALLY", "ENEMY", "NEUTRAL", "UNKNOWN_OWNER"):
            row = by_owner.get(owner, collections.Counter())
            eligible = row["eligible"]
            unique = row["derived_unique"]
            scored = row["true_unique"] + row["false_unique"]
            output[split][owner] = {
                **dict(row),
                "unique_rate": unique / eligible if eligible else None,
                "false_unique_rate": row["false_unique"] / unique if unique else None,
                "accuracy_of_unique": row["true_unique"] / scored if scored else None,
                "accuracy_denominator": scored,
                "unique_derivation_scored": scored,
                "endpoint_known_rate": row["endpoint_known"] / row["total"] if row["total"] else None,
                "input_ready_rate": row["input_ready"] / row["total"] if row["total"] else None,
                "current_leg_known_rate": row["current_leg_known"] / row["total"] if row["total"] else None,
            }
    return output


def git_state() -> dict[str, Any]:
    prefix = ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet"]
    def read(*args: str) -> str:
        return subprocess.run(prefix + list(args), cwd=ROOT, check=True, capture_output=True,
            text=True, encoding="utf-8").stdout.rstrip("\r\n")
    status = read("status", "--porcelain=v1", "--untracked-files=all")
    return {"head": read("rev-parse", "HEAD"), "branch": read("branch", "--show-current"),
        "remote": read("remote", "get-url", "origin"), "dirty": bool(status),
        "status_porcelain": status.splitlines()}


def run(report_path: Path = DEFAULT_REPORT, audit_path: Path = DEFAULT_AUDIT) -> dict[str, Any]:
    manifest = json.loads(DENOMINATOR.read_text(encoding="utf-8"))
    cohort_split = manifest["inputs"]["splits"]
    raw_manifest = manifest["inputs"]["raw_files"]
    expected_hashes = {Path(p.replace("\\", "/")).name: item["expected_sha256"]
                       for p, item in raw_manifest.items()}
    lineage_hash = sha256(LINEAGE)
    if lineage_hash != "1cdd5dd5d16f9ca3c01d19feb89ed48ce19a5db8a8093c6d8726e8245f706aed":
        raise RuntimeError("pinned endpoint-lineage fixture hash mismatch")
    lineage_tracks: dict[str, dict[str, Any]] = {}
    with gzip.open(LINEAGE, "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            if item.get("identity_reliable") and item.get("owner_class") == "ENEMY":
                key = item.get("identity_key_sha256")
                if key:
                    lineage_tracks[key] = {"age_class": item.get("age_class"),
                        "cohort": item.get("cohort"), "split": item.get("split")}
    if len(lineage_tracks) != 267:
        raise RuntimeError(f"expected 267 reliable blocked enemy track identities, got {len(lineage_tracks)}")
    source_paths = [DENOMINATOR, LINEAGE, ROOT / "src/kiomet_ai/v2/state.py",
        ROOT / "src/kiomet_ai/v2/observe/forces.py", ROOT / "src/kiomet_ai/v2/observe/extractor.py"]
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in source_paths}
    tool_hash = sha256(Path(__file__).resolve())
    by_split = {"development": collections.defaultdict(collections.Counter),
                "holdout": collections.defaultdict(collections.Counter)}
    cohort_counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    raw_hashes: dict[str, str] = {}
    raw_lines: dict[str, int] = {}
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=6) as zipped:
            import io
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as audit:
                for cohort in DEV + HOLDOUT:
                    name = f"snapshots-{cohort}.jsonl"
                    rel = f"runtime/research/v2/{name}"
                    path = ROOT / rel
                    raw_digest = hashlib.sha256()
                    split = cohort_split[cohort]
                    previous_scope_tick = None
                    with path.open("rb") as stream:
                        line_num = 0
                        for raw_line in stream:
                            raw_digest.update(raw_line)
                            line_num += 1
                            raw = json.loads(raw_line)
                            facts = raw.get("forces")
                            rows = value(facts)
                            cohort_counts[cohort]["raw_force_records_all_polls"] += len(rows) if isinstance(rows, list) else 0
                            scope_tick = (raw.get("document_id"), value(raw.get("match_id")),
                                value(raw.get("player_id")), value(raw.get("tick")))
                            if scope_tick == previous_scope_tick:
                                counter = cohort_counts[cohort]
                                counter["duplicate_poll_snapshots_skipped"] += 1
                                counter["raw_force_records_in_duplicate_polls_skipped"] += len(rows) if isinstance(rows, list) else 0
                                continue
                            previous_scope_tick = scope_tick
                            cohort_counts[cohort]["retained_scope_tick_snapshots"] += 1
                            if not isinstance(rows, list):
                                continue
                            towers = {t.get("id"): t for t in raw.get("towers", [])
                                if isinstance(t, dict) and type(t.get("id")) is int}
                            player_id = value(raw.get("player_id"))
                            counter = cohort_counts[cohort]
                            for force_index, force in enumerate(rows):
                                counter["force_records"] += 1
                                if not isinstance(force, dict):
                                    counter["malformed_force_rows"] += 1
                                    continue
                                observed_visible = (value(force.get("visibility")) is True and
                                    isinstance(force.get("visibility"), dict) and
                                    force["visibility"].get("knowledge") != "UNKNOWN")
                                owner = owner_class(force, player_id)
                                result = classify_current_leg(force, towers, player_id)
                                ready = result["direct_endpoint"] and result["source"] in towers and result["target"] in towers
                                endpoint_known = result["direct_endpoint"]
                                identity_reliable = _identity_reliable(force, rows, raw)
                                age = "UNKNOWN_AGE"
                                if identity_reliable:
                                    # Confidence is current-observation only. No future edge is consulted.
                                    age = "NEWBORN" if value(force.get("confidence")) == "NEW_TRACK" and result["progress"] == 0 else "PERSISTENCE_UNKNOWN"
                                stat = by_split[split][owner]
                                stat["total"] += 1
                                stat["endpoint_known"] += int(endpoint_known)
                                stat["endpoint_unknown"] += int(not endpoint_known)
                                stat["input_ready"] += int(ready)
                                stat["input_blocked"] += int(not ready)
                                stat["current_leg_known"] += int(result["classification"] == "DIRECT_ENDPOINT")
                                stat["current_leg_unknown"] += int(result["classification"] != "DIRECT_ENDPOINT")
                                stat["motion:" + result["motion_state"]] += 1
                                stat["visible_force_records"] += int(observed_visible)
                                stat["reliable_identity_records"] += int(identity_reliable)
                                stat["force_position_field_records"] += int(result["position_field_present"])
                                stat["force_direction_field_records"] += int(result["direction_field_present"])
                                stat["direct_endpoint"] += int(result["classification"] == "DIRECT_ENDPOINT")
                                stat["candidate_set"] += int(result["classification"] == "CANDIDATE_SET")
                                stat["ambiguous"] += int(result["classification"] == "AMBIGUOUS")
                                stat["unavailable"] += int(result["classification"] == "UNAVAILABLE")
                                eligible = (owner == "ENEMY" and observed_visible and result["progress_known"] and not endpoint_known)
                                stat["eligible"] += int(eligible)
                                stat["eligible_reliable_identity"] += int(eligible and identity_reliable)
                                stat["unscorable"] += int(eligible)
                                stat["true_unique"] += 0
                                stat["false_unique"] += 0
                                stat["zero_progress_missing_endpoint"] += int(eligible and result["progress"] == 0)
                                counter[f"owner:{owner}"] += 1
                                counter[f"class:{result['classification']}"] += 1
                                counter["eligible_enemy"] += int(eligible)
                                counter["eligible_enemy_reliable"] += int(eligible and identity_reliable)
                                counter["force_position_field_records"] += int(result["position_field_present"])
                                counter["force_direction_field_records"] += int(result["direction_field_present"])
                                if result["classification"] == "CANDIDATE_SET":
                                    counter["candidate_set_singleton"] += int(len(result["candidate_targets_or_sources"]) == 1)
                                audit.write(json.dumps({"cohort": cohort, "split": split, "line": line_num,
                                    "tick": value(raw.get("tick")),
                                    "sequence": value(raw.get("sequence")) if isinstance(raw.get("sequence"), dict) else raw.get("sequence"),
                                    "force_index": force_index,
                                    "observer_id_sha256": hashlib.sha256(str(value(force.get("id"))).encode("utf-8")).hexdigest()
                                        if value(force.get("id")) is not None else None,
                                    "identity_reliable_at_t": identity_reliable, "eligible_for_unique_derivation": eligible,
                                    "owner_class": owner, "endpoint_known": endpoint_known,
                                    "input_ready": ready, "derivation": result,
                                    "truth_scoring": "UNSCORABLE_NO_UNIQUE_PREDICTION" if eligible else "NOT_APPLICABLE"},
                                    ensure_ascii=False, separators=(",", ":")) + "\n")
                    actual_hash = raw_digest.hexdigest()
                    if actual_hash != expected_hashes[name]:
                        raise RuntimeError(f"raw pin mismatch {name}: {actual_hash}")
                    raw_hashes[rel] = actual_hash
                    raw_lines[cohort] = line_num
                    counter["raw_lines"] = line_num
                    if split == "development" and cohort == DEV[-1]:
                        development_freeze = {"completed_cohorts": list(DEV),
                            "tool_sha256_frozen_before_holdout": tool_hash,
                            "rule_constant": "DIRECT_ENDPOINT only; visible adjacency remains CANDIDATE_SET, never unique",
                            "holdout_started_after_development_hash_and_parse": True}

    totals = _summarize(by_split)
    # The current conservative rule produces no derived-unique prediction;
    # future truth cannot turn a candidate/unavailable result into a prediction.
    for split in ("development", "holdout"):
        eligible = totals[split]["ENEMY"]["eligible"]
        unique_rate = totals[split]["ENEMY"]["unique_rate"]
        if unique_rate is not None and unique_rate >= .9 and totals[split]["ENEMY"]["false_unique"] == 0:
            verdict = "STRONG"
        elif unique_rate is not None and unique_rate >= .6:
            verdict = "PARTIAL"
        else:
            verdict = "WEAK"
        totals[split]["ENEMY"]["verdict"] = verdict
        totals[split]["ENEMY"]["verdict_reason"] = "No force position/direction is retained; adjacency alone is not a proved current-leg selector."
        totals[split]["ENEMY"]["eligible_for_unique_derivation"] = eligible
    report = {"status": "CANDIDATE", "analysis_version": "enemy-current-leg-v1",
        "git": git_state(), "tool_sha256": tool_hash,
        "inputs": {"denominator_manifest": str(DENOMINATOR.relative_to(ROOT)),
            "denominator_sha256": sha256(DENOMINATOR), "endpoint_lineage_fixture": str(LINEAGE.relative_to(ROOT)),
            "endpoint_lineage_fixture_sha256": lineage_hash, "reliable_blocked_enemy_tracks": len(lineage_tracks),
            "reliable_blocked_enemy_tracks_by_age": dict(collections.Counter(x["age_class"] for x in lineage_tracks.values())),
            "raw_snapshot_sha256": raw_hashes, "source_sha256": sources},
        "method": {"source": "normal-player-visible retained canonical Force and current tower fields only",
            "schema_limit": "Force has no position or movement-direction fields. Static tower position and neighbors do not reveal the force's current coordinate or route.",
            "decision_rule": "Both current source and destination present => DIRECT_ENDPOINT. One present current-segment endpoint may yield visible adjacency CANDIDATE_SET only; even a singleton stays a candidate because no force-route adjacency rule is proved. Otherwise UNAVAILABLE.",
            "forbidden_inputs": ["t+1 or later during derivation", "future endpoint/outcome/arrival/capture", "ETA or unit-speed inversion", "hidden/server-private topology", "hidden actor state"],
            "future_scoring": "No unique derivations were emitted, so no future endpoint was consulted; eligible unresolved cases remain UNSCORABLE, not false unique.",
            "zero_progress": "ZERO_PROGRESS_NOT_STATIONARY_EVIDENCE; no static/stationary/parked label is inferred from zero progress alone."},
        "cohorts": {c: {"split": cohort_split[c], **dict(cohort_counts[c])} for c in ORDER},
        "owner_current_leg": totals, "development_freeze_checkpoint": development_freeze,
        "decision": {"current_leg_derivation": totals["holdout"]["ENEMY"]["verdict"],
            "holdout_unique_rate": totals["holdout"]["ENEMY"]["unique_rate"],
            "holdout_unique_accuracy": totals["holdout"]["ENEMY"]["accuracy_of_unique"],
            "holdout_false_unique": totals["holdout"]["ENEMY"]["false_unique"],
            "unique_rate_uses_eligible_enemy_missing_endpoint_records": True},
        "audit": {"path": str(audit_path.relative_to(ROOT)), "sha256": sha256(audit_path),
            "format": "deterministic gzip JSONL; one row per visible force record"}}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    output = run()
    print(json.dumps({"status": output["status"], "tool_sha256": output["tool_sha256"],
        "audit_sha256": output["audit"]["sha256"], "reliable_enemy_tracks": output["inputs"]["reliable_blocked_enemy_tracks"],
        "holdout": output["decision"]}, ensure_ascii=False), flush=True)
