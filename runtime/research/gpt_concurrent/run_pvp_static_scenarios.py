"""Run the offline PvP scenario catalog; performs no game or browser I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safe_battle_evaluator import (
    CAPACITIES,
    arbitrate_pvp_action,
    evaluate_attack,
    evaluate_battle,
    evaluate_defense,
)
import safe_battle_evaluator as evaluator_module


ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "GPT_PVP_PLANNER_STATIC_SCENARIOS.json"


def _case(world: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    data = dict(defaults)
    data.update(world)
    attacker_relation = data.get("attacker_owner_relation")
    defender_relation = data.get("defender_owner_relation")
    owner_ids = {"SELF": 1, "ENEMY": 2}
    tower_type = data.get("tower_type")
    capacity = CAPACITIES.get(tower_type)
    attacker_units = data.get("attacker_units", {})
    defender_units = data.get("defender_units", {})
    attacker_aura = data.get("attacker_aura_snapshot")
    defender_aura = data.get("defender_aura_snapshot")
    ruler_aura_state = data.get("ruler_aura_state") or {
        "attacker": {"ruler_unit_present": False, "aura_flag_snapshot": attacker_aura},
        "defender": {"ruler_unit_present": False, "aura_flag_snapshot": defender_aura},
    }
    shield_state = data.get("shield_state") or {
        "attacker": attacker_units.get("Shield", 0),
        "defender": defender_units.get("Shield", 0),
    }
    return {
        "battle_kind": data.get("battle_kind", "force_vs_tower"),
        "target_branch": data.get("target_branch", "tower_combat"),
        "attacker_owner_relation": attacker_relation,
        "defender_owner_relation": defender_relation,
        "self_owner_id": data.get("self_owner_id", 1),
        "attacker_owner_id": data.get("attacker_owner_id", owner_ids.get(attacker_relation)),
        "defender_owner_id": data.get("defender_owner_id", owner_ids.get(defender_relation)),
        "attacker_units": attacker_units,
        "defender_units": defender_units,
        "tower_type": tower_type,
        "tower_capacity": data.get("tower_capacity", capacity),
        "attacker_aura_snapshot": attacker_aura,
        "defender_aura_snapshot": defender_aura,
        "shield_state": shield_state,
        "special_unit_flags": data.get(
            "special_unit_flags", {"ruler": False, "shell": False, "emp": False, "nuke": False}
        ),
        "ruler_aura_state": ruler_aura_state,
        "world_context_required": data.get("world_context_required", False),
        "battle_differential_validated": data.get("battle_differential_validated", False),
        "observed_tick": data.get("observed_tick", 1),
        "force_collision_confirmed": data.get("force_collision_confirmed", False),
    }


def _defense_input(world: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    base_case = _case(world, defaults)
    candidates = []
    for supplied in world.get("reinforcement_candidates", []):
        candidate = {
            "source_tower_id": supplied.get("source_tower_id"),
            "reinforcement_eta": supplied.get("reinforcement_eta"),
            "post_merge_snapshot_exact": supplied.get("post_merge_snapshot_exact", False),
            "full_deployable_force": supplied.get("full_deployable_force"),
            "legality_evidence": supplied.get("legality_evidence"),
        }
        if candidate["post_merge_snapshot_exact"] is True:
            merged_world = dict(world)
            merged_world["defender_units"] = supplied.get("post_merge_defender_units", world.get("defender_units", {}))
            merged_world["defender_aura_snapshot"] = supplied.get(
                "post_merge_defender_aura_snapshot", world.get("defender_aura_snapshot", defaults["defender_aura_snapshot"])
            )
            merged_world.pop("reinforcement_candidates", None)
            candidate["post_merge_battle_case"] = _case(merged_world, defaults)
        candidates.append(candidate)
    return {
        "battle_case": base_case,
        "enemy_eta": world.get("enemy_eta", defaults.get("enemy_eta")),
        "incoming_path_valid": world.get("incoming_path_valid", defaults.get("incoming_path_valid", True)),
        "world_fresh": world.get("world_fresh", defaults.get("world_fresh", True)),
        "target_owner_fresh": world.get("target_owner_fresh", defaults.get("target_owner_fresh", True)),
        "reinforcement_candidates": candidates,
    }


def _run_one(scenario: dict[str, Any], defaults: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = scenario["operation"]
    world = scenario.get("world_inputs", {})
    if operation == "simultaneous":
        defenses = []
        target_id = None
        for item in world.get("defense_cases", []):
            defense = evaluate_defense(_defense_input(item, defaults))
            defense["target_tower_id"] = item.get("target_tower_id")
            defenses.append(defense)
            if defense.get("tower_lost") is True:
                target_id = item.get("target_tower_id")
        decision = arbitrate_pvp_action(
            defense_evaluations=defenses,
            attack_evaluations=[],
            neutral_expansion_candidate=None,
        )
        return {"supported": all(row.get("support_status") != "UNSUPPORTED" for row in defenses)}, {
            **decision,
            "target_tower_id": decision.get("target_tower_id") if decision.get("action") == "REINFORCE_SELF" else target_id,
        }

    case = _case(world, defaults)
    if operation == "attack":
        evidence = world.get("legality_evidence", {
            "source_is_self": True,
            "source_has_full_mobile_force": True,
            "target_is_enemy": True,
            "target_is_direct_neighbor": True,
            "path_valid": True,
            "world_fresh": True,
            "target_owner_fresh": True,
            "command_kind": "DeployForce",
            "server_acceptance_validated": False,
        })
        evaluated = evaluate_attack(
            {
                "battle_case": case,
                "deployable_force": world.get("attacker_units", defaults["attacker_units"]),
                "legality_evidence": evidence,
            }
        )
        decision = arbitrate_pvp_action(
            defense_evaluations=[],
            attack_evaluations=[evaluated],
            neutral_expansion_candidate={"validated": world.get("expansion_validated") is True},
        )
        return {"supported": evaluated.get("battle_supported", False), **evaluated}, decision

    if operation == "defense":
        evaluated = evaluate_defense(_defense_input(world, defaults))
        evaluated["target_tower_id"] = world.get("target_tower_id", scenario["id"])
        decision = arbitrate_pvp_action(
            defense_evaluations=[evaluated],
            attack_evaluations=[],
            neutral_expansion_candidate={"validated": world.get("expansion_validated") is True},
        )
        return {"supported": evaluated.get("support_status") != "UNSUPPORTED", **evaluated}, decision

    evaluated = evaluate_battle(case)
    decision = arbitrate_pvp_action(
        defense_evaluations=[],
        attack_evaluations=[],
        neutral_expansion_candidate={"validated": world.get("expansion_validated") is True},
    )
    return evaluated, decision


def run() -> tuple[int, int, list[dict[str, Any]]]:
    catalog = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    r8_catalog = json.loads((ROOT / "GPT_BATTLE_STATIC_CASES_R8.json").read_text(encoding="utf-8"))
    r8_case_ids = {case["case_id"] for case in r8_catalog["cases"]}
    passed = 0
    failures: list[dict[str, Any]] = []
    for scenario in catalog["scenarios"]:
        missing_basis = sorted(set(scenario.get("battle_case_basis", [])) - r8_case_ids)
        if not scenario.get("battle_case_basis") or missing_basis:
            failures.append(
                {
                    "id": scenario["id"],
                    "mismatches": {"battle_case_basis": {"missing": missing_basis}},
                }
            )
            continue
        evaluated, decision = _run_one(scenario, catalog["defaults"])
        expected = scenario["expected"]
        actual: dict[str, Any] = {
            "supported": evaluated.get("supported", False),
            "action": decision.get("action"),
            "projected_result": evaluated.get("projected_result"),
            "safety_margin": evaluated.get("safety_margin"),
            "tower_lost": evaluated.get("tower_lost"),
            "rescue_candidates": len(evaluated.get("rescue_candidates", [])),
            "reinforcement_status": next(
                (row.get("status") for row in evaluated.get("reinforcement_results", [])), None
            ),
            "target_tower_id": decision.get("target_tower_id"),
        }
        mismatches = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if not mismatches:
            passed += 1
        else:
            failures.append({"id": scenario["id"], "mismatches": mismatches, "actual": actual})
    return passed, len(catalog["scenarios"]), failures


def run_round8_wrapper_cases() -> tuple[int, int, list[dict[str, Any]]]:
    """Replay all Round 8 vectors through the new gate and compare supported outputs."""
    r8_catalog = json.loads((ROOT / "GPT_BATTLE_STATIC_CASES_R8.json").read_text(encoding="utf-8"))
    passed = 0
    failures: list[dict[str, Any]] = []
    original_predict = evaluator_module.predict_battle
    mirror_calls = 0

    def counted_predict(case: dict[str, Any]) -> dict[str, Any]:
        nonlocal mirror_calls
        mirror_calls += 1
        return original_predict(case)

    evaluator_module.predict_battle = counted_predict
    special_names = {"Ruler": "ruler", "Shell": "shell", "Emp": "emp", "Nuke": "nuke"}
    for source in r8_catalog["cases"]:
        source_case = source["input"]
        relation = source_case.get("relation")
        battle_kind = (
            "force_vs_force"
            if relation == "enemy_force" or source["expected_branch"] == "force_force_ordinary_or_guard"
            else "force_vs_tower"
        )
        attacker_owner = source_case.get("attacker_owner", 1)
        defender_owner = source_case.get("defender_owner", source_case.get("tower_owner", 2))
        owner_relations = {
            "neutral": ("SELF", "NEUTRAL"),
            "enemy": ("SELF", "ENEMY"),
            "enemy_force": ("SELF", "ENEMY"),
            "friendly": ("SELF", "SELF"),
        }
        attacker_relation, defender_relation = owner_relations.get(relation, ("UNKNOWN", "UNKNOWN"))
        attacker_units = source_case.get("attacker_units", {})
        defender_units = source_case.get("defender_units", {})
        attacker_aura = source_case.get("attacker_aura")
        defender_aura = source_case.get("defender_aura")
        flags = {
            flag: bool(attacker_units.get(unit, 0) or defender_units.get(unit, 0))
            for unit, flag in special_names.items()
        }
        tower_type = source_case.get("tower_type")
        case = {
            "battle_kind": battle_kind,
            "target_branch": source_case.get("target_branch", "force_collision" if battle_kind == "force_vs_force" else "tower_combat"),
            "attacker_owner_relation": attacker_relation,
            "defender_owner_relation": defender_relation,
            "self_owner_id": attacker_owner if type(attacker_owner) is int and attacker_owner > 0 else 1,
            "attacker_owner_id": attacker_owner,
            "defender_owner_id": defender_owner,
            "attacker_units": attacker_units,
            "defender_units": defender_units,
            "tower_type": tower_type,
            "tower_capacity": CAPACITIES.get(tower_type),
            "attacker_aura_snapshot": attacker_aura,
            "defender_aura_snapshot": defender_aura,
            "shield_state": {
                "attacker": attacker_units.get("Shield", 0),
                "defender": defender_units.get("Shield", 0),
            },
            "special_unit_flags": flags,
            "ruler_aura_state": {
                "attacker": {"ruler_unit_present": False, "aura_flag_snapshot": attacker_aura},
                "defender": {"ruler_unit_present": False, "aura_flag_snapshot": defender_aura},
            },
            "world_context_required": False,
            "observed_tick": 1,
            "force_collision_confirmed": relation == "enemy_force",
            "battle_differential_validated": False,
        }
        result = evaluate_battle(case)
        expected = source["expected_result"]
        if source["support_status"] == "SUPPORTED_STATIC_SUBSET":
            mirror = result.get("static_mirror_result") or {}
            mismatches = {
                key: {"expected": expected.get(key), "actual": mirror.get(key)}
                for key in ("winner", "attacker_survivors", "defender_survivors", "new_owner", "new_owner_relation")
                if expected.get(key) != mirror.get(key)
            }
            if result.get("supported") is not True:
                mismatches["supported"] = {"expected": True, "actual": result.get("supported")}
        else:
            mismatches = {}
            if result.get("supported") is not False or result.get("winner") is not None:
                mismatches["unsupported_gate"] = {"expected": False, "actual": result.get("supported")}
        if mismatches:
            failures.append({"case_id": source["case_id"], "mismatches": mismatches})
        else:
            passed += 1
    evaluator_module.predict_battle = original_predict
    expected_calls = sum(case["support_status"] == "SUPPORTED_STATIC_SUBSET" for case in r8_catalog["cases"])
    if mirror_calls != expected_calls:
        failures.append({"case_id": "mirror_call_gate", "mismatches": {"calls": {"expected": expected_calls, "actual": mirror_calls}}})
    return passed, len(r8_catalog["cases"]), failures


if __name__ == "__main__":
    ok, total, failed = run()
    r8_ok, r8_total, r8_failed = run_round8_wrapper_cases()
    print(json.dumps({
        "planner_scenarios": {"passed": ok, "total": total, "failures": failed},
        "round8_wrapper_cases": {"passed": r8_ok, "total": r8_total, "failures": r8_failed},
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok == total and r8_ok == r8_total else 1)
