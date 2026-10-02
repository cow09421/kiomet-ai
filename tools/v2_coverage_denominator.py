"""Read-only M2A coverage denominator over the six pinned observation cohorts.

This produces candidate descriptive evidence. It never changes simulator state,
uses no inferred actions, and does not treat isolated blocker probes as a world
step or a whole-world pass.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from kiomet_ai.v2.control import control_readiness_gaps
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import SimulationState, UnsupportedState, from_canonical, step
from v2_sim_differential import signature
from kiomet_ai.v2.observe.forces import motion
from kiomet_ai.v2.state import Units
from kiomet_ai.v2.sim.step import phase

DIFFERENTIAL_PATH = ROOT / "docs/V2_M2A_DIFFERENTIAL.json"
HOLDOUT_PATH = ROOT / "docs/V2_M2A_HOLDOUT.json"
TRAJECTORIES_PATH = ROOT / "docs/V2_M2A_TRAJECTORIES.json"
DEVELOPMENT_CORPUS = ROOT / "runtime/research/v2/luna-corpus/manager-checkpoint-development-corpus.jsonl"
HOLDOUT_CORPUS = ROOT / "runtime/research/v2/luna-corpus/manager-checkpoint-holdout-corpus.jsonl"
DEFAULT_OUTPUT = ROOT / "runtime/research/v2/coverage-denominator-candidate.json"
ANALYSIS_VERSION = "coverage-denominator-v1"
PROBE_LIMIT_PER_COHORT = 128


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _git_state() -> dict[str, Any]:
    prefix = ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet"]

    def read(*args: str) -> str:
        return subprocess.run(prefix + list(args), cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()

    status = read("status", "--porcelain=v1", "--untracked-files=all").rstrip("\r\n")
    return {"head": read("rev-parse", "HEAD").rstrip("\r\n"),
            "branch": read("branch", "--show-current").rstrip("\r\n"),
            "dirty": bool(status), "status_porcelain": status.splitlines()}


def _value(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) and "value" in fact else None


def _count_vector(fact: Any) -> tuple[int, ...] | None:
    value = _value(fact)
    pairs = value.get("counts") if isinstance(value, dict) else None
    if not isinstance(pairs, list):
        return None
    result: dict[int, int] = {}
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or
                pair[0] in result or not 0 <= pair[1] <= 255):
            return None
        result[pair[0]] = pair[1]
    if set(result) != set(range(10)):
        return None
    return tuple(result[i] for i in range(10))


def _raw_semantic_signature(raw: dict[str, Any]) -> tuple[dict[str, Any], bool, list[str]]:
    """Build activity from raw values, before any simulator conversion.

    Knowledge/source/time wrappers and observer Force IDs/confidence are not
    semantic inputs. An incomplete fact makes the signature unresolved, but
    known differences in remaining fields can still establish activity.
    """
    gaps: list[str] = []
    complete = raw.get("coverage") == "PLAYER_VISIBLE_COMPLETE"
    if not complete:
        gaps.append("coverage")
    towers_out: dict[int, dict[str, Any]] = {}
    towers = raw.get("towers")
    if not isinstance(towers, list):
        complete = False
        gaps.append("towers")
        towers = []
    for pos, row in enumerate(towers):
        if not isinstance(row, dict):
            complete = False
            gaps.append(f"tower:{pos}:record")
            continue
        vis = row.get("visibility")
        visible = _value(vis)
        if visible is False:
            continue
        if visible is not True or not isinstance(vis, dict) or vis.get("knowledge") == "UNKNOWN":
            complete = False
            gaps.append(f"tower:{pos}:visibility")
            continue
        ident = row.get("id")
        if type(ident) is not int:
            complete = False
            gaps.append(f"tower:{pos}:id")
            continue
        result: dict[str, Any] = {"id": ident}
        values = {
            "owner": _value(row.get("owner")),
            "relation": _value(row.get("relation")),
            "kind": _value(row.get("tower_type")),
            "units": _count_vector(row.get("units")),
            "capacity": _count_vector(row.get("capacity")),
            "production": _value(row.get("production")),
            "neighbors": _value(row.get("neighbors")),
            "position": _value(row.get("position")),
            "delay": _value(row.get("delay_ticks")),
        }
        effects_fact = row.get("effects")
        effects = _value(effects_fact)
        effects_semantic = None
        if isinstance(effects, list) and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in effects):
            effects_semantic = sorted((str(k), v) for k, v in effects)
        values["effects"] = effects_semantic
        line_fact = row.get("supply_line_present")
        line_value = _value(line_fact) if isinstance(line_fact, dict) else None
        if type(line_value) is bool:
            values["supply_line_present"] = line_value
        for name, value in values.items():
            fact_name = {"kind": "tower_type", "delay": "delay_ticks"}.get(name, name)
            if name == "effects":
                fact_name = "effects"
            if name == "supply_line_present" and type(value) is not bool:
                result[name] = None
                continue
            fact = row.get(fact_name)
            if (value is None or not isinstance(fact, dict) or fact.get("knowledge") == "UNKNOWN"):
                complete = False
                gaps.append(f"tower:{ident}:{name}")
            result[name] = value
        if ident in towers_out:
            complete = False
            gaps.append(f"tower:{ident}:duplicate")
        towers_out[ident] = result

    forces_value = raw.get("forces")
    forces = _value(forces_value)
    force_rows: list[dict[str, Any]] = []
    force_rows_for_alignment: list[dict[str, Any]] = []
    force_complete = (raw.get("coverage") == "PLAYER_VISIBLE_COMPLETE" and
                      isinstance(forces_value, dict) and forces_value.get("knowledge") != "UNKNOWN")
    if not isinstance(forces, list):
        complete = False
        force_complete = False
        gaps.append("forces")
        forces = []
    for pos, row in enumerate(forces):
        if not isinstance(row, dict):
            complete = False
            force_complete = False
            gaps.append(f"force:{pos}:record")
            continue
        vis = row.get("visibility")
        if _value(vis) is False:
            continue
        if _value(vis) is not True or not isinstance(vis, dict) or vis.get("knowledge") == "UNKNOWN":
            complete = False
            force_complete = False
            gaps.append(f"force:{pos}:visibility")
            continue
        semantic = {
            "owner": _value(row.get("owner")),
            "relation": _value(row.get("relation")),
            "source": _value(row.get("source")),
            "destination": _value(row.get("destination")),
            "units": _count_vector(row.get("units")),
            "progress": _value(row.get("progress")),
            "accelerated": _value(row.get("accelerated")),
        }
        for name, value in semantic.items():
            fact = row.get(name)
            if value is None or not isinstance(fact, dict) or fact.get("knowledge") == "UNKNOWN":
                complete = False
                force_complete = False
                gaps.append(f"force:{pos}:{name}")
        force_rows.append(semantic)
        observer_id = _value(row.get("id"))
        if isinstance(observer_id, str):
            force_rows_for_alignment.append({"observer_id": observer_id, **semantic})
    # Per-destination order is semantic; observer object identity is not.
    inbound: dict[Any, list[Any]] = {}
    for force in force_rows:
        inbound.setdefault(force["destination"], []).append(
            (force["owner"], force["source"], force["units"], force["progress"],
             force["accelerated"], force["relation"]))
    sig = {"towers": [towers_out[k] for k in sorted(towers_out)],
           "forces": sorted(force_rows, key=lambda x: repr(tuple(x.values()))),
           "inbound_order": [(k, tuple(v)) for k, v in sorted(inbound.items(), key=lambda x: repr(x[0]))],
           "_force_rows_for_alignment": force_rows_for_alignment,
           "_force_collection_complete": force_complete}
    return sig, complete, sorted(set(gaps))


def _active(before: tuple[dict[str, Any], bool, list[str]],
            after: tuple[dict[str, Any], bool, list[str]]) -> str:
    left, left_complete, _ = before
    right, right_complete, _ = after
    left_sem = {k: v for k, v in left.items() if not k.startswith("_")}
    right_sem = {k: v for k, v in right.items() if not k.startswith("_")}
    if left_complete and right_complete and left_sem == right_sem:
        return "INACTIVE"
    # A known difference on the same semantic entity/field proves activity.
    # A field becoming known, or a visibility-set change alone, does not.
    lt = {x["id"]: x for x in left.get("towers", []) if isinstance(x.get("id"), int)}
    rt = {x["id"]: x for x in right.get("towers", []) if isinstance(x.get("id"), int)}
    for ident in lt.keys() & rt.keys():
        for key in lt[ident].keys() & rt[ident].keys():
            a, b = lt[ident][key], rt[ident][key]
            if a is not None and b is not None and a != b:
                return "ACTIVE_KNOWN"
    # Force multiset changes are reliable only when both complete observations
    # positively enumerate every visible force and all its semantic fields.
    if (left.get("_force_collection_complete") is True and
            right.get("_force_collection_complete") is True and
            (left.get("forces") != right.get("forces") or
             left.get("inbound_order") != right.get("inbound_order"))):
        return "ACTIVE_KNOWN"
    # Observer IDs are alignment aids only. A same, unique track with a
    # differing known semantic field establishes activity even when some
    # unrelated force fields remain unavailable.
    def unique_by_observer(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in rows:
            if isinstance(row.get("observer_id"), str):
                grouped[row["observer_id"]].append(row)
        return {key: values[0] for key, values in grouped.items() if len(values) == 1}
    lf = unique_by_observer(left.get("_force_rows_for_alignment", []))
    rf = unique_by_observer(right.get("_force_rows_for_alignment", []))
    for observer_id in lf.keys() & rf.keys():
        for key in ("owner", "relation", "source", "destination", "units", "progress", "accelerated"):
            a, b = lf[observer_id].get(key), rf[observer_id].get(key)
            if a is not None and b is not None and a != b:
                return "ACTIVE_KNOWN"
    return "ACTIVE_UNKNOWN"


def _scope(raw: dict[str, Any]) -> tuple[Any, Any, Any]:
    return raw.get("document_id"), _value(raw.get("match_id")), _value(raw.get("player_id"))


def _consecutive(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, int | None]:
    same_scope = _scope(before) == _scope(after)
    before_tick, after_tick = _value(before.get("tick")), _value(after.get("tick"))
    delta = ((after_tick - before_tick) & 65535
             if type(before_tick) is int and type(after_tick) is int else None)
    return same_scope and delta == 1, delta


def _primary_class(code: str) -> str:
    upper = code.upper()
    if upper.startswith("NOT_READY"):
        return "NOT_READY"
    if "SUPPLY_LINE" in upper:
        return "SUPPLY_LINE"
    if "POST_ARRIVAL" in upper or "PATH" in upper or "TERMINAL" in upper:
        return "UNKNOWN_PATH"
    if "FUEL" in upper:
        return "FUEL"
    if "COMBAT" in upper or "FORCE" in upper and "UNKNOWN" in upper:
        return "COMBAT"
    if "SPECIAL_PRODUCTION" in upper:
        return "SPECIAL_PRODUCTION"
    if "SPECIAL_UNITS" in upper:
        return "SPECIAL_UNITS"
    if "KING" in upper or "RULER" in upper:
        return "KING"
    if "RELATION" in upper or "OWNER" in upper:
        return "RELATION"
    if "GAP" in upper or "CONSECUTIVE" in upper or "SCOPE_CHANGED" in upper:
        return "OBSERVATION_GAP"
    if "EXTERNAL" in upper:
        return "EXTERNAL_ACTION_UNACCOUNTED_CANDIDATE"
    if not code or code == "UNKNOWN":
        return "UNKNOWN"
    return "OTHER"


def _readiness_bucket(gap: str) -> str:
    lower = gap.lower()
    if any(x in lower for x in ("source_continuity", "match_id", "tick")):
        return "clock"
    if any(x in lower for x in ("lifecycle", "source_mode", "client_version")):
        return "lifecycle"
    if "coverage" in lower or gap == "towers":
        return "coverage"
    if ":relation" in lower:
        return "relation"
    if ":accelerated" in lower:
        return "force_acceleration"
    if any(x in lower for x in ("source", "destination", "progress", "unit", "path")):
        return "path_or_force_input"
    return "input_fields"


def _normalize_readiness_gap(gap: str) -> str:
    gap = re.sub(r"tower:\d+:", "tower:*:", gap)
    gap = re.sub(r"force:\d+:", "force:*:", gap)
    return gap


def _readiness_edge_labels(stage: str, gaps: list[str] | tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Deduplicate after identifier normalization, once per edge and stage."""
    normalized = sorted({stage + ":" + _normalize_readiness_gap(gap) for gap in gaps})
    buckets = sorted({stage + ":" + _readiness_bucket(gap) for gap in gaps})
    return normalized, buckets


