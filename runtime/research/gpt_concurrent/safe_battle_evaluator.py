"""Conservative, offline PvP evaluation wrappers for the Round 8 mirror.

This module never connects to the game, a browser, CDP, or the production WASM.
It calls the mirror only after the static-support gate accepts every required
fact. Runtime parity and command acceptance remain explicitly unvalidated.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from battle_mirror_partial import CAPACITIES, predict_battle


MANY_UNITS = {"Fighter", "Chopper", "Bomber", "Tank", "Soldier"}
SUPPORTED_UNITS = {"Shield", *MANY_UNITS}
EXCLUDED_UNITS = {"Shell", "Emp", "Nuke", "Ruler"}
MARGINAL_SURVIVOR_MAX_DEFAULT = 1  # Planner policy only; not a game rule.


def _failure(reason: str, *, status: str = "UNSUPPORTED") -> dict[str, Any]:
    reason_lower = reason.lower()
    evaluation_status = (
        "UNKNOWN"
        if any(marker in reason_lower for marker in ("unknown", "missing", "required", "stale", "not known", "explicit", "must be known"))
        else "UNSUPPORTED"
    )
    return {
        "supported": False,
        "support_status": status,
        "static_support_status": status,
        "evaluation_status": evaluation_status,
        "support_reason": reason,
        "winner": None,
        "attacker_survivors": None,
        "defender_survivors": None,
        "new_owner": None,
        "confidence": "NONE",
        "runtime_validation_required": True,
        "unsupported_reason": reason,
    }


def _valid_counts(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and not (set(value) - SUPPORTED_UNITS - EXCLUDED_UNITS)
        and all(type(count) is int and 0 <= count <= 255 for count in value.values())
        and not any(value.get(unit, 0) for unit in EXCLUDED_UNITS)
    )


def _gate_battle(case: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Return a rejection reason or a normalized case for the mirror."""
    if case.get("world_context_required") is not False:
        return "full or unknown world/player context is required", None
    if type(case.get("observed_tick")) is not int or case["observed_tick"] < 0:
        return "a known non-negative observation tick is required", None

    if not _valid_counts(case.get("attacker_units")) or not _valid_counts(
        case.get("defender_units")
    ):
        return "unit maps must contain only known 8-bit counts; special units are excluded", None
    if not any(case["attacker_units"].values()):
        return "empty attacker force cannot enter battle resolution", None
    if not any(case["defender_units"].values()):
        return "empty defender force or tower follows a non-battle arrival branch", None

    flags = case.get("special_unit_flags")
    required_flags = {"ruler", "shell", "emp", "nuke"}
    if not isinstance(flags, dict) or set(flags) != required_flags:
        return "all four special-unit flags must be explicitly supplied", None
    if any(value is not False for value in flags.values()):
        return "Ruler/Shell/EMP/Nuke participation is unsupported", None

    attacker_rel = case.get("attacker_owner_relation")
    defender_rel = case.get("defender_owner_relation")
    if not isinstance(attacker_rel, str) or not isinstance(defender_rel, str):
        return "both owner relations must be known", None
    self_owner_id = case.get("self_owner_id")
    if type(self_owner_id) is not int or self_owner_id <= 0:
        return "the controlled player's owner id is unknown", None
    if attacker_rel == "SELF" and defender_rel == "ENEMY":
        relation = "enemy"
    elif attacker_rel == "ENEMY" and defender_rel == "SELF":
        relation = "enemy"
    elif attacker_rel == "SELF" and defender_rel == "NEUTRAL":
        relation = "neutral"
    elif attacker_rel == "ENEMY_FORCE" and defender_rel == "ENEMY_FORCE":
        return "PvP force owners cannot be mapped to the controlled player", None
    else:
        return "owner relationship is outside the supported PvP relations", None

    attacker_aura = case.get("attacker_aura_snapshot")
    defender_aura = case.get("defender_aura_snapshot")
    if type(attacker_aura) is not bool or type(defender_aura) is not bool:
        return "both aura snapshots must be explicit booleans", None
    ruler_states = case.get("ruler_aura_state")
    if not isinstance(ruler_states, dict):
        return "Ruler aura provenance is required even when no Ruler participates", None
    for side, expected_aura in (("attacker", attacker_aura), ("defender", defender_aura)):
        snapshot = ruler_states.get(side)
        if not isinstance(snapshot, dict):
            return f"{side} Ruler/aura state is missing", None
        if snapshot.get("ruler_unit_present") is not False:
            return f"{side} Ruler participation is unsupported or unknown", None
        if type(snapshot.get("aura_flag_snapshot")) is not bool:
            return f"{side} aura provenance is unknown", None
        if snapshot["aura_flag_snapshot"] != expected_aura:
            return f"{side} aura snapshot conflicts with its provenance", None

    shield_state = case.get("shield_state")
    if not isinstance(shield_state, dict):
        return "explicit Shield counts are required", None
    for side, units_key in (("attacker", "attacker_units"), ("defender", "defender_units")):
        count = shield_state.get(side)
        if type(count) is not int or count != case[units_key].get("Shield", 0):
            return f"{side} Shield state does not match the supplied unit vector", None

    battle_kind = case.get("battle_kind")
    normalized: dict[str, Any] = {
        "battle_kind": battle_kind,
        "relation": relation,
        "target_branch": case.get("target_branch"),
        "attacker_units": dict(case["attacker_units"]),
        "defender_units": dict(case["defender_units"]),
        "attacker_aura": attacker_aura,
        "defender_aura": defender_aura,
    }
    if battle_kind == "force_vs_tower":
        if case.get("target_branch") != "tower_combat":
            return "only a nonempty tower-combat branch is supported", None
        tower_type = case.get("tower_type")
        if not CAPACITIES or tower_type not in CAPACITIES:
            return "tower type has no validated capacity mapping", None
        capacity = case.get("tower_capacity")
        if not isinstance(capacity, dict) or capacity != CAPACITIES[tower_type]:
            return "tower capacity is missing or differs from the validated table", None
        attacker_owner = case.get("attacker_owner_id")
        tower_owner = case.get("defender_owner_id")
        if type(attacker_owner) is not int or attacker_owner <= 0:
            return "attacker owner is unknown", None
        if (attacker_rel == "SELF") != (attacker_owner == self_owner_id):
            return "attacker owner id conflicts with its SELF/ENEMY relation", None
        if relation == "neutral":
            if defender_rel != "NEUTRAL" or tower_owner is not None:
                return "neutral tower owner fields conflict", None
        elif type(tower_owner) is not int or tower_owner <= 0 or tower_owner == attacker_owner:
            return "enemy tower owner is unknown or conflicts with attacker", None
        elif (defender_rel == "SELF") != (tower_owner == self_owner_id):
            return "tower owner id conflicts with its SELF/ENEMY relation", None
        normalized.update(
            {
                "tower_type": tower_type,
                "attacker_owner": attacker_owner,
                "tower_owner": tower_owner,
            }
        )
    elif battle_kind == "force_vs_force":
        if case.get("target_branch") != "force_collision" or case.get("force_collision_confirmed") is not True:
            return "force collision must already be confirmed by the caller", None
        attacker_owner = case.get("attacker_owner_id")
        defender_owner = case.get("defender_owner_id")
        if (
            type(attacker_owner) is not int
            or attacker_owner <= 0
            or type(defender_owner) is not int
            or defender_owner <= 0
            or attacker_owner == defender_owner
        ):
            return "force owners must be distinct known positive ids", None
        if (attacker_rel == "SELF") != (attacker_owner == self_owner_id):
            return "attacker owner id conflicts with its SELF/ENEMY relation", None
        if (defender_rel == "SELF") != (defender_owner == self_owner_id):
            return "defender owner id conflicts with its SELF/ENEMY relation", None
        normalized.update(
            {
                "battle_kind": "force_vs_force",
                "relation": "enemy_force",
                "target_branch": "force_collision",
                "attacker_owner": attacker_owner,
                "defender_owner": defender_owner,
                "tower_type": None,
                "tower_owner": None,
            }
        )
    else:
        return "battle kind is outside the supported mirror branches", None

    return None, normalized


