"""多威脅迴歸測試集（P0-C）。

驗證 Threat A → Battle state 1 → Threat B → Battle state 2：
每波不得從原始塔狀態獨立評估，殘兵必須帶入下一場。

涵蓋：第二波擊穿、第一波守住、削弱後到達、
同節拍 UNKNOWN、第二波 owner UNKNOWN、威脅單位未知。

只寫 fixtures／tests，不改正式邏輯（pvp_live.py 為 FOREIGN_ACTIVE）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat

SELF_ID = 7
ENEMY_ID = 12
TOWER = "Cliff"


def unit_counts(soldier: int = 0, shield: int = 0) -> dict[str, int]:
    return {
        "Shield": shield, "Fighter": 0, "Chopper": 0, "Bomber": 0,
        "Tank": 0, "Soldier": soldier, "Ruler": 0, "Shell": 0,
        "Emp": 0, "Nuke": 0,
    }


def threat(eta_ticks, soldier=1, shield=0, owner=True) -> dict:
    row: dict = {"eta_ticks": eta_ticks,
                 "units": unit_counts(soldier=soldier, shield=shield)}
    if owner:
        row["owner_id"] = ENEMY_ID
        row["owner_relation"] = "ENEMY"
    return row


def test_second_wave_breakthrough():
    """第一波守住、第二波擊穿 → UNSAFE，lost_at_index=1。"""
    defenders = unit_counts(soldier=10, shield=10)
    light = threat(5, soldier=1)
    heavy = threat(9, soldier=20)
    result = evaluate_multi_threat(defenders, [light, heavy],
                                   CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNSAFE"
    assert result["reason"] == "tower-lost"
    assert result["lost_at_index"] == 1
    assert result["eta_ticks"] == 9


def test_first_wave_held_both_safe():
    """兩波皆守住 → SAFE，且 final_defenders 反映消耗。"""
    defenders = unit_counts(soldier=10, shield=10)
    result = evaluate_multi_threat(
        defenders, [threat(5, soldier=1), threat(9, soldier=2)],
        CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "SAFE"
    assert result["reason"] == "all-threats-held"
    final = result["final_defenders"]
    assert final["Soldier"] <= 10
    assert final["Shield"] <= 10


def test_weakened_arrival_uses_battle_state_1():
    """第二波面對的是第一波後的殘兵，而非原始守軍。

    強波單獨對滿編守軍可守住；但經第一波削弱後失守，
    證明逐場攜帶而非獨立評估。
    """
    defenders = unit_counts(soldier=10, shield=10)
    first = threat(5, soldier=4)
    second = threat(9, soldier=18)
    alone = evaluate_multi_threat(defenders, [second],
                                  CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    sequential = evaluate_multi_threat(defenders, [first, second],
                                       CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert alone["result"] == "SAFE"
    assert sequential["result"] == "UNSAFE"
    assert sequential["lost_at_index"] == 1


def test_same_tick_unknown():
    """同節拍多支 → UNSUPPORTED_TEMPORAL_CASE（ABSTAIN）。"""
    defenders = unit_counts(soldier=10, shield=10)
    result = evaluate_multi_threat(
        defenders, [threat(5, soldier=1), threat(5, soldier=2)],
        CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "UNSUPPORTED_TEMPORAL_CASE"


def test_second_wave_owner_unknown():
    """第二波缺 owner_relation → threat-owner-evidence-incomplete。"""
    defenders = unit_counts(soldier=10, shield=10)
    first = threat(5, soldier=1)
    second = {"eta_ticks": 9, "units": unit_counts(soldier=1),
              "owner_id": ENEMY_ID}
    result = evaluate_multi_threat(defenders, [first, second],
                                   CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-owner-evidence-incomplete"
    assert result["resolved_before"] == 1


def test_second_wave_owner_conflicts_with_batch():
    """第二波 owner 與整批 enemy_id 矛盾 → UNKNOWN。"""
    defenders = unit_counts(soldier=10, shield=10)
    first = threat(5, soldier=1)
    second = threat(9, soldier=1)
    second["owner_id"] = 99
    result = evaluate_multi_threat(defenders, [first, second],
                                   CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-owner-conflicts-with-batch"


def test_empty_threat_units_unknown():
    """空inline威脅單位 → threat-units-unknown（不當成零傷亡）。"""
    defenders = unit_counts(soldier=10, shield=10)
    empty = {"eta_ticks": 9, "units": unit_counts()}
    result = evaluate_multi_threat(defenders, [empty],
                                   CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-units-unknown"


def test_missing_eta_unknown_not_zero():
    """缺 ETA 不得當成 0（立即到達）→ threat-eta-unknown。"""
    defenders = unit_counts(soldier=10, shield=10)
    result = evaluate_multi_threat(
        defenders, [{"units": unit_counts(soldier=1)}],
        CAPACITIES, TOWER, SELF_ID, ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-eta-unknown"


def test_distinct_enemy_ids_evaluated_with_none_batch():
    """逐列不同 ENEMY id＋batch None → 逐列採用評估，不 UNKNOWN。"""
    defenders = unit_counts(soldier=10, shield=10)
    first = threat(5, soldier=1)
    first["owner_id"] = 21
    first["owner_relation"] = "ENEMY"
    second = threat(9, soldier=2)
    second["owner_id"] = 22
    second["owner_relation"] = "ENEMY"
    result = evaluate_multi_threat(defenders, [first, second],
                                   CAPACITIES, TOWER, SELF_ID, None)
    assert result["result"] == "SAFE"
    assert result["reason"] == "all-threats-held"


def test_unknown_relation_still_fail_closed_with_none_batch():
    """relation UNKNOWN 即使有 owner_id 仍 UNKNOWN。"""
    defenders = unit_counts(soldier=10, shield=10)
    row = threat(5, soldier=1)
    row["owner_id"] = 26
    row["owner_relation"] = "UNKNOWN"
    result = evaluate_multi_threat(defenders, [row],
                                   CAPACITIES, TOWER, SELF_ID, None)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-owner-conflicts-with-batch"
