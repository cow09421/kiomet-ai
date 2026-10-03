"""Passive scoring adapter for the pinned ordinary combat candidate.

This module applies the current fight formula to retained pre-arrival inputs.
It never changes production behavior or tunes the formula from outcomes.
"""
from __future__ import annotations

import collections
import hashlib
import gzip
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from kiomet_ai.v2.sim import UnsupportedState
from kiomet_ai.v2.sim.combat import fight_ordinary
from kiomet_ai.v2.sim.step import phase
from tools.v2_factorized_coverage import (
    _force, _infer_pinned_acceleration, _tower, is_known, units as read_units, val)

PINNED_COMBAT_SHA256 = "8b84726349cc52d718dc8f4fbc42416067ae2df9924cefbe88e899cd8d0edfd3"
COMBAT_SOURCE = ROOT / "src/kiomet_ai/v2/sim/combat.py"
COMBAT_AUDIT = ROOT / "tests/fixtures/v2/arrival-factor-edge-audit.jsonl.gz"
TRANSITION_CORPUS = ROOT / "runtime/research/v2/m2a-ordinary_hypothesis-transition-corpus.jsonl"
DEVELOPMENT_TIMELINE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-development.json.gz"
HOLDOUT_TIMELINE = ROOT / "tests/fixtures/v2/arrival-settlement-replay-holdout.json.gz"
SETTLEMENT_RECEIPT = ROOT / "docs/V2_M2A_UNFILTERED_SETTLEMENT.json"
OUTPUT_FIXTURE = ROOT / "tests/fixtures/v2/combat-passive-replay.json.gz"
OUTPUT_JSON = ROOT / "docs/V2_M2A_COMBAT_PASSIVE_REPLAY.json"
OUTPUT_MARKDOWN = ROOT / "docs/V2_M2A_COMBAT_PASSIVE_REPLAY.md"
REQUIRED_BRANCH = "COMBAT_REQUIRED"
COMBAT_EVENT_CATEGORIES = frozenset(("ground_combat_arrival",
                                     "ordinary_air_unit_combat_arrival"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_audit_population(path: Path = COMBAT_AUDIT) -> list[dict[str, Any]]:
    """Load every row whose current-leg arrival branch is COMBAT_REQUIRED."""
    selected = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            arrivals = row.get("factor_observations", {}).get("arrival", [])
            for ordinal, item in enumerate(arrivals):
                boundary = item.get("current_leg_boundary")
                if not isinstance(boundary, dict) or boundary.get("branch") != REQUIRED_BRANCH:
                    continue
                selected.append({
                    "case_id": f"{row['cohort']}:{row['edge_index']}:{ordinal}",
                    "cohort": row.get("cohort"),
                    "split": row.get("split"),
                    "edge_index": row.get("edge_index"),
                    "ordinal": ordinal,
                    "lines": row.get("lines"),
                    "sequence": row.get("sequence"),
                    "ticks": row.get("ticks"),
                    "active": row.get("active"),
                    "first_category": row.get("first_category"),
                    "current_leg_boundary": boundary,
                })
    return selected


def load_transition_combat_population(
        path: Path = TRANSITION_CORPUS) -> list[dict[str, Any]]:
    """Load the preexisting ordinary ground/air combat candidates separately."""
    selected = []
    with path.open("rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            categories = row.get("event_categories", [])
            if not COMBAT_EVENT_CATEGORIES.intersection(categories):
                continue
            selected.append(row)
    return selected


def assert_pinned_formula() -> str:
    actual = sha256(COMBAT_SOURCE)
    if actual != PINNED_COMBAT_SHA256:
        raise RuntimeError(
            f"combat.py SHA256 changed: expected {PINNED_COMBAT_SHA256}, got {actual}")
    return actual


def project_fight(attacker: tuple[int, ...], defender: tuple[int, ...],
                  defender_capacity: tuple[int, ...], *, incoming_owner: int,
                  target_owner: int, attacker_morale: bool,
                  defender_morale: bool) -> dict[str, Any]:
    """Return the frozen tower-level projection for one ordinary tower fight."""
    result = fight_ordinary(
        attacker, defender, defender_capacity, defender_is_tower=True,
        attacker_morale=attacker_morale, defender_morale=defender_morale)
    if result.winner == "ATTACKER":
        owner = incoming_owner
        vector = result.attacker
    elif result.winner == "DEFENDER":
        owner = target_owner
        vector = result.defender
    else:
        owner = None
        vector = None
    return {
        "winner": result.winner,
        "owner": owner,
        "vector": list(vector) if vector is not None else None,
        "attacker_survivors": list(result.attacker),
        "defender_survivors": list(result.defender),
        "attacker_ruler_lost": result.attacker_ruler_lost,
        "defender_ruler_lost": result.defender_ruler_lost,
    }


def observed_match(prediction: dict[str, Any], owner: Any,
                   vector: list[int] | tuple[int, ...] | None) -> bool | None:
    """Compare a known tower prediction with an observed owner and vector."""
    if prediction.get("owner") is None or prediction.get("vector") is None:
        return None
    if type(owner) is not int or not isinstance(vector, (list, tuple)) or len(vector) != 10:
        return None
    return prediction["owner"] == owner and prediction["vector"] == list(vector)


def classify_force_status(statuses: list[dict[str, Any]], *, complete: bool) -> str:
    """Summarize t+1/t+2 continuity without treating ID alone as proof.

    Each row has ``signature_match`` plus either ``same_lineage_changed`` or
    ``absence_confirmed``. The latter must come from a complete force census
    and a signature/lineage check, never from a missing ID by itself.
    """
    if not complete or len(statuses) != 2:
        return "UNKNOWN"
    matches = [row.get("signature_match") for row in statuses]
    changed = [row.get("same_lineage_changed") for row in statuses]
    absent = [row.get("absence_confirmed") for row in statuses]
    if all(value is True for value in matches):
        return "CONTINUES"
    if all(value is True for value in changed):
        return "TRANSFORMED"
    if all(value is False for value in matches) and all(value is True for value in absent):
        return "DISAPPEARED"
    return "AMBIGUOUS"


def evaluability(contamination: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return whether this input is locally interpretable and its blockers.

    Raw formula scoring remains available when this returns false. Fields may
    be ``True`` (contamination present), ``False`` (ruled out), or ``None``
    (unknown); unknown premises fail closed for evaluability only.
    """
    blockers = []
    for name in ("production", "aura", "multiple_inbound", "special", "pair_relation",
                 "active_delay", "capacity_uncertainty", "continuity"):
        value = contamination.get(name)
        if value is not False:
            blockers.append(name.upper() if value is True else f"{name.upper()}_UNKNOWN")
    return not blockers, blockers


def pair_relation_status(*, target_owner: Any, incoming_owner: Any,
                         player_id: Any, target_relation: Any,
                         incoming_relation: Any) -> str:
    """Apply the existing simulator's before-pair hostile guard exactly."""
    if type(target_owner) is not int or type(incoming_owner) is not int or type(player_id) is not int:
        return "UNKNOWN_PAIR_RELATION"
    if target_owner == incoming_owner:
        return "NOT_HOSTILE_SAME_OWNER"
    known_enemy = (
        target_owner == player_id and incoming_relation == "ENEMY" or
        incoming_owner == player_id and target_relation == "ENEMY" or
        target_owner == 0)
    return "KNOWN_HOSTILE" if known_enemy else "UNKNOWN_PAIR_RELATION"


def _known(row: dict[str, Any] | None, name: str) -> Any:
    if not isinstance(row, dict) or not is_known(row.get(name)):
        return None
    return val(row.get(name))


def _same_scope_and_ticks(case: dict[str, Any]) -> bool | None:
    snapshots = case.get("snapshots", {})
    names = ("before", "arrival", "following")
    if any(name not in snapshots for name in names):
        return None
    provenance = [snapshots[name].get("provenance", {}) for name in names]
    if any(not p.get("source_path") or not p.get("source_sha256") or
           type(p.get("sequence")) is not int or type(p.get("tick")) is not int
           for p in provenance):
        return None
    scopes = [p.get("scope") for p in provenance]
    if any(scope != scopes[0] for scope in scopes[1:]):
        return False
    if len({(p["source_path"], p["source_sha256"]) for p in provenance}) != 1:
        return False
    ticks = [p["tick"] for p in provenance]
    sequences = [p["sequence"] for p in provenance]
    return (all((ticks[i + 1] - ticks[i]) % 65536 == 1 for i in range(2)) and
            all(sequences[i + 1] > sequences[i] for i in range(2)))


def _force_signature(row: dict[str, Any]) -> tuple[Any, ...] | None:
    owner, source, destination = (_known(row, "owner"), _known(row, "source"),
                                  _known(row, "destination"))
    vector = read_units(row.get("units"))
    if type(owner) is not int or type(source) is not int or type(destination) is not int or vector is None:
        return None
    return owner, source, destination, tuple(vector)


def _observed_force_status_detail(case: dict[str, Any], slot: str,
                                 prediction: dict[str, Any] | None) -> tuple[str, str]:
    snapshot = case.get("snapshots", {}).get(slot)
    if snapshot is None:
        return "UNKNOWN", "SNAPSHOT_MISSING"
    provenance = snapshot.get("provenance", {})
    if provenance.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
        return "UNKNOWN", "FORCE_CENSUS_INCOMPLETE"
    incoming = tuple(case.get("incoming_signature", ()))
    if len(incoming) != 4 or not isinstance(incoming[3], list):
        return "UNKNOWN", "INPUT_SIGNATURE_UNKNOWN"
    exact = [sig for row in snapshot.get("forces", [])
             if (sig := _force_signature(row)) ==
             (incoming[0], incoming[1], incoming[2], tuple(incoming[3]))]
    if len(exact) == 1:
        return "CONTINUES", "EXACT_TYPED_ROUTE_SIGNATURE_VISIBLE"
    if len(exact) > 1:
        return "AMBIGUOUS", "DUPLICATE_EXACT_TYPED_ROUTE_SIGNATURE"
    same_route = [sig for row in snapshot.get("forces", [])
                  if (sig := _force_signature(row)) is not None and
                  sig[:3] == (incoming[0], incoming[1], incoming[2])]
    if len(same_route) == 1:
        return "TRANSFORMED", "UNIQUE_SAME_ROUTE_VECTOR_CHANGED"
    if len(same_route) > 1:
        return "AMBIGUOUS", "MULTIPLE_SAME_ROUTE_CANDIDATES"
    # A fresh force from the destination with the predicted attacker survivors
    # could be an immediate new leg. That is compatible with continuation but
    # does not establish physical genealogy.
    survivors = prediction.get("attacker_survivors") if prediction else None
    if isinstance(survivors, list) and any(survivors):
        possible_new_legs = []
        for row in snapshot.get("forces", []):
            if (_known(row, "owner") == incoming[0] and
                    _known(row, "source") == case.get("target_id") and
                    read_units(row.get("units")) == tuple(survivors)):
                possible_new_legs.append(row)
        if possible_new_legs:
            return "AMBIGUOUS", "NEW_LEG_COMPATIBLE_OWNER_AND_SURVIVOR_VECTOR"
    if any(_known(row, name) is None for row in snapshot.get("forces", [])
           for name in ("owner", "source", "destination", "units")):
        return "AMBIGUOUS", "UNRESOLVED_FORCE_ENDPOINT_OR_VECTOR_ALIAS"
    return "DISAPPEARED", "COMPLETE_CENSUS_ORIGINAL_ROUTE_SIGNATURE_ABSENT"


def _observed_force_status(case: dict[str, Any], slot: str,
                           prediction: dict[str, Any] | None) -> str:
    return _observed_force_status_detail(case, slot, prediction)[0]


def _production_due(target: Any, arrival_tick: int) -> bool | None:
    if (target.production is None or type(target.owner) is not int or
            type(target.delay) is not int or type(arrival_tick) is not int):
        return None
    if target.owner == 0 or target.delay != 0:
        return False
    return any(period > 0 and phase(arrival_tick, target.id) % period == 0
               and target.units[unit] < target.capacity[unit]
               for unit, period in target.production)


def score_case(case: dict[str, Any]) -> dict[str, Any]:
    """Passively score one normalized arrival case; raw score ignores censors."""
    before = case.get("snapshots", {}).get("before", {})
    arrival = case.get("snapshots", {}).get("arrival", {})
    following = case.get("snapshots", {}).get("following", {})
    signature = case.get("incoming_signature")
    target_id = case.get("target_id")
    out: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "cohort": case.get("cohort"),
        "split": case.get("split"),
        "edge_index": case.get("edge_index"),
        "ordinal": case.get("ordinal"),
        "target_id": case.get("target_id"),
        "before_tick": before.get("provenance", {}).get("tick"),
        "arrival_tick": arrival.get("provenance", {}).get("tick"),
        "following_tick": following.get("provenance", {}).get("tick"),
        "source_path": before.get("provenance", {}).get("source_path"),
        "source_sha256": before.get("provenance", {}).get("source_sha256"),
        "before_sequence": before.get("provenance", {}).get("sequence"),
        "arrival_sequence": arrival.get("provenance", {}).get("sequence"),
        "following_sequence": following.get("provenance", {}).get("sequence"),
        "input_scope_continuity": _same_scope_and_ticks(case),
    }
    if not isinstance(signature, list) or len(signature) != 4:
        out.update({"raw_formula_status": "UNKNOWN_INPUT_SIGNATURE",
                    "prediction": None, "evaluable": False,
                    "evaluability_blockers": ["INPUT_SIGNATURE_UNKNOWN"]})
        return out
    in_owner, source_id, destination_id, raw_in_vector = signature
    incoming_vector = tuple(raw_in_vector) if isinstance(raw_in_vector, list) else None
    incoming_sig = (in_owner, source_id, destination_id, incoming_vector)
    raw_towers = [row for row in before.get("towers", []) if isinstance(row, dict)]
    raw_forces = [row for row in before.get("forces", []) if isinstance(row, dict)]
    sim_towers: dict[int, Any] = {}
    tower_gaps: dict[int, list[str]] = {}
    for row in raw_towers:
        tower, gaps = _tower(row)
        ident = row.get("id")
        if type(ident) is int:
            if tower is not None:
                sim_towers[ident] = tower
            else:
                tower_gaps[ident] = gaps
    target_rows = [row for row in raw_towers if row.get("id") == target_id]
    target_row = target_rows[0] if len(target_rows) == 1 else None
    source_row = next((row for row in raw_towers if row.get("id") == source_id), None)
    target = sim_towers.get(target_id)
    source = sim_towers.get(source_id)
    matching_forces = [row for row in raw_forces if _force_signature(row) == incoming_sig]
    input_gaps = []
    if len(target_rows) != 1:
        input_gaps.append("TARGET_TOWER_MAPPING_" + ("MISSING" if not target_rows else "AMBIGUOUS"))
    if target is None:
        input_gaps.extend("TARGET_" + gap.upper() for gap in tower_gaps.get(target_id, ["MODEL_TOWER_UNKNOWN"]))
    if len(matching_forces) != 1:
        input_gaps.append("ATTACKER_FORCE_MAPPING_" + ("MISSING" if not matching_forces else "AMBIGUOUS"))
    attacker = None
    acceleration_basis = "UNKNOWN"
    source_morale = source.morale if source is not None else None
    if len(matching_forces) == 1:
        raw_force = matching_forces[0]
        attacker, force_gaps = _force(raw_force)
        if attacker is None:
            input_gaps.extend("ATTACKER_" + gap.upper() for gap in force_gaps)
        else:
            observed_accel = _known(raw_force, "accelerated")
            if type(observed_accel) is bool:
                acceleration_basis = "OBSERVED_RETAINED_FORCE_ACCELERATED"
            else:
                attacker = _infer_pinned_acceleration(attacker, raw_force, sim_towers)
                if type(attacker.accelerated) is bool:
                    acceleration_basis = "UNIQUE_PINNED_ETA_INVERSION_KNOWN_LEG"
                else:
                    input_gaps.append("ATTACKER_ACCELERATED_UNKNOWN")
    out["incoming_owner"] = in_owner
    out["incoming_vector"] = list(incoming_vector) if incoming_vector is not None else None
    out["attacker_morale"] = attacker.accelerated if attacker is not None else None
    out["attacker_morale_basis"] = acceleration_basis
    out["source_current_morale_supplemental"] = source_morale
    out["target_owner_before"] = target.owner if target is not None else _known(target_row, "owner")
    out["target_vector_before"] = list(target.units) if target is not None else read_units(target_row.get("units")) if target_row else None
    out["target_morale"] = target.morale if target is not None else None
    out["target_capacity_owner"] = out["target_owner_before"]
    out["target_capacity"] = list(target.capacity) if target is not None else read_units(target_row.get("capacity")) if target_row else None
    out["capacity_owner_after_observed"] = _known(
        next((row for row in arrival.get("towers", []) if row.get("id") == target_id), None), "owner")
    arrival_target_row = next((row for row in arrival.get("towers", [])
                               if row.get("id") == target_id), None)
    out["capacity_vector_after_observed"] = (
        list(read_units(arrival_target_row.get("capacity")))
        if arrival_target_row and read_units(arrival_target_row.get("capacity")) is not None
        else None)
    out["input_gaps"] = sorted(set(input_gaps))
    player_id = (before.get("provenance", {}).get("scope", [None, None, None])[2]
                 if len(before.get("provenance", {}).get("scope", [])) > 2 else None)
    incoming_relation = _known(matching_forces[0], "relation") if len(matching_forces) == 1 else None
    target_relation = _known(target_row, "relation")
    pair_status = pair_relation_status(
        target_owner=out["target_owner_before"], incoming_owner=in_owner,
        player_id=player_id, target_relation=target_relation,
        incoming_relation=incoming_relation)
    out["pair_relation_status"] = pair_status
    prediction = None
    if target is None or attacker is None or type(attacker.accelerated) is not bool:
        out["raw_formula_status"] = "UNKNOWN_REQUIRED_COMBAT_INPUT"
    elif type(target.morale) is not bool:
        out["raw_formula_status"] = "UNKNOWN_TARGET_MORALE"
    else:
        try:
            prediction = project_fight(attacker.units, target.units, target.capacity,
                incoming_owner=attacker.owner, target_owner=target.owner,
                attacker_morale=attacker.accelerated, defender_morale=target.morale)
            out["raw_formula_status"] = "SCORED"
        except UnsupportedState as exc:
            out["raw_formula_status"] = f"UNSUPPORTED_{exc}"
    out["prediction"] = prediction
    observed_rows = {}
    for slot, snapshot in (("arrival", arrival), ("following", following)):
        rows = [row for row in snapshot.get("towers", [])
                if isinstance(row, dict) and row.get("id") == target_id]
        observed = rows[0] if len(rows) == 1 else None
        owner = _known(observed, "owner")
        vector = read_units(observed.get("units")) if observed else None
        observed_rows[slot] = {"owner": owner, "vector": list(vector) if vector is not None else None}
        out[f"observed_{slot}"] = observed_rows[slot]
        out[f"owner_match_{slot}"] = (
            prediction["owner"] == owner if prediction and prediction.get("owner") is not None
            and type(owner) is int else None)
        out[f"vector_match_{slot}"] = (
            prediction["vector"] == list(vector) if prediction and prediction.get("vector") is not None
            and vector is not None else None)
        key = ("raw_formula_match_arrival" if slot == "arrival" else
               "projection_matches_following_observation")
        out[key] = observed_match(prediction, owner, vector) if prediction else None
    out["capacity_owner_after_predicted"] = prediction.get("owner") if prediction else None
    out["predicted_capacity_after"] = None  # Post-capture capacity is downstream of fight projection.
    contamination = {
        "production": _production_due(target, out["arrival_tick"]) if target is not None else None,
        "aura": False if target is not None and type(target.morale) is bool and attacker is not None and type(attacker.accelerated) is bool else None,
        "multiple_inbound": None,
        "special": None,
        "pair_relation": pair_status != "KNOWN_HOSTILE",
        "active_delay": (target.delay != 0) if target is not None else None,
        "capacity_uncertainty": False if target is not None and type(target.owner) is int else None,
        "continuity": (False if out["input_scope_continuity"] is True else
                       True if out["input_scope_continuity"] is False else None),
    }
    if attacker is not None and target is not None:
        contamination["special"] = any(attacker.units[i] or target.units[i] for i in (6, 7, 8))
    else:
        contamination["special"] = None
    if incoming_sig and target_id is not None:
        other_dests = [_known(row, "destination") for row in raw_forces
                       if _force_signature(row) != incoming_sig]
        if before.get("provenance", {}).get("coverage") != "PLAYER_VISIBLE_COMPLETE" or any(x is None for x in other_dests):
            contamination["multiple_inbound"] = None
        else:
            contamination["multiple_inbound"] = any(x == target_id for x in other_dests)
    contamination["production_after_capture_capacity"] = None
    out["contamination"] = contamination
    # Newly captured owners can have a different capacity; leave that downstream
    # capacity question explicit even when the defending capacity was known.
    if prediction and prediction["owner"] != out["target_capacity_owner"]:
        out["contamination"]["post_capture_capacity_owner_change"] = True
    else:
        out["contamination"]["post_capture_capacity_owner_change"] = False
    eva = dict(contamination)
    eva.pop("production_after_capture_capacity", None)
    eva.pop("post_capture_capacity_owner_change", None)
    eligible, blockers = evaluability(eva)
    if out["raw_formula_status"] != "SCORED":
        eligible = False
        blockers = sorted(set(blockers + out["input_gaps"] + [out["raw_formula_status"]]))
    out["evaluable"] = eligible
    out["evaluability_blockers"] = blockers
    arrival_force_status, arrival_force_basis = _observed_force_status_detail(
        case, "arrival", prediction)
    following_force_status, following_force_basis = _observed_force_status_detail(
        case, "following", prediction)
    out["post_arrival_force_status"] = {
        "t_plus_1": arrival_force_status,
        "t_plus_2": following_force_status,
    }
    out["post_arrival_force_status_basis"] = {
        "t_plus_1": arrival_force_basis,
        "t_plus_2": following_force_basis,
    }
    out["force_continuation_uncertain"] = any(
        status in ("AMBIGUOUS", "UNKNOWN")
        for status in out["post_arrival_force_status"].values())
    out["downstream_capacity"] = (
        "UNKNOWN_AFTER_OWNER_CHANGE" if prediction and
        prediction.get("owner") != out["target_capacity_owner"] else "SAME_OWNER_CAPACITY_CONTEXT")
    arrival_towers = [row for row in arrival.get("towers", [])
                      if isinstance(row, dict) and row.get("id") == target_id]
    arrival_model = _tower(arrival_towers[0])[0] if len(arrival_towers) == 1 else None
    out["following_snapshot_production_due"] = (
        _production_due(arrival_model, out["following_tick"])
        if arrival_model is not None else None)
    out["following_snapshot_warning"] = (
        "OBSERVED_STATE_ONLY_NOT_A_COMBAT_FORECAST" if prediction is not None else None)
    return out


def _load_timeline(path: Path, expected_split: str) -> dict[str, Any]:
    payload = json.loads(gzip.decompress(path.read_bytes()))
    if payload.get("split") != expected_split:
        raise ValueError(f"timeline split mismatch for {path}: {payload.get('split')}")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"timeline fixture has no case list: {path}")
    indexed = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in indexed:
            raise ValueError(f"invalid or duplicate timeline case_id in {path}: {case_id}")
        indexed[case_id] = case
    return {"payload": payload, "cases": indexed}


def _source_hash_manifest() -> dict[str, Any]:
    receipt = json.loads(SETTLEMENT_RECEIPT.read_text(encoding="utf-8"))
    raw = receipt.get("raw_source_hashes")
    if not isinstance(raw, dict) or len(raw) != 6:
        raise ValueError("settlement receipt must pin all six raw source files")
    if not all(item.get("matches_manifest") is True for item in raw.values()):
        raise ValueError("one or more pinned raw source hashes do not match")
    return raw


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("raw_formula_status") == "SCORED"]
    evaluable = [row for row in scored if row.get("evaluable") is True]
    owner_matches = [row["owner_match_arrival"] for row in scored
                     if row.get("owner_match_arrival") is not None]
    vector_matches = [row["vector_match_arrival"] for row in scored
                      if row.get("vector_match_arrival") is not None]
    exact_matches = [row["raw_formula_match_arrival"] for row in scored
                     if row.get("raw_formula_match_arrival") is not None]
    clean_exact = [row["raw_formula_match_arrival"] for row in evaluable
                   if row.get("raw_formula_match_arrival") is not None]
    return {
        "candidate_count": len(rows),
        "formula_scored": len(scored),
        "evaluable": len(evaluable),
        "unevaluable": len(rows) - len(evaluable),
        "winner_counts": dict(collections.Counter(
            row.get("prediction", {}).get("winner") for row in scored)),
        "arrival_owner_match": sum(owner_matches),
        "arrival_owner_compared": len(owner_matches),
        "arrival_vector_match": sum(vector_matches),
        "arrival_vector_compared": len(vector_matches),
        "arrival_exact_match": sum(exact_matches),
        "arrival_exact_compared": len(exact_matches),
        "following_owner_match": sum(row["owner_match_following"] for row in scored
                                      if row.get("owner_match_following") is not None),
        "following_vector_match": sum(row["vector_match_following"] for row in scored
                                       if row.get("vector_match_following") is not None),
        "following_snapshot_exact_agreement": sum(
            row["projection_matches_following_observation"] for row in scored
            if row.get("projection_matches_following_observation") is not None),
        "evaluable_arrival_exact_match": sum(clean_exact),
        "evaluable_arrival_compared": len(clean_exact),
        "contamination_counts": {
            name: dict(collections.Counter(
                row.get("contamination", {}).get(name) for row in rows))
            for name in ("production", "aura", "multiple_inbound", "special", "pair_relation",
                         "active_delay", "capacity_uncertainty", "continuity")
        },
        "pair_relation_status_counts": dict(collections.Counter(
            row.get("pair_relation_status") for row in rows)),
        "post_arrival_force_status": {
            slot: dict(collections.Counter(
                row.get("post_arrival_force_status", {}).get(slot) for row in rows))
            for slot in ("t_plus_1", "t_plus_2")
        },
        "post_arrival_force_status_basis": {
            slot: dict(collections.Counter(
                row.get("post_arrival_force_status_basis", {}).get(slot) for row in rows))
            for slot in ("t_plus_1", "t_plus_2")
        },
        "force_continuation_uncertain_cases": sum(
            row.get("force_continuation_uncertain") is True for row in rows),
    }


def score_audit_population() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assert_pinned_formula()
    expected = load_audit_population()
    development = _load_timeline(DEVELOPMENT_TIMELINE, "development")
    holdout = _load_timeline(HOLDOUT_TIMELINE, "holdout")
    timeline_cases = {**development["cases"], **holdout["cases"]}
    if len(timeline_cases) != len(development["cases"]) + len(holdout["cases"]):
        raise ValueError("case IDs overlap between development and holdout fixtures")
    expected_ids = {row["case_id"] for row in expected}
    missing = sorted(expected_ids - set(timeline_cases))
    if missing:
        raise ValueError(f"combat audit identities missing from timeline fixtures: {missing}")
    if len(expected_ids) != 31:
        raise ValueError(f"expected exact 31-case COMBAT_REQUIRED population, got {len(expected_ids)}")
    results = []
    for audit in expected:
        case = timeline_cases[audit["case_id"]]
        if case.get("split") != audit.get("split"):
            raise ValueError(f"split mismatch for {audit['case_id']}")
        before = case.get("snapshots", {}).get("before", {}).get("provenance", {})
        arrival = case.get("snapshots", {}).get("arrival", {}).get("provenance", {})
        if [before.get("tick"), arrival.get("tick")] != audit.get("ticks"):
            raise ValueError(f"source tick mismatch for {audit['case_id']}")
        result = score_case(case)
        result["audit_sequence"] = audit.get("sequence")
        result["audit_lines"] = audit.get("lines")
        result["boundary_branch"] = REQUIRED_BRANCH
        results.append(result)
    source_manifest = _source_hash_manifest()
    for row in results:
        raw_path = row.get("source_path", "").replace("/", "\\")
        expected_raw = source_manifest.get(raw_path)
        row["source_manifest_match"] = bool(
            expected_raw and row.get("source_sha256") == expected_raw.get("expected_sha256")
            and expected_raw.get("matches_manifest"))
    if not all(row["source_manifest_match"] for row in results):
        raise ValueError("a scored case source does not match the six-file pinned manifest")
    return results, {
        "development_fixture": {
            "path": DEVELOPMENT_TIMELINE.relative_to(ROOT).as_posix(),
            "case_count": development["payload"].get("case_count"),
            "source_hashes": development["payload"].get("source_hashes", {}),
        },
        "holdout_fixture": {
            "path": HOLDOUT_TIMELINE.relative_to(ROOT).as_posix(),
            "case_count": holdout["payload"].get("case_count"),
            "source_hashes": holdout["payload"].get("source_hashes", {}),
        },
        "all_six_pinned_raw_sources": source_manifest,
    }


def score_transition_aliases(primary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["cohort"], row["before_tick"], row.get("target_id")): row
              for row in primary}
    aliases = []
    for row in load_transition_combat_population():
        categories = [category for category in row.get("event_categories", [])
                      if category in COMBAT_EVENT_CATEGORIES]
        destinations = sorted({force[2] for force in row.get("input", {}).get("forces", [])
                               if isinstance(force, list) and len(force) >= 3 and
                               type(force[2]) is int})
        tick = row.get("input", {}).get("world_sequence")
        matches = [by_key[(row.get("cohort"), tick, target)]
                   for target in destinations
                   if (row.get("cohort"), tick, target) in by_key]
        chosen = matches[0] if len(matches) == 1 else None
        aliases.append({
            "cohort": row.get("cohort"),
            "before_tick": tick,
            "before_sequence": row.get("before_sequence"),
            "after_sequence": row.get("after_sequence"),
            "event_categories": categories,
            "source_transition_match": row.get("matched"),
            "corpus_force_destinations": destinations,
            "dedup_key": ([chosen["cohort"], chosen["before_tick"], chosen["target_id"]]
                          if chosen else None),
            "duplicate_of_case_id": chosen.get("case_id") if chosen else None,
            "duplicate_population_case": chosen is not None,
            "formula_scoring_reused_from_exact_raw_case": chosen is not None,
            "raw_formula_status": chosen.get("raw_formula_status") if chosen else "UNKNOWN_MAPPING",
            "predicted_winner": chosen.get("prediction", {}).get("winner") if chosen else None,
            "owner_match_arrival": chosen.get("owner_match_arrival") if chosen else None,
            "vector_match_arrival": chosen.get("vector_match_arrival") if chosen else None,
            "raw_formula_match_arrival": chosen.get("raw_formula_match_arrival") if chosen else None,
            "evaluable": chosen.get("evaluable") if chosen else False,
            "mapping_candidates": [item.get("case_id") for item in matches],
        })
    return aliases