def evaluate_battle(case: dict[str, Any]) -> dict[str, Any]:
    """Gate first, then call the ordinary-unit mirror for accepted cases."""
    if not isinstance(case, dict):
        return _failure("battle input must be an object")
    reason, normalized = _gate_battle(case)
    if reason is not None or normalized is None:
        return _failure(reason or "support gate rejected the case")

    # This is the only call site for the battle mirror.
    mirrored = predict_battle(normalized)
    if not mirrored.get("supported"):
        return _failure(mirrored.get("unsupported_reason") or "mirror rejected the case")
    runtime_validated = case.get("battle_differential_validated") is True
    return {
        "supported": True,
        "support_status": "SUPPORTED" if runtime_validated else "RUNTIME_VALIDATION_NEEDED",
        "static_support_status": "SUPPORTED",
        "evaluation_status": "SUPPORTED" if runtime_validated else "UNKNOWN",
        "support_reason": (
            "static subset and external battle differential gate passed"
            if runtime_validated
            else "SUPPORTED_STATIC_SUBSET; production differential not run"
        ),
        "winner": mirrored["winner"],
        "attacker_survivors": mirrored["attacker_survivors"],
        "defender_survivors": mirrored["defender_survivors"],
        "new_owner": mirrored["new_owner"],
        "new_owner_relation": mirrored["new_owner_relation"],
        "confidence": (
            "EXTERNAL_RUNTIME_VALIDATION_GATE_PASSED_FOR_CALLER_DECLARED_SCOPE"
            if runtime_validated
            else mirrored["confidence"]
        ),
        "runtime_validation_required": not runtime_validated,
        "unsupported_reason": None,
        "static_mirror_result": mirrored,
    }


