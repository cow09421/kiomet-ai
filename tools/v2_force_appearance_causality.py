"""Bounded source-causality analysis for accepted force-appearance edges.

The fixed candidate universe is the committed coverage-denominator edge gzip.
Each event is evaluated only from its prebirth and birth observations plus
strictly earlier same-recording observations. No game/client code is run.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

EDGE_FIXTURE = ROOT / "tests/fixtures/v2/coverage-denominator-edges.jsonl.gz"
COVERAGE_REPORT = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
OUTPUT = ROOT / "runtime/research/v2/force-appearance-causality-candidate.json"
ROWS_GZIP = ROOT / "runtime/research/v2/force-appearance-causality-candidates.jsonl.gz"
ANALYSIS_VERSION = "force-appearance-causality-v1"
APPEARANCE_LABEL = "FORCE_TRACK_APPEARANCE_CANDIDATE_CAUSE_UNKNOWN"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state() -> dict[str, Any]:
    prefix = ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet"]

    def read(*args: str) -> str:
        return subprocess.run(prefix + list(args), cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.rstrip("\r\n")

    status = read("status", "--porcelain=v1", "--untracked-files=all")
    return {"head": read("rev-parse", "HEAD"), "branch": read("branch", "--show-current"),
            "dirty": bool(status), "status_porcelain": status.splitlines()}


def _value(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) and "value" in fact else None


def _known(fact: Any) -> bool:
    return (isinstance(fact, dict) and _value(fact) is not None and
            fact.get("knowledge") not in (None, "UNKNOWN"))


def _vector(fact: Any) -> list[int] | None:
    if not _known(fact):
        return None
    value = _value(fact)
    pairs = value.get("counts") if isinstance(value, dict) else None
    if not isinstance(pairs, list):
        return None
    counts: dict[int, int] = {}
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or
                pair[0] in counts or pair[1] < 0):
            return None
        counts[pair[0]] = pair[1]
    return [counts[i] for i in range(10)] if set(counts) == set(range(10)) else None


def _rows(record: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    raw = record.get(key)
    values = _value(raw) if key == "forces" else raw
    if (not isinstance(values, list) or
            (key == "forces" and isinstance(raw, dict) and raw.get("knowledge") == "UNKNOWN") or
            not all(isinstance(item, dict) for item in values)):
        return None
    return values


def _scope(record: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (record.get("document_id"), _value(record.get("match_id")),
            _value(record.get("player_id")))


def _tick(record: dict[str, Any]) -> int | None:
    value = _value(record.get("tick"))
    return value if type(value) is int else None


def _consecutive(before: dict[str, Any], after: dict[str, Any]) -> bool:
    a, b = _tick(before), _tick(after)
    return (_scope(before) == _scope(after) and a is not None and b is not None and
            ((b - a) & 0xFFFF) == 1)


def _tower_map(record: dict[str, Any]) -> dict[int, dict[str, Any]] | None:
    towers = _rows(record, "towers")
    if towers is None:
        return None
    result: dict[int, dict[str, Any]] = {}
    for tower in towers:
        ident = tower.get("id")
        if type(ident) is not int or ident in result:
            return None
        result[ident] = tower
    return result


def _force_id(force: dict[str, Any]) -> str | None:
    value = _value(force.get("id"))
    return value if isinstance(value, str) else None


def _visible(force: dict[str, Any]) -> bool:
    fact = force.get("visibility")
    return _value(fact) is True and isinstance(fact, dict) and fact.get("knowledge") == "OBSERVED"


def _visible_tower(tower: dict[str, Any] | None) -> bool:
    fact = tower.get("visibility") if tower else None
    return _value(fact) is True and isinstance(fact, dict) and fact.get("knowledge") == "OBSERVED"


def _reliable_fresh_forces(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Require a complete consecutive pair and a genuinely observed zero-progress fresh track."""
    if not _consecutive(before, after):
        return [], "SCOPE_OR_WORLD_TICK_NOT_CONSECUTIVE"
    if before.get("coverage") != "PLAYER_VISIBLE_COMPLETE" or after.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
        return [], "INCOMPLETE_PLAYER_VISIBLE_COVERAGE"
    old_rows, new_rows = _rows(before, "forces"), _rows(after, "forces")
    if old_rows is None or new_rows is None:
        return [], "INCOMPLETE_FORCE_COLLECTION"
    old_ids = {_force_id(row) for row in old_rows if _force_id(row) is not None}
    new_ids = [_force_id(row) for row in new_rows if _force_id(row) is not None]
    if len(new_ids) != len(set(new_ids)):
        return [], "DUPLICATE_FORCE_ID_IN_BIRTH_OBSERVATION"
    found = []
    for force in new_rows:
        ident = _force_id(force)
        if (ident is None or ident in old_ids or not _visible(force) or
                _value(force.get("confidence")) != "NEW_TRACK" or
                _value(force.get("progress")) != 0 or
                not isinstance(force.get("progress"), dict) or
                force["progress"].get("knowledge") != "OBSERVED" or
                not _known(force.get("source")) or not _known(force.get("destination")) or
                not isinstance(force.get("units"), dict) or force["units"].get("knowledge") != "OBSERVED" or
                _vector(force.get("units")) is None):
            continue
        found.append(force)
    return found, None


