"""PvP 安全評估器測試：閘門優先、拒絕語意、仲裁順序、確定性。

測正式層 kiomet_ai.pvp（由 GPT Round 10 移植），不測研究目錄。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import TowerUnitCounts
from kiomet_ai.pvp import (
    arbitrate_pvp_action,
    evaluate_attack,
    evaluate_battle,
    evaluate_defense,
)
from kiomet_ai.pvp_live import battle_case_for_tower_attack


def base_case(**over):
    case = {
        "world_context_required": False,
        "observed_tick": 10,
        "attacker_units": {"Fighter": 4, "Soldier": 4, "Shield": 0},
        "defender_units": {"Soldier": 2, "Shield": 10},
        "special_unit_flags": {"ruler": False, "shell": False,
                               "emp": False, "nuke": False},
        "attacker_owner_relation": "SELF",
        "defender_owner_relation": "NEUTRAL",
        "self_owner_id": 7,
        "attacker_aura_snapshot": False,
        "defender_aura_snapshot": False,
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False, "aura_flag_snapshot": False},
            "defender": {"ruler_unit_present": False, "aura_flag_snapshot": False},
        },
        "shield_state": {"attacker": 0, "defender": 10},
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "tower_type": "Cliff",
        "tower_capacity": dict(CAPACITIES["Cliff"]),
        "attacker_owner_id": 7,
        "defender_owner_id": None,
    }
    case.update(over)
    return case


def test_supported_many_vs_neutral():
    result = evaluate_battle(base_case())
    assert result["supported"] is True
    assert result["evaluation_status"] in ("SUPPORTED", "UNKNOWN")
    assert "winner" in result and result["winner"] in ("attacker", "defender", "contested")
    assert "win_probability" not in result
    assert "probability" not in str(result)


def test_special_unit_rejection():
    case = base_case()
    case["special_unit_flags"] = {"ruler": True, "shell": False,
                                  "emp": False, "nuke": False}
    result = evaluate_battle(case)
    assert result["supported"] is False


def test_unknown_owner_rejection():
    case = base_case()
    case["attacker_owner_relation"] = "UNKNOWN"
    result = evaluate_battle(case)
    assert result["supported"] is False


def test_unknown_aura_rejection():
    case = base_case()
    case["attacker_aura_snapshot"] = None
    result = evaluate_battle(case)
    assert result["supported"] is False


def test_empty_attacker_rejection():
    case = base_case()
    case["attacker_units"] = {"Fighter": 0, "Soldier": 0, "Shield": 0}
    result = evaluate_battle(case)
    assert result["supported"] is False


def test_defense_requires_eta():
    result = evaluate_defense({"battle_case": base_case()})
    assert result["support_status"] == "UNSUPPORTED"
    assert "ETA" in result["unsupported_reason"]


def test_arbitration_defense_priority():
    defense_loss = {"support_status": "SUPPORTED", "tower_lost": True,
                    "enemy_eta": 5, "target_tower_id": 9,
                    "minimum_sufficient_reinforcement": None,
                    "reinforcement_command_validated": False}
    attack = {"safe_attack_candidate": True, "target_tower_id": 3,
              "source_tower_id": 1}
    result = arbitrate_pvp_action(
        defense_evaluations=[defense_loss],
        attack_evaluations=[attack],
        neutral_expansion_candidate=None)
    # 有損失但無驗證救援 → ABSTAIN（不亂派）
    assert result["action"] == "ABSTAIN"


def test_arbitration_attack_over_neutral():
    attack = {"safe_attack_candidate": True, "target_tower_id": 3,
              "source_tower_id": 1}
    neutral = {"validated": True}
    result = arbitrate_pvp_action(
        defense_evaluations=[],
        attack_evaluations=[attack],
        neutral_expansion_candidate=neutral)
    assert result["action"] == "ATTACK_ENEMY"


def test_arbitration_neutral_fallback():
    neutral = {"validated": True}
    result = arbitrate_pvp_action(
        defense_evaluations=[],
        attack_evaluations=[{"safe_attack_candidate": False}],
        neutral_expansion_candidate=neutral)
    assert result["action"] == "EXPAND_NEUTRAL"


def test_arbitration_deterministic():
    attack = {"safe_attack_candidate": True, "target_tower_id": 3,
              "source_tower_id": 1}
    first = arbitrate_pvp_action(
        defense_evaluations=[], attack_evaluations=[attack],
        neutral_expansion_candidate=None)
    second = arbitrate_pvp_action(
        defense_evaluations=[], attack_evaluations=[attack],
        neutral_expansion_candidate=None)
    assert first == second
    assert first["action"] == "ATTACK_ENEMY"


def test_attack_requires_robust_win():
    data = {"legality_evidence": {
        "source_is_self": True, "source_has_full_mobile_force": True,
        "target_is_enemy": True, "target_is_direct_neighbor": True,
        "path_valid": True, "world_fresh": True, "target_owner_fresh": True,
        "command_kind": "DeployForce"},
        "deployable_force": {"Fighter": 4, "Soldier": 4},
        "battle_case": None}
    result = evaluate_attack(data)
    # battle_case 缺失 → 不支援（不猜）
    assert result["safe_attack_candidate"] is False


def _many_units(*, soldier=0, shield=0):
    return TowerUnitCounts(
        units_kind="MANY", fighter=0, chopper=0, bomber=0, tank=0,
        soldier=soldier, shield=shield)


def _evaluate_live_attack_case(*, attacker_shield=0, runtime_proofs=True):
    source = SimpleNamespace(
        owner="SELF", unit_counts=_many_units(soldier=20),
        deployable_force=SimpleNamespace(counts={
            "Shield": attacker_shield, "Fighter": 0, "Chopper": 0,
            "Bomber": 0, "Tank": 0, "Soldier": 20, "Shell": 0,
            "Emp": 0, "Nuke": 0, "Ruler": 0,
        }))
    target = SimpleNamespace(
        owner="ENEMY", unit_counts=_many_units(soldier=1),
        tower_type="Cliff")
    case = battle_case_for_tower_attack(
        source, target, 7, 7, 12, False, False, CAPACITIES)
    assert case is not None
    case["battle_differential_validated"] = runtime_proofs
    return evaluate_attack({
        "legality_evidence": {
            "source_is_self": True,
            "source_has_full_mobile_force": True,
            "target_is_enemy": True,
            "target_is_direct_neighbor": True,
            "path_valid": True,
            "world_fresh": True,
            "target_owner_fresh": True,
            "command_kind": "DeployForce",
            "server_acceptance_validated": runtime_proofs,
        },
        "deployable_force": {"Soldier": 20},
        "battle_case": case,
    })


def test_live_attack_battle_case_accepts_exact_zero_filled_mobile_vector():
    result = _evaluate_live_attack_case()

    assert result["battle_supported"] is True
    assert result["result"] == "ATTACK_WIN"
    assert result["safe_attack_candidate"] is True


def test_first_attack_uses_static_prediction_then_keeps_runtime_proof_pending():
    result = _evaluate_live_attack_case(runtime_proofs=False)

    assert result["result"] == "ATTACK_WIN"
    assert result["static_support_status"] == "SUPPORTED"
    assert result["safe_attack_candidate"] is False
    assert result["dispatch_safe_candidate"] is True
    assert result["runtime_validation_required"] is True

    decision = arbitrate_pvp_action(
        defense_evaluations=[], attack_evaluations=[result],
        neutral_expansion_candidate=None)
    assert decision["action"] == "ATTACK_ENEMY"
    assert decision["evaluation_status"] == "SUPPORTED_STATIC"
    assert decision["runtime_validation_required"] is True


def test_live_attack_rejects_nonmobile_shield_outside_deployable_force():
    result = _evaluate_live_attack_case(attacker_shield=1)

    assert result["safe_attack_candidate"] is False
    assert result["unsupported_reason"] == (
        "battle input does not match the exact full deployable force")