def _command_legality(evidence: dict[str, Any]) -> tuple[str, str | None]:
    required = (
        "source_is_self",
        "source_has_full_mobile_force",
        "target_is_enemy",
        "target_is_direct_neighbor",
        "path_valid",
        "world_fresh",
        "target_owner_fresh",
    )
    values = [evidence.get(key) for key in required]
    if any(value is False for value in values):
        return "ILLEGAL", "one or more command-legality predicates are false"
    if any(value is not True for value in values):
        return "UNKNOWN", "one or more command-legality predicates are unknown"
    if evidence.get("command_kind") != "DeployForce":
        return "UNKNOWN", "command kind is not confirmed as DeployForce"
    return "LEGAL_STATIC_SHAPE", None


def _reinforcement_command_validated(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    required = (
        "source_is_self",
        "source_has_full_mobile_force",
        "target_is_self",
        "path_valid",
        "world_fresh",
        "target_owner_fresh",
    )
    return (
        all(evidence.get(key) is True for key in required)
        and evidence.get("command_kind") == "DeployForce"
        and evidence.get("server_acceptance_validated") is True
    )


def evaluate_attack(data: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a supplied SELF-to-ENEMY direct-neighbor attack; never chooses a target."""
    if not isinstance(data, dict):
        return {"result": "UNSUPPORTED", "legality": "UNKNOWN", "evaluation_status": "UNKNOWN", "unsupported_reason": "input must be an object"}
    evidence = data.get("legality_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    legality, legality_reason = _command_legality(evidence)
    battle = evaluate_battle(data.get("battle_case"))
    if legality == "ILLEGAL":
        return {
            "result": "ILLEGAL",
            "legality": legality,
            "evaluation_status": "UNSUPPORTED",
            "battle_supported": battle["supported"],
            "projected_result": "UNSUPPORTED" if not battle["supported"] else None,
            "safe_attack_candidate": False,
            "unsupported_reason": legality_reason,
            "runtime_validation_required": True,
        }

    force = data.get("deployable_force")
    if not _valid_counts(force) or not force or set(force) - MANY_UNITS:
        return {
            "result": "UNSUPPORTED",
            "legality": legality,
            "evaluation_status": "UNSUPPORTED",
            "battle_supported": battle["supported"],
            "projected_result": "UNSUPPORTED",
            "safe_attack_candidate": False,
            "unsupported_reason": "attack source must provide its exact nonempty mobile Many composition",
            "runtime_validation_required": True,
        }
    raw_case = data.get("battle_case")
    if (
        not isinstance(raw_case, dict)
        or raw_case.get("attacker_owner_relation") != "SELF"
        or raw_case.get("defender_owner_relation") != "ENEMY"
        or raw_case.get("attacker_units") != force
    ):
        return {
            "result": "UNSUPPORTED",
            "legality": legality,
            "evaluation_status": "UNSUPPORTED",
            "battle_supported": battle["supported"],
            "projected_result": "UNSUPPORTED",
            "safe_attack_candidate": False,
            "unsupported_reason": "battle attacker must be this exact SELF deployable force against an ENEMY tower",
            "runtime_validation_required": True,
        }
    normalized_force = {unit: count for unit, count in force.items() if count}
    normalized_attackers = {
        unit: count for unit, count in raw_case.get("attacker_units", {}).items() if count
    }
    if normalized_attackers != normalized_force:
        return {
            "result": "UNSUPPORTED",
            "legality": legality,
            "evaluation_status": "UNSUPPORTED",
            "battle_supported": battle["supported"],
            "projected_result": "UNSUPPORTED",
            "safe_attack_candidate": False,
            "unsupported_reason": "battle input does not match the exact full deployable force",
            "runtime_validation_required": True,
        }
    if not battle["supported"]:
        return {
            "result": "UNSUPPORTED",
            "legality": legality,
            "evaluation_status": battle.get("evaluation_status", "UNKNOWN"),
            "battle_supported": False,
            "projected_result": "UNSUPPORTED",
            "safe_attack_candidate": False,
            "unsupported_reason": battle["unsupported_reason"],
            "battle_evaluation": battle,
            "runtime_validation_required": True,
        }

    projected = {
        "attacker": "ATTACK_WIN",
        "defender": "ATTACK_LOSE",
        "contested": "ATTACK_CONTESTED",
    }[battle["winner"]]
    survivors = sum(battle["attacker_survivors"].get(unit, 0) for unit in MANY_UNITS)
    marginal_max = data.get("marginal_survivor_max", MARGINAL_SURVIVOR_MAX_DEFAULT)
    if type(marginal_max) is not int or marginal_max < 0:
        return {
            "result": "UNSUPPORTED",
            "legality": legality,
            "evaluation_status": "UNSUPPORTED",
            "battle_supported": True,
            "projected_result": projected,
            "safe_attack_candidate": False,
            "unsupported_reason": "marginal survivor policy must be a non-negative integer",
            "runtime_validation_required": True,
        }
    margin = (
        "ROBUST_WIN"
        if projected == "ATTACK_WIN" and survivors > marginal_max
        else "MARGINAL_WIN"
        if projected == "ATTACK_WIN"
        else projected
    )
    command_validated = evidence.get("server_acceptance_validated") is True
    safe = (
        margin == "ROBUST_WIN"
        and legality == "LEGAL_STATIC_SHAPE"
        and command_validated
        and battle["support_status"] == "SUPPORTED"
    )
    result = "ATTACK_WIN" if projected == "ATTACK_WIN" else projected
    if legality == "UNKNOWN":
        result = "UNSUPPORTED"
    return {
        "result": result,
        "legality": legality,
        "evaluation_status": (
            "SUPPORTED"
            if legality == "LEGAL_STATIC_SHAPE" and command_validated and battle["support_status"] == "SUPPORTED"
            else "UNKNOWN"
            if legality == "UNKNOWN" or not command_validated or battle["support_status"] != "SUPPORTED"
            else "UNSUPPORTED"
        ),
        "battle_supported": True,
        "projected_result": projected,
        "safety_margin": margin,
        "surviving_mobile_units": survivors,
        "marginal_survivor_max": marginal_max,
        "margin_parameter_status": "TUNABLE_POLICY_NOT_GAME_RULE",
        "safe_attack_candidate": safe,
        "unsupported_reason": legality_reason if legality == "UNKNOWN" else None,
        "battle_evaluation": battle,
        "runtime_validation_required": (
            battle["runtime_validation_required"]
            or not command_validated
            or legality != "LEGAL_STATIC_SHAPE"
        ),
    }


def evaluate_defense(data: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an incoming force; reinforcement needs an exact post-merge snapshot."""
    if not isinstance(data, dict):
        return {"support_status": "UNSUPPORTED", "evaluation_status": "UNKNOWN", "unsupported_reason": "input must be an object"}
    enemy_eta = data.get("enemy_eta")
    if type(enemy_eta) is not int or enemy_eta < 0:
        return {"support_status": "UNSUPPORTED", "evaluation_status": "UNKNOWN", "unsupported_reason": "enemy ETA is unknown"}
    for evidence_key in ("incoming_path_valid", "world_fresh", "target_owner_fresh"):
        if data.get(evidence_key) is not True:
            return {
                "support_status": "UNSUPPORTED",
                "evaluation_status": "UNKNOWN",
                "unsupported_reason": f"{evidence_key} must be explicitly true for defense evaluation",
                "tower_survives": None,
                "tower_lost": None,
                "rescue_candidates": [],
                "runtime_validation_required": True,
            }
    raw_case = data.get("battle_case")
    if (
        not isinstance(raw_case, dict)
        or raw_case.get("attacker_owner_relation") != "ENEMY"
        or raw_case.get("defender_owner_relation") != "SELF"
    ):
        return {"support_status": "UNSUPPORTED", "evaluation_status": "UNKNOWN", "unsupported_reason": "defense requires incoming ENEMY force against a SELF tower"}
    base = evaluate_battle(raw_case)
    if not base["supported"]:
        return {
            "support_status": "UNSUPPORTED",
            "evaluation_status": base.get("evaluation_status", "UNKNOWN"),
            "unsupported_reason": base["unsupported_reason"],
            "tower_survives": None,
            "tower_lost": None,
            "survivors": None,
            "rescue_candidates": [],
            "runtime_validation_required": True,
        }

    lost = base["winner"] in {"attacker", "contested"}
    result: dict[str, Any] = {
        "support_status": base["support_status"],
        "evaluation_status": base["evaluation_status"],
        "support_reason": (
            "battle differential gate passed for the supplied scope; timing and arrival facts remain caller supplied"
            if base["support_status"] == "SUPPORTED"
            else "static ordinary battle only; timing/arrival facts are caller supplied"
        ),
        "tower_survives": not lost,
        "tower_lost": lost,
        "survivors": base["defender_survivors"],
        "battle_evaluation": base,
        "enemy_eta": enemy_eta,
        "reinforcement_results": [],
        "rescue_candidates": [],
        "minimum_sufficient_reinforcement": None,
        "rescue_requirement_status": "UNSUPPORTED_UNLESS_EXACT_POST_MERGE_SNAPSHOT_IS_SUPPLIED",
        "runtime_validation_required": base["runtime_validation_required"],
    }

    candidates = data.get("reinforcement_candidates", [])
    if not isinstance(candidates, list):
        result["support_status"] = "UNSUPPORTED"
        result["evaluation_status"] = "UNSUPPORTED"
        result["unsupported_reason"] = "reinforcement_candidates must be a list"
        return result
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        eta = candidate.get("reinforcement_eta")
        if type(eta) is not int or eta < 0:
            result["reinforcement_results"].append({"status": "UNSUPPORTED", "reason": "reinforcement ETA unknown"})
            continue
        if eta > enemy_eta:
            result["reinforcement_results"].append(
                {"status": "REINFORCEMENT_TOO_LATE", "reinforcement_eta": eta, "enemy_eta": enemy_eta}
            )
            continue
        if eta == enemy_eta:
            result["reinforcement_results"].append(
                {"status": "UNSUPPORTED", "reason": "same-tick order is not validated", "reinforcement_eta": eta}
            )
            continue
        snapshot = candidate.get("post_merge_battle_case")
        if candidate.get("post_merge_snapshot_exact") is not True or not isinstance(snapshot, dict):
            result["reinforcement_results"].append(
                {"status": "UNSUPPORTED", "reason": "friendly merge is not inferred; exact post-merge state is required"}
            )
            continue
        invariant_fields = (
            "battle_kind",
            "target_branch",
            "attacker_owner_relation",
            "defender_owner_relation",
            "attacker_owner_id",
            "defender_owner_id",
            "attacker_units",
            "attacker_aura_snapshot",
            "observed_tick",
            "tower_type",
            "tower_capacity",
            "world_context_required",
        )
        if any(snapshot.get(key) != raw_case.get(key) for key in invariant_fields):
            result["reinforcement_results"].append(
                {"status": "UNSUPPORTED", "reason": "post-merge snapshot changed the incoming force or target context"}
            )
            continue
        if snapshot.get("defender_units") is None:
            result["reinforcement_results"].append(
                {"status": "UNSUPPORTED", "reason": "post-merge defender composition is missing"}
            )
            continue
        merged = evaluate_battle(snapshot)
        if merged["runtime_validation_required"]:
            result["runtime_validation_required"] = True
        row = {
            "status": merged["support_status"] if merged["supported"] else "UNSUPPORTED",
            "reinforcement_eta": eta,
            "battle_evaluation": merged,
        }
        if merged["support_status"] == "SUPPORTED" and merged["winner"] == "defender":
            force = candidate.get("full_deployable_force")
            if (
                candidate.get("source_tower_id") is None
                or not _valid_counts(force)
                or not force
                or set(force) - MANY_UNITS
            ):
                row["status"] = "UNSUPPORTED"
                row["reason"] = "candidate must identify its source tower and exact full mobile force a command would dispatch"
            else:
                row["status"] = "RESCUE_CANDIDATE"
                row["source_tower_id"] = candidate.get("source_tower_id")
                row["full_deployable_force"] = dict(force)
                row["unit_count"] = sum(force.values())
                row["command_validated"] = _reinforcement_command_validated(
                    candidate.get("legality_evidence")
                )
                result["rescue_candidates"].append(row)
        result["reinforcement_results"].append(row)

    if result["rescue_candidates"]:
        # This is a discrete comparison of supplied full forces, never a fabricated mix.
        validated_candidates = [
            row for row in result["rescue_candidates"] if row.get("command_validated") is True
        ]
        chosen = min(
            validated_candidates or result["rescue_candidates"],
            key=lambda row: (row["unit_count"], str(row.get("source_tower_id", ""))),
        )
        result["minimum_sufficient_reinforcement"] = {
            "source_tower_id": chosen.get("source_tower_id"),
            "full_deployable_force": chosen["full_deployable_force"],
            "unit_count": chosen["unit_count"],
            "command_validated": chosen.get("command_validated") is True,
            "comparison_metric": (
                "unit_count among exact full-force candidates with validated command evidence; tunable policy, not game cost"
                if validated_candidates
                else "unit_count among supplied exact full-force candidates; command evidence is still unvalidated"
            ),
        }
        result["rescue_requirement_status"] = "SUPPORTED_STATIC_CANDIDATE_COMPARISON"
        result["reinforcement_command_validated"] = any(
            row.get("command_validated") is True for row in result["rescue_candidates"]
        )
        if not result["reinforcement_command_validated"]:
            result["runtime_validation_required"] = True
    else:
        result["reinforcement_command_validated"] = False
    return result


def arbitrate_pvp_action(
    *,
    defense_evaluations: list[dict[str, Any]],
    attack_evaluations: list[dict[str, Any]],
    neutral_expansion_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deterministic priority: proven defense, robust attack, neutral expansion, abstain."""
    states = ["OBSERVE", "ASSESS_THREATS", "EVALUATE_DEFENSE"]
    unresolved_threat = any(
        item.get("support_status") != "SUPPORTED" or item.get("tower_lost") is None
        for item in defense_evaluations
    )
    losses = [item for item in defense_evaluations if item.get("tower_lost") is True]
    if unresolved_threat:
        states.extend(["SELECT_ACTION", "ABSTAIN"])
        status = (
            "UNSUPPORTED"
            if any(item.get("support_status") == "UNSUPPORTED" for item in defense_evaluations)
            else "UNKNOWN"
        )
        return {"action": "ABSTAIN", "evaluation_status": status, "reason": "an unresolved incoming threat prevents a safe next action", "state_trace": states}
    if losses:
        states.append("SELECT_ACTION")
        threat = min(
            losses,
            key=lambda item: (item.get("enemy_eta", 2**63), str(item.get("target_tower_id", ""))),
        )
        candidate = threat.get("minimum_sufficient_reinforcement")
        if (
            candidate
            and candidate.get("command_validated") is True
            and threat.get("reinforcement_command_validated") is True
        ):
            return {"action": "REINFORCE_SELF", "evaluation_status": "SUPPORTED", "candidate": candidate, "target_tower_id": threat.get("target_tower_id"), "reason": "supported projected tower loss and validated timely rescue", "state_trace": states}
        states.append("ABSTAIN")
        return {"action": "ABSTAIN", "evaluation_status": "SUPPORTED", "reason": "projected loss has no validated timely rescue command", "state_trace": states}

    states.extend(["EVALUATE_ATTACK", "SELECT_ACTION"])
    safe_attacks = sorted(
        (item for item in attack_evaluations if item.get("safe_attack_candidate") is True),
        key=lambda item: (
            str(item.get("target_tower_id", "")),
            str(item.get("source_tower_id", "")),
            json.dumps(item, ensure_ascii=False, sort_keys=True),
        ),
    )
    if safe_attacks:
        return {"action": "ATTACK_ENEMY", "evaluation_status": "SUPPORTED", "candidate": safe_attacks[0], "reason": "first supplied legal robust-win candidate", "state_trace": states}
    states.append("EVALUATE_EXPANSION")
    if isinstance(neutral_expansion_candidate, dict) and neutral_expansion_candidate.get("validated") is True:
        return {"action": "EXPAND_NEUTRAL", "evaluation_status": "SUPPORTED", "candidate": neutral_expansion_candidate, "reason": "no projected loss or safe attack; existing expansion candidate is validated", "state_trace": states}
    states.append("ABSTAIN")
    return {"action": "ABSTAIN", "evaluation_status": "SUPPORTED", "reason": "no validated defense, safe attack, or expansion candidate", "state_trace": states}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level input must be a JSON object")
        operation = payload.get("operation", "battle")
        if operation == "battle":
            result = evaluate_battle(payload.get("case"))
        elif operation == "attack":
            result = evaluate_attack(payload.get("input"))
        elif operation == "defense":
            result = evaluate_defense(payload.get("input"))
        elif operation == "arbitrate":
            result = arbitrate_pvp_action(**payload.get("input", {}))
        else:
            result = _failure("unknown operation")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result = _failure(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
