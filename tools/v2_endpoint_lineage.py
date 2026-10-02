"""Offline lineage audit for active current-leg endpoint refusals.

This tool follows only pinned saved observations and the accepted coverage
edge audit. The snapshots are serialized canonical observer outputs, not raw
extractor inputs. It never fills endpoints or bypasses readiness.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
from datetime import datetime, timezone
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

from kiomet_ai.v2.serialization import entity_from_dict
from kiomet_ai.v2.state import Force

COVERAGE_JSON = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
EDGE_GZIP = ROOT / "tests/fixtures/v2/coverage-denominator-edges.jsonl.gz"
DEFAULT_JSON = ROOT / "runtime/research/v2/endpoint-lineage-candidate.json"
DEFAULT_GZIP = ROOT / "runtime/research/v2/endpoint-lineage-entities.jsonl.gz"
EXPECTED_ENDPOINT_EDGES = 4766
EXPECTED_EDGE_GZIP_SHA256 = "8a67b03919070a1385dc0269207f4622101b62e4c5409fc4df19b99ff9e5346d"
TARGET_FILTER = {"active": "ACTIVE_KNOWN", "primary_category": "UNKNOWN_PATH",
                 "primary_blocker": "NOT_READY",
                 "detailed_readiness_bucket": "current_leg_endpoint"}

# Frozen before any holdout results are summarized. No outcome-dependent
# threshold is used; development and holdout execute this exact rule table.
METHOD = {
    "version": "endpoint-lineage-v1",
    "edge_filter": TARGET_FILTER,
    "classification_order": ["A_RAW_ABSENT", "B_EXTRACTOR_LOSS", "C_GAMESTATE_LOSS",
        "D_SIMSTATE_LOSS", "E_PROVENANCE_OR_READINESS_REJECT",
        "F_TRUE_INFORMATION_CEILING", "G_UNCLASSIFIED"],
    "class_a": "endpoint field value absent at earliest retained canonical serialized observer output; upstream extractor input remains UNKNOWN",
    "class_b_to_e": "require a same-scope contemporaneous saved artifact positively showing the endpoint at one pipeline stage and absent or rejected at the next",
    "class_f": "requires positive current normal-player-visible evidence excluding a reliable endpoint; no reverse-engineered, hidden, future, or stale last-known fact",
    "force_age": {"NEWBORN": "reliable NEW_TRACK and progress exactly zero",
        "PERSISTENT": "one consecutive observed continuation", "LONG_LIVED": "at least two consecutive observed continuations",
        "UNKNOWN_AGE": "otherwise, including NEW_TRACK with nonzero progress"},
    "identity": "document, match, player, reliable derived observer id; duplicate, missing, malformed, or discontinuous identity is not unique",
    "lineage": "raw-retained snapshot -> Force dataclass restoration -> dataclass serialization roundtrip; SimulationState mapping is NOT_RUN when whole-state readiness refuses",
    "scope": "six pinned complete development/holdout recordings; 4766 ACTIVE_KNOWN first current-leg UNKNOWN_PATH/NOT_READY edges",
    "future_or_hidden_completion": "prohibited",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-c", "safe.directory=E:/SteamLibrary/kiomet", *args],
            cwd=ROOT, check=True, capture_output=True, text=True).stdout.rstrip("\r\n")
    status = run("status", "--porcelain", "--untracked-files=all")
    return {"branch": run("branch", "--show-current"), "head": run("rev-parse", "HEAD"),
        "remote": run("remote", "get-url", "origin"), "dirty": bool(status),
        "dirty_paths": [line[3:] for line in status.splitlines() if len(line) >= 4]}


def _fact(row: dict[str, Any], name: str) -> dict[str, Any]:
    value = row.get(name)
    if not isinstance(value, dict) or not {"value", "knowledge", "source", "observed_at_ms"}.issubset(value):
        return {"field_present": name in row, "value": None, "knowledge": "UNKNOWN",
                "provenance": "MALFORMED_OR_ABSENT_FACT", "observed_at_ms": None,
                "fact_shape_valid": False}
    return {"field_present": True, "value": value["value"], "knowledge": value["knowledge"],
            "provenance": value["source"], "observed_at_ms": value["observed_at_ms"],
            "fact_shape_valid": True}


def endpoint_field_status(fact: dict[str, Any]) -> str:
    if not fact.get("fact_shape_valid"):
        return "UNKNOWN"
    if fact.get("value") is None and fact.get("knowledge") == "UNKNOWN":
        return "NO"
    if type(fact.get("value")) is int and fact.get("knowledge") in ("OBSERVED", "DERIVED"):
        return "YES"
    return "UNKNOWN"


def classify_lineage(source: dict[str, Any], destination: dict[str, Any],
                     stage_evidence: dict[str, Any] | None = None) -> tuple[str, str]:
    """Classify by first positively evidenced boundary; unknown is never F."""
    evidence = stage_evidence or {}
    fields = (source, destination)
    if not isinstance(stage_evidence, dict):
        evidence = {}
    if evidence.get("raw_extractor_has_endpoint") is True and evidence.get("extractor_output_has_endpoint") is False:
        return "B_EXTRACTOR_LOSS", "paired raw-extractor-to-extractor-output evidence"
    if ((evidence.get("extractor_output_has_endpoint") is True and evidence.get("canonical_gamestate_has_endpoint") is False) or
            (evidence.get("canonical_serialized_has_endpoint") is True and evidence.get("gamestate_after_restore_has_endpoint") is False)):
        return "C_GAMESTATE_LOSS", "paired previous-stage-to-canonical-GameState evidence"
    if evidence.get("canonical_has_endpoint") is True and evidence.get("simstate_has_endpoint") is False:
        return "D_SIMSTATE_LOSS", "paired canonical-to-SimulationState evidence"
    if evidence.get("endpoint_present_but_readiness_rejected") is True:
        return "E_PROVENANCE_OR_READINESS_REJECT", "endpoint value exists but a recorded provenance/readiness gate rejects it"
    if evidence.get("current_player_visibility_excludes_endpoint") is True:
        return "F_TRUE_INFORMATION_CEILING", "positive current normal-player visibility evidence excludes endpoint"
    if any(not f.get("fact_shape_valid") for f in fields):
        return "G_UNCLASSIFIED", "malformed or absent retained endpoint Fact"
    if any(f.get("value") is None and f.get("knowledge") == "UNKNOWN" for f in fields):
        # A is strictly a retained-record boundary description. It does not
        # identify the upstream cause or prove a normal-player information ceiling.
        return "A_RAW_ABSENT", "absent at earliest retained observer output; upstream first-loss layer unresolved"
    if all(endpoint_field_status(f) == "YES" for f in fields):
        return "G_UNCLASSIFIED", "both endpoints are present; this entity should not be endpoint-blocked"
    return "G_UNCLASSIFIED", "no positive evidence identifies a first loss layer"


def owner_class(owner: dict[str, Any], relation: dict[str, Any], player_id: Any) -> str:
    value = owner.get("value")
    rel = relation.get("value")
    if relation.get("fact_shape_valid") and relation.get("knowledge") in ("OBSERVED", "DERIVED"):
        if rel in ("SELF", "ALLY", "ENEMY", "NEUTRAL"):
            if rel == "SELF" and type(value) is int and type(player_id) is int and value != player_id:
                return "UNKNOWN_OWNER"
            if rel != "SELF" and type(value) is int and type(player_id) is int and value == player_id:
                return "UNKNOWN_OWNER"
            return rel
    if type(value) is int and type(player_id) is int and player_id > 0:
        if value == player_id:
            return "SELF"
        if value == 0:
            return "NEUTRAL"
    return "UNKNOWN_OWNER"


def age_class(confidence: Any, progress: Any, continuation_count: int | None,
              identity_reliable: bool) -> str:
    if not identity_reliable:
        return "UNKNOWN_AGE"
    if confidence == "NEW_TRACK" and type(progress) is int and progress == 0:
        return "NEWBORN"
    if continuation_count is None:
        return "UNKNOWN_AGE"
    if continuation_count >= 2:
        return "LONG_LIVED"
    if continuation_count == 1:
        return "PERSISTENT"
    return "UNKNOWN_AGE"


def _scope(raw: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (raw.get("document_id"), _fact(raw, "match_id").get("value"),
            _fact(raw, "player_id").get("value"))


def _endpoint_pair(force: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {"source": _fact(force, "source"), "target": _fact(force, "destination")}


def _force_summary(force: dict[str, Any], index: int, player_id: Any,
                   age: str = "UNKNOWN_AGE", reliable: bool = False) -> dict[str, Any]:
    ident = _fact(force, "id")
    confidence = _fact(force, "confidence")
    progress = _fact(force, "progress")
    owner = _fact(force, "owner")
    relation = _fact(force, "relation")
    identity_reliable = (reliable and ident.get("knowledge") == "DERIVED" and
        isinstance(ident.get("value"), str) and bool(ident["value"]) and
        confidence.get("value") in ("NEW_TRACK", "UNIQUE_CONTINUATION"))
    return {"force_index": index,
        "force_observer_id": ident.get("value") if identity_reliable else None,
        "identity_reliable": identity_reliable,
        "owner_class": owner_class(owner, relation, player_id),
        "owner_fact": owner, "relation_fact": relation,
        "age_class": age if identity_reliable else "UNKNOWN_AGE",
        "confidence": confidence, "progress": progress,
        "visibility": _fact(force, "visibility"),
        "endpoints": _endpoint_pair(force), "raw_force": force}


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _read_edge_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    coverage = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    pins = coverage["inputs"]["raw_files"]
    expected_gzip_hash = coverage["edge_audit"]["sha256"]
    if expected_gzip_hash != EXPECTED_EDGE_GZIP_SHA256 or sha256_file(EDGE_GZIP) != expected_gzip_hash:
        raise ValueError("EDGE_AUDIT_GZIP_PIN_MISMATCH")
    edges = []
    digest = hashlib.sha256()
    with gzip.open(EDGE_GZIP, "rb") as stream:
        for line in stream:
            digest.update(line)
            row = json.loads(line)
            if all(row.get(k) == v for k, v in TARGET_FILTER.items()):
                edges.append(row)
    if digest.hexdigest() != coverage["edge_audit"]["decompressed_sha256"]:
        raise ValueError("EDGE_AUDIT_DECOMPRESSED_PIN_MISMATCH")
    if len(edges) != EXPECTED_ENDPOINT_EDGES:
        raise ValueError(f"ENDPOINT_EDGE_DENOMINATOR_MISMATCH:{len(edges)}")
    return edges, {"coverage_json_sha256": sha256_file(COVERAGE_JSON),
        "edge_gzip_sha256": sha256_file(EDGE_GZIP), "edge_decompressed_sha256": digest.hexdigest(),
        "edge_rows_total": coverage["edge_audit"]["rows"], "endpoint_edge_rows": len(edges),
        "raw_pins": pins}


def _snapshot_record_minimal(raw: dict[str, Any], line: int,
                             age_by_index: dict[int, tuple[str, bool]],
                             retain_raw_force_indices: set[int] | None = None) -> dict[str, Any]:
    forces = raw.get("forces")
    rows = forces.get("value") if isinstance(forces, dict) else None
    if not isinstance(rows, list):
        return {"line": line, "sequence": raw.get("sequence"), "scope": list(_scope(raw)),
                "tick": _fact(raw, "tick").get("value"), "forces_shape_valid": False, "forces": []}
    player_id = _fact(raw, "player_id").get("value")
    summarized = [_force_summary(f, i, player_id, *age_by_index.get(i, ("UNKNOWN_AGE", False)))
                  for i, f in enumerate(rows)]
    retain_raw_force_indices = retain_raw_force_indices or set()
    for summary in summarized:
        if summary["force_index"] not in retain_raw_force_indices:
            summary.pop("raw_force", None)
    return {"line": line, "sequence": raw.get("sequence"), "scope": list(_scope(raw)),
        "tick": _fact(raw, "tick").get("value"), "sampled_at_ms": raw.get("sampled_at_ms"),
        "forces_shape_valid": True,
        "forces": summarized}


def _cohort_snapshot_summaries(path: Path, edge_rows: list[dict[str, Any]],
                               expected_hash: str) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    wanted_lines = set()
    wanted_force_indices: dict[int, set[int]] = collections.defaultdict(set)
    for edge in edge_rows:
        wanted_lines.add(edge["before_line"])
        wanted_lines.add(edge["after_line"])
        for force_index in _force_gap_fields(edge):
            wanted_force_indices[edge["before_line"]].add(force_index)
        for force_index in _force_gap_fields(edge, "after"):
            wanted_force_indices[edge["after_line"]].add(force_index)
    selected: dict[int, dict[str, Any]] = {}
    continuities: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    last_scope: tuple[Any, ...] | None = None
    last_tick: int | None = None
    run_index = 0
    previous_entities: dict[str, dict[str, Any]] = {}
    previous_count: dict[str, int] = {}
    physical_line = 0
    distinct_observations = 0
    identity_restarts = 0
    newborn_nonzero_progress = 0
    duplicates_skipped = 0
    with path.open("rb") as stream:
        for raw_bytes in stream:
            physical_line += 1
            digest.update(raw_bytes)
            try:
                raw = json.loads(raw_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                if physical_line in wanted_lines:
                    selected[physical_line] = {"line": physical_line, "parse_error": True, "forces": []}
                last_scope = None
                last_tick = None
                previous_entities = {}
                previous_count = {}
                run_index += 1
                continue
            scope = _scope(raw)
            tick = _fact(raw, "tick").get("value")
            if scope == last_scope and tick == last_tick:
                duplicates_skipped += 1
                if physical_line in wanted_lines:
                    # Edge references should normally point to the retained row;
                    # preserve a summary but do not use this poll for continuity.
                    selected[physical_line] = _snapshot_record_minimal(raw, physical_line, {},
                        wanted_force_indices.get(physical_line, set()))
                continue
            continuous = (scope == last_scope and type(tick) is int and type(last_tick) is int and
                          ((tick - last_tick) & 0xFFFF) == 1)
            if not continuous:
                run_index += 1
                previous_entities = {}
                previous_count = {}
            distinct_observations += 1
            forces_obj = raw.get("forces")
            force_rows = forces_obj.get("value") if isinstance(forces_obj, dict) else None
            age_by_index: dict[int, tuple[str, bool]] = {}
            current_entities: dict[str, dict[str, Any]] = {}
            if isinstance(force_rows, list):
                id_counts = collections.Counter(
                    _fact(force, "id").get("value") for force in force_rows
                    if isinstance(force, dict) and isinstance(_fact(force, "id").get("value"), str))
                player_id = _fact(raw, "player_id").get("value")
                scope_identity_valid = (isinstance(scope[0], str) and bool(scope[0]) and
                    isinstance(scope[1], str) and bool(scope[1]) and
                    type(scope[2]) is int and scope[2] > 0)
                for index, force in enumerate(force_rows):
                    if not isinstance(force, dict):
                        age_by_index[index] = ("UNKNOWN_AGE", False)
                        continue
                    ident = _fact(force, "id")
                    confidence = _fact(force, "confidence").get("value")
                    progress = _fact(force, "progress").get("value")
                    reliable = (ident.get("knowledge") == "DERIVED" and
                        isinstance(ident.get("value"), str) and bool(ident["value"]) and
                        id_counts.get(ident["value"]) == 1 and
                        confidence in ("NEW_TRACK", "UNIQUE_CONTINUATION") and scope_identity_valid)
                    id_value = ident.get("value") if reliable else None
                    identity_key = ("|".join(map(str, (*scope, id_value))) if id_value is not None else None)
                    prior = previous_entities.get(identity_key) if continuous and identity_key else None
                    prior_count = previous_count.get(identity_key) if prior else None
                    cont_count = ((prior_count + 1) if prior_count is not None else None)
                    if confidence == "NEW_TRACK" and progress == 0:
                        if prior:
                            age = "UNKNOWN_AGE"
                        else:
                            age = "NEWBORN"
                            cont_count = 0
                    else:
                        age = age_class(confidence, progress, cont_count, reliable)
                    if reliable and confidence == "NEW_TRACK":
                        identity_restarts += 1
                        if progress != 0:
                            newborn_nonzero_progress += 1
                    age_by_index[index] = (age, reliable)
                    current = _force_summary(force, index, player_id, age, reliable)
                    if identity_key:
                        current_entities[identity_key] = {"line": physical_line, "scope": scope,
                            "sequence": raw.get("sequence"),
                            "tick": tick, "summary": current,
                            "continuation_count": cont_count if cont_count is not None else 0}
                        if prior and continuous and type(tick) is int and type(prior.get("tick")) is int:
                            for endpoint_name in ("source", "target"):
                                old_fact = prior["summary"]["endpoints"][endpoint_name]
                                new_fact = current["endpoints"][endpoint_name]
                                if endpoint_field_status(old_fact) == "YES" and endpoint_field_status(new_fact) == "NO":
                                    continuities.append({"cohort": edge_rows[0]["cohort"] if edge_rows else path.stem,
                                        "identity_key_sha256": sha256_bytes(identity_key.encode("utf-8")),
                                        "from_sequence": prior.get("sequence"), "to_sequence": raw.get("sequence"),
                                        "from_tick": prior["tick"], "to_tick": tick,
                                        "from_line": prior["line"], "to_line": physical_line,
                                        "endpoint": endpoint_name,
                                        "from_value": old_fact.get("value"), "to_value": None,
                                        "from_provenance": old_fact.get("provenance"),
                                        "to_provenance": new_fact.get("provenance"),
                                        "reason": "same reliable id and continuous scope/tick changed from known to UNKNOWN"})
            if physical_line in wanted_lines:
                selected[physical_line] = _snapshot_record_minimal(raw, physical_line, age_by_index,
                    wanted_force_indices.get(physical_line, set()))
            last_scope, last_tick = scope, tick
            previous_entities, previous_count = current_entities, {
                identity: row["continuation_count"] for identity, row in current_entities.items()}
    actual_hash = digest.hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"SNAPSHOT_PIN_MISMATCH:{path.name}")
    return selected, continuities, {"path": path.relative_to(ROOT).as_posix(),
        "expected_sha256": expected_hash, "actual_sha256": actual_hash,
        "matches_pin": True, "physical_lines": physical_line,
        "distinct_first_observations": distinct_observations,
        "repeated_same_scope_tick_polls_skipped": duplicates_skipped,
        "reliable_new_track_records": identity_restarts,
        "new_track_nonzero_progress_records_not_called_newborn": newborn_nonzero_progress}


def _force_gap_fields(edge: dict[str, Any], readiness_stage: str = "before") -> dict[int, set[str]]:
    result: dict[int, set[str]] = collections.defaultdict(set)
    gap_key = "control_readiness_gaps" if readiness_stage == "before" else "after_input_readiness_gaps"
    for gap in edge.get(gap_key, []):
        parts = gap.split(":")
        if len(parts) == 3 and parts[0] == "force" and parts[1].isdigit() and parts[2] in ("source", "destination"):
            result[int(parts[1])].add(parts[2])
    return dict(result)


def _blocked_observation(edge: dict[str, Any]) -> tuple[str, int, int, dict[int, set[str]]]:
    # The gate actually reached is decisive. Executed edges passed before-state
    # conversion/step and can only be attributed to after-input readiness.
    if edge.get("comparison_execution") == "EXECUTED":
        after_gaps = _force_gap_fields(edge, "after")
        if after_gaps:
            return "AFTER", edge["after_line"], edge["after_sequence"], after_gaps
    else:
        before_gaps = _force_gap_fields(edge, "before")
        if before_gaps:
            return "BEFORE", edge["before_line"], edge["before_sequence"], before_gaps
    return "UNKNOWN_STAGE", edge["before_line"], edge["before_sequence"], {}


def _lineage_field(raw_fact: dict[str, Any], game_fact: dict[str, Any],
                   roundtrip_fact: dict[str, Any], readiness_reason: str | None,
                   blocked_observation_stage: str) -> dict[str, Any]:
    first_stage = "EARLIEST_RETAINED_CANONICAL_OBSERVER_OUTPUT" if endpoint_field_status(raw_fact) == "NO" else "UNKNOWN"
    return {"RAW_HAS_ENDPOINT_AT_RETAINED_OBSERVER_OUTPUT": endpoint_field_status(raw_fact),
        "EXTRACTOR_HAS_ENDPOINT": "UNKNOWN",
        "GAMESTATE_HAS_ENDPOINT": endpoint_field_status(game_fact),
        "SIMSTATE_HAS_ENDPOINT": "UNKNOWN_NOT_RUN",
        "raw_retained_observer_output": raw_fact,
        "upstream_raw_extractor_input": {"value": None, "knowledge": "UNKNOWN",
            "reason": "no contemporaneous paired extractor input is retained for this cohort/sequence"},
        "extractor_output": {"value": None, "knowledge": "UNKNOWN",
            "reason": "no contemporaneous separately serialized extractor output is retained"},
        "canonical_gamestate_after_restore": game_fact,
        "serialization_roundtrip": roundtrip_fact,
        "simulationstate_mapping": {"value": None, "status": "NOT_RUN",
            "reason": ("before-state readiness refused before construction" if blocked_observation_stage == "BEFORE" else
                       "after-state readiness refused before observed after-state construction" if blocked_observation_stage == "AFTER" else
                       "endpoint gate stage could not be aligned")},
        "blocked_observation_stage": blocked_observation_stage,
        "readiness_reason": readiness_reason,
        "first_proven_boundary": first_stage,
        "upstream_first_loss_layer": "UNRESOLVED"}


def _entity_audit(edge: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
                  force_row: dict[str, Any], gap_fields: set[str],
                  blocked_observation_stage: str, blocked_line: int, blocked_sequence: int) -> dict[str, Any]:
    index = force_row["force_index"]
    endpoints = force_row["endpoints"]
    raw_source, raw_target = endpoints["source"], endpoints["target"]
    readiness = (edge.get("control_readiness_gaps", []) if blocked_observation_stage == "BEFORE"
                 else edge.get("after_input_readiness_gaps", []))
    source_gap = f"force:{index}:source" in readiness
    target_gap = f"force:{index}:destination" in readiness
    raw_force = force_row["raw_force"]
    restored = entity_from_dict(Force, raw_force)
    roundtrip = entity_from_dict(Force, dataclasses.asdict(restored))
    as_fact = lambda fact: {"field_present": True, "value": fact.value,
        "knowledge": fact.knowledge.value, "provenance": fact.source,
        "observed_at_ms": fact.observed_at_ms, "fact_shape_valid": True}
    source_game, target_game = as_fact(restored.source), as_fact(restored.destination)
    source_rt, target_rt = as_fact(roundtrip.source), as_fact(roundtrip.destination)
    game_known = endpoint_field_status(source_game) == "YES" or endpoint_field_status(target_game) == "YES"
    raw_known = endpoint_field_status(raw_source) == "YES" or endpoint_field_status(raw_target) == "YES"
    stage_evidence = {"raw_extractor_has_endpoint": None, "extractor_output_has_endpoint": None,
        "canonical_gamestate_has_endpoint": None, "canonical_serialized_has_endpoint": raw_known,
        "gamestate_after_restore_has_endpoint": game_known, "simstate_has_endpoint": None,
        "endpoint_present_but_readiness_rejected": False,
        "current_player_visibility_excludes_endpoint": False}
    classification, reason = classify_lineage(raw_source, raw_target, stage_evidence)
    if (source_gap and endpoint_field_status(raw_source) == "YES") or (
            target_gap and endpoint_field_status(raw_target) == "YES"):
        classification, reason = "E_PROVENANCE_OR_READINESS_REJECT", "endpoint value present but listed in readiness gap (inconsistent evidence; retain as E candidate)"
    relation = force_row["relation_fact"]
    owner = force_row["owner_fact"]
    identity_key_hash = None
    if force_row.get("identity_reliable") and force_row.get("force_observer_id"):
        scope_value = (after if blocked_observation_stage == "AFTER" else before).get("scope") or []
        identity_key = "|".join(map(str, (*scope_value, force_row["force_observer_id"])))
        identity_key_hash = sha256_bytes(identity_key.encode("utf-8"))
    fields = {"source": _lineage_field(raw_source, source_game, source_rt,
                    f"force:{index}:source" if source_gap else None, blocked_observation_stage),
              "target": _lineage_field(raw_target, target_game, target_rt,
                    f"force:{index}:destination" if target_gap else None, blocked_observation_stage)}
    missing_fields = [name for name, fact in (("source", raw_source), ("target", raw_target))
                      if endpoint_field_status(fact) == "NO"]
    roundtrip_preserved = source_game == source_rt and target_game == target_rt
    if raw_known and not game_known:
        classification, reason = "C_GAMESTATE_LOSS", "retained canonical endpoint did not survive GameState restoration"
    elif game_known and not roundtrip_preserved:
        classification, reason = "C_GAMESTATE_LOSS", "canonical Force endpoint changed across serialization roundtrip"
    return {"cohort": edge["cohort"], "split": edge["split"],
        "edge_index": edge["edge_index"], "before_line": edge["before_line"],
        "after_line": edge["after_line"], "before_sequence": edge["before_sequence"],
        "after_sequence": edge["after_sequence"], "before_tick": edge["before_tick"],
        "after_tick": edge["after_tick"], "scope": before.get("scope"),
        "blocked_observation_stage": blocked_observation_stage,
        "blocked_observation_line": blocked_line, "blocked_observation_sequence": blocked_sequence,
        "force_index": index,
        "force_observer_id": None,
        "identity_reliable": force_row.get("identity_reliable", False),
        "identity_key_sha256": identity_key_hash,
        "owner_class": force_row["owner_class"], "owner_fact": owner,
        "relation_fact": relation, "age_class": force_row["age_class"],
        "visibility": force_row["visibility"], "confidence": force_row["confidence"],
        "progress": force_row["progress"], "blocked_fields_from_readiness": sorted(gap_fields),
        "missing_endpoint_fields_at_retained_observation": missing_fields,
        "endpoint_lineage": fields,
        "required_stage_presence": {
            "RAW_HAS_SOURCE": fields["source"]["RAW_HAS_ENDPOINT_AT_RETAINED_OBSERVER_OUTPUT"],
            "RAW_HAS_TARGET": fields["target"]["RAW_HAS_ENDPOINT_AT_RETAINED_OBSERVER_OUTPUT"],
            "EXTRACTOR_HAS_SOURCE": "UNKNOWN", "EXTRACTOR_HAS_TARGET": "UNKNOWN",
            "GAMESTATE_HAS_SOURCE": fields["source"]["GAMESTATE_HAS_ENDPOINT"],
            "GAMESTATE_HAS_TARGET": fields["target"]["GAMESTATE_HAS_ENDPOINT"],
            "SIMSTATE_HAS_SOURCE": "UNKNOWN_NOT_RUN", "SIMSTATE_HAS_TARGET": "UNKNOWN_NOT_RUN"},
        "entity_dataclass_restoration": {"status": "PRESERVED" if roundtrip_preserved else "CHANGED",
            "raw_force_row_to_canonical_Force": True,
            "canonical_Force_to_dataclass_dict_to_Force": True,
            "scope_note": "reproduces current mapping on retained serialized record; not evidence about historic extractor output"},
        "final_classification": classification, "classification_reason": reason,
        "root_cause_identified": classification not in ("A_RAW_ABSENT", "G_UNCLASSIFIED"),
        "FIRST_LOSS_LAYER": ("UNRESOLVED_UPSTREAM; absent only at earliest retained canonical observer output"
            if classification == "A_RAW_ABSENT" else
            "UNRESOLVED" if classification == "G_UNCLASSIFIED" else classification),
        "upstream_raw_extractor_truth": "UNKNOWN",
        "information_ceiling_proven": False,
        "readiness_gaps_at_blocked_observation": readiness,
        "before_state_conversion_and_step": ("EXECUTED_BEFORE_AFTER_READINESS_REFUSAL"
            if edge.get("comparison_execution") == "EXECUTED" and blocked_observation_stage == "AFTER"
            else "NOT_RUN_BEFORE_READINESS_REFUSAL" if blocked_observation_stage == "BEFORE" else "UNKNOWN"),
        "after_state_conversion": "NOT_RUN" if blocked_observation_stage == "AFTER" else "NOT_REQUIRED_FOR_BEFORE_REFUSAL",
        "first_loss_layer_upstream": "UNRESOLVED_BEFORE_OR_AT_EARLIEST_RETAINED_CANONICAL_OBSERVER_OUTPUT"}


def _cohort_stats(edges: list[dict[str, Any]], entities: list[dict[str, Any]],
                  continuity: list[dict[str, Any]]) -> dict[str, Any]:
    by_edge: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for entity in entities:
        by_edge[(entity["cohort"], entity["edge_index"])].append(entity)
    result = {}
    for cohort in sorted({e["cohort"] for e in edges}):
        cohort_edges = [e for e in edges if e["cohort"] == cohort]
        cohort_entities = [x for x in entities if x["cohort"] == cohort]
        counts = [len(by_edge[(cohort, e["edge_index"])]) for e in cohort_edges]
        owners = collections.Counter(e["owner_class"] for e in cohort_entities)
        ages = collections.Counter(e["age_class"] for e in cohort_entities)
        classes = collections.Counter(e["final_classification"] for e in cohort_entities)
        ids: dict[str, dict[str, Any]] = {}
        for entity in cohort_entities:
            key = entity.get("identity_key_sha256")
            if key and entity.get("identity_reliable"):
                ids.setdefault(key, entity)
        unique_owner = collections.Counter(x["owner_class"] for x in ids.values())
        unique_age = collections.Counter(x["age_class"] for x in ids.values())
        unique_classes = collections.Counter(x["final_classification"] for x in ids.values())
        owner_by_class = collections.Counter(f"{x['owner_class']}|{x['final_classification']}" for x in cohort_entities)
        owner_by_age = collections.Counter(f"{x['owner_class']}|{x['age_class']}" for x in cohort_entities)
        firstloss = collections.Counter()
        for entity in cohort_entities:
            for field in entity["endpoint_lineage"].values():
                firstloss[field["first_proven_boundary"]] += 1
        result[cohort] = {"split": cohort_edges[0]["split"] if cohort_edges else None,
            "endpoint_blocked_edges": len(cohort_edges), "blocked_entity_edge_occurrences": len(cohort_entities),
            "unique_reliable_track_identities": len(ids),
            "unidentified_or_unreliable_entity_occurrences": sum(not e["identity_reliable"] for e in cohort_entities),
            "owner_occurrences": dict(sorted(owners.items())), "age_occurrences": dict(sorted(ages.items())),
            "classification_occurrences": dict(sorted(classes.items())),
            "owner_by_class_occurrences": dict(sorted(owner_by_class.items())),
            "owner_by_age_occurrences": dict(sorted(owner_by_age.items())),
            "unique_owner_first_blocked_occurrence": dict(sorted(unique_owner.items())),
            "unique_age_first_blocked_occurrence": dict(sorted(unique_age.items())),
            "unique_class_first_blocked_occurrence": dict(sorted(unique_classes.items())),
            "endpoint_field_first_proven_boundary_occurrences": dict(sorted(firstloss.items())),
            "blocked_entity_count_per_edge": {"mean": sum(counts)/len(counts) if counts else None,
                "median": _percentile(counts, .5), "p75": _percentile(counts, .75),
                "p90": _percentile(counts, .90), "p95": _percentile(counts, .95),
                "max": max(counts) if counts else None,
                "edges_1": sum(c == 1 for c in counts), "edges_2": sum(c == 2 for c in counts),
                "edges_3plus": sum(c >= 3 for c in counts), "histogram": dict(sorted(collections.Counter(counts).items()))},
            "known_to_unknown_endpoint_continuities": sum(x["cohort"] == cohort for x in continuity)}
    return result


def run_analysis(output_json: Path = DEFAULT_JSON, output_gzip: Path = DEFAULT_GZIP) -> dict[str, Any]:
    edges, pins = _read_edge_audit()
    coverage = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    raw_pins = pins["raw_pins"]
    by_cohort: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for edge in edges:
        by_cohort[edge["cohort"]].append(edge)
    cohorts_meta: dict[str, dict[str, Any]] = {}
    snapshots: dict[tuple[str, int], dict[str, Any]] = {}
    continuity = []
    split_by_cohort = {value["cohort"]: value["split"] for value in raw_pins.values()}
    ordered_cohorts = sorted(by_cohort, key=lambda c: (0 if split_by_cohort.get(c) == "development" else 1, c))
    method_hash_before = sha256_bytes(json.dumps(METHOD, sort_keys=True, separators=(",", ":")).encode())
    tool_hash_at_run_start = sha256_file(Path(__file__).resolve())
    development_freeze = None
    # Development recordings establish the deterministic rules and freeze the
    # exact method hash before holdout rows are classified.
    for cohort in ordered_cohorts:
        pin_item = next((v for k, v in raw_pins.items() if v.get("cohort") == cohort), None)
        if not pin_item or not pin_item.get("matches_manifest"):
            raise ValueError(f"RAW_SNAPSHOT_PIN_NOT_ACCEPTED:{cohort}")
        if pin_item["split"] == "holdout" and development_freeze is None:
            dev_meta = [item for item in cohorts_meta.values() if item["split"] == "development"]
            if len(dev_meta) != 3:
                raise ValueError("DEVELOPMENT_PASS_INCOMPLETE_BEFORE_HOLDOUT")
            freeze_hash = sha256_file(Path(__file__).resolve())
            if freeze_hash != tool_hash_at_run_start:
                raise RuntimeError("TOOL_CHANGED_BEFORE_HOLDOUT")
            development_freeze = {"completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "tool_sha256_at_run_start_and_freeze": freeze_hash,
                "method_sha256": method_hash_before,
                "development_recordings_fully_hashed_and_parsed_before_holdout": True,
                "development_endpoint_edge_rows": sum(x["endpoint_edges_in_audit"] for x in dev_meta),
                "holdout_started_after_freeze": True,
                "outcome_dependent_threshold_tuning": False}
        rel = next(k for k, v in raw_pins.items() if v.get("cohort") == cohort)
        path = ROOT / Path(rel)
        selected, cont, meta = _cohort_snapshot_summaries(path, by_cohort[cohort], pin_item["expected_sha256"])
        meta["cohort"] = cohort
        meta["split"] = pin_item["split"]
        meta["endpoint_edges_in_audit"] = len(by_cohort[cohort])
        meta["method_hash"] = method_hash_before
        meta["analysis_order"] = "DEVELOPMENT_RULE_FREEZE" if pin_item["split"] == "development" else "FROZEN_HOLDOUT_APPLY"
        cohorts_meta[cohort] = meta
        for line, record in selected.items():
            snapshots[(cohort, line)] = record
        continuity.extend(cont)
        if pin_item["split"] == "development":
            meta["development_rules_frozen_before_holdout"] = True
    method_hash_after = sha256_bytes(json.dumps(METHOD, sort_keys=True, separators=(",", ":")).encode())
    if method_hash_before != method_hash_after:
        raise RuntimeError("METHOD_CHANGED_DURING_DEVELOPMENT_HOLDOUT_ANALYSIS")

    entity_rows: list[dict[str, Any]] = []
    edge_rows_out = []
    consistency = collections.Counter()
    for edge in edges:
        before = snapshots.get((edge["cohort"], edge["before_line"]))
        after = snapshots.get((edge["cohort"], edge["after_line"]))
        if not before or not after or before.get("parse_error") or after.get("parse_error"):
            edge_rows_out.append({"cohort": edge["cohort"], "edge_index": edge["edge_index"],
                "before_sequence": edge["before_sequence"], "after_sequence": edge["after_sequence"],
                "blocked_entities": None, "lineage_status": "G_UNCLASSIFIED_MISSING_PINNED_RECORD"})
            continue
        if before.get("sequence") != edge["before_sequence"] or after.get("sequence") != edge["after_sequence"]:
            raise ValueError(f"EDGE_SEQUENCE_LINE_MISMATCH:{edge['cohort']}:{edge['edge_index']}")
        blocked_stage, blocked_line, blocked_sequence, gap_by_force = _blocked_observation(edge)
        blocked_observation = snapshots.get((edge["cohort"], blocked_line))
        summaries = {x["force_index"]: x for x in (blocked_observation or {}).get("forces", [])}
        per_edge = []
        for index in sorted(set(summaries) | set(gap_by_force)):
            force = summaries.get(index)
            if force is None:
                force = {"force_index": index, "force_observer_id": None,
                    "identity_reliable": False, "identity_key_sha256": None,
                    "owner_class": "UNKNOWN_OWNER", "owner_fact": {"value": None, "knowledge": "UNKNOWN", "provenance": "force row unavailable"},
                    "relation_fact": {"value": None, "knowledge": "UNKNOWN", "provenance": "force row unavailable"},
                    "age_class": "UNKNOWN_AGE", "confidence": {"value": None, "knowledge": "UNKNOWN"},
                    "progress": {"value": None, "knowledge": "UNKNOWN"},
                    "visibility": {"value": None, "knowledge": "UNKNOWN"},
                    "endpoints": {"source": {"field_present": False, "value": None, "knowledge": "UNKNOWN", "provenance": "row unavailable", "fact_shape_valid": False},
                                  "target": {"field_present": False, "value": None, "knowledge": "UNKNOWN", "provenance": "row unavailable", "fact_shape_valid": False}}}
            facts = force["endpoints"]
            missing = {name for name, fact in facts.items() if endpoint_field_status(fact) == "NO"}
            # Count the blocked entity once even when both fields are absent.
            if not missing and not gap_by_force.get(index):
                continue
            raw_force = None
            # Rehydrate only the selected Force row to test the canonical mapping;
            # the original raw record stays bounded to this selected entity.
            # Preserve row values in the summary and use those field facts below.
            raw_force_row = force.get("_raw_force")
            if raw_force_row is None:
                # Set by the selected-line collector for lineage evidence.
                raw_force_row = force.get("raw_force")
            if raw_force_row is None:
                # A missing raw entity row cannot be called an extractor loss.
                entity = {"cohort": edge["cohort"], "split": edge["split"],
                    "edge_index": edge["edge_index"], "before_line": edge["before_line"],
                    "after_line": edge["after_line"], "before_sequence": edge["before_sequence"],
                    "after_sequence": edge["after_sequence"], "force_index": index,
                    "force_observer_id": force.get("force_observer_id"),
                    "identity_reliable": force.get("identity_reliable", False),
                    "identity_key_sha256": force.get("identity_key_sha256"),
                    "owner_class": force["owner_class"], "age_class": force["age_class"],
                    "final_classification": "G_UNCLASSIFIED", "classification_reason": "selected force source row unavailable",
                    "endpoint_lineage": {}, "missing_endpoint_fields_at_retained_observation": sorted(missing),
                    "blocked_fields_from_readiness": sorted(gap_by_force.get(index, set())),
                    "upstream_raw_extractor_truth": "UNKNOWN", "information_ceiling_proven": False}
            else:
                # The collector attaches exact fields just for this one entity.
                roundtrip = force.get("roundtrip", {})
                owner = force["owner_fact"]
                relation = force["relation_fact"]
                temp = {**force, "raw_force": raw_force_row, "roundtrip": roundtrip,
                    "owner_fact": owner, "relation_fact": relation}
                entity = _entity_audit(edge, before, after, temp, gap_by_force.get(index, set()),
                    blocked_stage, blocked_line, blocked_sequence)
            readiness_name = {"source": "source", "target": "destination"}
            entity["readiness_gap_matches_missing_endpoint"] = all(
                (readiness_name[field] in gap_by_force.get(index, set())) for field in missing)
            if not entity.get("endpoint_lineage"):
                entity["endpoint_lineage"] = {name: _lineage_field(facts[name], facts[name], facts[name],
                    f"force:{index}:{readiness_name[name]}" if readiness_name[name] in gap_by_force.get(index, set()) else None,
                    blocked_stage) for name in ("source", "target")}
                entity["final_classification"] = "G_UNCLASSIFIED"
                entity["classification_reason"] = "readiness names a force endpoint but matching retained force row is unavailable"
                entity["blocked_observation_stage"] = blocked_stage
                entity["blocked_observation_line"] = blocked_line
                entity["blocked_observation_sequence"] = blocked_sequence
                entity["first_loss_layer_upstream"] = "UNRESOLVED"
                entity["required_stage_presence"] = {
                    "RAW_HAS_SOURCE": facts["source"].get("knowledge", "UNKNOWN"),
                    "RAW_HAS_TARGET": facts["target"].get("knowledge", "UNKNOWN"),
                    "EXTRACTOR_HAS_SOURCE": "UNKNOWN", "EXTRACTOR_HAS_TARGET": "UNKNOWN",
                    "GAMESTATE_HAS_SOURCE": "UNKNOWN_NOT_RUN", "GAMESTATE_HAS_TARGET": "UNKNOWN_NOT_RUN",
                    "SIMSTATE_HAS_SOURCE": "UNKNOWN_NOT_RUN", "SIMSTATE_HAS_TARGET": "UNKNOWN_NOT_RUN"}
            consistency["blocked_force_entity_occurrences"] += 1
            consistency["raw_missing_fields"] += len(missing)
            consistency["gate_fields_match_missing_fields"] += sum(
                readiness_name[field] in gap_by_force.get(index, set()) for field in missing)
            consistency["unmatched_readiness_missing_endpoint_entity"] += int(
                not entity["readiness_gap_matches_missing_endpoint"])
            entity_rows.append(entity)
            per_edge.append(entity)
        edge_rows_out.append({"cohort": edge["cohort"], "split": edge["split"],
            "edge_index": edge["edge_index"], "before_line": edge["before_line"],
            "after_line": edge["after_line"], "before_sequence": edge["before_sequence"],
            "after_sequence": edge["after_sequence"], "before_tick": edge["before_tick"],
            "after_tick": edge["after_tick"], "whole_world_first_blocker": edge["primary_category"] + ":" + edge["primary_blocker"],
            "blocked_observation_stage": blocked_stage,
            "readiness_reasons": (edge.get("control_readiness_gaps", []) if blocked_stage == "BEFORE" else
                                  edge.get("after_input_readiness_gaps", []) if blocked_stage == "AFTER" else []),
            "blocked_entity_count": len(per_edge),
            "blocked_entity_identity_hashes": [x.get("identity_key_sha256") for x in per_edge if x.get("identity_key_sha256")],
            "lineage_status": "ENTITY_DETAIL_IN_GZIP"})

    # Rebuild distribution summaries after enrichment (class labels are fixed).
    cohort_stats = _cohort_stats(edges, entity_rows, continuity)
    owner_counts = collections.Counter(x["owner_class"] for x in entity_rows)
    age_counts = collections.Counter(x["age_class"] for x in entity_rows)
    class_counts = collections.Counter(x["final_classification"] for x in entity_rows)
    unique: dict[str, dict[str, Any]] = {}
    for entity in entity_rows:
        key = entity.get("identity_key_sha256")
        if key and entity.get("identity_reliable"):
            unique.setdefault(key, entity)
    unique_owner = collections.Counter(x["owner_class"] for x in unique.values())
    unique_age = collections.Counter(x["age_class"] for x in unique.values())
    unique_class = collections.Counter(x["final_classification"] for x in unique.values())
    owner_by_class = collections.Counter(f"{x['owner_class']}|{x['final_classification']}" for x in entity_rows)
    owner_by_age = collections.Counter(f"{x['owner_class']}|{x['age_class']}" for x in entity_rows)
    unique_owner_by_class = collections.Counter(f"{x['owner_class']}|{x['final_classification']}" for x in unique.values())
    unique_owner_by_age = collections.Counter(f"{x['owner_class']}|{x['age_class']}" for x in unique.values())
    edge_counts = [x["blocked_entity_count"] for x in edge_rows_out if type(x.get("blocked_entity_count")) is int]
    by_endpoint_field = collections.Counter()
    for entity in entity_rows:
        for field_name, field in entity.get("endpoint_lineage", {}).items():
            by_endpoint_field[field["first_proven_boundary"]] += 1
    positive_be = sum(class_counts.get(x, 0) for x in (
        "B_EXTRACTOR_LOSS", "C_GAMESTATE_LOSS", "D_SIMSTATE_LOSS", "E_PROVENANCE_OR_READINESS_REJECT"))
    stop = {"recoverable_B_to_E_positive_evidence_occurrences": positive_be,
        "B_to_E_positive_identifiability_rate": positive_be / len(entity_rows) if entity_rows else None,
        "recoverability_rate_identified_by_positive_lineage_evidence": None,
        "rate_status": "observed positive-evidence rate is not the true recoverable rate; upstream artifacts are not retained",
        "20_percent_recoverable_stop_condition": "UNASSESSABLE; true B-E recoverability denominator is unavailable",
        "F_true_information_ceiling_occurrences": class_counts.get("F_TRUE_INFORMATION_CEILING", 0),
        "deepening_decision": "NEEDS_MORE_EVIDENCE",
        "reason": "the pinned retained-observation boundary proves endpoint absence but has no contemporaneous upstream extractor payload; neither recoverable pipeline loss nor normal-player information ceiling is established"}
    result = {"status": "CANDIDATE_ENDPOINT_LINEAGE_ANALYSIS_ONLY",
        "analysis_version": "endpoint-lineage-v1", "formal_credit": 0,
        "head_state": _git_state(),
        "method": {**METHOD, "sha256": method_hash_before,
            "development_cohorts": [c for c, x in cohorts_meta.items() if x["split"] == "development"],
            "holdout_cohorts": [c for c, x in cohorts_meta.items() if x["split"] == "holdout"],
            "development_method_frozen_before_holdout": method_hash_before == method_hash_after,
            "method_hash_at_holdout": method_hash_after,
            "development_freeze": development_freeze,
            "tool_sha256_at_holdout": sha256_file(Path(__file__).resolve())},
        "pins": pins, "cohorts": cohort_stats,
        "recording_checks": cohorts_meta,
        "denominators": {"endpoint_blocked_edges": len(edges),
            "blocked_force_entity_edge_occurrences": len(entity_rows),
            "unique_reliable_document_match_player_track_identities": len(unique),
            "unidentified_or_unreliable_entity_edge_occurrences": sum(not x.get("identity_reliable") for x in entity_rows),
            "edges_with_one_blocked_entity": sum(x == 1 for x in edge_counts),
            "edges_with_two_blocked_entities": sum(x == 2 for x in edge_counts),
            "edges_with_three_or_more_blocked_entities": sum(x >= 3 for x in edge_counts),
            "edges_missing_source_record": sum(x.get("lineage_status") == "G_UNCLASSIFIED_MISSING_PINNED_RECORD" for x in edge_rows_out)},
        "owner_distribution_entity_edge_occurrences": dict(sorted(owner_counts.items())),
        "owner_by_lineage_class_entity_edge_occurrences": dict(sorted(owner_by_class.items())),
        "owner_by_age_entity_edge_occurrences": dict(sorted(owner_by_age.items())),
        "age_distribution_entity_edge_occurrences": dict(sorted(age_counts.items())),
        "lineage_class_distribution_entity_edge_occurrences": dict(sorted(class_counts.items())),
        "unique_identity_first_blocked_occurrence_owner_distribution": dict(sorted(unique_owner.items())),
        "unique_identity_first_blocked_occurrence_age_distribution": dict(sorted(unique_age.items())),
        "unique_identity_first_blocked_occurrence_class_distribution": dict(sorted(unique_class.items())),
        "unique_identity_owner_by_class_first_blocked_occurrence": dict(sorted(unique_owner_by_class.items())),
        "unique_identity_owner_by_age_first_blocked_occurrence": dict(sorted(unique_owner_by_age.items())),
        "endpoint_field_first_proven_boundary_occurrences": dict(sorted(by_endpoint_field.items())),
        "blocked_entities_per_edge": {"mean": sum(edge_counts)/len(edge_counts) if edge_counts else None,
            "median": _percentile(edge_counts, .5), "p75": _percentile(edge_counts, .75),
            "p90": _percentile(edge_counts, .90), "p95": _percentile(edge_counts, .95),
            "max": max(edge_counts) if edge_counts else None,
            "histogram": {str(k): v for k, v in sorted(collections.Counter(edge_counts).items())}},
        "known_to_unknown_endpoint_continuities": {"count": len(continuity),
            "by_cohort": dict(collections.Counter(x["cohort"] for x in continuity)),
            "records_in_entity_gzip": True},
        "consistency_checks": dict(consistency),
        "other_runtime_lineage_artifacts": _review_other_artifacts(cohorts_meta),
        "recoverability_and_stop_condition": stop,
        "limits": {"saved_snapshot_files_are_serialized_canonical_observer_outputs": True,
            "upstream_raw_extractor_input_available_for_exact_cohort_sequence": False,
            "SimulationState_conversion_for_endpoint_blocked_edges": "NOT_RUN: whole-state readiness refused before constructor",
            "normal_player_information_ceiling_proven": False,
            "pipeline_loss_proven": False,
            "F_not_inferred_from_unknown": True,
            "whole_world_endpoint_edge_denominator_is_not_unlock_count": True,
            "factorized_coverage_and_all_blocker_sets": "NOT_IN_THIS_ENDPOINT_LINEAGE_TOOL; no independent support asserted"},
        "per_edge_summary_records": edge_rows_out,
        "entity_audit_gzip": {"path": output_gzip.relative_to(ROOT).as_posix() if output_gzip.is_relative_to(ROOT) else str(output_gzip),
            "format": "one JSON object per blocked entity-edge incidence; gz mtime=0",
            "rows": len(entity_rows), "sha256": None, "decompressed_sha256": None},
        "source_sha256": {"tools/v2_endpoint_lineage.py": sha256_file(Path(__file__).resolve()),
            "docs/V2_M2A_COVERAGE_DENOMINATOR.json": pins["coverage_json_sha256"],
            "tests/fixtures/v2/coverage-denominator-edges.jsonl.gz": pins["edge_gzip_sha256"]}}
    output_gzip.parent.mkdir(parents=True, exist_ok=True)
    decompressed_digest = hashlib.sha256()
    with output_gzip.open("wb") as raw_out:
        with gzip.GzipFile(fileobj=raw_out, mode="wb", filename="", mtime=0, compresslevel=9) as out:
            for entity in entity_rows:
                line = (json.dumps(entity, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                decompressed_digest.update(line)
                out.write(line)
    result["entity_audit_gzip"]["sha256"] = sha256_file(output_gzip)
    result["entity_audit_gzip"]["decompressed_sha256"] = decompressed_digest.hexdigest()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _review_other_artifacts(cohorts_meta: dict[str, Any]) -> dict[str, Any]:
    # Restrict discovery to already retained observer/capture artifacts; never
    # inspect transport payloads or read hidden/client-private state.
    candidates = [ROOT / "runtime/research/v2/first-raw.json",
        ROOT / "runtime/research/v2/snapshots.jsonl",
        ROOT / "runtime/research/v2/lifecycle-rows-66df0cdafc26.jsonl",
        ROOT / "runtime/research/v2/transport-rows-000fe06516c1.jsonl",
        ROOT / "runtime/research/v2/mainline-preflight.json",
        ROOT / "runtime/research/v2/controlled-transition-77636cad4e97.jsonl"]
    reviewed = []
    for path in candidates:
        if not path.exists():
            reviewed.append({"path": path.relative_to(ROOT).as_posix(), "present": False,
                "usable_as_paired_upstream_endpoint_stage": False})
            continue
        try:
            if path.suffix == ".jsonl":
                with path.open("r", encoding="utf-8") as stream:
                    sample = json.loads(next(stream))
            else:
                sample = json.loads(path.read_text(encoding="utf-8"))
            keys = sorted(sample.keys()) if isinstance(sample, dict) else []
            row = {"path": path.relative_to(ROOT).as_posix(), "present": True,
                "sha256": sha256_file(path), "sample_top_level_keys": keys,
                "has_canonical_force_collection": "forces" in sample,
                "has_document_sequence_scope": all(k in sample for k in ("document_id", "match_id", "sequence")),
                "same_pinned_cohort_scope_and_sequence_proven": False,
                "usable_as_paired_upstream_endpoint_stage": False}
            reviewed.append(row)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, StopIteration) as exc:
            reviewed.append({"path": path.relative_to(ROOT).as_posix(), "present": True,
                "sha256": sha256_file(path), "review_status": "NOT_PARSEABLE_AS_SNAPSHOT", "error_type": type(exc).__name__,
                "usable_as_paired_upstream_endpoint_stage": False})
    return {"policy": "no other runtime artifact is paired unless document/match/player/tick/sequence and source pin prove contemporaneous legal current-view identity",
        "reviewed_candidates": reviewed,
        "paired_upstream_extractors_found": 0,
        "claim_scope": "bounded review of named candidate snapshots/observer outputs; not proof no such artifact exists anywhere outside these reviewed paths"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-gzip", type=Path, default=DEFAULT_GZIP)
    args = parser.parse_args()
    result = run_analysis(args.output_json, args.output_gzip)
    print(json.dumps({"status": result["status"], "denominators": result["denominators"],
        "owner_distribution": result["owner_distribution_entity_edge_occurrences"],
        "age_distribution": result["age_distribution_entity_edge_occurrences"],
        "lineage_classes": result["lineage_class_distribution_entity_edge_occurrences"],
        "recoverability": result["recoverability_and_stop_condition"],
        "gzip_sha256": result["entity_audit_gzip"]["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