def _relation_owner_class(owner: Any, relation: Any, player_id: Any) -> str:
    if type(owner) is int and type(player_id) is int and owner == player_id:
        return "SELF"
    if relation in ("SELF", "OWN"):
        return "SELF"
    if relation in ("ALLY", "FRIENDLY"):
        return "ALLY"
    if relation == "ENEMY":
        return "ENEMY"
    if relation == "NEUTRAL":
        return "NEUTRAL"
    return "UNKNOWN_OWNER"


def _fresh_birth_events(history: list[dict[str, Any]],
                        sources: set[int] | None = None) -> list[dict[str, Any]]:
    """Detect only reliable pre-T births in adjacent retained observations."""
    events: list[dict[str, Any]] = []
    for before, after in zip(history, history[1:]):
        fresh, error = _reliable_fresh_forces(before, after)
        if error or not fresh:
            continue
        grouped: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
        for force in fresh:
            src_fact = force.get("source")
            src = _value(src_fact)
            if type(src) is int and (sources is None or src in sources):
                grouped[src].append(force)
        for source, forces in grouped.items():
            vectors = [_vector(force.get("units")) for force in forces]
            if any(vector is None for vector in vectors):
                continue
            aggregate = [sum(vector[i] for vector in vectors if vector is not None) for i in range(10)]
            events.append({"tick": _tick(after), "source": source,
                           "force_count": len(forces), "aggregate_units": aggregate,
                           "identities": [_force_id(force) for force in forces]})
    return events


