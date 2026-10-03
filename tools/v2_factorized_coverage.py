"""Descriptive factor/entity coverage and blocker bounds for pinned M2A edges.

This analysis reuses pinned raw snapshots and the frozen whole-world edge
fixture. Local probes are explicitly conditional and never certify a world
transition. It does not fill fields or alter simulator gates.
"""
from __future__ import annotations

import collections
import gzip
import io
import hashlib
import json
import math
import sys
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.v2.observe.forces import motion
from kiomet_ai.v2.sim import SimulationState, UnsupportedState, step, ordinary_arrival_boundary
from kiomet_ai.v2.sim.model import SimForce, SimTower
from kiomet_ai.v2.sim.step import phase
from kiomet_ai.v2.observe.rules import DOWNGRADE
from kiomet_ai.v2.state import Units

FIXTURE = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
DEFAULT_REPORT = ROOT / "runtime/research/v2/factorized-coverage-candidate.json"
DEFAULT_AUDIT = ROOT / "runtime/research/v2/factorized-coverage-edge-audit.jsonl.gz"
VERSION = "factorized-coverage-v1"
COHORT_ORDER = ("fe678ebb30ce", "03d032d57e5b", "daf86d0544b7",
                "85391858b5d8", "7d56a775bc4c", "b1f7f9416e92")
FACTOR_NAMES = ("tower_local", "force_local", "movement", "production", "arrival", "ownership")
GATES = ("endpoint", "upgrade_emp", "supply_line", "special", "movement", "arrival",
         "combat", "unknown_path", "relation", "fuel", "other", "after_input_endpoint", "comparison")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_state() -> dict[str, Any]:
    prefix = ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet"]
    def read(*args: str) -> str:
        return subprocess.run(prefix + list(args), cwd=ROOT, check=True,
            capture_output=True, text=True).stdout.rstrip("\r\n")
    status = read("status", "--porcelain=v1", "--untracked-files=all")
    return {"head": read("rev-parse", "HEAD"), "branch": read("branch", "--show-current"),
            "dirty": bool(status), "status_porcelain": status.splitlines()}


def val(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) else None


def is_known(fact: Any) -> bool:
    return isinstance(fact, dict) and fact.get("knowledge") != "UNKNOWN" and fact.get("value") is not None


def units(fact: Any) -> tuple[int, ...] | None:
    data = val(fact)
    pairs = data.get("counts") if isinstance(data, dict) else None
    if not isinstance(pairs, list):
        return None
    try:
        out = dict(pairs)
        if set(out) != set(range(10)) or any(type(out[i]) is not int or not 0 <= out[i] <= 255 for i in range(10)):
            return None
        return tuple(out[i] for i in range(10))
    except (ValueError, TypeError):
        return None


def _tower(row: dict[str, Any]) -> tuple[SimTower | None, list[str]]:
    ident = row.get("id")
    gaps: list[str] = []
    req = ("owner", "tower_type", "units", "capacity", "production", "neighbors", "position", "delay_ticks")
    vals = {k: val(row.get(k)) for k in req}
    for name in req:
        f = row.get(name)
        if not is_known(f): gaps.append(name)
    uv, cv = units(row.get("units")), units(row.get("capacity"))
    pos = vals["position"]
    if type(ident) is not int: gaps.append("id")
    if uv is None: gaps.append("units_vector")
    if cv is None: gaps.append("capacity_vector")
    if not isinstance(pos, (list, tuple)) or len(pos) != 2 or any(type(x) is not int for x in pos): gaps.append("position")
    prod = vals["production"]
    if not isinstance(prod, list): gaps.append("production_shape")
    if gaps:
        return None, sorted(set(gaps))
    effects = val(row.get("effects"))
    effect_map = dict(effects) if isinstance(effects, list) and all(isinstance(x, (list, tuple)) and len(x) == 2 for x in effects) else {}
    morale = effect_map.get("MORALE_BOOST") if type(effect_map.get("MORALE_BOOST")) is bool else None
    line = val(row.get("supply_line_present")) if is_known(row.get("supply_line_present")) else None
    try:
        result = SimTower(ident, vals["owner"], vals["tower_type"], uv, cv,
            tuple((int(x[0]), int(x[1])) for x in prod), tuple(vals["neighbors"]),
            tuple(pos), vals["delay_ticks"], morale, val(row.get("relation")), line)
        return result, []
    except Exception as exc:
        return None, ["SIMTOWER:" + type(exc).__name__]


def _force(row: dict[str, Any]) -> tuple[SimForce | None, list[str]]:
    req = ("owner", "source", "destination", "units", "progress")
    gaps = [x for x in req if not is_known(row.get(x))]
    uv = units(row.get("units"))
    if uv is None: gaps.append("units_vector")
    accel = val(row.get("accelerated"))
    if type(accel) is not bool: accel = None  # Speed remains observable; arrival threshold may not.
    if gaps: return None, sorted(set(gaps))
    try:
        return SimForce(val(row["owner"]), val(row["source"]), val(row["destination"]), uv,
                        val(row["progress"]), accel, val(row.get("relation")),
                        val(row.get("terminal")), val(row.get("fuel"))), []
    except Exception as exc:
        return None, ["SIMFORCE:" + type(exc).__name__]


def _infer_pinned_acceleration(force: SimForce, row: dict[str, Any], towers: dict[int, SimTower]) -> SimForce:
    accel_fact = row.get("accelerated")
    if force.accelerated is not None or is_known(accel_fact):
        return force
    eta_fact = row.get("eta_ms")
    eta, source = val(eta_fact), eta_fact.get("source") if isinstance(eta_fact, dict) else None
    if type(eta) is not int or not isinstance(source, str) or "pinned current-leg" not in source:
        return force
    if force.source not in towers or force.destination not in towers:
        return force
    candidates = [boost for boost in (False, True)
        if motion(Units(tuple(enumerate(force.units))), towers[force.source].position,
            towers[force.destination].position, boost, force.progress)[2] == eta]
    if len(candidates) != 1:
        return force
    return SimForce(force.owner, force.source, force.destination, force.units,
        force.progress, candidates[0], force.relation, force.terminal, force.fuel)


