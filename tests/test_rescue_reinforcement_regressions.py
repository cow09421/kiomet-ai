"""救援／增援管線回歸：evaluate_defense 候選管線與 arbitrate REINFORCE_SELF。

Round 10/11 靜態評估器已存在，但下列路徑在本測試前為零覆蓋：
- REINFORCEMENT_TOO_LATE、same-tick order unsupported
- post-merge snapshot 不精確／改動情境／缺合成資料
- RESCUE_CANDIDATE 的 command_validated 分流與 minimum 選擇
- arbitrate_pvp_action 的 REINFORCE_SELF 與未驗證救援 ABSTAIN

成功證據：上述每個狀態位元都由明確輸入觸發且斷言值不變。
失敗證據：任一路徑回 None／錯狀態／未驗證救援被放行。
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp import arbitrate_pvp_action, evaluate_defense
from kiomet_ai.pvp_live import _defense_case


def unit_counts(soldier: int = 0, shield: int = 0) -> dict[str, int]:
    return {
        "Shield": shield,
        "Fighter": 0,
        "Chopper": 0,
        "Bomber": 0,
        "Tank": 0,
        "Soldier": soldier,
        "Ruler": 0,
        "Shell": 0,
        "Emp": 0,
        "Nuke": 0,
    }


def base_data() -> dict:
    case = _defense_case(
        unit_counts(soldier=10, shield=10),
        unit_counts(soldier=3),
        "Cliff", CAPACITIES, self_id=7, enemy_id=12,
    )
    assert case is not None
    case["battle_differential_validated"] = True
    return {
        "enemy_eta": 10,
        "incoming_path_valid": True,
        "world_fresh": True,
        "target_owner_fresh": True,
        "battle_case": case,
    }


def merged_snapshot(defender: dict) -> dict:
    snap = copy.deepcopy(base_data()["battle_case"])
    snap["defender_units"] = dict(defender)
    snap["shield_state"] = {"attacker": 0, "defender": defender["Shield"]}
    return snap


def candidate(eta: int, snap: dict | None, *, source: int = 42,
              force: dict | None = None, evidence: dict | None = None,
              exact: bool = True) -> dict:
    legal = {
        "source_is_self": True,
        "source_has_full_mobile_force": True,
        "target_is_self": True,
        "path_valid": True,
        "world_fresh": True,
        "target_owner_fresh": True,
        "command_kind": "DeployForce",
        "server_acceptance_validated": True,
    }
    if evidence is not None:
        legal = evidence
    return {
        "reinforcement_eta": eta,
        "post_merge_snapshot_exact": exact,
        "post_merge_battle_case": snap,
        "source_tower_id": source,
        "full_deployable_force": force if force is not None
        else {"Soldier": 5},
        "legality_evidence": legal,
    }


def with_candidates(*candidates) -> dict:
    data = base_data()
    data["reinforcement_candidates"] = list(candidates)
    return data


def test_reinforcement_arriving_after_enemy_is_too_late():
    result = evaluate_defense(with_candidates(
        candidate(15, merged_snapshot(unit_counts(soldier=20, shield=20))),
    ))
    row = result["reinforcement_results"][0]
    assert row["status"] == "REINFORCEMENT_TOO_LATE"
    assert row["enemy_eta"] == 10
    assert result["rescue_candidates"] == []
    assert result["minimum_sufficient_reinforcement"] is None
    assert result["reinforcement_command_validated"] is False


def test_same_tick_reinforcement_order_is_unsupported():
    result = evaluate_defense(with_candidates(
        candidate(10, merged_snapshot(unit_counts(soldier=20, shield=20))),
    ))
    row = result["reinforcement_results"][0]
    assert row["status"] == "UNSUPPORTED"
    assert row["reason"] == "same-tick order is not validated"
    assert result["rescue_candidates"] == []


def test_unknown_eta_and_non_list_candidates_fail_closed():
    unknown_eta = evaluate_defense(with_candidates(candidate(None, None)))
    assert unknown_eta["reinforcement_results"][0] == {
        "status": "UNSUPPORTED",
        "reason": "reinforcement ETA unknown",
    }

    bad_list = base_data()
    bad_list["reinforcement_candidates"] = {"Soldier": 5}
    result = evaluate_defense(bad_list)
    assert result["support_status"] == "UNSUPPORTED"
    assert result["evaluation_status"] == "UNSUPPORTED"


def test_non_exact_snapshot_is_not_inferred():
    snap = merged_snapshot(unit_counts(soldier=20, shield=20))
    inexact = evaluate_defense(with_candidates(candidate(4, snap, exact=False)))
    assert inexact["reinforcement_results"][0]["reason"] == (
        "friendly merge is not inferred; exact post-merge state is required"
    )

    missing = evaluate_defense(with_candidates(candidate(4, None)))
    assert missing["reinforcement_results"][0]["status"] == "UNSUPPORTED"
    assert missing["rescue_candidates"] == []


def test_snapshot_changing_context_or_missing_composition_is_rejected():
    altered = merged_snapshot(unit_counts(soldier=20, shield=20))
    altered["attacker_units"] = unit_counts(soldier=9)
    changed = evaluate_defense(with_candidates(candidate(4, altered)))
    assert changed["reinforcement_results"][0]["reason"] == (
        "post-merge snapshot changed the incoming force or target context"
    )

    hollow = merged_snapshot(unit_counts(soldier=20, shield=20))
    hollow["defender_units"] = None
    hollow["shield_state"] = {"attacker": 0, "defender": 0}
    missing = evaluate_defense(with_candidates(candidate(4, hollow)))
    assert missing["reinforcement_results"][0]["reason"] == (
        "post-merge defender composition is missing"
    )


def test_rescue_candidate_without_command_evidence_flags_runtime():
    result = evaluate_defense(with_candidates(candidate(
        4, merged_snapshot(unit_counts(soldier=20, shield=20)),
        evidence={
            "source_is_self": True,
            "source_has_full_mobile_force": True,
            "target_is_self": True,
            "path_valid": True,
            "world_fresh": True,
            "target_owner_fresh": True,
            "command_kind": "DeployForce",
            "server_acceptance_validated": False,
        },
    )))
    row = result["rescue_candidates"][0]
    assert row["status"] == "RESCUE_CANDIDATE"
    assert row["command_validated"] is False
    assert result["reinforcement_command_validated"] is False
    assert result["rescue_requirement_status"] == (
        "SUPPORTED_STATIC_CANDIDATE_COMPARISON"
    )
    assert result["minimum_sufficient_reinforcement"]["command_validated"] is False
    assert result["runtime_validation_required"] is True


def test_validated_rescues_select_minimum_unit_count():
    snap = merged_snapshot(unit_counts(soldier=20, shield=20))
    small = candidate(4, snap, source=42, force={"Soldier": 5})
    large = candidate(6, snap, source=7,
                      force={"Soldier": 9, "Tank": 2})
    result = evaluate_defense(with_candidates(large, small))
    assert result["reinforcement_command_validated"] is True
    chosen = result["minimum_sufficient_reinforcement"]
    assert chosen["source_tower_id"] == 42
    assert chosen["unit_count"] == 5
    assert chosen["command_validated"] is True
    assert all(r["status"] == "RESCUE_CANDIDATE"
               for r in result["rescue_candidates"])
    assert result["runtime_validation_required"] is False


def test_arbitration_returns_reinforce_self_for_validated_rescue():
    outcome = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "SUPPORTED",
            "tower_lost": True,
            "enemy_eta": 5,
            "target_tower_id": 9,
            "minimum_sufficient_reinforcement": {
                "source_tower_id": 42, "unit_count": 5,
                "command_validated": True,
            },
            "reinforcement_command_validated": True,
        }],
        attack_evaluations=[],
        neutral_expansion_candidate=None,
    )
    assert outcome["action"] == "REINFORCE_SELF"
    assert outcome["evaluation_status"] == "SUPPORTED"
    assert outcome["target_tower_id"] == 9
    assert "ABSTAIN" not in outcome["state_trace"]


def test_arbitration_abstains_when_rescue_not_validated():
    candidate_row = {"source_tower_id": 42, "unit_count": 5,
                     "command_validated": False}
    unvalidated_flag = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "SUPPORTED", "tower_lost": True,
            "enemy_eta": 5, "target_tower_id": 9,
            "minimum_sufficient_reinforcement": candidate_row,
            "reinforcement_command_validated": False,
        }],
        attack_evaluations=[], neutral_expansion_candidate=None,
    )
    assert unvalidated_flag["action"] == "ABSTAIN"
    assert unvalidated_flag["reason"] == (
        "projected loss has no validated timely rescue command"
    )

    unvalidated_candidate = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "SUPPORTED", "tower_lost": True,
            "enemy_eta": 5, "target_tower_id": 9,
            "minimum_sufficient_reinforcement": candidate_row,
            "reinforcement_command_validated": True,
        }],
        attack_evaluations=[], neutral_expansion_candidate=None,
    )
    assert unvalidated_candidate["action"] == "ABSTAIN"


def test_arbitration_unresolved_threat_abstains_with_unknown_status():
    outcome = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "RUNTIME_VALIDATION_NEEDED",
            "tower_lost": None,
            "enemy_eta": 8,
            "target_tower_id": 9,
        }],
        attack_evaluations=[{"support_status": "SUPPORTED"}],
        neutral_expansion_candidate={"target_tower_id": 3},
    )
    assert outcome["action"] == "ABSTAIN"
    assert outcome["evaluation_status"] == "UNKNOWN"
    assert outcome["state_trace"][-1] == "ABSTAIN"
    assert "SELECT_ACTION" in outcome["state_trace"]