def _source_features(before: dict[str, Any], after: dict[str, Any], source: int | None,
                     history: list[dict[str, Any]]) -> dict[str, Any]:
    if source is None:
        return {"source_tower_visible_before_birth": "UNKNOWN", "source_tower_visible_at_birth": "UNKNOWN",
                "source_owner": None,
                "source_owner_class": "UNKNOWN_OWNER",
                "source_units_before": None, "source_units_at_birth": None,
                "source_removal_vector": None, "new_force_aggregate_vector": None,
                "source_removal_equals_new_force_vector": None,
                "supply_line_before_birth": "UNKNOWN", "production_clock_status": "UNKNOWN",
                "production_due": [],
                "mobile_production_due": [], "overflow_units_before": [],
                "capacity_status": "UNKNOWN", "overflow_status": "UNKNOWN",
                "overflow_cleanup_due_local_rule": None,
                "visible_inbound_status": "UNKNOWN_FORCE_SET", "visible_force_destinations_unknown": [],
                "visible_inbound_forces": [],
                "prior_source_births": [], "prior_intervals": [],
                "composition_batch_recurrence": "UNKNOWN_SOURCE"}
    before_towers, after_towers = _tower_map(before), _tower_map(after)
    before_tower_row = before_towers.get(source) if before_towers is not None else None
    after_tower_row = after_towers.get(source) if after_towers is not None else None
    bt = before_tower_row if _visible_tower(before_tower_row) else None
    at = after_tower_row if _visible_tower(after_tower_row) else None
    before_units = _vector(bt.get("units")) if bt else None
    after_units = _vector(at.get("units")) if at else None
    removal = ([a - b for a, b in zip(before_units, after_units)]
               if before_units is not None and after_units is not None else None)
    before_force_rows = _rows(before, "forces")
    after_force_rows = _rows(after, "forces")
    if before_force_rows is not None and after_force_rows is not None:
        old_ids = {_force_id(force) for force in before_force_rows if _force_id(force) is not None}
        appearance_rows = [force for force in after_force_rows
            if _force_id(force) is not None and _force_id(force) not in old_ids and
               _value(force.get("confidence")) == "NEW_TRACK" and
               _value(force.get("source")) == source and _visible(force)]
    else:
        appearance_rows = []
    vectors = [(_vector(force.get("units")) if isinstance(force.get("units"), dict) and
                force["units"].get("knowledge") == "OBSERVED" else None)
               for force in appearance_rows]
    aggregate = ([sum(v[i] for v in vectors if v is not None) for i in range(10)]
                 if vectors and all(v is not None for v in vectors) else None)
    exact_conservation = removal == aggregate if removal is not None and aggregate is not None else None
    line_fact = bt.get("supply_line_present") if bt else None
    line_value = _value(line_fact) if isinstance(line_fact, dict) and line_fact.get("knowledge") != "UNKNOWN" else None
    line = "YES" if line_value is True else "NO" if line_value is False else "UNKNOWN"
    production_fact = bt.get("production") if bt else None
    production = _value(production_fact) if _known(production_fact) else None
    target_tick = _tick(before)
    due: list[dict[str, int]] = []
    if isinstance(production, list) and target_tick is not None:
        # Existing model phase convention; this is a clock opportunity, not proof of production.
        from kiomet_ai.v2.sim.step import phase
        next_tick = (target_tick + 1) & 0xFFFF
        for pair in production:
            if (isinstance(pair, (list, tuple)) and len(pair) == 2 and
                    type(pair[0]) is int and type(pair[1]) is int and pair[1] > 0 and
                    phase(next_tick, source) % pair[1] == 0):
                due.append({"unit_index": pair[0], "period_ticks": pair[1]})
    # Unit index zero is the repository's immobile shield; other vector slots are mobile.
    mobile_due = [item for item in due if item["unit_index"] != 0]
    capacity = _vector(bt.get("capacity")) if bt else None
    overflow = ([{"unit_index": i, "units": count, "capacity": capacity[i]}
                 for i, count in enumerate(before_units or [])
                 if capacity is not None and count > capacity[i]])
    owner_fact = bt.get("owner") if bt else None
    owner_known = _known(owner_fact)
    overflow_assessable = capacity is not None and before_units is not None and target_tick is not None and owner_known
    overflow_due: bool | None = None
    if overflow_assessable:
        from kiomet_ai.v2.sim.step import phase
        overflow_due = bool(_value(owner_fact) and overflow and
            phase((target_tick + 1) & 0xFFFF, source) % 120 == 0)
    inbound = []
    unknown_destination_forces = []
    preforces = _rows(before, "forces")
    if preforces is not None:
        for force in preforces:
            if not _visible(force):
                continue
            if not _known(force.get("destination")):
                unknown_destination_forces.append({"observer_id": _force_id(force),
                    "source": _value(force.get("source")), "progress": _value(force.get("progress")),
                    "destination_knowledge": force.get("destination", {}).get("knowledge")
                        if isinstance(force.get("destination"), dict) else None})
            elif _value(force.get("destination")) == source:
                eta = _value(force.get("eta_ms"))
                inbound.append({"owner": _value(force.get("owner")), "source": _value(force.get("source")),
                    "destination": source, "progress": _value(force.get("progress")),
                    "eta_ms": eta,
                    "eta_knowledge": force.get("eta_ms", {}).get("knowledge") if isinstance(force.get("eta_ms"), dict) else None,
                    "units": _vector(force.get("units")),
                    "eta_within_one_250ms_tick_by_derived_value": eta <= 250 if type(eta) is int else None})
    prior_events = _fresh_birth_events(history, {source})
    ticks = [event["tick"] for event in prior_events if type(event.get("tick")) is int]
    intervals = [((ticks[i] - ticks[i - 1]) & 0xFFFF) for i in range(1, len(ticks))]
    current_vectors = [vector for vector in vectors if vector is not None]
    same_batch = bool(current_vectors) and any(event["aggregate_units"] == aggregate for event in prior_events)
    birth_tick = _tick(after)
    repeated_interval = (len(intervals) >= 2 and len(set(intervals)) == 1 and
                         birth_tick is not None and ticks and
                         ((birth_tick - ticks[-1]) & 0xFFFF) == intervals[-1])
    recurrence = ("REPEATED_SAME_INTERVAL_AND_BATCH" if repeated_interval and same_batch else
                  "PRIOR_BATCH_MATCH_ONLY" if same_batch else
                  "PRIOR_INTERVAL_PATTERN_ONLY" if repeated_interval else
                  "IRREGULAR_OR_TOO_FEW_PRIOR_BIRTHS")
    return {"source_tower_visible_before_birth": "YES" if bt else
        "NO" if before_tower_row and isinstance(before_tower_row.get("visibility"), dict) and
            before_tower_row["visibility"].get("knowledge") == "OBSERVED" and
            _value(before_tower_row.get("visibility")) is False else "UNKNOWN",
        "source_tower_visible_at_birth": "YES" if at else
        "NO" if after_tower_row and isinstance(after_tower_row.get("visibility"), dict) and
            after_tower_row["visibility"].get("knowledge") == "OBSERVED" and
            _value(after_tower_row.get("visibility")) is False else "UNKNOWN",
        "source_owner": _value(bt.get("owner")) if bt else None,
        "source_relation": _value(bt.get("relation")) if bt else None,
        "source_owner_class": _relation_owner_class(_value(bt.get("owner")) if bt else None,
            _value(bt.get("relation")) if bt else None, _value(before.get("player_id"))),
        "source_units_before": before_units, "source_units_at_birth": after_units,
        "source_removal_vector": removal, "new_force_aggregate_vector": aggregate,
        "source_removal_equals_new_force_vector": exact_conservation,
        "supply_line_before_birth": line,
        "production_clock_status": "KNOWN" if _known(production_fact) and isinstance(production, list) else "UNKNOWN",
        "production_due": due,
        "mobile_production_due": mobile_due, "overflow_units_before": overflow,
        "capacity_status": "KNOWN" if capacity is not None else "UNKNOWN",
        "overflow_status": "ASSESSED" if overflow_assessable else "UNKNOWN",
        "overflow_cleanup_due_local_rule": overflow_due,
        "visible_inbound_status": ("UNKNOWN_FORCE_SET" if preforces is None or before.get("coverage") != "PLAYER_VISIBLE_COMPLETE" else
            "UNKNOWN_DESTINATIONS" if unknown_destination_forces else
            "INBOUND_VISIBLE" if inbound else "NO_VISIBLE_INBOUND_TO_SOURCE"),
        "visible_force_destinations_unknown": unknown_destination_forces,
        "visible_inbound_forces": inbound,
        "prior_source_births": prior_events, "prior_intervals": intervals,
        "composition_batch_recurrence": recurrence}