def _rows(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = val(raw.get(key)) if key == "forces" else raw.get(key)
    return value if isinstance(value, list) else []


def _keyed_forces(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in _rows(raw, "forces"):
        if isinstance(row, dict) and val(row.get("id")) is not None:
            out[str(val(row.get("id")))].append(row)
    return dict(out)


def _reliable_id(raw: dict[str, Any], row: dict[str, Any]) -> bool:
    ident = row.get("id")
    scope_ok = (isinstance(raw.get("document_id"), str) and bool(raw["document_id"])
        and isinstance(val(raw.get("match_id")), str) and bool(val(raw.get("match_id")))
        and type(val(raw.get("player_id"))) is int and val(raw.get("player_id")) > 0)
    rows = _rows(raw, "forces")
    ident_value = val(ident)
    unique = sum(1 for item in rows if isinstance(item, dict) and val(item.get("id")) == ident_value) == 1
    return (scope_ok and unique and isinstance(ident, dict) and ident.get("knowledge") == "DERIVED"
        and isinstance(ident_value, str) and bool(ident_value)
        and val(row.get("visibility")) is True
        and val(row.get("confidence")) in ("NEW_TRACK", "UNIQUE_CONTINUATION"))


def _edge_horizon_compatible(before_raw: dict[str, Any], after_raw: dict[str, Any]) -> tuple[bool, str | None]:
    scope_before = (before_raw.get("document_id"), val(before_raw.get("match_id")), val(before_raw.get("player_id")))
    scope_after = (after_raw.get("document_id"), val(after_raw.get("match_id")), val(after_raw.get("player_id")))
    if scope_before != scope_after:
        return False, "SCOPE_CHANGED"
    before_tick, after_tick = val(before_raw.get("tick")), val(after_raw.get("tick"))
    if type(before_tick) is not int or type(after_tick) is not int:
        return False, "TICK_UNKNOWN"
    if (after_tick - before_tick) % 65536 != 1:
        return False, "NONCONSECUTIVE_TICK"
    return True, None


def _unique_continuation(before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]],
                         before_raw: dict[str, Any], after_raw: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if len(before_rows) != 1 or len(after_rows) != 1:
        return None, "AMBIGUOUS_OR_MISSING_IDENTITY"
    before, after = before_rows[0], after_rows[0]
    horizon_ok, horizon_reason = _edge_horizon_compatible(before_raw, after_raw)
    if not horizon_ok:
        return None, horizon_reason
    if not _reliable_id(before_raw, before) or not _reliable_id(after_raw, after):
        return None, "UNRELIABLE_OR_INVISIBLE_IDENTITY"
    if val(after.get("confidence")) != "UNIQUE_CONTINUATION":
        return None, "AFTER_CONFIDENCE_NOT_UNIQUE_CONTINUATION"
    fields = ("owner", "source", "destination", "units")
    if any(not is_known(before.get(name)) or not is_known(after.get(name)) for name in fields):
        return None, "IDENTITY_FIELDS_UNKNOWN"
    if any(val(before[name]) != val(after[name]) for name in fields):
        return None, "CURRENT_LEG_METADATA_CHANGED"
    return after, None


def _canonical_fields(raw: dict[str, Any]) -> tuple[dict[int, SimTower], dict[int, list[str]]]:
    made: dict[int, SimTower] = {}
    gaps: dict[int, list[str]] = {}
    for row in _rows(raw, "towers"):
        if not isinstance(row, dict): continue
        tower, missing = _tower(row)
        ident = row.get("id")
        if tower:
            made[tower.id] = tower
        elif type(ident) is int:
            gaps[ident] = missing
    return made, gaps


def _force_endpoints(raw: dict[str, Any], towers: dict[int, SimTower]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    available, unavailable = [], []
    for index, row in enumerate(_rows(raw, "forces")):
        if not isinstance(row, dict): continue
        force, missing = _force(row)
        if force:
            force = _infer_pinned_acceleration(force, row, towers)
            absent = [x for x in (force.source, force.destination) if x not in towers]
            if absent:
                unavailable.append({"force_index": index, "observer_id": val(row.get("id")),
                                    "missing_endpoint_tower_ids": absent,
                                    "reason": "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"})
            else:
                available.append({"index": index, "row": row, "force": force})
        else:
            unavailable.append({"force_index": index, "observer_id": val(row.get("id")),
                                "missing_fields": missing,
                                "reason": "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"})
    return available, unavailable


def _gate_template() -> dict[str, Any]:
    return {g: {"status": "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", "evidence": [], "unresolved_evidence": []} for g in GATES}


def _put_gate(gates: dict[str, Any], gate: str, status: str, evidence: Any) -> None:
    slot = gates[gate]
    if status == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN":
        slot.setdefault("unresolved_evidence", []).append(evidence)
    if status == "BLOCKED" or slot["status"] != "BLOCKED" and status == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN":
        slot["status"] = status
    elif status == "POTENTIAL" and slot["status"] in ("CLEAR", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN") and not slot.get("unresolved_evidence"):
        slot["status"] = "POTENTIAL"
    slot["evidence"].append(evidence)


def _set_clear(gates: dict[str, Any], gate: str, evidence: Any) -> None:
    slot = gates[gate]
    if slot["status"] == "CLEAR" or slot["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN" and not slot["evidence"]:
        slot["status"] = "CLEAR"
    slot["evidence"].append(evidence)


def _tower_guard_gates(raw: dict[str, Any], towers: dict[int, SimTower]) -> dict[str, Any]:
    gates = _gate_template()
    tick = val(raw.get("tick"))
    if type(tick) is not int:
        for gate in ("upgrade_emp", "supply_line", "special"):
            _put_gate(gates, gate, "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", "tick_unknown")
        return gates
    sequence = (tick + 1) & 65535
    raw_towers = [row for row in _rows(raw, "towers") if isinstance(row, dict)]
    if len({row.get("id") for row in raw_towers}) != len(raw_towers):
        _put_gate(gates, "other", "BLOCKED", {"reason": "DUPLICATE_TOWER_IDS"})
    tower_fields_complete = all(all(is_known(row.get(k)) for k in
        ("owner", "tower_type", "units", "capacity", "production", "delay_ticks")) for row in raw_towers)
    neutral_fields_complete = all(all(is_known(row.get(k)) for k in ("owner", "tower_type", "units")) for row in raw_towers)
    if tower_fields_complete:
        _set_clear(gates, "upgrade_emp", "all visible tower delays known")
        _set_clear(gates, "supply_line", "all production/overflow inputs known; unknown line is guarded by exact predicates")
        _set_clear(gates, "special", "all visible tower production inputs known")
    if neutral_fields_complete:
        _set_clear(gates, "other", "all neutral decay/downgrade inputs known")
    for row in _rows(raw, "towers"):
        if not isinstance(row, dict): continue
        missing = []
        for name in ("delay_ticks", "owner", "units", "capacity", "production", "supply_line_present", "tower_type"):
            f = row.get(name)
            if name == "supply_line_present":
                continue  # Unknown is a supported value with a guarded consequence.
            if not is_known(f): missing.append(name)
        if "delay_ticks" in missing:
            _put_gate(gates, "upgrade_emp", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"tower_id": row.get("id"), "field": "delay_ticks"})
        if set(missing) & {"owner", "units", "capacity", "production", "tower_type"}:
            for gate in ("supply_line", "special"):
                _put_gate(gates, gate, "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"tower_id": row.get("id"), "fields": missing})
        if set(missing) & {"units", "capacity", "neighbors", "position"}:
            _put_gate(gates, "other", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"tower_id": row.get("id"), "fields": missing})
    for tower in towers.values():
        clock = phase(sequence, tower.id)
        if not tower.owner and DOWNGRADE[tower.kind] != 27 and clock % 240 == 0:
            _put_gate(gates, "other", "BLOCKED", {"tower_id": tower.id, "reason": "NEUTRAL_DOWNGRADE"})
        if not tower.owner and clock % 40 == 0 and any(tower.units):
            _put_gate(gates, "other", "BLOCKED", {"tower_id": tower.id, "reason": "NEUTRAL_UNIT_DECAY"})
        if tower.delay:
            _put_gate(gates, "upgrade_emp", "BLOCKED", {"tower_id": tower.id, "delay": tower.delay})
        overflow_blocked_here = False
        post_decay_units = list(tower.units)
        if tower.owner and clock % 120 == 0:
            for unit, count in enumerate(tower.units):
                if count > tower.capacity[unit]:
                    if unit in (4, 5) and tower.supply_line_present is False:
                        post_decay_units[unit] -= 1
                    elif unit or tower.kind == 15:
                        overflow_blocked_here = True
                        _put_gate(gates, "supply_line", "BLOCKED", {"tower_id": tower.id,
                            "reason": "MOBILE_OVERFLOW_SUPPLY_LINE", "unit": unit,
                            "supply_line_present": tower.supply_line_present})
                    else:
                        post_decay_units[unit] -= 1
        for unit, period in tower.production:
            if period <= 0:
                _put_gate(gates, "other", "BLOCKED", {"tower_id": tower.id, "reason": "INVALID_PRODUCTION_PERIOD"})
                continue
            if clock % period != 0: continue
            if overflow_blocked_here:
                _put_gate(gates, "supply_line", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {
                    "tower_id": tower.id, "reason": "production guard follows blocked owned overflow branch"})
                continue
            if unit in (6, 7, 8, 9):
                _put_gate(gates, "special", "BLOCKED", {"tower_id": tower.id, "reason": "SPECIAL_PRODUCTION", "unit": unit})
            elif (1 <= unit <= 5 and any(post_decay_units[6:10])):
                continue
            elif (tower.owner and not post_decay_units[9] and (unit or tower.kind == 15)
                  and tower.capacity[unit] - post_decay_units[unit] < 2 and tower.supply_line_present is not False):
                _put_gate(gates, "supply_line", "BLOCKED", {"tower_id": tower.id,
                    "reason": "PRODUCTION_SUPPLY_LINE", "unit": unit,
                    "supply_line_present": tower.supply_line_present})
    return gates


def _edge_gates(edge: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
                towers: dict[int, SimTower], forces: list[dict[str, Any]],
                unavailable: list[dict[str, Any]], tower_gaps: dict[int, list[str]]) -> dict[str, Any]:
    gates = _tower_guard_gates(before, towers)
    force_rows = _rows(before, "forces")
    force_collection_known = is_known(before.get("forces")) and before.get("coverage") == "PLAYER_VISIBLE_COMPLETE"
    if edge.get("primary_category") == "UNKNOWN_PATH" and edge.get("primary_blocker") == "NOT_READY":
        for item in edge.get("control_readiness_gaps", []):
            if ":source" in item or ":destination" in item:
                _put_gate(gates, "endpoint", "BLOCKED", {"readiness_gap": item})
    endpoint_unknowns = [x for x in unavailable if
        x.get("missing_endpoint_tower_ids") or
        any(field in (x.get("missing_fields") or []) for field in ("source", "destination"))]
    for item in endpoint_unknowns:
        _put_gate(gates, "endpoint", "BLOCKED", item)
    if unavailable:
        _put_gate(gates, "endpoint", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", unavailable)
    if forces:
        complete_force_inputs = force_collection_known and not unavailable and len(forces) == len(force_rows)
        if complete_force_inputs:
            _set_clear(gates, "endpoint", "all visible force endpoints resolve to visible towers")
        else:
            _put_gate(gates, "endpoint", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", unavailable or "force collection incomplete")
        if complete_force_inputs:
            _set_clear(gates, "movement", "all current-leg movement input fields available")
            _set_clear(gates, "arrival", "all current-leg arrival thresholds evaluable")
            _set_clear(gates, "combat", "all visible force arrival contexts evaluated")
            _set_clear(gates, "unknown_path", "all current force legs either non-arriving or terminal-known")
            _set_clear(gates, "relation", "all potentially interacting pair relations evaluated")
            _set_clear(gates, "fuel", "all current-leg arrival fuel branches evaluated")
            _set_clear(gates, "special", "all visible force unit categories known")
            _set_clear(gates, "other", "all visible force owner/count/vector prerequisites evaluated")
        else:
            for gate in ("movement", "arrival", "combat", "unknown_path", "fuel", "relation", "special", "other"):
                _put_gate(gates, gate, "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", unavailable or "force collection incomplete")
        # Positive locally known guard witnesses remain usable even if a
        # different force has an unknown endpoint. Missing remote rows only
        # keep the rest of the population unevaluable.
        for i, left in enumerate(forces):
            a = left["force"]
            if not a.owner:
                _put_gate(gates, "other", "BLOCKED", {"force_index": left["index"], "reason": "ZOMBIE_FORCE"})
            if any(a.units[j] for j in (6, 7, 8)):
                _put_gate(gates, "special", "BLOCKED", {"force_index": left["index"], "reason": "SPECIAL_UNITS"})
            for right in forces[i+1:]:
                b = right["force"]
                if a.owner != b.owner and (a.source, a.destination) == (b.destination, b.source):
                    _put_gate(gates, "combat", "BLOCKED", {"force_indices": [left["index"], right["index"]], "reason": "OPPOSED_FORCE_COMBAT"})
        for item in forces:
            force, row, index = item["force"], item["row"], item["index"]
            src, dst = towers[force.source], towers[force.destination]
            try:
                speed, req, _eta = motion(Units(tuple(enumerate(force.units))), src.position,
                                          dst.position, bool(force.accelerated), force.progress)
            except Exception as exc:
                for gate in ("movement", "arrival", "combat", "unknown_path", "fuel", "relation"):
                    _put_gate(gates, gate, "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": type(exc).__name__})
                continue
            progress = min(255, force.progress + speed)
            if force.accelerated is None and force.progress + speed >= max(1, req * 4 // 5):
                _put_gate(gates, "movement", "BLOCKED", {"force_index": index, "reason": "UNKNOWN_ARRIVAL_ACCELERATION"})
                _put_gate(gates, "arrival", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": "UNKNOWN_ARRIVAL_ACCELERATION"})
                _put_gate(gates, "combat", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": "arrival threshold depends on acceleration"})
                _put_gate(gates, "unknown_path", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": "arrival threshold depends on acceleration"})
                _put_gate(gates, "fuel", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": "arrival threshold depends on acceleration"})
            elif progress >= req:
                _set_clear(gates, "arrival", {"force_index": index, "reason": "current_leg_threshold_reached_and_arrival_branch_evaluated",
                    "predicted_progress": progress, "required": req})
                if dst.owner != force.owner and (dst.owner or any(dst.units)):
                    _put_gate(gates, "combat", "BLOCKED", {"force_index": index, "reason": "UNVERIFIED_NORMAL_COMBAT"})
                    if (dst.relation is None or force.relation is None) and dst.owner not in (0, force.owner):
                        _put_gate(gates, "relation", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", {"force_index": index, "reason": "UNKNOWN_PAIR_RELATION"})
                    elif dst.owner not in (0, force.owner):
                        _set_clear(gates, "relation", {"force_index": index, "reason": "known_pair_relation"})
                else:
                    _set_clear(gates, "combat", {"force_index": index, "reason": "no_occupied_foreign_destination"})
                    _set_clear(gates, "relation", {"force_index": index, "reason": "no_relation_gate_on_arrival"})
                if val(row.get("terminal")) is not True and not edge.get("scenario_terminal_forces"):
                    _put_gate(gates, "unknown_path", "BLOCKED", {"force_index": index, "reason": "UNKNOWN_POST_ARRIVAL_PATH"})
                else:
                    _set_clear(gates, "unknown_path", {"force_index": index, "reason": "terminal_known"})
                if val(row.get("fuel")) is None:
                    merge = (dst.owner == force.owner and dst.supply_line_present is False and
                             any(force.units[i] for i in (4, 5)) and
                             not any(force.units[i] for i in (1, 2, 3, 6, 7, 8, 9)) and
                             not any(dst.units[i] for i in (1, 2, 3, 6, 7, 8, 9)))
                    if merge:
                        _set_clear(gates, "fuel", {"force_index": index, "reason": "fuel_irrelevant_terminal_friendly_many_merge"})
                    else:
                        _put_gate(gates, "fuel", "BLOCKED", {"force_index": index, "reason": "UNKNOWN_ARRIVAL_FUEL"})
                elif val(row.get("fuel")) <= 0:
                    _put_gate(gates, "fuel", "BLOCKED", {"force_index": index, "reason": "EXPIRED_ARRIVAL"})
                else:
                    _set_clear(gates, "fuel", {"force_index": index, "reason": "fuel_positive"})
            else:
                _set_clear(gates, "arrival", {"force_index": index, "predicted_progress": progress, "required": req})
                for gate in ("combat", "unknown_path", "relation", "fuel"):
                    _set_clear(gates, gate, {"force_index": index, "reason": "current_leg_not_arriving"})
    elif force_collection_known and not force_rows:
        for gate in ("endpoint", "movement", "arrival", "combat", "unknown_path", "relation", "fuel", "special", "other"):
            _set_clear(gates, gate, "complete visible force set is empty")
    else:
        for gate in ("endpoint", "movement", "arrival", "combat", "unknown_path", "relation", "fuel", "special", "other"):
            _put_gate(gates, gate, "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", "force collection unknown/incomplete")
    # The guard-support surface and exact endpoint comparison are separate:
    # mismatches are known non-agreements; refusals have unknown residual result.
    if edge.get("comparison_status") == "SUCCESS":
        _set_clear(gates, "comparison", "complete exact full-state agreement")
    elif edge.get("comparison_status") == "MISMATCH":
        _put_gate(gates, "comparison", "BLOCKED", {"reason": "SUPPORTED_BUT_MISMATCH", "cause": "UNKNOWN"})
    else:
        _put_gate(gates, "comparison", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN",
                  {"reason": "whole-world comparison not executed or endpoint conversion refused"})
    after_endpoint_gaps = [x for x in edge.get("after_input_readiness_gaps", [])
                           if x.startswith("force:") and (x.endswith(":source") or x.endswith(":destination"))]
    if after_endpoint_gaps:
        _put_gate(gates, "after_input_endpoint", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN",
                  [{"stage": "after_input", "readiness_gap": x} for x in after_endpoint_gaps])
    elif is_known(after.get("forces")) and after.get("coverage") == "PLAYER_VISIBLE_COMPLETE":
        _set_clear(gates, "after_input_endpoint", "after force collection is present; no after-input endpoint gap in fixture")
    else:
        _put_gate(gates, "after_input_endpoint", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN", "after-input force collection incomplete")
    # Preserve the observed API first refusal as a confirmed blocker even when
    # a separately evaluated guard also applies. Unknown guard families stay
    # NTE and are never inferred clear from this mapping.
    first = edge.get("primary_blocker") or ""
    first_gate = None
    if first in ("ACTIVE_UPGRADE_OR_EMP",): first_gate = "upgrade_emp"
    elif first in ("PRODUCTION_SUPPLY_LINE", "MOBILE_OVERFLOW_SUPPLY_LINE"): first_gate = "supply_line"
    elif first in ("SPECIAL_PRODUCTION", "SPECIAL_UNITS"): first_gate = "special"
    elif first in ("UNVERIFIED_NORMAL_COMBAT", "OPPOSED_FORCE_COMBAT"): first_gate = "combat"
    elif first == "UNKNOWN_POST_ARRIVAL_PATH": first_gate = "unknown_path"
    elif first == "UNKNOWN_ARRIVAL_ACCELERATION": first_gate = "movement"
    elif first in ("UNKNOWN_ARRIVAL_FUEL", "EXPIRED_ARRIVAL"): first_gate = "fuel"
    elif first == "UNKNOWN_PAIR_RELATION": first_gate = "relation"
    elif (first == "NOT_READY" and edge.get("primary_category") == "UNKNOWN_PATH"
          and any(x.startswith("force:") and (x.endswith(":source") or x.endswith(":destination"))
                  for x in edge.get("control_readiness_gaps", []))): first_gate = "endpoint"
    elif first == "NOT_READY" and edge.get("primary_category") == "OBSERVATION_GAP": first_gate = "other"
    elif first and first not in ("OBSERVATION_GAP", "INVALID_RAW_RECORD", "NOT_READY", "NONE") and not first.startswith(("PARSE:", "STEP:", "AFTER_PARSE:")):
        first_gate = "other"
    if first_gate:
        _put_gate(gates, first_gate, "BLOCKED", {"source": "observed_api_first_refusal", "code": first})
    return gates


def _factor_stats() -> dict[str, collections.Counter]:
    stats = {name: collections.Counter() for name in FACTOR_NAMES}
    stats["ownership"]["conditional_projection_opportunities"] = 0
    return stats


def _tower_projection(t: SimTower) -> tuple[Any, ...]:
    return (t.owner, t.units, t.capacity, t.production, t.delay)


def _factor_edge(edge: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
                 towers: dict[int, SimTower], tower_gaps: dict[int, list[str]],
                 available_forces: list[dict[str, Any]], unavailable: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, collections.Counter]]:
    stats = _factor_stats()
    local_horizon_ok, local_horizon_reason = _edge_horizon_compatible(before, after)
    details: dict[str, Any] = {"conditional_probes": [], "movement": [], "production": [], "arrival": [],
        "local_comparison_horizon": {"eligible": local_horizon_ok, "reason": local_horizon_reason}}
    after_towers, after_tower_gaps = _canonical_fields(after)
    before_rows = {r["id"]: r for r in _rows(before, "towers") if isinstance(r, dict) and type(r.get("id")) is int}
    after_rows = {r["id"]: r for r in _rows(after, "towers") if isinstance(r, dict) and type(r.get("id")) is int}
    # Tower-local conditional no-force probes.
    for ident, tower in towers.items():
        ctr = stats["tower_local"]; ctr["opportunities"] += 1; ctr["input_ready"] += 1
        isolated = SimulationState(val(before.get("tick")), val(before.get("player_id")), str(val(before.get("match_id"))),
                                   before.get("document_id", ""), (tower,), (), 0)
        try:
            predicted = step(isolated)
            ctr["semantically_supported"] += 1
            detail = {"tower_id": ident, "support": "CONDITIONAL_ISOLATED_NO_FORCE_SUCCESS"}
            if ident in after_towers and local_horizon_ok:
                ctr["comparable"] += 1
                ok = _tower_projection(predicted.towers[0]) == _tower_projection(after_towers[ident])
                ctr["matches" if ok else "mismatches"] += 1
                detail["projection_match"] = ok
                if is_known(after_rows.get(ident, {}).get("owner")):
                    own = stats["ownership"]
                    own["conditional_projection_opportunities"] += 1
                    own["conditional_projection_comparable"] += 1
                    owner_ok = predicted.towers[0].owner == val(after_rows[ident]["owner"])
                    own["conditional_projection_matches" if owner_ok else "conditional_projection_mismatches"] += 1
                    detail["conditional_owner_projection_match"] = owner_ok
            else:
                ctr["not_comparable"] += 1
                if ident in after_towers:
                    detail["after_projection_status"] = "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
                    detail["after_projection_reason"] = local_horizon_reason
            details["conditional_probes"].append(detail)
        except UnsupportedState as exc:
            ctr["unsupported"] += 1
            details["conditional_probes"].append({"tower_id": ident, "support": "CONDITIONAL_GUARD_BLOCK",
                                                    "reason": str(exc).split(":", 1)[0]})
    for ident, missing in tower_gaps.items():
        ctr = stats["tower_local"]
        ctr["opportunities"] += 1
        ctr["input_not_ready"] += 1
        details["conditional_probes"].append({"tower_id": ident, "support": "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN",
                                               "missing_fields": missing})
    # Force-local and pure current-leg movement.
    forces_before = _keyed_forces(before)
    forces_after = _keyed_forces(after)
    for item in available_forces:
        force, row, index = item["force"], item["row"], item["index"]
        key = str(val(row.get("id")))
        stats["force_local"]["opportunities"] += 1
        stats["force_local"]["input_ready"] += 1
        state = SimulationState(val(before.get("tick")), val(before.get("player_id")), str(val(before.get("match_id"))),
                                before.get("document_id", ""),
                                tuple(towers[k] for k in (force.source, force.destination)), (force,), 0)
        try:
            predicted_local = step(state)
            stats["force_local"]["semantically_supported"] += 1
            support = "CONDITIONAL_ENDPOINT_ONLY_STEP_SUCCESS"
        except UnsupportedState as exc:
            predicted_local = None
            stats["force_local"]["unsupported"] += 1
            support = "CONDITIONAL_GUARD_BLOCK:" + str(exc).split(":", 1)[0]
        details["conditional_probes"].append({"force_index": index, "observer_id": val(row.get("id")), "support": support})
        if predicted_local is not None:
            after_towers_local, _ = _canonical_fields(after)
            matched_ids = sorted({force.source, force.destination} & after_towers_local.keys())
            if len(matched_ids) == 2 and local_horizon_ok:
                stats["force_local"]["comparable"] += 2
                for ident in matched_ids:
                    agrees = _tower_projection(next(t for t in predicted_local.towers if t.id == ident)) == _tower_projection(after_towers_local[ident])
                    stats["force_local"]["matches" if agrees else "mismatches"] += 1
                details["conditional_probes"][-1]["endpoint_projection_accuracy"] = {
                    "comparable_endpoint_towers": 2,
                    "projection_unit": "source_and_destination_tower_owner_units_capacity_production_delay",
                    "matches": sum(_tower_projection(next(t for t in predicted_local.towers if t.id == ident)) == _tower_projection(after_towers_local[ident]) for ident in matched_ids),
                    "label": "CONDITIONAL_ISOLATED_ENDPOINT_PROJECTION"}
            else:
                stats["force_local"]["not_comparable"] += len(matched_ids) if len(matched_ids) == 2 else 1
                if len(matched_ids) == 2:
                    details["conditional_probes"][-1]["endpoint_projection_accuracy"] = {
                        "comparable_endpoint_towers": 0, "status": "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN",
                        "reason": local_horizon_reason,
                        "label": "CONDITIONAL_ISOLATED_ENDPOINT_PROJECTION"}
        stats["movement"]["opportunities"] += 1
        stats["movement"]["input_ready"] += 1
        src, dst = towers[force.source], towers[force.destination]
        speed, required, eta = motion(Units(tuple(enumerate(force.units))), src.position, dst.position,
                                      bool(force.accelerated), force.progress)
        stats["movement"]["semantically_supported"] += 1
        predicted_progress = min(255, force.progress + speed)
        observed, alignment_gap = _unique_continuation(forces_before.get(key, []), forces_after.get(key, []), before, after)
        if observed and type(val(observed.get("progress"))) is int:
            stats["movement"]["comparable"] += 1
            agrees = val(observed["progress"]) == predicted_progress
            stats["movement"]["matches" if agrees else "mismatches"] += 1
            comparison = "MATCH" if agrees else "MISMATCH"
        else:
            stats["movement"]["not_comparable"] += 1
            comparison = alignment_gap or "PROGRESS_UNKNOWN"
            stats["movement"]["ambiguous_or_unavailable_continuation"] += 1
        movement_detail = {"observer_id_for_alignment_only": val(row.get("id")), "source": force.source,
            "destination": force.destination, "speed": speed, "predicted_progress": predicted_progress,
            "required_progress": required, "current_leg_eta_ms_estimate": eta,
            "observed_progress_result": comparison,
            "alignment_reason": alignment_gap,
            "metric_limits": "progress compares only a unique same-ID continuation with unchanged known owner/source/destination/unit vector; ETA is a current-leg estimator, not arrival error"}
        details["movement"].append(movement_detail)
        # Arrival is a separate factor only when this known current leg reaches
        # the observed endpoint under the pinned movement calculation.
        if force.accelerated is None and force.progress + speed >= max(1, required * 4 // 5):
            stats["arrival"]["upstream_unknown_force_instances"] += 1
        elif predicted_progress >= required:
            stats["arrival"]["opportunities"] += 1
            stats["arrival"]["input_ready"] += 1
            if edge.get("comparison_execution") == "EXECUTED":
                stats["arrival"]["semantically_supported"] += 1
            details["arrival"].append({**movement_detail,
                "semantic_support": "EXECUTED_CONDITIONAL" if edge.get("comparison_execution") == "EXECUTED" else "NOT_REACHED_OR_REFUSED",
                "whole_world_comparison_status": edge.get("comparison_status"),
                "reason": "combat/path/fuel evaluated independently in ALL_BLOCKERS"})
            try:
                boundary = ordinary_arrival_boundary(force, src, dst, val(before.get('tick')),
                    other_inbound=tuple(other['force'] for other in available_forces if other['index'] != index),
                    inbound_context_complete=not unavailable and is_known(before.get('forces'))
                        and before.get('coverage') == 'PLAYER_VISIBLE_COMPLETE', fixed_morale=True)
                if boundary is not None:
                    stats['arrival']['current_leg_boundary_supported'] += 1
                    stats['arrival']['boundary_downstream_censored'] += bool(boundary.downstream_censors)
                    details['arrival'][-1]['current_leg_boundary'] = {
                        'status': boundary.status, 'tick': boundary.tick, 'branch': boundary.branch,
                        'censors': boundary.downstream_censors,
                        'accuracy': 'UNKNOWN_UNTIL_INDEPENDENT_EVENT_CORROBORATION',
                        'premise': 'fixed one-tick morale; local known-leg factor, not whole-world result'}
            except UnsupportedState as exc:
                stats['arrival']['current_leg_boundary_excluded'] += 1
                details['arrival'][-1]['boundary_exclusion'] = str(exc)
    for item in unavailable:
        for factor in ("force_local", "movement"):
            stats[factor]["opportunities"] += 1
            stats[factor]["input_not_ready"] += 1
        stats["arrival"]["upstream_unknown_force_instances"] += 1
    if len(details["arrival"]) == 1 and edge.get("comparison_status") == "SUCCESS" and local_horizon_ok:
        stats["arrival"]["comparable"] += 1
        stats["arrival"]["matches"] += 1
        details["arrival"][0]["whole_world_exact_match_unique_arrival"] = True
    elif details["arrival"] and edge.get("comparison_status") == "MISMATCH" and local_horizon_ok:
        stats["arrival"]["accuracy_unknown_due_to_whole_world_mismatch"] += len(details["arrival"])
    elif details["arrival"] and not local_horizon_ok:
        stats["arrival"]["not_comparable_due_to_horizon_gap"] += len(details["arrival"])
    # Production local factor: all due tower instances retained; only the strict
    # empty-force, no-appearance, complete snapshot subset can receive the
    # independent-local comparison label. Everything else stays conditional.
    next_tick = ((val(before.get("tick")) + 1) & 65535) if type(val(before.get("tick"))) is int else None
    before_force_rows, after_force_rows = _rows(before, "forces"), _rows(after, "forces")
    before_tower_ids = {t.id for t in towers.values()}
    force_lists_complete = (before.get("coverage") == after.get("coverage") == "PLAYER_VISIBLE_COMPLETE"
        and is_known(before.get("forces")) and is_known(after.get("forces"))
        and all(isinstance(f, dict) and is_known(f.get("source")) and is_known(f.get("destination"))
                and val(f.get("source")) in before_tower_ids and val(f.get("destination")) in before_tower_ids
                for f in before_force_rows + after_force_rows))
    no_birth_or_loss = not edge.get("new_force_diagnostic", {}).get("candidate_count") and not any(
        x.startswith("FORCE_TRACK_DISAPPEARANCE") for x in edge.get("event_pattern_labels", []))
    for ident, tower in towers.items():
        if next_tick is None: continue
        due = [(unit, period) for unit, period in tower.production if period > 0 and phase(next_tick, ident) % period == 0]
        for unit, period in due:
            ctr = stats["production"]; ctr["opportunities"] += 1
            ctr["input_ready"] += 1
            local = SimulationState(val(before.get("tick")), val(before.get("player_id")), str(val(before.get("match_id"))),
                                    before.get("document_id", ""), (tower,), (), 0)
            try:
                predicted = step(local)
                ctr["semantically_supported"] += 1
                observed_tower = after_towers.get(ident)
                no_visible_interaction = force_lists_complete and not before_force_rows and not after_force_rows and no_birth_or_loss
                # Snapshots cannot prove absence of external/scoped side effects.
                independent = False
                record = {"tower_id": ident, "unit_index": unit, "period_ticks": period,
                          "independent_complete_eligible": False,
                          "no_visible_force_interaction_observed": bool(no_visible_interaction),
                          "label": "CONDITIONAL_LOCAL_ONLY_UNKNOWN_EXTERNAL_OR_SCOPE_EFFECTS"}
                if observed_tower and local_horizon_ok:
                    ctr["comparable"] += 1
                    ok = predicted.towers[0].units == observed_tower.units
                    ctr["matches" if ok else "mismatches"] += 1
                    record["unit_vector_match"] = ok
                else:
                    ctr["not_comparable"] += 1
                    if observed_tower:
                        record["after_projection_status"] = "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN"
                        record["after_projection_reason"] = local_horizon_reason
                details["production"].append(record)
            except UnsupportedState as exc:
                ctr["unsupported"] += 1
                details["production"].append({"tower_id": ident, "unit_index": unit,
                    "support": "CONDITIONAL_GUARD_BLOCK", "reason": str(exc).split(":", 1)[0],
                    "independent_complete_eligible": False})
    # Ownership has a whole-world comparable population; owner-change rows are
    # candidates and never labeled captures or combat wins.
    own = stats["ownership"]
    own_rows_before = {r.get("id"): r for r in _rows(before, "towers") if isinstance(r, dict) and type(r.get("id")) is int}
    own_rows_after = {r.get("id"): r for r in _rows(after, "towers") if isinstance(r, dict) and type(r.get("id")) is int}
    for ident, row in own_rows_before.items():
        own["opportunities"] += 1
        if is_known(row.get("owner")) and ident in own_rows_after and is_known(own_rows_after[ident].get("owner")):
            own["input_ready"] += 1
        else:
            own["input_not_ready"] += 1
    if edge.get("comparison_status") in ("SUCCESS", "MISMATCH") and local_horizon_ok:
        decision = edge.get("observed_event_patterns", {}).get("decision_metrics", {}).get("ownership")
        if decision:
            own["comparable"] += decision.get("eligible_tower_pairs", 0)
            own["semantically_supported"] += decision.get("eligible_tower_pairs", 0)
            own["matches"] += decision.get("correct", 0)
            own["mismatches"] += decision.get("mismatch", 0)
            own["whole_world_comparable_edges"] += 1
    else:
        own["whole_world_input_unavailable_edges"] += 1
    return details, stats


def _bounds(edge_records: list[dict[str, Any]]) -> dict[str, Any]:
    active_known = [e for e in edge_records if e.get("active") == "ACTIVE_KNOWN"]
    active = [e for e in active_known if e.get("comparison_status") not in ("SUCCESS", "MISMATCH")]
    mismatches = [e for e in active_known if e.get("comparison_status") == "MISMATCH"]
    mismatch_exclusive = 0
    for edge in mismatches:
        gates = edge["all_blockers"]
        blocked = {g for g, v in gates.items() if v["status"] == "BLOCKED"}
        unknown = {g for g, v in gates.items() if v["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN" or v.get("unresolved_evidence")}
        if blocked == {"comparison"} and not unknown:
            mismatch_exclusive += 1
    exclusive = {g: 0 for g in GATES}
    for edge in active:
        gates = edge["all_blockers"]
        blocked = {g for g, v in gates.items() if v["status"] == "BLOCKED"}
        unknown = {g for g, v in gates.items() if v["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN" or v.get("unresolved_evidence")}
        for gate in blocked:
            if not unknown and blocked == {gate}:
                exclusive[gate] += 1
    requested = ["endpoint", "upgrade_emp", "supply_line", "combat", "special", "movement",
                 "arrival", "unknown_path", "relation", "fuel", "other", "after_input_endpoint", "comparison"]
    combinations = [[gate] for gate in GATES] + [["endpoint", gate]
        for gate in ("upgrade_emp", "supply_line", "combat", "special", "movement", "arrival",
                     "unknown_path", "relation", "fuel", "other", "after_input_endpoint", "comparison")]
    table = []
    def eligible_sets(fixed: list[str]) -> tuple[set[int], set[int]]:
        lower_set: set[int] = set()
        upper_set: set[int] = set()
        for index, edge in enumerate(active):
            gates = edge["all_blockers"]
            blocked = {g for g, v in gates.items() if v["status"] == "BLOCKED"}
            unknown = {g for g, v in gates.items() if v["status"] == "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN" or v.get("unresolved_evidence")}
            if not blocked.intersection(fixed) or blocked-set(fixed):
                continue
            upper_set.add(index)
            if not unknown-set(fixed):
                lower_set.add(index)
        return lower_set, upper_set
    for fixed in combinations:
        lower_set, upper_set = eligible_sets(fixed)
        lower, upper = len(lower_set), len(upper_set)
        table.append({"resolved_gates": fixed, "certified_lower_edges": lower,
                      "optimistic_upper_edges": upper,
                      "upper_minus_lower_due_to_unknown": upper-lower,
                      "bound_kind": "GUARD_SUPPORT_BOUND_NOT_ACTUAL_COMPARABILITY",
                      "interpretation": "unknown residual inputs widen the guard-support upper; these bounds do not predict a code fix or whole-world match"})
    greedy = []
    fixed: list[str] = []
    previous_low = previous_high = 0
    for gate in requested:
        fixed.append(gate)
        lower_set, upper_set = eligible_sets(fixed)
        lo, hi = len(lower_set), len(upper_set)
        marginal_low = max(0, lo-previous_high)
        marginal_high = max(0, hi-previous_low)
        greedy.append({"newly_resolved_gate": gate, "cumulative_lower": lo, "cumulative_upper": hi,
                       "marginal_lower": marginal_low, "marginal_upper": marginal_high,
                       "marginal_interval_method": "max(0,new_lower-previous_upper) .. max(0,new_upper-previous_lower)"})
        previous_low, previous_high = lo, hi
    return {"active_known_edge_denominator": len(active_known),
            "new_unlock_analysis_population_excluding_success_and_mismatch": len(active),
            "excluded_already_compared_success_edges": sum(e.get("comparison_status") == "SUCCESS" for e in active_known),
            "excluded_already_compared_mismatch_edges": len(mismatches),
            "observed_comparison_mismatch_edges": len(mismatches),
            "comparison_mismatch_exclusive_residual_edges_descriptive_only": mismatch_exclusive,
            "exclusive_blocker_counts_certified": exclusive,
            "marginal_scenario_bounds": table, "greedy_order_all_gates_hypothetical": greedy,
            "solver_note": "A guard is exclusive only when all other gates, including the comparison/exogenous residual gate, are evaluable and clear. Whole-world exact mismatches are confirmed comparison blockers with UNKNOWN cause; unexecuted/rejected comparisons are NOT_EVALUABLE. Reported unlock bounds concern guard support only; actual newly comparable lower bound is 0 and causal actual upper is UNKNOWN.",
            "actual_newly_comparable_edges_lower": 0, "actual_newly_comparable_edges_upper": None}


def _summarize_factor(stats: collections.Counter) -> dict[str, Any]:
    out = dict(stats)
    for key, numerator in (("input_readiness", stats["input_ready"]),
                           ("semantic_coverage", stats["semantically_supported"]),
                           ("accuracy", stats["matches"])):
        denom = stats["opportunities"] if key == "input_readiness" else (stats["input_ready"] if key == "semantic_coverage" else stats["comparable"])
        out[key] = {"numerator": numerator, "denominator": denom,
                    "rate": numerator / denom if denom else None}
    out["accuracy"] = {"numerator": stats["matches"], "denominator": stats["comparable"],
                       "rate": stats["matches"] / stats["comparable"] if stats["comparable"] else None}
    return out


def run(report_path: Path = DEFAULT_REPORT, audit_path: Path = DEFAULT_AUDIT) -> dict[str, Any]:
    fixture_hash = sha256(FIXTURE)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    edge_fixture = ROOT / fixture["edge_audit"]["path"]
    if sha256(edge_fixture) != fixture["edge_audit"]["sha256"]:
        raise RuntimeError("accepted complete edge fixture hash mismatch")
    expected = (fixture["totals"]["counts"]["all_distinct_observed_tick_edges"],
                fixture["totals"]["active_counts"]["ACTIVE_KNOWN"],
                fixture["totals"]["active_counts"]["ACTIVE_UNKNOWN"])
    if expected != (13059, 6458, 61):
        raise RuntimeError(f"pinned denominator changed: {expected}")
    input_hashes = {}
    for rel, row in fixture["inputs"]["raw_files"].items():
        path = ROOT / rel.replace("\\", "/")
        actual = sha256(path)
        if actual != row["expected_sha256"] or actual != row["actual_sha256"]:
            raise RuntimeError(f"raw pin mismatch: {rel}")
        input_hashes[rel.replace("\\", "/")] = actual
    source_paths = [FIXTURE, ROOT / "src/kiomet_ai/v2/control.py", ROOT / "src/kiomet_ai/v2/sim/model.py",
                    ROOT / "src/kiomet_ai/v2/sim/step.py", ROOT / "src/kiomet_ai/v2/sim/arrival.py",
                    ROOT / "src/kiomet_ai/v2/observe/forces.py"]
    source_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in source_paths}
    tool_hash = sha256(Path(__file__).resolve())
    edges_by_cohort: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    decompressed = hashlib.sha256()
    with gzip.open(edge_fixture, "rb") as zipped:
        for raw_line in zipped:
            decompressed.update(raw_line)
            row = json.loads(raw_line)
            edges_by_cohort[row["cohort"]].append(row)
    decompressed_sha = decompressed.hexdigest()
    if decompressed_sha != fixture["edge_audit"]["decompressed_sha256"]:
        raise RuntimeError("accepted complete edge fixture decompressed hash mismatch")
    if sum(map(len, edges_by_cohort.values())) != fixture["edge_audit"]["rows"]:
        raise RuntimeError("accepted complete edge fixture row count mismatch")
    report: dict[str, Any] = {"status": "CANDIDATE", "analysis_version": VERSION,
        "question": "How much visible entity/factor support exists, and how do overlapping blocker unknowns bound potential unlock?",
        "fixture": {"path": str(FIXTURE.relative_to(ROOT)), "sha256": fixture_hash,
                    "complete_edge_audit_path": str(edge_fixture.relative_to(ROOT)),
                    "complete_edge_audit_sha256": fixture["edge_audit"]["sha256"],
                    "complete_edge_audit_decompressed_sha256": decompressed_sha,
                    "all_edges": expected[0], "active_known": expected[1], "active_unknown": expected[2],
                    "raw_sha256": input_hashes},
        "sources": source_hashes, "tool_sha256": tool_hash,
        "git": git_state(),
        "method": {"order": "Development cohorts first, freeze tool hash/rules, then holdout with identical logic.",
            "locality": "Tower/force local probes are conditional isolated operations, never whole-world success.",
            "production": "Production arithmetic is always reported as a local conditional factor. Independent-complete eligibility additionally requires complete visible force collections, no visible forces in either endpoint, and no observed birth/disappearance; this cannot exclude unobserved external/scope effects and earns no whole-world credit.",
            "all_blockers": "Each gate is BLOCKED, CLEAR, or NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN. No endpoint is imputed; exact source guards remain in place.",
            "marginal": "New-unlock bounds exclude already-comparable SUCCESS and already-compared MISMATCH edges. Certified lower requires all relevant gates outside intervention set evaluable and clear; optimistic upper assumes unresolved upstream gates clear. Neither bound is an implementation promise.",
            "cause_limit": "Visible force appearance, unit change, owner change and production due are observations/candidates; no inferred actor, capture, internal event, or production causality.",
            "endpoint_stages": "Primary NOT_READY/UNKNOWN_PATH refusals are split by explicit stage; after-input gaps never become current endpoint blockers.",
            "ownership": "Owner-field inputs are counted independently of simulator acceptance. Isolated owner projections are conditional local comparisons; whole-world owner-change agreement is a separate table, and owner change is not labeled capture.",
            "production_due": "A due production period is a potential local arithmetic opportunity, not proof of an observed production event or independent production cause."},
        "cohorts": [], "development_freeze_checkpoint": None,
        "factor_totals": {name: collections.Counter() for name in FACTOR_NAMES}}
    edge_records_for_bounds: list[dict[str, Any]] = []
    per_gate = collections.Counter()
    per_readiness_reason = collections.Counter()
    per_after_readiness_reason = collections.Counter()
    per_readiness_entities = collections.Counter()
    endpoint_edge_counts: dict[str, int] = {}
    endpoint_stage_counts = collections.Counter()
    success_confirmed_blockers = collections.Counter()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("wb") as audit_file:
      with gzip.GzipFile(fileobj=audit_file, mode="wb", filename="", mtime=0, compresslevel=6) as compressed:
       with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as audit:
        for cohort in COHORT_ORDER:
            c = next(x for x in fixture["cohorts"] if x["cohort"] == cohort)
            cohort_edges = edges_by_cohort[cohort]
            rel = f"runtime/research/v2/snapshots-{cohort}.jsonl"
            raw_path = ROOT / rel
            split = c["split"]
            # Select only raw lines referenced by this frozen edge fixture.
            needed = set()
            for edge in cohort_edges:
                needed.update((edge["before_line"], edge["after_line"]))
            selected: dict[int, dict[str, Any]] = {}
            with raw_path.open("r", encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    if number in needed:
                        selected[number] = json.loads(line)
            csummary = {"cohort": cohort, "split": split, "edges": 0, "active_known": 0,
                        "active_unknown": 0, "endpoint_blocked_active_edges": 0,
                        "primary_unknown_path_not_ready_active_edges": 0,
                        "primary_before_endpoint_not_ready_active_edges": 0,
                        "primary_after_only_endpoint_not_ready_active_edges": 0,
                        "after_input_endpoint_unknown_active_edges": 0,
                        "factor_totals": {name: collections.Counter() for name in FACTOR_NAMES},
                        "gate_states": collections.Counter(), "endpoint_entities": 0}
            for edge in cohort_edges:
                before, after = selected.get(edge["before_line"]), selected.get(edge["after_line"])
                if before is None or after is None:
                    raise RuntimeError(f"fixture line absent {cohort}:{edge['edge_index']}")
                towers, tower_gaps = _canonical_fields(before)
                available, unavailable = _force_endpoints(before, towers)
                gates = _edge_gates(edge, before, after, towers, available, unavailable, tower_gaps)
                if any(item["status"] not in ("BLOCKED", "CLEAR", "NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN")
                       for item in gates.values()):
                    raise RuntimeError("ALL_BLOCKERS emitted a noncanonical status")
                success_blocked = [gate for gate, item in gates.items()
                                   if edge.get("comparison_status") == "SUCCESS" and item["status"] == "BLOCKED"
                                   and gate != "comparison"]
                success_confirmed_blockers.update(success_blocked)
                # Any readiness endpoint incidence remains individual evidence.
                endpoint_gaps = [x for x in edge.get("control_readiness_gaps", [])
                                 if x.startswith("force:") and (x.endswith(":source") or x.endswith(":destination"))]
                endpoint_blocked = bool(endpoint_gaps) or any(x.get("missing_endpoint_tower_ids") or
                    any(f in (x.get("missing_fields") or []) for f in ("source", "destination"))
                    for x in unavailable)
                after_endpoint_gaps = [x for x in edge.get("after_input_readiness_gaps", [])
                    if x.startswith("force:") and (x.endswith(":source") or x.endswith(":destination"))]
                primary_endpoint_not_ready = (edge.get("primary_blocker") == "NOT_READY" and
                    edge.get("primary_category") == "UNKNOWN_PATH")
                if edge["active"] == "ACTIVE_KNOWN":
                    csummary["active_known"] += 1
                elif edge["active"] == "ACTIVE_UNKNOWN":
                    csummary["active_unknown"] += 1
                if edge["active"] == "ACTIVE_KNOWN" and endpoint_blocked:
                    csummary["endpoint_blocked_active_edges"] += 1
                    endpoint_edge_counts[cohort] = endpoint_edge_counts.get(cohort, 0) + 1
                    for item in endpoint_gaps:
                        per_readiness_entities[item.rsplit(":", 1)[-1]] += 1
                if edge["active"] == "ACTIVE_KNOWN" and primary_endpoint_not_ready:
                    csummary["primary_unknown_path_not_ready_active_edges"] += 1
                    endpoint_stage_counts["primary_unknown_path_not_ready_active_edges"] += 1
                    if endpoint_gaps or any(x.get("missing_endpoint_tower_ids") or
                        any(f in (x.get("missing_fields") or []) for f in ("source", "destination")) for x in unavailable):
                        csummary["primary_before_endpoint_not_ready_active_edges"] += 1
                        endpoint_stage_counts["primary_before_endpoint_not_ready_active_edges"] += 1
                    elif after_endpoint_gaps:
                        csummary["primary_after_only_endpoint_not_ready_active_edges"] += 1
                        endpoint_stage_counts["primary_after_only_endpoint_not_ready_active_edges"] += 1
                if edge["active"] == "ACTIVE_KNOWN" and after_endpoint_gaps:
                    csummary["after_input_endpoint_unknown_active_edges"] += 1
                    endpoint_stage_counts["after_input_endpoint_unknown_active_edges"] += 1
                details, factor_counts = _factor_edge(edge, before, after, towers, tower_gaps, available, unavailable)
                for name, ctr in factor_counts.items():
                    csummary["factor_totals"][name].update(ctr)
                    report["factor_totals"][name].update(ctr)
                for gate, data in gates.items():
                    per_gate[gate + ":" + data["status"]] += 1
                    csummary["gate_states"][gate + ":" + data["status"]] += 1
                for gap in edge.get("control_readiness_gaps", []):
                    per_readiness_reason[gap] += 1
                for gap in edge.get("after_input_readiness_gaps", []):
                    per_after_readiness_reason[gap] += 1
                record = {"cohort": cohort, "split": split, "edge_index": edge["edge_index"],
                    "lines": [edge["before_line"], edge["after_line"]],
                    "sequence": [edge["before_sequence"], edge["after_sequence"]],
                    "ticks": [edge["before_tick"], edge["after_tick"]],
                    "active": edge["active"], "whole_world_status": edge["comparison_status"],
                    "first_blocker": edge.get("primary_blocker"), "first_category": edge.get("primary_category"),
                    "endpoint_blocked_active_edge": edge["active"] == "ACTIVE_KNOWN" and endpoint_blocked,
                    "primary_unknown_path_not_ready": primary_endpoint_not_ready,
                    "primary_before_endpoint_not_ready": primary_endpoint_not_ready and endpoint_blocked,
                    "primary_after_only_endpoint_not_ready": primary_endpoint_not_ready and not endpoint_blocked and bool(after_endpoint_gaps),
                    "blocked_endpoint_force_gaps": endpoint_gaps,
                    "after_input_readiness_gaps": [
                        {"stage": "after_input", "force_index": int(x.split(":")[1]) if x.startswith("force:") else None,
                         "entity_kind": x.split(":")[0] if ":" in x else "unknown",
                         "field": x.rsplit(":", 1)[-1], "raw_readiness_gap": x}
                        for x in edge.get("after_input_readiness_gaps", [])],
                    "after_input_endpoint_unknowns": [
                        {"stage": "after_input", "force_index": int(x.split(":")[1]), "field": x.rsplit(":", 1)[-1],
                         "observer_id": (val(_rows(after, "forces")[int(x.split(":")[1])].get("id"))
                             if int(x.split(":")[1]) < len(_rows(after, "forces")) and isinstance(_rows(after, "forces")[int(x.split(":")[1])], dict) else None),
                         "raw_readiness_gap": x}
                        for x in edge.get("after_input_readiness_gaps", [])
                        if x.startswith("force:") and (x.endswith(":source") or x.endswith(":destination"))],
                    "entity_endpoint_unavailable": unavailable,
                    "all_blockers": gates,
                    "success_confirmed_blocked_gates": success_blocked,
                    "factor_observations": details}
                audit.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                edge_records_for_bounds.append({"active": edge["active"], "comparison_status": edge.get("comparison_status"),
                                                "all_blockers": gates})
                csummary["edges"] += 1
            csummary["factor_totals"] = {k: _summarize_factor(v) for k, v in csummary["factor_totals"].items()}
            csummary["gate_states"] = dict(csummary["gate_states"])
            report["cohorts"].append(csummary)
            if split == "development" and len(report["cohorts"]) == 3:
                report["development_freeze_checkpoint"] = {
                    "completed_cohorts": [x["cohort"] for x in report["cohorts"]],
                    "rule_version": VERSION, "tool_sha256_frozen_before_holdout": tool_hash,
                    "fixture_sha256": fixture_hash,
                    "statement": "No rule or threshold was changed after these development summaries; holdout is processed next with the identical frozen tool hash."}
    report["factor_totals"] = {k: _summarize_factor(v) for k, v in report["factor_totals"].items()}
    report["all_blocker_counts"] = dict(per_gate)
    report["raw_readiness_gap_occurrences"] = dict(per_readiness_reason)
    report["after_input_readiness_gap_occurrences"] = dict(per_after_readiness_reason)
    report["endpoint_field_gap_occurrences"] = dict(per_readiness_entities)
    report["endpoint_blocked_active_edges_by_cohort"] = endpoint_edge_counts
    report["endpoint_stage_counts"] = dict(endpoint_stage_counts)
    report["success_confirmed_blocked_gate_counts"] = dict(success_confirmed_blockers)
    report["marginal_bounds"] = _bounds(edge_records_for_bounds)
    decompressed_audit_hash = hashlib.sha256()
    with gzip.open(audit_path, "rb") as audit_stream:
        for block in iter(lambda: audit_stream.read(1024 * 1024), b""):
            decompressed_audit_hash.update(block)
    report["edge_audit"] = {"path": str(audit_path.relative_to(ROOT)), "sha256": sha256(audit_path),
                            "decompressed_sha256": decompressed_audit_hash.hexdigest(),
                            "encoding": "deterministic gzip JSONL; one row per frozen edge", "edge_rows": len(edge_records_for_bounds)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "edges": result["edge_audit"]["edge_rows"],
                      "active": result["marginal_bounds"]["active_known_edge_denominator"],
                      "edge_audit_sha256": result["edge_audit"]["sha256"]}, ensure_ascii=False), flush=True)