def _unsupported_status(code: str) -> tuple[str, str]:
    """UnsupportedState is a deliberate API refusal, not malformed coverage."""
    return "REJECTED", _primary_class(code)


def _not_ready_classification(gaps: list[str] | tuple[str, ...]) -> tuple[str, str, str]:
    """Classify NOT_READY by its enumerated input gaps, keeping raw code intact."""
    if any(any(token in gap.lower() for token in ("source_continuity", "match_id", "tick")) for gap in gaps):
        return "OBSERVATION_GAP", "REJECTED_OBSERVATION_GAP", "clock"
    if any(re.search(r"force:\d+:(source|destination)$", gap) for gap in gaps):
        return "UNKNOWN_PATH", "REJECTED_UNKNOWN_PATH", "current_leg_endpoint"
    return "NOT_READY", "REJECTED_NOT_READY", (_readiness_bucket(gaps[0]) if gaps else "UNKNOWN")


def _known_field_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Raw event patterns; all labels remain candidate observations."""
    left = {x.get("id"): x for x in before.get("towers", []) if isinstance(x, dict)}
    right = {x.get("id"): x for x in after.get("towers", []) if isinstance(x, dict)}
    tower_changes = []
    owner_changes = []
    for ident in left.keys() & right.keys():
        a, b = left[ident], right[ident]
        au, bu = _count_vector(a.get("units")), _count_vector(b.get("units"))
        if au is not None and bu is not None and au != bu:
            tower_changes.append({"tower_id": ident, "before_units": list(au), "after_units": list(bu),
                                  "delta": [y-x for x,y in zip(au,bu)]})
        ao, bo = _value(a.get("owner")), _value(b.get("owner"))
        if type(ao) is int and type(bo) is int and ao != bo:
            owner_changes.append({"tower_id": ident, "before_owner": ao, "after_owner": bo,
                                  "classification": "CAPTURE_OR_OWNER_CHANGE_CANDIDATE_CAUSE_UNKNOWN"})
    lforce, rforce = _value(before.get("forces")), _value(after.get("forces"))
    def keyed(rows):
        result = {}
        if not isinstance(rows, list):
            return result
        for row in rows:
            if isinstance(row, dict):
                ident = _value(row.get("id"))
                if isinstance(ident, str):
                    result[ident] = row
        return result
    lf, rf = keyed(lforce), keyed(rforce)
    common = lf.keys() & rf.keys()
    moved = [ident for ident in common
             if _value(lf[ident].get("progress")) != _value(rf[ident].get("progress"))]
    born = [ident for ident in rf.keys() - lf.keys()
            if _value(rf[ident].get("confidence")) == "NEW_TRACK"]
    gone = list(lf.keys() - rf.keys())
    # A due phase is only a potential event; unit increase can be arrival or
    # another world transition and is never called confirmed production.
    due = []
    tick = _value(before.get("tick"))
    if type(tick) is int:
        next_sequence = (tick + 1) & 65535
        for tower in before.get("towers", []):
            if not isinstance(tower, dict) or type(tower.get("id")) is not int:
                continue
            for pair in _value(tower.get("production")) or []:
                if (isinstance(pair, (list, tuple)) and len(pair) == 2 and
                        type(pair[0]) is int and type(pair[1]) is int and pair[1] > 0):
                    phase_value = phase(next_sequence, tower["id"])
                    if phase_value % pair[1] == 0:
                        due.append({"tower_id": tower["id"], "unit_index": pair[0],
                                    "period_ticks": pair[1], "phase_remainder": 0,
                                    "classification": "PRODUCTION_DUE_POTENTIAL_NOT_OBSERVED_PRODUCTION"})
    event_labels = []
    if born: event_labels.append("FORCE_TRACK_APPEARANCE_CANDIDATE_CAUSE_UNKNOWN")
    if gone: event_labels.append("FORCE_TRACK_DISAPPEARANCE_CANDIDATE_CAUSE_UNKNOWN")
    if moved: event_labels.append("FORCE_PROGRESS_CHANGE_OBSERVED")
    if owner_changes: event_labels.append("OWNER_CHANGE_CAPTURE_CANDIDATE_CAUSE_UNKNOWN")
    if due: event_labels.append("PRODUCTION_DUE_POTENTIAL")
    if tower_changes:
        if due and any(any(delta > 0 for delta in change["delta"]) for change in tower_changes):
            event_labels.append("UNIT_INCREASE_PRODUCTION_OR_ARRIVAL_CANDIDATE")
        else:
            event_labels.append("TOWER_UNIT_VECTOR_CHANGE_CAUSE_UNKNOWN")
    return {"tower_unit_vector_changes": tower_changes, "owner_changes": owner_changes,
            "force_progress_changed_observer_ids": moved, "new_track_candidate_observer_ids": born,
            "force_track_disappearance_observer_ids": gone, "production_due_potential": due,
            "event_labels": event_labels}


def _birth_diagnostic(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    bforces, aforces = _value(before.get("forces")), _value(after.get("forces"))
    if not isinstance(bforces, list) or not isinstance(aforces, list):
        return {"status": "UNKNOWN", "candidate_count": 0, "candidates": []}
    before_ids = {_value(f.get("id")) for f in bforces if isinstance(f, dict)}
    candidates = []
    for force in aforces:
        if not isinstance(force, dict):
            continue
        ident = _value(force.get("id"))
        conf = _value(force.get("confidence"))
        if ident not in before_ids and conf == "NEW_TRACK":
            candidates.append({"observer_id": ident, "confidence": "NEW_TRACK",
                               "owner": _value(force.get("owner")),
                               "source": _value(force.get("source")),
                               "destination": _value(force.get("destination")),
                               "units": _count_vector(force.get("units")),
                               "progress": _value(force.get("progress")),
                               "cause": "UNKNOWN", "classification": "CANDIDATE"})
    return {"status": "CANDIDATE" if candidates else "NO_RELIABLE_CANDIDATE",
            "candidate_count": len(candidates), "candidates": candidates}


def _error_code(exc: BaseException) -> str:
    return str(exc).split(":", 1)[0] or type(exc).__name__


def _decision_metrics(before_state: SimulationState, predicted: SimulationState,
                      after_state: SimulationState, after_canonical: Any) -> dict[str, Any]:
    p_towers = {t.id: t for t in predicted.towers}
    o_towers = {t.id: t for t in after_state.towers}
    owner_pairs = [(p_towers[i].owner, o_towers[i].owner) for i in p_towers.keys() & o_towers.keys()]
    unit_pairs = [(p_towers[i].units, o_towers[i].units) for i in p_towers.keys() & o_towers.keys()]
    p_forces: dict[tuple[Any, ...], list[Any]] = collections.defaultdict(list)
    o_forces: dict[tuple[Any, ...], list[Any]] = collections.defaultdict(list)
    for force in predicted.forces:
        key = (force.owner, force.source, force.destination, force.units)
        p_forces[key].append(force)
    canonical_forces = getattr(getattr(after_canonical, "forces", None), "value", None) or ()
    for force in after_state.forces:
        key = (force.owner, force.source, force.destination, force.units)
        o_forces[key].append(force)
    canonical_by_key: dict[tuple[Any, ...], list[Any]] = collections.defaultdict(list)
    for force in canonical_forces:
        units_fact = getattr(force, "units", None)
        units_obj = getattr(units_fact, "value", None)
        unit_counts = dict(getattr(units_obj, "counts", ())) if units_obj is not None else {}
        units = tuple(unit_counts[i] for i in range(10)) if set(unit_counts) == set(range(10)) else None
        if units is None:
            continue
        key = (getattr(getattr(force, "owner", None), "value", None),
               getattr(getattr(force, "source", None), "value", None),
               getattr(getattr(force, "destination", None), "value", None), units)
        canonical_by_key[key].append(force)
    eta_errors = []
    eta_unknown = 0
    for key in p_forces.keys() & o_forces.keys():
        if len(p_forces[key]) != 1 or len(o_forces[key]) != 1 or len(canonical_by_key.get(key, ())) != 1:
            eta_unknown += min(len(p_forces[key]), len(o_forces[key]))
            continue
        predicted_force = p_forces[key][0]
        observed_force = canonical_by_key[key][0]
        src, dst = p_towers.get(predicted_force.source), p_towers.get(predicted_force.destination)
        observed_eta_fact = getattr(observed_force, "eta_ms", None)
        observed_eta = getattr(observed_eta_fact, "value", None)
        if src is None or dst is None or type(observed_eta) is not int or predicted_force.accelerated is None:
            eta_unknown += 1
            continue
        try:
            eta = motion(Units(tuple(enumerate(predicted_force.units))), src.position,
                         dst.position, predicted_force.accelerated, predicted_force.progress)[2]
        except Exception:
            eta_unknown += 1
            continue
        if type(eta) is int:
            eta_errors.append(abs(eta - observed_eta) / 250.0)
        else:
            eta_unknown += 1
    b_towers = {t.id: t for t in before_state.towers}
    changed_owner_ids = [i for i in b_towers.keys() & o_towers.keys()
                         if i in {t.id for t in before_state.towers} and
                         b_towers[i].owner != o_towers[i].owner]
    return {"ownership": {"eligible_tower_pairs": len(owner_pairs),
                "correct": sum(a == b for a, b in owner_pairs),
                "mismatch": sum(a != b for a, b in owner_pairs),
                "accuracy": sum(a == b for a, b in owner_pairs) / len(owner_pairs) if owner_pairs else None},
            "remaining_units": {"eligible_tower_vectors": len(unit_pairs),
                "exact_vectors": sum(a == b for a, b in unit_pairs),
                "absolute_unit_error": sum(abs(x-y) for a,b in unit_pairs for x,y in zip(a,b)),
                "exact_vector_share": sum(a == b for a, b in unit_pairs) / len(unit_pairs) if unit_pairs else None},
            "current_leg_eta_estimator_agreement": {"eligible_force_pairs": len(eta_errors), "unknown_or_ambiguous_pairs": eta_unknown,
                "absolute_eta_error_ticks": eta_errors,
                "mean_absolute_eta_error_ticks": sum(eta_errors)/len(eta_errors) if eta_errors else None,
                "exact_eta_pairs": sum(x == 0 for x in eta_errors)},
            "owner_change_result_agreement": {"observed_owner_change_towers": len(changed_owner_ids),
                "correct_final_owner": sum(p_towers[i].owner == o_towers[i].owner for i in changed_owner_ids),
                "eligible": len(changed_owner_ids),
                "accuracy": (sum(p_towers[i].owner == o_towers[i].owner for i in changed_owner_ids) /
                             len(changed_owner_ids) if changed_owner_ids else None),
                "actual_capture_verdict": "UNKNOWN_FROM_OBSERVED_OWNER_CHANGE_ALONE"}}


def _probe_object_blockers(state: SimulationState) -> list[dict[str, Any]]:
    """Overlapping local probes; never a whole-state acceptance result."""
    found: list[dict[str, Any]] = []
    for tower in state.towers:
        small = SimulationState(state.world_sequence, state.player, state.match_epoch,
                                state.document, (tower,), (), state.simulated_ticks)
        try:
            step(small)
        except UnsupportedState as exc:
            found.append({"scope": "PER_TOWER_PROBE_ONLY", "tower_id": tower.id,
                          "code": _error_code(exc)})
    towers = {t.id: t for t in state.towers}
    for index, force in enumerate(state.forces):
        endpoints = {ident: towers[ident] for ident in (force.source, force.destination)
                     if ident in towers}
        if len(endpoints) != 2:
            found.append({"scope": "PER_FORCE_PROBE_ONLY", "force_index": index,
                          "code": "ENDPOINT_UNAVAILABLE"})
            continue
        # Keep endpoint tower guards visible in the diagnostic, but label the
        # result as an isolated probe, not a counterfactual whole-world result.
        small = SimulationState(state.world_sequence, state.player, state.match_epoch,
                                state.document, tuple(endpoints.values()), (force,), state.simulated_ticks)
        try:
            step(small)
        except UnsupportedState as exc:
            found.append({"scope": "PER_FORCE_ENDPOINT_PROBE_ONLY", "force_index": index,
                          "code": _error_code(exc)})
    return found


def _hash_inputs() -> dict[str, Any]:
    differential = json.loads(DIFFERENTIAL_PATH.read_text(encoding="utf-8"))
    holdout = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    trajectories = json.loads(TRAJECTORIES_PATH.read_text(encoding="utf-8"))
    expected_raw = {row["cohort"]: row["raw_sha256"] for row in trajectories.get("cohorts", [])}
    split = {}
    for key, doc in (("development", differential), ("holdout", holdout)):
        for row in doc.get("cohorts", []):
            if row.get("cohort"):
                split[row["cohort"]] = key
    cohorts = sorted(set(expected_raw) | set(split))
    expected_corpus = {
        str(DEVELOPMENT_CORPUS.relative_to(ROOT)): differential.get("corpus_sha256"),
        str(HOLDOUT_CORPUS.relative_to(ROOT)): holdout.get("corpus_sha256"),
    }
    files: dict[str, dict[str, Any]] = {}
    for cohort in cohorts:
        path = ROOT / "runtime/research/v2" / f"snapshots-{cohort}.jsonl"
        actual = _sha256(path) if path.is_file() else None
        files[str(path.relative_to(ROOT))] = {"cohort": cohort, "split": split.get(cohort, "trajectory_only"),
                                             "expected_sha256": expected_raw.get(cohort),
                                             "actual_sha256": actual,
                                             "matches_manifest": actual is not None and actual == expected_raw.get(cohort)}
    corpora = {}
    for rel, expected in expected_corpus.items():
        path = ROOT / rel
        actual = _sha256(path) if path.is_file() else None
        corpora[rel] = {"expected_sha256": expected, "actual_sha256": actual,
                        "matches_manifest": actual is not None and actual == expected}
    return {"cohorts": cohorts, "splits": split, "raw_files": files, "corpus_manifests": corpora,
            "all_raw_hashes_match": all(x["matches_manifest"] for x in files.values()),
            "all_corpus_hashes_match": all(x["matches_manifest"] for x in corpora.values())}


def _analyze_cohort(cohort: str, split: str, raw_path: Path) -> dict[str, Any]:
    counts = collections.Counter()
    status_counts = collections.Counter()
    primary_counts = collections.Counter()
    readiness_counts = collections.Counter()
    readiness_transition_counts = collections.Counter()
    readiness_bucket_transition_counts = collections.Counter()
    multi_counts = collections.Counter()
    active_by_status = collections.Counter()
    event_counts = collections.Counter()
    edges: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    previous_tick_key: tuple[Any, Any] | None = None
    previous_semantic: tuple[dict[str, Any], bool, list[str]] | None = None
    probes_done = 0
    with raw_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            counts["raw_records"] += 1
            try:
                raw = json.loads(line)
            except Exception as exc:
                counts["invalid_json_records"] += 1
                current = None
                semantic = ({}, False, [f"invalid_json:{type(exc).__name__}"])
            else:
                current = raw if isinstance(raw, dict) else None
                semantic = _raw_semantic_signature(raw) if current is not None else ({}, False, ["record_not_object"])
            if current is None:
                previous_tick_key = None
                sample = {"raw": None, "semantic": semantic, "scope": None, "tick": None,
                          "sequence": None, "line": line_number}
            else:
                scope = _scope(current)
                tick = _value(current.get("tick"))
                key = (scope, tick)
                # Only collapse repeated contiguous, known scope/tick polls.
                if type(tick) is int and key == previous_tick_key:
                    counts["same_scope_tick_duplicate_records"] += 1
                    continue
                if type(tick) is int:
                    previous_tick_key = key
                else:
                    previous_tick_key = None
                sample = {"raw": current, "semantic": semantic, "scope": scope, "tick": tick,
                          "sequence": current.get("sequence"), "line": line_number}
            counts["retained_observations"] += 1
            if previous is None:
                previous = sample
                previous_semantic = semantic
                counts["initial_observations_without_prior"] += 1
                continue
            counts["all_distinct_observed_tick_edges"] += 1
            before_raw, after_raw = previous["raw"], sample["raw"]
            active = _active(previous_semantic, semantic)
            active_by_status[active] += 1
            ref = {"before_line": previous["line"], "after_line": sample["line"],
                   "before_sequence": previous["sequence"], "after_sequence": sample["sequence"],
                   "before_tick": previous["tick"], "after_tick": sample["tick"]}
            scope_same = previous["scope"] == sample["scope"]
            tick_delta = ((sample["tick"] - previous["tick"]) & 65535
                          if type(sample["tick"]) is int and type(previous["tick"]) is int else None)
            consecutive = scope_same and tick_delta == 1
            if consecutive:
                counts["same_scope_consecutive_edges"] += 1
            else:
                counts["scope_or_tick_gap_edges"] += 1
            status = None
            primary = None
            category = None
            readiness_rule = None
            readiness: tuple[str, ...] = ()
            after_readiness: tuple[str, ...] = ()
            detailed_readiness_bucket = None
            multi: list[dict[str, Any]] = []
            decision = None
            execution = "NOT_ATTEMPTED_GAP"
            birth = (_birth_diagnostic(before_raw, after_raw)
                     if before_raw is not None and after_raw is not None else
                     {"status": "UNKNOWN", "candidate_count": 0, "candidates": []})
            event_patterns = (_known_field_delta(before_raw, after_raw)
                              if before_raw is not None and after_raw is not None else {})
            event_labels: list[str] = []
            event_labels.extend(event_patterns.get("event_labels", []))
            if birth["candidate_count"]:
                event_counts["new_force_track_candidate_edges"] += 1
            if not consecutive:
                status, primary, category = "REJECTED", "OBSERVATION_GAP", "OBSERVATION_GAP"
            elif before_raw is None or after_raw is None:
                status, primary, category = "COVERAGE_GAP", "INVALID_RAW_RECORD", "OTHER"
            else:
                try:
                    before_canonical = state_from_dict(before_raw)
                    readiness = control_readiness_gaps(before_canonical, before_canonical.received_at_ms)
                    for item in readiness:
                        readiness_counts["before:" + item] += 1
                    normalized, buckets = _readiness_edge_labels("before", readiness)
                    readiness_transition_counts.update(normalized)
                    readiness_bucket_transition_counts.update(buckets)
                    before_state = from_canonical(before_canonical)
                except UnsupportedState as exc:
                    primary = _error_code(exc)
                    if primary == "NOT_READY":
                        # The gate string contains a truncated list; keep the
                        # independently enumerated full readiness gaps above.
                        status = "REJECTED"
                        category, classification, detailed_readiness_bucket = _not_ready_classification(readiness)
                        readiness_rule = {"classification": classification,
                                          "input_stage": detailed_readiness_bucket,
                                          "raw_api_code": primary}
                    else:
                        status, category = _unsupported_status(primary)
                except Exception as exc:
                    primary = f"PARSE:{type(exc).__name__}"
                    status, category = "COVERAGE_GAP", "COVERAGE"
                else:
                    try:
                        prediction = step(before_state)
                    except UnsupportedState as exc:
                        primary = _error_code(exc)
                        status, category = "REJECTED", _primary_class(primary)
                        if probes_done < PROBE_LIMIT_PER_COHORT:
                            multi = _probe_object_blockers(before_state)
                            probes_done += 1
                            for probe in multi:
                                multi_counts[probe["code"]] += 1
                    except Exception as exc:
                        primary = f"STEP:{type(exc).__name__}"
                        status, category = "COVERAGE_GAP", "OTHER"
                    else:
                        execution = "EXECUTED"
                        try:
                            after_canonical = state_from_dict(after_raw)
                            after_readiness = control_readiness_gaps(after_canonical, after_canonical.received_at_ms)
                            for item in after_readiness:
                                readiness_counts["after:" + item] += 1
                            normalized, buckets = _readiness_edge_labels("after", after_readiness)
                            readiness_transition_counts.update(normalized)
                            readiness_bucket_transition_counts.update(buckets)
                            after_state = from_canonical(after_canonical)
                        except UnsupportedState as exc:
                            primary = _error_code(exc)
                            if primary == "NOT_READY":
                                category, classification, detailed_readiness_bucket = _not_ready_classification(after_readiness)
                                status = "REJECTED"
                                readiness_rule = {"classification": classification,
                                                  "input_stage": detailed_readiness_bucket,
                                                  "raw_api_code": primary}
                            else:
                                status, category = _unsupported_status(primary)
                        except Exception as exc:
                            primary = f"AFTER_PARSE:{type(exc).__name__}"
                            status, category = "COVERAGE_GAP", "COVERAGE"
                        else:
                            status = "SUCCESS" if signature(prediction) == signature(after_state) else "MISMATCH"
                            category = "EXACT_MATCH" if status == "SUCCESS" else "EXACT_MISMATCH"
                            if status == "MISMATCH" and birth["candidate_count"]:
                                event_labels.append("EXTERNAL_ACTION_UNACCOUNTED_CANDIDATE_ACTOR_CAUSE_UNKNOWN")
                                event_counts["external_action_unaccounted_candidate_edges"] += 1
                            decision = _decision_metrics(before_state, prediction, after_state, after_canonical)
                            event_patterns["decision_metrics"] = decision
            for label in set(event_labels):
                event_counts[label] += 1
            status_counts[status] += 1
            primary_counts[f"{category}:{primary or 'NONE'}"] += 1
            edge = {"edge_index": counts["all_distinct_observed_tick_edges"], **ref,
                    "scope_same": scope_same, "tick_delta_mod_u16": tick_delta,
                    "same_scope_consecutive": consecutive, "active": active,
                    "raw_activity_gaps": sorted(set(previous_semantic[2] + semantic[2])),
                    "comparison_status": status, "comparison_execution": execution,
                    "primary_blocker": primary, "primary_category": category,
                    "detailed_readiness_bucket": detailed_readiness_bucket,
                    "readiness_primary_rule": readiness_rule,
                    "control_readiness_gaps": list(readiness),
                    "after_input_readiness_gaps": list(after_readiness),
                    "multi_blocker": multi, "new_force_diagnostic": birth,
                    "event_pattern_labels": sorted(set(event_labels)),
                    "observed_event_patterns": event_patterns}
            if status == "MISMATCH" and isinstance(before_raw, dict) and isinstance(after_raw, dict):
                edge["mismatch_scope"] = "COMPLETE_SIGNATURE"
            edges.append(edge)
            previous, previous_semantic = sample, semantic
    active_known = active_by_status["ACTIVE_KNOWN"]
    active_unknown = active_by_status["ACTIVE_UNKNOWN"]
    active_success = sum(1 for e in edges if e["active"] == "ACTIVE_KNOWN" and e["comparison_status"] == "SUCCESS")
    active_mismatch = sum(1 for e in edges if e["active"] == "ACTIVE_KNOWN" and e["comparison_status"] == "MISMATCH")
    active_accepted = active_success + active_mismatch
    status_total = sum(status_counts.values())
    executed = status_counts["SUCCESS"] + status_counts["MISMATCH"]
    active_unknown_executable = sum(1 for e in edges if e["active"] == "ACTIVE_UNKNOWN" and
                                    e["comparison_status"] in ("SUCCESS", "MISMATCH"))
    gameplay = collections.defaultdict(collections.Counter)
    for edge in edges:
        patterns = edge.get("observed_event_patterns", {})
        labels = set(edge.get("event_pattern_labels", []))
        layers = []
        if any(x.startswith("FORCE_TRACK_APPEARANCE") for x in labels): layers.append("force_appearance_candidate")
        if "FORCE_PROGRESS_CHANGE_OBSERVED" in labels: layers.append("movement_observed")
        if "PRODUCTION_DUE_POTENTIAL" in labels: layers.append("production_due_potential")
        if "UNIT_INCREASE_PRODUCTION_OR_ARRIVAL_CANDIDATE" in labels: layers.append("production_or_arrival_candidate")
        if any(x.startswith("OWNER_CHANGE") for x in labels): layers.append("capture_or_owner_candidate")
        if any(x.startswith("FORCE_TRACK_DISAPPEARANCE") for x in labels): layers.append("arrival_or_disappearance_candidate")
        if edge["comparison_status"] == "COVERAGE_GAP": layers.append("coverage_gap")
        if edge["comparison_status"] == "REJECTED": layers.append("rejected")
        if not layers and edge["active"] == "ACTIVE_KNOWN": layers.append("other_known_activity")
        for layer in set(layers):
            gameplay[layer][edge["comparison_status"]] += 1
    decision_totals = {"ownership_pairs": 0, "ownership_correct": 0,
        "unit_vectors": 0, "unit_vectors_exact": 0, "absolute_unit_error": 0,
        "capture_eligible": 0, "capture_correct": 0, "eta_pairs": 0,
        "eta_exact": 0, "eta_error_ticks": []}
    for edge in edges:
        decision = edge.get("observed_event_patterns", {}).get("decision_metrics")
        if not decision: continue
        own = decision["ownership"]; units = decision["remaining_units"]
        cap = decision["owner_change_result_agreement"]; eta = decision["current_leg_eta_estimator_agreement"]
        decision_totals["ownership_pairs"] += own["eligible_tower_pairs"]
        decision_totals["ownership_correct"] += own["correct"]
        decision_totals["unit_vectors"] += units["eligible_tower_vectors"]
        decision_totals["unit_vectors_exact"] += units["exact_vectors"]
        decision_totals["absolute_unit_error"] += units["absolute_unit_error"]
        decision_totals["capture_eligible"] += cap["eligible"]
        decision_totals["capture_correct"] += cap["correct_final_owner"]
        decision_totals["eta_pairs"] += eta["eligible_force_pairs"]
        decision_totals["eta_exact"] += eta["exact_eta_pairs"]
        decision_totals["eta_error_ticks"].extend(eta["absolute_eta_error_ticks"])
    eta_vals = sorted(decision_totals.pop("eta_error_ticks"))
    def quantile(q: float) -> float | None:
        if not eta_vals: return None
        index = (len(eta_vals)-1)*q
        lo, hi = int(index), min(int(index)+1, len(eta_vals)-1)
        return eta_vals[lo] + (eta_vals[hi]-eta_vals[lo])*(index-lo)
    decision_summary = {**decision_totals,
        "ownership_accuracy": decision_totals["ownership_correct"] / decision_totals["ownership_pairs"] if decision_totals["ownership_pairs"] else None,
        "remaining_units_exact_vector_share": decision_totals["unit_vectors_exact"] / decision_totals["unit_vectors"] if decision_totals["unit_vectors"] else None,
        "capture_accuracy": decision_totals["capture_correct"] / decision_totals["capture_eligible"] if decision_totals["capture_eligible"] else None,
        "eta_error_ticks_p25_median_p75_max": {"p25": quantile(.25), "median": quantile(.5), "p75": quantile(.75), "max": eta_vals[-1] if eta_vals else None}}
    primary_shares = {f"{category}:{code}": n for (category, code), n in
                      collections.Counter((e["primary_category"], e["primary_blocker"] or "NONE") for e in edges).items()}
    return {"cohort": cohort, "split": split, "counts": dict(counts),
            "active_counts": dict(active_by_status), "comparison_status_counts": dict(status_counts),
            "primary_blockers": dict(primary_counts), "control_readiness_gap_counts": dict(readiness_counts),
            "control_readiness_gap_transition_counts_normalized": dict(readiness_transition_counts),
            "control_readiness_bucket_transition_counts": dict(readiness_bucket_transition_counts),
            "multi_blocker_probe_counts_sampled": dict(multi_counts),
            "multi_blocker_probe_edges_sampled": probes_done,
            "known_active_metrics": {"known_active_edges": active_known,
                "active_unknown_edges": active_unknown,"known_active_executable": active_accepted,
                "known_active_success": active_success,"known_active_mismatch": active_mismatch,
                "accuracy_among_comparable_known_active": active_success / (active_success + active_mismatch)
                    if active_success + active_mismatch else None,
                "coverage_lower_bound_known_active_over_known_plus_unknown": active_accepted / (active_known + active_unknown)
                    if active_known + active_unknown else None,
                "coverage_upper_bound_if_all_active_unknown_executable": (active_accepted + active_unknown) / (active_known + active_unknown)
                    if active_known + active_unknown else None,
                "active_unknown_executable": active_unknown_executable,
                "known_active_coverage": active_accepted / active_known if active_known else None},
            "coverage_metrics": {"all_edges": status_total, "same_scope_consecutive": counts["same_scope_consecutive_edges"],
                "executable": executed, "accepted": executed, "rejected": status_counts["REJECTED"],
                "mismatches": status_counts["MISMATCH"], "coverage_gaps": status_counts["COVERAGE_GAP"],
                "exact_match_share_all_edges": status_counts["SUCCESS"] / status_total if status_total else None,
                "accuracy_among_executable": status_counts["SUCCESS"] / executed if executed else None,
                "coverage_among_consecutive": executed / counts["same_scope_consecutive_edges"] if counts["same_scope_consecutive_edges"] else None},
            "gameplay_candidate_layers": {k: dict(v) for k, v in gameplay.items()},
            "decision_metric_totals": decision_summary,
            "primary_blocker_ranking": sorted(primary_shares.items(), key=lambda x: (-x[1], x[0])),
            "edges": edges}


def run_coverage(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    inputs = _hash_inputs()
    git = _git_state()
    source_paths = [DIFFERENTIAL_PATH, HOLDOUT_PATH, TRAJECTORIES_PATH,
                    ROOT / "src/kiomet_ai/v2/control.py", ROOT / "src/kiomet_ai/v2/state.py",
                    ROOT / "src/kiomet_ai/v2/serialization.py", ROOT / "src/kiomet_ai/v2/sim/model.py",
                    ROOT / "src/kiomet_ai/v2/sim/step.py", ROOT / "tools/v2_sim_differential.py"]
    source_manifest = {str(p.relative_to(ROOT)): _sha256(p) for p in source_paths}
    core_mismatches = []
    for report_path in (DIFFERENTIAL_PATH, HOLDOUT_PATH):
        doc = json.loads(report_path.read_text(encoding="utf-8"))
        for rel, expected in (doc.get("source_manifest") or {}).items():
            path = ROOT / Path(rel.replace("\\", "/"))
            if path.is_file() and _sha256(path) != expected:
                core_mismatches.append({"manifest": str(report_path.relative_to(ROOT)),
                                        "path": rel, "expected": expected,
                                        "actual": _sha256(path)})
    result: dict[str, Any] = {"status": "CANDIDATE", "analysis_version": ANALYSIS_VERSION,
        "question": "What share of all observed adjacent tick edges and raw-visible active edges can the current default simulator API execute and match?",
        "method": {"first_observation": "Retain the first observation in each contiguous scope/world-tick run; repeated polls within that run are not separate edges. Scope is document_id, match_id, player_id.",
            "all_denominator": "Every adjacent retained distinct-observation edge, including scope changes and skipped/missing ticks. Gaps are explicit rejected edges; same-scope consecutive edges are a separate subdenominator.",
        "active": "Determined from raw observation values before simulator conversion. Excludes timestamps, world tick, knowledge/provenance wrappers, force observer IDs/confidence. Semantic fields include all known effects and known optional supply-line values. Unknown optional supply-line values alone do not make an otherwise complete signature incomplete. Incomplete signatures remain ACTIVE_UNKNOWN unless a same-known-field semantic difference establishes ACTIVE_KNOWN.",
            "execution": "For same-scope consecutive edges only: from_canonical(before), step(before) with default Scenario/no inferred actions/combat/supply-line/terminal premises, then exact full signature comparison with from_canonical(after). Success, mismatch, rejection, and coverage gap are mutually exclusive.",
            "gap_precedence": "Scope/tick discontinuity is classified as REJECTED_OBSERVATION_GAP before execution; it remains in ALL denominator.",
        "candidate_events": "Observed new force track and raw state-change patterns are independent diagnostics. A new track is only CANDIDATE with actor/cause UNKNOWN; a due production phase is potential, not observed production. Unit increases and owner changes are descriptive candidates, not proof of production, capture, or actor.",
        "decision_metrics": "Ownership/unit metrics apply to comparable endpoints. Current-leg ETA agreement is predicted motion estimator versus observer estimate, not actual arrival error; actual-arrival tick error remains UNKNOWN. An observed owner change is not automatically a capture or winner label.",
            "multi_blockers": "Primary blocker is the API's first refusal. Separate per-tower/per-force isolated step probes are overlapping diagnostics only, sampled to a fixed maximum per cohort, never counted as whole-state acceptance.",
            "sampling_risk": "Six retained, preselected development/holdout sessions are not a random sample of global gameplay."},
        "inputs": inputs,"source_hashes_current":source_manifest,"historical_source_manifest_mismatches":core_mismatches,
        "manifest_consistent_for_raw_data":inputs["all_raw_hashes_match"] and inputs["all_corpus_hashes_match"],
        "simulator_manifest_drift":bool(core_mismatches),"git":git,"tool_sha256":_sha256(Path(__file__).resolve()),
        "cohorts":[]}
    if not result["manifest_consistent_for_raw_data"]:
        result["status"] = "FAIL_CLOSED_SOURCE_MANIFEST_MISMATCH"
    else:
        for cohort in inputs["cohorts"]:
            rel = f"runtime/research/v2/snapshots-{cohort}.jsonl"
            result["cohorts"].append(_analyze_cohort(cohort, inputs["splits"].get(cohort, "trajectory_only"), ROOT / rel))
        totals = collections.Counter()
        all_primary = collections.Counter()
        all_status = collections.Counter()
        all_active = collections.Counter()
        all_ready_occurrences = collections.Counter()
        all_ready_transitions = collections.Counter()
        all_buckets = collections.Counter()
        all_gameplay = collections.defaultdict(collections.Counter)
        all_decision = collections.Counter()
        for c in result["cohorts"]:
            totals.update(c["counts"]); all_primary.update(c["primary_blockers"])
            all_status.update(c["comparison_status_counts"]); all_active.update(c["active_counts"])
            all_ready_occurrences.update(c["control_readiness_gap_counts"])
            all_ready_transitions.update(c["control_readiness_gap_transition_counts_normalized"])
            all_buckets.update(c["control_readiness_bucket_transition_counts"])
            for key, counts in c["gameplay_candidate_layers"].items(): all_gameplay[key].update(counts)
            all_decision.update({k:v for k,v in c["decision_metric_totals"].items() if isinstance(v, int)})
        active_rank = sorted(((c["cohort"], c["active_counts"].get("ACTIVE_KNOWN", 0),
                               c["active_counts"].get("ACTIVE_UNKNOWN", 0)) for c in result["cohorts"]),
                             key=lambda x: (-x[1], -x[2], x[0]))
        primary_rank = sorted(all_primary.items(), key=lambda x: (-x[1], x[0]))
        result["totals"] = {"counts": dict(totals), "active_counts": dict(all_active),
                             "comparison_status_counts": dict(all_status),
                             "primary_blockers": dict(all_primary),
                             "coverage_metrics": {"all_edges": sum(all_status.values()),
                                 "same_scope_consecutive": totals["same_scope_consecutive_edges"],
                                 "executable": all_status["SUCCESS"] + all_status["MISMATCH"],
                                 "rejected": all_status["REJECTED"], "mismatches": all_status["MISMATCH"],
                                 "coverage_gaps": all_status["COVERAGE_GAP"],
                                 "exact_match_share_all_edges": all_status["SUCCESS"] / sum(all_status.values()) if sum(all_status.values()) else None,
                                 "accuracy_among_executable": all_status["SUCCESS"] / (all_status["SUCCESS"] + all_status["MISMATCH"]) if all_status["SUCCESS"] + all_status["MISMATCH"] else None},
                             "readiness_gap_occurrences": dict(all_ready_occurrences),
                             "readiness_gap_transitions_normalized": dict(all_ready_transitions),
                             "readiness_bucket_transitions": dict(all_buckets),
                             "gameplay_candidate_layers": {k:dict(v) for k,v in all_gameplay.items()},
                             "decision_metric_integer_totals": dict(all_decision),
                             "active_cohort_ranking": active_rank,
                             "primary_blocker_ranking": primary_rank}
        if core_mismatches:
            result["status"] = "CANDIDATE_SIMULATOR_MANIFEST_DRIFT"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_coverage(args.output)
    print(json.dumps({"status": result["status"], "analysis_version": result["analysis_version"],
                      "manifest_consistent_for_raw_data": result["manifest_consistent_for_raw_data"],
                      "cohorts": len(result["cohorts"]),
                      "totals": result.get("totals", {})}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