def _analyze_candidate(edge: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
                      history: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    fresh, pair_error = _reliable_fresh_forces(before, after)
    diag = edge.get("new_force_diagnostic", {}).get("candidates", [])
    # Preserve all fixture candidate identities, including entities failing the stricter birth test.
    entity_rows = []
    current_force_rows = _rows(after, "forces") or []
    current_by_id = {_force_id(force): force for force in current_force_rows if _force_id(force) is not None}
    previous_force_rows = _rows(before, "forces")
    previous_ids = ({_force_id(force) for force in previous_force_rows if _force_id(force) is not None}
                    if previous_force_rows is not None else set())
    for candidate in diag:
        ident = candidate.get("observer_id")
        force = current_by_id.get(ident)
        if force is None:
            entity_rows.append({"observer_id": ident, "reliable_newborn": False,
                "age": "UNKNOWN_AGE", "reliability_reason": "FIXTURE_CANDIDATE_NOT_FOUND_IN_BIRTH_ROW",
                "visibility_observed_true": None, "force_owner_class": "UNKNOWN_OWNER",
                "source_owner_class": "UNKNOWN_OWNER", "source": None,
                "destination": None, "unit_vector": None})
            continue
        if not _visible(force):
            entity_rows.append({"observer_id": ident, "reliable_newborn": False,
                "age": "UNKNOWN_AGE", "reliability_reason": "FORCE_NOT_PROVEN_NORMAL_PLAYER_VISIBLE",
                "visibility_observed_true": False, "force_owner_class": "UNKNOWN_OWNER",
                "source_owner_class": "UNKNOWN_OWNER", "source": None, "destination": None,
                "unit_vector": None, "progress": None, "confidence": None})
            continue
        source = _value(force.get("source")) if _known(force.get("source")) else None
        destination = _value(force.get("destination")) if _known(force.get("destination")) else None
        vector = (_vector(force.get("units")) if isinstance(force.get("units"), dict) and
                  force["units"].get("knowledge") == "OBSERVED" else None)
        progress = _value(force.get("progress")) if _known(force.get("progress")) else None
        reliable = (force in fresh and source is not None and destination is not None and vector is not None)
        missing = []
        if source is None: missing.append("source")
        if destination is None: missing.append("destination")
        if vector is None: missing.append("unit_vector")
        if progress != 0: missing.append("observed_zero_progress")
        source_towers = _tower_map(before)
        raw_src_tower = source_towers.get(source) if source is not None and source_towers is not None else None
        src_tower = raw_src_tower if _visible_tower(raw_src_tower) else None
        force_owner = _relation_owner_class(_value(force.get("owner")),
            _value(force.get("relation")), _value(before.get("player_id")))
        source_owner = _relation_owner_class(_value(src_tower.get("owner")) if src_tower else None,
            _value(src_tower.get("relation")) if src_tower else None, _value(before.get("player_id")))
        entity_rows.append({"observer_id": ident, "reliable_newborn": reliable,
            "age": "NEWBORN" if reliable else "UNKNOWN_AGE",
            "reliability_reason": "RELIABLE_FRESH_NEW_TRACK_AT_OBSERVED_ZERO_PROGRESS" if reliable else
                ",".join(missing) if missing else pair_error or "FRESH_TRACK_NOT_PROVEN",
            "force_owner_class": force_owner, "source_owner_class": source_owner,
            "visibility_observed_true": True,
            "owner": _value(force.get("owner")),
            "source": source, "destination": destination, "unit_vector": vector,
            "source_knowledge": force.get("source", {}).get("knowledge") if isinstance(force.get("source"), dict) else None,
            "destination_knowledge": force.get("destination", {}).get("knowledge") if isinstance(force.get("destination"), dict) else None,
            "unit_vector_knowledge": force.get("units", {}).get("knowledge") if isinstance(force.get("units"), dict) else None,
            "progress": progress, "confidence": _value(force.get("confidence")),
            "identity_absent_from_prebirth_force_set": (ident not in previous_ids
                if previous_force_rows is not None else None),
            "force_relation": _value(force.get("relation"))})
    sources = sorted({row["source"] for row in entity_rows if type(row.get("source")) is int})
    source_features_by_source = [
        {"source": source, **_source_features(before, after, source, history)}
        for source in sources]
    if any(row.get("source") is None for row in entity_rows) or not source_features_by_source:
        source_features_by_source.append({"source": None,
            **_source_features(before, after, None, history)})
    source_features = {"sources": source_features_by_source,
        "all_source_inventories_visible": bool(source_features_by_source) and
            all(x["source_tower_visible_before_birth"] == "YES" and
                x["source_units_before"] is not None and x["source_units_at_birth"] is not None
                for x in source_features_by_source),
        "all_source_batches_conserved": bool(source_features_by_source) and
            all(x["source_removal_equals_new_force_vector"] is True for x in source_features_by_source),
        "all_lines_known_true": bool(source_features_by_source) and
            all(x["supply_line_before_birth"] == "YES" for x in source_features_by_source),
        "all_sources_repeated_same_interval_and_batch": bool(source_features_by_source) and
            all(x["composition_batch_recurrence"] == "REPEATED_SAME_INTERVAL_AND_BATCH"
                for x in source_features_by_source)}
    essential_complete = (pair_error is None and bool(entity_rows) and
        all(row["reliable_newborn"] for row in entity_rows) and
        source_features["all_source_inventories_visible"])
    external = False  # No case-linked ACTION_INTENT/UI_ACTION_RESULT exists in this fixture universe.
    internal = (essential_complete and source_features["all_source_batches_conserved"] and
        source_features["all_lines_known_true"] and
        source_features["all_sources_repeated_same_interval_and_batch"])
    if external:
        classification = "LIKELY_EXTERNAL"
        reason = "POSITIVE_CASE_LINKED_ACTION_PROVENANCE"
    elif internal:
        classification = "LIKELY_INTERNAL"
        reason = "KNOWN_PREBIRTH_LINE_WITH_REPEATED_PRIOR_INTERVAL_AND_BATCH_PATTERN"
    elif essential_complete:
        classification = "AMBIGUOUS"
        reason = "RELIABLE_BIRTH_AND_SOURCE_STATE_WITH_CAUSAL_ALTERNATIVES_UNRESOLVED"
    else:
        classification = "UNKNOWN"
        reason = "INCOMPLETE_OR_UNRELIABLE_BIRTH_SOURCE_OR_COMPOSITION_INPUTS"
    return {"cohort": edge["cohort"], "split": edge["split"], "edge_index": edge["edge_index"],
        "before_line": edge["before_line"], "after_line": edge["after_line"],
        "before_sequence": edge["before_sequence"], "after_sequence": edge["after_sequence"],
        "before_tick": edge["before_tick"], "birth_tick": edge["after_tick"],
        "temporal_cutoff": "No observation later than this candidate birth row is consulted.",
        "fixture_candidate_entity_count": len(diag), "reliable_newborn_entity_count": sum(x["reliable_newborn"] for x in entity_rows),
        "entity_candidates": entity_rows, "source_features": source_features,
        "action_evidence": "NO_CASE_LINKED_ACTION_INTENT_OR_UI_ACTION_RESULT_IN_COVERAGE_FIXTURE",
        "classification": classification, "classification_reason": reason,
        "causal_credit": 0}


def _freeze_development_rule(dev_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Thresholds are preregistered for holdout; dev is the only split used to
    # inspect how many cases satisfy the fixed evidence pattern.
    base = {"rule_version": "force-causality-rule-v1",
        "likely_external": "Only a positive independently recorded case-linked ACTION_INTENT/UI_ACTION_RESULT matching scope, player, source, destination, and aggregate vector.",
        "likely_internal": "A complete reliable birth with exact source-vector conservation, a known-true prebirth source line, at least two strictly prebirth equal source-birth intervals, current interval equal to that repeated interval, and exact aggregate batch composition recurrence.",
        "ambiguous": "Complete reliable zero-progress fresh birth plus complete visible source inventory, with no uniquely supported cause; exact source depletion alone never establishes external action.",
        "unknown": "Any missing source/destination/vector, incomplete scope/tick/force collection, or unproved zero-progress fresh identity remains UNKNOWN.",
        "initial_observation": "Left-censored; never counted as a reliable prior birth.",
        "new_track": "NEW_TRACK confidence alone is insufficient; require observed progress 0 and absence from the complete immediately preceding force set.",
        "holdout_tuning": "No thresholds or categories are changed after development; holdout is evaluation only.",
        "dev_candidate_edges": len(dev_rows),
        "dev_entity_candidates": sum(x["fixture_candidate_entity_count"] for x in dev_rows),
        "dev_classification_counts": dict(collections.Counter(x["classification"] for x in dev_rows))}
    base["rule_sha256"] = hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return base


def _load_fixture() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report = json.loads(COVERAGE_REPORT.read_text(encoding="utf-8"))
    audit = report.get("edge_audit", {})
    actual = sha256(EDGE_FIXTURE)
    if (audit.get("path") != EDGE_FIXTURE.relative_to(ROOT).as_posix() or
            audit.get("sha256") != actual or audit.get("rows") != 13059):
        raise ValueError("accepted coverage edge fixture pin/row count mismatch")
    rows = []
    decompressed = hashlib.sha256()
    with gzip.open(EDGE_FIXTURE, "rt", encoding="utf-8") as stream:
        for line in stream:
            decompressed.update(line.encode("utf-8"))
            row = json.loads(line)
            if APPEARANCE_LABEL in row.get("event_pattern_labels", []):
                rows.append(row)
    if audit.get("decompressed_sha256") != decompressed.hexdigest():
        raise ValueError("accepted coverage edge fixture decompressed hash mismatch")
    if len(rows) != 646:
        raise ValueError(f"expected exact fixed 646 candidate edges, got {len(rows)}")
    return rows, report


def _analyze_split(edges: list[dict[str, Any]], snapshots: dict[str, Path], split: str,
                   rule: dict[str, Any] | None) -> list[dict[str, Any]]:
    selected = sorted((edge for edge in edges if edge["split"] == split),
                      key=lambda edge: (edge["cohort"], edge["after_line"], edge["edge_index"]))
    by_cohort: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for edge in selected:
        by_cohort[edge["cohort"]].append(edge)
    results: list[dict[str, Any]] = []
    for cohort, cohort_edges in sorted(by_cohort.items()):
        path = snapshots[cohort]
        history: list[dict[str, Any]] = []
        pending = {edge["after_line"]: edge for edge in cohort_edges}
        max_line = max(pending)
        with path.open("r", encoding="utf-8") as stream:
            previous_key = None
            previous_retained: dict[str, Any] | None = None
            for line_no, line in enumerate(stream, 1):
                if line_no > max_line:
                    break
                row = json.loads(line)
                row_scope, row_tick = _scope(row), _tick(row)
                key = (row_scope, row_tick)
                first = not (type(row_tick) is int and key == previous_key)
                if not first:
                    continue
                if type(row_tick) is int:
                    previous_key = key
                else:
                    previous_key = None
                edge = pending.get(line_no)
                if edge is not None:
                    before = previous_retained
                    if before is None or (before.get("sequence") != edge["before_sequence"] or
                                          row.get("sequence") != edge["after_sequence"]):
                        raise ValueError(f"coverage fixture raw line/sequence mismatch at {cohort}:{line_no}")
                    if rule is None:
                        # Development is analyzed before the holdout rule is frozen.
                        pass
                    case = _analyze_candidate(edge, before, row, history, rule or {})
                    results.append(case)
                history.append(row)
                previous_retained = row
    return results


def run_analysis() -> dict[str, Any]:
    git_before = _git_state()
    edges, report = _load_fixture()
    snapshot_pins = {}
    for row in report["inputs"]["raw_files"].values():
        if not row.get("matches_manifest") or row.get("expected_sha256") != row.get("actual_sha256"):
            raise ValueError(f"accepted report raw pin is not verified: {row.get('cohort')}")
        snapshot_pins[row["cohort"]] = row["expected_sha256"]
    snapshot_paths = {cohort: ROOT / "runtime/research/v2" / f"snapshots-{cohort}.jsonl"
                      for cohort in snapshot_pins}
    for cohort, path in snapshot_paths.items():
        if not path.is_file() or sha256(path) != snapshot_pins[cohort]:
            raise ValueError(f"snapshot hash mismatch: {cohort}")
    dev_cases = _analyze_split(edges, snapshot_paths, "development", None)
    rule = _freeze_development_rule(dev_cases)
    # The exact frozen rule object/hash is now supplied unchanged to holdout.
    holdout_cases = _analyze_split(edges, snapshot_paths, "holdout", rule)
    cases = sorted(dev_cases + holdout_cases,
                   key=lambda case: (case["cohort"], case["after_line"], case["edge_index"]))
    for case in cases:
        case["classification_rule_sha256"] = rule["rule_sha256"]
    counts = collections.Counter(case["classification"] for case in cases)
    entity_counts = collections.Counter()
    age_counts = collections.Counter()
    force_owner_counts = collections.Counter()
    source_owner_counts = collections.Counter()
    source_conservation = collections.Counter()
    split_counts = {}
    cohort_counts = {}
    split_entities: dict[str, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: {"age": collections.Counter(), "force_owner": collections.Counter(),
                 "source_owner": collections.Counter(), "entity_status": collections.Counter()})
    cohort_entities: dict[str, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: {"age": collections.Counter(), "force_owner": collections.Counter(),
                 "source_owner": collections.Counter(), "entity_status": collections.Counter()})
    edge_entity_histogram = collections.Counter()
    diagnostics = {"has_visible_inbound": 0, "has_mobile_production_due": 0,
        "has_overflow_cleanup_due": 0, "all_sources_line_yes": 0,
        "all_sources_line_no": 0, "all_sources_line_unknown": 0,
        "prior_recurrence_repeated_batch": 0, "prior_recurrence_other": 0}
    for case in cases:
        split_counts.setdefault(case["split"], collections.Counter())[case["classification"]] += 1
        cohort_counts.setdefault(case["cohort"], collections.Counter())[case["classification"]] += 1
        source_conservation["EXACT_ALL_SOURCES" if case["source_features"]["all_source_batches_conserved"] is True else
                            "NOT_EXACT_AT_LEAST_ONE_SOURCE" if any(x.get("source_removal_equals_new_force_vector") is False
                                for x in case["source_features"]["sources"]) else "UNKNOWN_OR_PARTIAL"] += 1
        edge_entity_histogram[str(case["fixture_candidate_entity_count"])] += 1
        source_groups = case["source_features"]["sources"]
        diagnostics["has_visible_inbound"] += int(any(bool(x.get("visible_inbound_forces")) for x in source_groups))
        diagnostics["has_mobile_production_due"] += int(any(bool(x.get("mobile_production_due")) for x in source_groups))
        diagnostics["has_overflow_cleanup_due"] += int(any(x.get("overflow_cleanup_due_local_rule") is True for x in source_groups))
        diagnostics["all_sources_line_yes"] += int(bool(source_groups) and all(x.get("supply_line_before_birth") == "YES" for x in source_groups))
        diagnostics["all_sources_line_no"] += int(bool(source_groups) and all(x.get("supply_line_before_birth") == "NO" for x in source_groups))
        diagnostics["all_sources_line_unknown"] += int(not source_groups or any(x.get("supply_line_before_birth") == "UNKNOWN" for x in source_groups))
        diagnostics["prior_recurrence_repeated_batch"] += int(any(x.get("composition_batch_recurrence") == "REPEATED_SAME_INTERVAL_AND_BATCH" for x in source_groups))
        diagnostics["prior_recurrence_other"] += int(any(x.get("composition_batch_recurrence") != "REPEATED_SAME_INTERVAL_AND_BATCH" for x in source_groups))
        for entity in case["entity_candidates"]:
            entity_counts["RELIABLE_NEWBORN" if entity["reliable_newborn"] else "UNRESOLVED"] += 1
            age_counts[entity["age"]] += 1
            force_owner_counts[entity["force_owner_class"]] += 1
            source_owner_counts[entity["source_owner_class"]] += 1
            split_entities[case["split"]]["age"][entity["age"]] += 1
            split_entities[case["split"]]["force_owner"][entity["force_owner_class"]] += 1
            split_entities[case["split"]]["source_owner"][entity["source_owner_class"]] += 1
            split_entities[case["split"]]["entity_status"]["RELIABLE_NEWBORN" if entity["reliable_newborn"] else "UNRESOLVED"] += 1
            cohort_entities[case["cohort"]]["age"][entity["age"]] += 1
            cohort_entities[case["cohort"]]["force_owner"][entity["force_owner_class"]] += 1
            cohort_entities[case["cohort"]]["source_owner"][entity["source_owner_class"]] += 1
            cohort_entities[case["cohort"]]["entity_status"]["RELIABLE_NEWBORN" if entity["reliable_newborn"] else "UNRESOLVED"] += 1
    source_hashes = {"coverage_edge_fixture": sha256(EDGE_FIXTURE),
        "coverage_report": sha256(COVERAGE_REPORT),
        **{f"snapshot:{cohort}": sha256(path) for cohort, path in sorted(snapshot_paths.items())}}
    # Deterministic gzip JSONL with one row per fixture candidate edge; candidate entities stay nested.
    ROWS_GZIP.parent.mkdir(parents=True, exist_ok=True)
    with ROWS_GZIP.open("wb") as raw_out:
        with gzip.GzipFile(fileobj=raw_out, mode="wb", filename="", mtime=0) as gz:
            for case in cases:
                gz.write((json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"status": "CANDIDATE_CAUSALITY_ONLY_NO_FORMAL_CREDIT", "analysis_version": ANALYSIS_VERSION,
        "fixed_universe": {"authority": EDGE_FIXTURE.relative_to(ROOT).as_posix(),
            "coverage_report": COVERAGE_REPORT.relative_to(ROOT).as_posix(),
            "fixture_rows": 13059, "appearance_candidate_edges": 646,
            "appearance_candidate_entities": sum(x["fixture_candidate_entity_count"] for x in cases),
            "cohort_count": len({x["cohort"] for x in cases}),
            "not_the_legacy_13_case_set": True},
        "git_state_before_artifacts": git_before,
        "source_hashes": source_hashes,
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
        "fixture_sha256_matches_accepted_report": True,
        "snapshot_sha256_matches_accepted_report": True,
        "development_rule": rule,
        "holdout_protocol": "Rule hash frozen after development-only analysis; same classifier applies to holdout without threshold updates.",
        "classification_counts_by_edge": dict(counts),
        "classification_counts_by_split": {key: dict(value) for key, value in sorted(split_counts.items())},
        "classification_counts_by_cohort": {key: dict(value) for key, value in sorted(cohort_counts.items())},
        "candidate_entity_counts": dict(entity_counts), "candidate_entity_age_counts": dict(age_counts),
        "candidate_entity_force_owner_counts": dict(force_owner_counts),
        "candidate_entity_source_owner_counts": dict(source_owner_counts),
        "candidate_entity_strata_by_split": {key: {name: dict(counter) for name, counter in value.items()}
            for key, value in sorted(split_entities.items())},
        "candidate_entity_strata_by_cohort": {key: {name: dict(counter) for name, counter in value.items()}
            for key, value in sorted(cohort_entities.items())},
        "candidate_entity_count_per_edge_histogram": dict(edge_entity_histogram),
        "prebirth_causal_feature_edge_counts": diagnostics,
        "source_removal_equals_candidate_batch": dict(source_conservation),
        "runtime_candidate_rows_gzip": {"path": ROWS_GZIP.relative_to(ROOT).as_posix(),
            "sha256": sha256(ROWS_GZIP), "rows": len(cases), "mtime": 0,
            "format": "deterministic gzip JSONL; one edge per line with all candidate entity records"},
        "causal_limits": ["Source depletion/force-vector conservation alone is not evidence of external player action.",
            "No case-linked durable ActionIntent/UI action records are included in the accepted coverage fixture.",
            "NEW_TRACK confidence alone is insufficient; reliability also requires complete consecutive scope, zero observed progress, and fresh identity.",
            "Supply-line, production-clock, overflow and incoming-force facts are evaluated only from the immediate prebirth/current birth observations; prior recurrence uses strictly earlier complete births.",
            "These six preselected recordings are not a random sample of gameplay; holdout is descriptive evaluation, not a population estimate.",
            "Classifications do not prove the actual actor; every candidate carries zero formal credit."]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = run_analysis()
    print(json.dumps({"path": OUTPUT.relative_to(ROOT).as_posix(),
        "status": result["status"], "edges": result["fixed_universe"]["appearance_candidate_edges"],
        "entities": result["fixed_universe"]["appearance_candidate_entities"],
        "classification_counts_by_edge": result["classification_counts_by_edge"],
        "rows_gzip_sha256": result["runtime_candidate_rows_gzip"]["sha256"]}, ensure_ascii=False))