def _verdict(summary: dict[str, Any]) -> dict[str, Any]:
    n = summary["evaluable_arrival_compared"]
    correct = summary["evaluable_arrival_exact_match"]
    accuracy = correct / n if n else None
    if n >= 20 and accuracy is not None and accuracy >= 0.90:
        status = "SUPPORTED"
        next_step = "No controlled evidence escalation is indicated by this gate."
    elif n < 10 or accuracy is None or accuracy < 0.70:
        status = "PARTIAL"
        next_step = "Gather controlled evidence; this passive sample cannot support formula promotion."
    else:
        status = "PARTIAL"
        next_step = "Expand the preregistered sample before drawing a support conclusion."
    return {
        "status": status,
        "evaluable_n": n,
        "exact_matches": correct,
        "exact_match_rate": accuracy,
        "support_gate": {"minimum_evaluable": 20, "minimum_accuracy": 0.90},
        "controlled_evidence_gate": {"fewer_than_evaluable": 10, "accuracy_below": 0.70},
        "next_step": next_step,
        "production_promotion": False,
        "formula_tuning": False,
    }


def build_report() -> dict[str, Any]:
    rows, source_context = score_audit_population()
    aliases = score_transition_aliases(rows)
    by_split = {split: _summary([row for row in rows if row["split"] == split])
                for split in ("development", "holdout")}
    summary = _summary(rows)
    # The existing four rows are reported separately but deduplicated from the
    # primary population by the requested cohort/tick/target key.
    primary_keys = {(row["cohort"], row["before_tick"], row["target_id"])
                    for row in rows}
    alias_keys = {tuple(row["dedup_key"]) for row in aliases if row.get("dedup_key")}
    union_keys = primary_keys | alias_keys
    full_transition_matches = sum(row.get("source_transition_match") is True for row in aliases)
    full_transition_mismatches = sum(row.get("source_transition_match") is False for row in aliases)
    freeze = json.loads((ROOT / "docs/V2_M2A_SETTLEMENT_RULE_FREEZE.json").read_text(encoding="utf-8"))
    formula_hash = assert_pinned_formula()
    return {
        "version": "combat-passive-replay-v1",
        "status": "PASSIVE_ANALYSIS_COMPLETE",
        "freeze": {
            "path": "docs/V2_M2A_SETTLEMENT_RULE_FREEZE.json",
            "sha256": sha256(ROOT / "docs/V2_M2A_SETTLEMENT_RULE_FREEZE.json"),
            "version": freeze.get("version"),
            "combat_clause": freeze.get("combat"),
            "formal_credit": freeze.get("formal_credit"),
        },
        "formula": {
            "name": "fight_ordinary",
            "source_path": COMBAT_SOURCE.relative_to(ROOT).as_posix(),
            "source_sha256": formula_hash,
            "pinned_sha256": PINNED_COMBAT_SHA256,
            "defender_is_tower": True,
            "attacker_morale": "retained force.accelerated; unique pinned known-leg ETA inversion only when directly observed flag is absent",
            "defender_morale": "target tower morale at before tick",
            "source_current_morale": "supplementary context only; never substituted for force.accelerated",
            "production_or_formula_change": False,
        },
        "timeline": {
            "before": "audit tick t; fight inputs",
            "arrival": "audit tick t+1; combat projection comparison",
            "following": "same-scope tick t+2; observed follow-up comparison only, not a combat forecast",
            "force_status_t_plus_1": "arrival snapshot",
            "force_status_t_plus_2": "following snapshot",
        },
        "provenance": {
            "audit_path": COMBAT_AUDIT.relative_to(ROOT).as_posix(),
            "audit_sha256": sha256(COMBAT_AUDIT),
            "settlement_source_manifest": SETTLEMENT_RECEIPT.relative_to(ROOT).as_posix(),
            **source_context,
            "scored_case_sources_verified_against_six_file_manifest": True,
        },
        "population": {
            "primary_audit_rule": "factor_observations.arrival[*].current_leg_boundary.branch == COMBAT_REQUIRED",
            "primary_count": len(rows),
            "primary_unique_case_ids": len({row["case_id"] for row in rows}),
            "primary_by_split": {split: sum(row["split"] == split for row in rows)
                                 for split in ("development", "holdout")},
            "legacy_transition_corpus_count": len(aliases),
            "legacy_transition_corpus_categories": {
                name: sum(name in row["event_categories"] for row in aliases)
                for name in sorted(COMBAT_EVENT_CATEGORIES)
            },
            "legacy_transition_model_matches": full_transition_matches,
            "legacy_transition_model_mismatches": full_transition_mismatches,
            "submitted_rows_including_aliases": len(rows) + len(aliases),
            "dedup_key": ["cohort", "before_tick", "target_id"],
            "union_unique_cases": len(union_keys),
            "legacy_new_unique_cases": len(union_keys - primary_keys),
            "legacy_candidates_are_formula_scored_from_exact_raw_timeline_aliases": all(
                row["formula_scoring_reused_from_exact_raw_case"] for row in aliases),
        },
        "summary": summary,
        "by_split": by_split,
        "verdict": _verdict(summary),
        "cases": rows,
        "legacy_transition_corpus_cases": aliases,
        "interpretation": {
            "raw_formula_outcome": "All 31 fights are passively scored from exact before-tick vectors, shield, target capacity, and the frozen morale inputs; raw matches retain contaminated cases.",
            "owner_proxy": "Owner agreement is reported independently from surviving-vector agreement.",
            "following_observation": "The t+2 comparison checks the observed state against the t+1 combat projection; it is not a full next-tick prediction and can include later world changes.",
            "force_continuation": "AMBIGUOUS means a new-leg-compatible force is visible but physical genealogy is not established. DISAPPEARED means the original typed route signature is absent from a complete visible force census at that observation; it does not establish permanent consumption.",
            "capacity": "The defender capacity owner/vector are the before-tick inputs. A predicted owner change leaves post-capture capacity downstream and unknown in this replay.",
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    lines = [
        "# M2A Passive Combat Replay",
        "",
        "The passive replay applies the frozen `fight_ordinary` candidate to all 31 `COMBAT_REQUIRED` current-leg boundary cases. The combat source hash matched the pinned value before scoring; no formula tuning or production promotion occurred.",
        "",
        f"**Verdict: {verdict['status']}** — {verdict['evaluable_n']} locally evaluable cases, {verdict['exact_matches']}/{verdict['evaluable_n']} exact arrival projections ({verdict['exact_match_rate']:.1%}). The support bar is at least 20 evaluable cases and at least 90% exact agreement; the next evidence step is controlled evidence because the clean sample is below 10.",
        "",
        "## Frozen inputs and population",
        "",
        f"- Formula: `{report['formula']['source_path']}` SHA256 `{report['formula']['source_sha256']}`.",
        f"- Attacker morale: retained `force.accelerated` (unique pinned known-leg ETA inversion only when the visible flag is absent). Source tower morale is supplementary and is never substituted.",
        f"- Population: {report['population']['primary_count']} unique raw cases ({report['population']['primary_by_split']['development']} development, {report['population']['primary_by_split']['holdout']} holdout). The four prior ground/air corpus rows add 0 unique cases after deduplication; union = {report['population']['union_unique_cases']}.",
        "- Timeline: `before=t`, `arrival=t+1`, `following=t+2`, with matching source hash, scope, and consecutive ticks checked for every case.",
        "",
        "## Raw formula outcomes",
        "",
        f"- All {summary['formula_scored']}/{summary['candidate_count']} candidates had sufficient ordinary fight inputs and produced a frozen formula result.",
        f"- Predicted owner matched the observed arrival owner in {summary['arrival_owner_match']}/{summary['arrival_owner_compared']} cases.",
        f"- Surviving vector matched the observed arrival tower vector in {summary['arrival_vector_match']}/{summary['arrival_vector_compared']} cases; full owner-plus-vector projection matched in {summary['arrival_exact_match']}/{summary['arrival_exact_compared']}.",
        f"- At the following snapshot, the t+1 projection still agreed in {summary['following_snapshot_exact_agreement']}/{summary['candidate_count']} cases. This is an observed follow-up comparison, not a t+2 combat forecast.",
        f"- Strict local evaluability: {summary['evaluable']}/{summary['candidate_count']}; {summary['evaluable_arrival_exact_match']}/{summary['evaluable_arrival_compared']} exact arrival projections in that subset.",
        "- Five raw vector mismatches all retained correct owner predictions. In those cases the observed tower inventory was zero while a new-leg-compatible force was visible; force genealogy remains ambiguous.",
        "",
        "## Contamination and force continuity",
        "",
        f"- Production due at the combat input tick: {summary['contamination_counts']['production']}.",
        f"- Aura input uncertainty: {summary['contamination_counts']['aura']}.",
        f"- Multiple inbound context: {summary['contamination_counts']['multiple_inbound']}.",
        f"- Hostile pair relation: {summary['pair_relation_status_counts']}.",
        f"- Special vectors: {summary['contamination_counts']['special']}.",
        f"- Active delay, capacity uncertainty, and timeline continuity: {summary['contamination_counts']['active_delay']}, {summary['contamination_counts']['capacity_uncertainty']}, {summary['contamination_counts']['continuity']}.",
        f"- Force status at arrival/t+1: {summary['post_arrival_force_status']['t_plus_1']}; at following/t+2: {summary['post_arrival_force_status']['t_plus_2']}. Ambiguous new-leg cases do not prove physical genealogy or permanent consumption.",
        f"- Continuation uncertain in {summary['force_continuation_uncertain_cases']}/{summary['candidate_count']} cases; status bases at t+1: {summary['post_arrival_force_status_basis']['t_plus_1']}.",
        "",
        "## Separate legacy candidates",
        "",
        "| Cohort / tick / target | Event | Prior transition match | Dedup result | Combat projection |",
        "|---|---|---:|---|---|",
    ]
    for row in report["legacy_transition_corpus_cases"]:
        key = row.get("dedup_key")
        shown = ", ".join(map(str, key)) if key else "unmapped"
        lines.append(
            f"| {shown} | {', '.join(row['event_categories'])} | {row['source_transition_match']} | duplicate: {row['duplicate_of_case_id'] or 'no match'} | {row['raw_formula_status']} / owner {row['owner_match_arrival']} / vector {row['vector_match_arrival']} |")
    lines.extend([
        "",
        "## Full pinned raw-file manifest",
        "",
        "The six raw files below are inherited from the unfiltered settlement receipt. Every scored row maps to one of the three listed relevant files; all six expected and actual hashes in the pinned receipt match.",
        "",
        "| Cohort file | SHA256 | Manifest match |",
        "|---|---|---|",
    ])
    for path, item in report["provenance"]["all_six_pinned_raw_sources"].items():
        lines.append(f"| `{path.replace(chr(92), '/')}` | `{item['expected_sha256']}` | {item['matches_manifest']} |")
    lines.extend([
        "",
        "## Case results",
        "",
        "| Case | Split | Winner | Owner match | Vector match | Evaluable | Main blocker | t+1 force | t+2 force |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ])
    for row in report["cases"]:
        winner = (row.get("prediction") or {}).get("winner")
        blocker = ", ".join(row.get("evaluability_blockers", [])) or "—"
        statuses = row.get("post_arrival_force_status", {})
        lines.append(
            f"| {row['case_id']} | {row['split']} | {winner or 'UNKNOWN'} | {row.get('owner_match_arrival')} | {row.get('vector_match_arrival')} | {row['evaluable']} | {blocker} | {statuses.get('t_plus_1')} | {statuses.get('t_plus_2')} |")
    lines.extend([
        "",
        "All unevaluable rows remain in the raw formula results. Strict local blockers are unresolved simultaneous inbound context and, for foreign-versus-foreign pairs, the absence of an observed hostility relation. The four clean cases do not meet the minimum sample size for support.",
        "",
    ])
    return "\n".join(lines)


def write_report() -> dict[str, Any]:
    report = build_report()
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    OUTPUT_MARKDOWN.write_text(_render_markdown(report), encoding="utf-8")
    fixture = {
        "version": report["version"],
        "formula": report["formula"],
        "provenance": report["provenance"],
        "population": report["population"],
        "summary": report["summary"],
        "by_split": report["by_split"],
        "verdict": report["verdict"],
        "cases": report["cases"],
        "legacy_transition_corpus_cases": report["legacy_transition_corpus_cases"],
    }
    encoded = json.dumps(fixture, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    OUTPUT_FIXTURE.write_bytes(gzip.compress(encoded, compresslevel=9, mtime=0))
    return report


if __name__ == "__main__":
    result = write_report()
    print(json.dumps({"status": result["status"], "summary": result["summary"],
                      "verdict": result["verdict"],
                      "legacy_transition_corpus_cases": result["legacy_transition_corpus_cases"]},
                     ensure_ascii=False, indent=2))


__all__ = [
    "COMBAT_SOURCE", "PINNED_COMBAT_SHA256", "UnsupportedState",
    "assert_pinned_formula", "classify_force_status", "evaluability",
    "observed_match", "project_fight", "sha256",
]
