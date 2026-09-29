"""Offline Round 10 PvP contract red-team audit; no game/network I/O."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from safe_battle_evaluator import CAPACITIES, evaluate_attack, evaluate_battle, evaluate_defense
from temporal_battle_simulator import build_scenarios as build_temporal_scenarios
from temporal_battle_simulator import run_static_scenarios as run_temporal_scenarios
from temporal_battle_simulator import simulate as simulate_temporal


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "GPT_PVP_RED_TEAM_MATRIX.json"
SCENARIO_SOURCE = ROOT / "GPT_PVP_PLANNER_STATIC_SCENARIOS.json"


def _base_case(
    attacker_units: dict[str, int] | None = None,
    defender_units: dict[str, int] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    attacker_units = attacker_units if attacker_units is not None else {"Soldier": 20}
    defender_units = defender_units if defender_units is not None else {"Soldier": 1}
    case: dict[str, Any] = {
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "attacker_owner_relation": "SELF",
        "defender_owner_relation": "ENEMY",
        "self_owner_id": 1,
        "attacker_owner_id": 1,
        "defender_owner_id": 2,
        "attacker_units": deepcopy(attacker_units),
        "defender_units": deepcopy(defender_units),
        "tower_type": "Town",
        "tower_capacity": CAPACITIES["Town"],
        "attacker_aura_snapshot": False,
        "defender_aura_snapshot": False,
        "shield_state": {
            "attacker": attacker_units.get("Shield", 0),
            "defender": defender_units.get("Shield", 0),
        },
        "special_unit_flags": {"ruler": False, "shell": False, "emp": False, "nuke": False},
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False, "aura_flag_snapshot": False},
            "defender": {"ruler_unit_present": False, "aura_flag_snapshot": False},
        },
        "world_context_required": False,
        "observed_tick": 1,
        "force_collision_confirmed": False,
        "battle_differential_validated": False,
    }
    case.update(overrides)
    return case


def _attack_probe(case: dict[str, Any]) -> dict[str, Any]:
    return evaluate_attack({
        "battle_case": case,
        "deployable_force": case.get("attacker_units"),
        "legality_evidence": {
            "source_is_self": True,
            "source_has_full_mobile_force": True,
            "target_is_enemy": True,
            "target_is_direct_neighbor": True,
            "path_valid": True,
            "world_fresh": True,
            "target_owner_fresh": True,
            "command_kind": "DeployForce",
            "server_acceptance_validated": True,
        },
    })


def _probe_round10_gates() -> dict[str, Any]:
    unknown = {}
    for name, mutation in {
        "units": lambda c: c.update(attacker_units=None),
        "owner": lambda c: c.update(defender_owner_id=None),
        "aura": lambda c: c.update(attacker_aura_snapshot=None),
        "shield": lambda c: c.update(shield_state={"attacker": 99, "defender": 0}),
        "tower_type": lambda c: c.update(tower_type="UnknownTower", tower_capacity=None),
    }.items():
        case = _base_case()
        mutation(case)
        result = evaluate_battle(case)
        unknown[name] = {"supported": result.get("supported"), "status": result.get("support_status"), "reason": result.get("unsupported_reason")}

    eta_result = evaluate_defense({
        "battle_case": _base_case({"Soldier": 2}, {"Soldier": 8}, attacker_owner_relation="ENEMY", defender_owner_relation="SELF", attacker_owner_id=2, defender_owner_id=1),
        "enemy_eta": 1.99,
        "incoming_path_valid": True,
        "world_fresh": True,
        "target_owner_fresh": True,
        "reinforcement_candidates": [],
    })
    same_tick_result = evaluate_defense({
        "battle_case": _base_case({"Soldier": 2}, {"Soldier": 8}, attacker_owner_relation="ENEMY", defender_owner_relation="SELF", attacker_owner_id=2, defender_owner_id=1),
        "enemy_eta": 5,
        "incoming_path_valid": True,
        "world_fresh": True,
        "target_owner_fresh": True,
        "reinforcement_candidates": [{"reinforcement_eta": 5}],
    })

    special = {}
    for key, unit in (("ruler", "Ruler"), ("shell", "Shell"), ("emp", "Emp"), ("nuke", "Nuke")):
        case = _base_case({unit: 1}, {"Soldier": 2})
        case["special_unit_flags"][key] = True
        case["attacker_units"] = {unit: 1}
        case["shield_state"]["attacker"] = 0
        case["ruler_aura_state"]["attacker"]["ruler_unit_present"] = key == "ruler"
        special[key] = evaluate_battle(case).get("support_status")

    # Use the Round 10 canonical marginal-win fixture, not a hand-built combat expectation.
    catalog = json.loads(SCENARIO_SOURCE.read_text(encoding="utf-8"))
    marginal_source = next(row for row in catalog["scenarios"] if row["id"] == "S09_marginal_enemy_attack")
    world = marginal_source["world_inputs"]
    owner_ids = {"SELF": 1, "ENEMY": 2}
    cap = CAPACITIES[world.get("tower_type", catalog["defaults"]["tower_type"])]
    units_a = world.get("attacker_units", catalog["defaults"]["attacker_units"])
    units_d = world.get("defender_units", catalog["defaults"]["defender_units"])
    case = _base_case(units_a, units_d)
    case.update({
        "battle_differential_validated": True,
        "tower_type": world.get("tower_type", catalog["defaults"]["tower_type"]),
        "tower_capacity": world.get("tower_capacity", cap),
        "attacker_aura_snapshot": world.get("attacker_aura_snapshot", False),
        "defender_aura_snapshot": world.get("defender_aura_snapshot", False),
    })
    for field in ("special_unit_flags", "ruler_aura_state", "shield_state"):
        if field in world:
            case[field] = deepcopy(world[field])
    evidence = deepcopy(world.get("legality_evidence", {}))
    marginal_result = evaluate_attack({"battle_case": case, "deployable_force": units_a, "legality_evidence": evidence})

    return {
        "unknown_fields": unknown,
        "float_eta": {"status": eta_result.get("support_status"), "reason": eta_result.get("unsupported_reason")},
        "same_tick_reinforcement": [row.get("status") for row in same_tick_result.get("reinforcement_results", [])],
        "special_units": special,
        "marginal_attack": {"safety_margin": marginal_result.get("safety_margin"), "safe_attack_candidate": marginal_result.get("safe_attack_candidate"), "result": marginal_result.get("result")},
    }


CATEGORIES: list[dict[str, Any]] = [
    {"category": "STALE_WORLD（過期世界）", "severity": "CRITICAL", "pass": False, "cases": ["目標由 ENEMY 變為 SELF", "世界快照在計畫後改變", "新入站敵軍在派送前出現"], "actual": "Round 10 checks freshness during evaluation; there is no dispatch-time version token to recheck it.", "fix": "Dispatch-time Action Validity Token and full threat refresh."},
    {"category": "STALE_SOURCE（過期來源）", "severity": "CRITICAL", "pass": False, "cases": ["來源兵力被另一行動花掉", "來源遭敵軍攻擊後兵力下降", "來源 owner 在派送前改變"], "actual": "Exact deployable force is checked at planning time only; no source-state version or atomic reservation exists in the Round 10 interface.", "fix": "Re-read source owner, units, threats and source_state_version at dispatch."},
    {"category": "DOUBLE_SPEND（雙重花費）", "severity": "CRITICAL", "pass": False, "cases": ["Defense and Attack choose the same source", "two planners reserve the same force", "two same-cycle proposals spend overlapping units"], "actual": "The arbitrator selects one candidate per invocation but has no shared atomic source reservation across proposals or cycles.", "fix": "Single-writer arbitrator; atomically reserve by source_state_version and invalidate siblings."},
    {"category": "VERIFY-IN-FLIGHT（驗證尚未完成）", "severity": "HIGH", "pass": False, "cases": ["前一命令仍 VERIFYING", "下一 cycle 重送同一提案", "驗證逾時後忙迴圈重試"], "actual": "The Round 10 battle evaluator has no in-flight execution lock, idempotency key or retry state contract.", "fix": "Lock proposal/source/target until verification completes; require explicit terminal result before retry."},
    {"category": "SAME TARGET DOUBLE ACTION（同目標重複行動）", "severity": "CRITICAL", "pass": False, "cases": ["兩個 Threat 同一 cycle 救同一塔", "攻擊與增援同時選同一目標", "驗證重播再次點擊相同目標"], "actual": "Arbitration is deterministic inside one call but does not deduplicate or lock independent dispatches to the same target.", "fix": "Target/action reservation and idempotent dispatch token."},
    {"category": "DEFENSE CREATES NEW LOSS（防守導致新失塔）", "severity": "CRITICAL", "pass": False, "cases": ["A 派援救 B 後 A 被已知敵軍攻下", "援軍抽走 A 最後防守兵", "同 cycle 兩次抽走同一來源"], "actual": "DefenseEvaluator scores the threatened target; it does not evaluate the source tower after dispatch.", "fix": "Run Source Safety Gate over the exact post-dispatch force and every known incoming threat."},
    {"category": "ATTACK CREATES HOME WEAKNESS（攻擊造成來源空虛）", "severity": "CRITICAL", "pass": False, "cases": ["A 對 B 為 ROBUST_WIN 但 A 隨即失守", "A 派出全部普通兵後守不住入站敵軍", "攻擊改變 A 的光環／防守快照"], "actual": "AttackEvaluator classifies target battle margin but does not replay known threats against the post-attack source state.", "fix": "Source Safety Gate must run for ATTACK_ENEMY too."},
    {"category": "SECOND ENEMY FORCE（第二支敵軍）", "severity": "HIGH", "pass": False, "cases": ["第二支敵軍晚 1 tick 到達", "第一場守住但第二場攻下", "同目標兩支敵軍同 tick 且順序未知"], "actual": "DefenseEvaluator evaluates one supplied incoming Force; arbitration does not build a sequential same-target tower-state chain.", "fix": "Multi-Threat Defense: sort and simulate each known Force against prior writeback."},
    {"category": "SECOND REINFORCEMENT（第二支援軍）", "severity": "HIGH", "pass": False, "cases": ["兩支援軍各自看似救得住但合併容量未知", "援軍與敵軍同 tick", "兩援軍同 tick 順序改變可派兵結果"], "actual": "One equal-ETA candidate is rejected safely, but multiple candidates are not jointly sequenced or merged by exact collection order.", "fix": "ABSTAIN on unresolved same-tick order; otherwise evaluate each exact intermediate merge state and source safety."},
    {"category": "OWNER FLIP（塔主切換）", "severity": "CRITICAL", "pass": False, "cases": ["Target owner changes after plan", "first same-tick Force captures before second arrives", "neutral capture changes second Force to hostile"], "actual": "Planning checks target owner freshness but has no dispatch-time token; one-force evaluator cannot re-read owner across same-tick arrivals.", "fix": "Re-read owner per event and reject stale token; preserve sequential event ordering."},
    {"category": "AURA CHANGE（光環改變）", "severity": "HIGH", "pass": False, "cases": ["Tower+45 snapshot changes", "Force+21 snapshot changes", "Ruler loss changes aura before dispatch"], "actual": "Aura is explicit at evaluation, but no aura/source/target version token is rechecked at dispatch.", "fix": "Bind aura snapshots to source_state_version/target_state_version and invalidate on change."},
    {"category": "UNKNOWN BECOMES ZERO（未知值變成零）", "severity": "HIGH", "pass": True, "cases": ["units missing/null", "owner missing or inconsistent", "aura/shield/tower type/ETA unknown"], "actual": "SafeBattleEvaluator strictly validates the supplied fields; incomplete or conflicting inputs are rejected rather than filled with zero.", "fix": "Keep strict validation and add equivalent strictness to temporal, source-safety and dispatch interfaces."},
    {"category": "MARGINAL WIN（邊際勝利）", "severity": "MEDIUM", "pass": True, "cases": ["one survivor at threshold", "equal to marginal_survivor_max", "marginal threshold missing/invalid"], "actual": "AttackEvaluator labels the threshold case MARGINAL_WIN and does not set safe_attack_candidate; invalid thresholds are rejected.", "fix": "Keep ROBUST_WIN as a policy gate and test it with actual supported differential cases."},
    {"category": "TIME QUANTIZATION（時間量化）", "severity": "HIGH", "pass": True, "cases": ["ETA 1.99 seconds", "ETA 2.01 seconds", "seconds straddle one server tick"], "actual": "DefenseEvaluator requires nonnegative integer ETA; a float ETA is rejected. This prevents accidental float ordering inside that API, but caller-side conversion still needs the interval rule.", "fix": "Require integer arrival ticks; when only seconds exist, use conservative tick intervals and ABSTAIN on overlap."},
    {"category": "MATCH TRANSITION（對局切換）", "severity": "CRITICAL", "pass": False, "cases": ["match_id changes between plan and execute", "old proposal survives result screen", "new match reuses tower IDs"], "actual": "Round 10 proposal inputs contain no match_id or dispatch token.", "fix": "Bind match_id and cycle_id in Action Validity Token."},
    {"category": "CAMERA / COORDINATE STALE（鏡頭／座標過期）", "severity": "HIGH", "pass": False, "cases": ["camera pans after world snapshot", "screen_xy from old zoom", "world fresh but coordinate transform stale"], "actual": "Round 10 validates static path/command facts but does not bind camera_version to the proposal or revalidate screen coordinates at dispatch.", "fix": "Bind camera_version; refresh coordinate transform and reject stale pointer coordinates."},
    {"category": "RULER INVOLVEMENT（國王參戰）", "severity": "CRITICAL", "pass": True, "cases": ["Ruler in attacker composition", "Ruler in defender composition", "Ruler loss can trigger player elimination"], "actual": "Round 10 SafeBattleEvaluator marks Ruler/global player state outside support and rejects the case.", "fix": "Keep Ruler cases unsupported until their global event chain is separately validated."},
    {"category": "SPECIAL UNIT HIDDEN IN COMPOSITION（兵種中藏有特殊單位）", "severity": "CRITICAL", "pass": True, "cases": ["Shell count > 0", "EMP count > 0", "Nuke count > 0"], "actual": "The battle gate rejects special-unit flags and compositions; they do not become ordinary forces by adding more Soldiers.", "fix": "Keep all special-unit cases unsupported."},
    {"category": "CAPACITY EDGE（容量邊界）", "severity": "HIGH", "pass": False, "cases": ["reinforcement exceeds target capacity", "tower type changed after merge snapshot", "neutral capture reconcile alters units"], "actual": "The evaluator refuses to infer merge, but it trusts caller-supplied post_merge_snapshot_exact without a versioned capacity/merge proof.", "fix": "Require exact merge evidence tied to target_state_version and validate each intermediate capacity result."},
    {"category": "ACTION COOLDOWN LOOP（行動冷卻忙迴圈）", "severity": "MEDIUM", "pass": False, "cases": ["cooldown blocks same proposal every cycle", "retry after timeout has no terminal verification", "planner emits identical action continuously"], "actual": "Round 10 arbitration has no cooldown state, retry budget, in-flight lock or terminal verification contract.", "fix": "Track proposal ID, attempt state, cooldown expiry and explicit verification outcome."},
]


def _scenario_rows(probes: dict[str, Any], temporal_probe: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_index, group in enumerate(CATEGORIES):
        for variant_index, variant in enumerate(group["cases"], start=1):
            scenario_id = f"RT{group_index + 1:02d}_{variant_index:02d}"
            actual = group["actual"]
            observed: dict[str, Any] | None = None
            if group["category"].startswith("UNKNOWN"):
                key = ("units", "owner", "aura", "shield", "tower_type")[(variant_index - 1) % 5]
                observed = probes["unknown_fields"].get(key)
            elif group["category"].startswith("TIME QUANTIZATION"):
                observed = probes["float_eta"]
            elif group["category"].startswith("SECOND REINFORCEMENT") and variant_index == 2:
                observed = {"reinforcement_status": probes["same_tick_reinforcement"]}
            elif group["category"].startswith("RULER"):
                observed = {"Ruler_gate": probes["special_units"].get("ruler")}
            elif group["category"].startswith("SPECIAL UNIT"):
                key = ("shell", "emp", "nuke")[(variant_index - 1) % 3]
                observed = {f"{key}_gate": probes["special_units"].get(key)}
            elif group["category"].startswith("MARGINAL WIN"):
                observed = probes["marginal_attack"]
            elif group["category"].startswith(("SECOND ENEMY", "SECOND REINFORCEMENT", "OWNER FLIP")):
                observed = {"round10_evaluator": probes.get("same_tick_reinforcement"), "temporal_order_model": temporal_probe.get("same_tick_order")}
            rows.append({
                "scenario_id": scenario_id,
                "category": group["category"],
                "world_state": {
                    "variant": variant,
                    "plan_state": "Round 10 evaluation snapshot",
                    "dispatch_state": "adversarial mutation described by variant",
                    "runtime_or_browser_used": False,
                },
                "expected_safe_behavior": "Reject stale/unknown/unsafe proposal; otherwise allow only a fully validated single action.",
                "actual_contract_behavior": actual,
                "pass_fail": "PASS" if group["pass"] else "FAIL",
                "severity": group["severity"],
                "required_fix": group["fix"],
                "observed_evaluator_probe": observed,
                "baseline": "ROUND10_CONTRACT_STATIC_AUDIT; FAIL means the documented Round 10 interface cannot guarantee the expected safety behavior.",
            })
    return rows


def build_matrix() -> dict[str, Any]:
    probes = _probe_round10_gates()
    temporal_passed, temporal_total, temporal_failures = run_temporal_scenarios()
    temporal_cases = build_temporal_scenarios()
    order_scenario = next(row for row in temporal_cases if row["scenario_id"] == "T07_reinforcement_first")
    temporal_probe = {
        "scenario_count": temporal_total,
        "passed": temporal_passed,
        "failures": temporal_failures,
        "same_tick_order": simulate_temporal(deepcopy(order_scenario["case"])),
        "scope": "server-reference ordering only; the supplied battle effects are static fixtures, not validated combat predictions",
    }
    rows = _scenario_rows(probes, temporal_probe)
    counts = {key: sum(row["pass_fail"] == key for row in rows) for key in ("PASS", "FAIL")}
    severity_counts = {level: sum(row["severity"] == level for row in rows) for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    severity_failures = {
        level: sum(row["severity"] == level and row["pass_fail"] == "FAIL" for row in rows)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }
    return {
        "artifact": "GPT Round 11 PvP Red-Team Matrix（第十一輪 PvP 紅隊矩陣）",
        "audit_target": "Round 10 SafeBattleEvaluator and planner contracts",
        "scope": "OFFLINE_STATIC_ONLY（僅離線靜態分析）",
        "scenario_count": len(rows),
        "summary": {"PASS": counts["PASS"], "FAIL": counts["FAIL"], **severity_counts},
        "severity_failures": severity_failures,
        "pass_fail_semantics": "PASS means the documented Round 10 contract enforces the expected safety behavior. FAIL identifies a contract gap; it is not a claim that a live game action occurred.",
        "round10_evaluator_probes": probes,
        "temporal_model_probe": temporal_probe,
        "scenarios": rows,
    }


def main() -> int:
    matrix = build_matrix()
    OUTPUT.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"scenario_count": matrix["scenario_count"], **matrix["summary"], "output": str(OUTPUT)}
    probes = matrix["round10_evaluator_probes"]
    probe_checks = {
        "unknown fields fail closed": all(row.get("supported") is False for row in probes["unknown_fields"].values()),
        "float ETA fails closed": probes["float_eta"].get("status") == "UNSUPPORTED",
        "same-tick reinforcement is rejected": "UNSUPPORTED" in probes["same_tick_reinforcement"],
        "special units are rejected": all(value == "UNSUPPORTED" for value in probes["special_units"].values()),
        "marginal attack is not safe": probes["marginal_attack"].get("safety_margin") == "MARGINAL_WIN" and probes["marginal_attack"].get("safe_attack_candidate") is False,
        "temporal ordering suite passes": matrix["temporal_model_probe"]["passed"] == matrix["temporal_model_probe"]["scenario_count"] == 36,
        "minimum adversarial count met": matrix["scenario_count"] >= 50,
    }
    summary["probe_checks"] = probe_checks
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(probe_checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
