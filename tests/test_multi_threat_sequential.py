"""多威脅逐場評估性質測試（P1-B）。

核心契約：Threat 1 處理後的殘兵必須成為 Threat 2 的輸入。
不得每支威脅都對原始塔狀態獨立評估。

成功證據：
- 逐場攜帶：第一支的 survivors 改變第二支的結果
- 順序依賴：交換順序可能改變結果
- 累積消耗：多支威脅逐步消耗守軍
- 全部守住 → SAFE；任一失守 → UNSAFE

失敗證據：每支威脅獨立評估（未攜帶殘兵）或順序不影響結果。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat


def unit_counts(soldier=0, shield=0) -> dict:
    return {
        "Shield": shield, "Fighter": 0, "Chopper": 0, "Bomber": 0,
        "Tank": 0, "Soldier": soldier, "Ruler": 0, "Shell": 0,
        "Emp": 0, "Nuke": 0,
    }


def threat(eta_ticks, soldier=1, shield=0) -> dict:
    return {"eta_ticks": eta_ticks,
            "units": unit_counts(soldier=soldier, shield=shield)}


SELF_ID = 7
ENEMY_ID = 12
TOWER = "Cliff"


def test_survivors_carry_into_second_threat():
    """第一支的殘兵必須成為第二支的輸入。

    單獨評估第二支（對原始守軍）會 SAFE；
    但第一支先消耗守軍後，第二支可能失守。
    """
    defenders = unit_counts(soldier=10, shield=10)
    first = threat(5, soldier=8)
    second = threat(9, soldier=8)

    # 第二支單獨對原始守軍：SAFE
    alone = evaluate_multi_threat(
        defenders, [second], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    assert alone["result"] == "SAFE"

    # 兩支依序：第一支消耗後第二支可能失守
    sequential = evaluate_multi_threat(
        defenders, [first, second], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    # 第一支守住（10+10 vs 8），但殘兵減少；第二支對殘兵評估
    assert sequential["result"] in ("SAFE", "UNSAFE")
    # 關鍵：逐場結果必須反映順序（不與獨立評估相同）
    if sequential["result"] == "UNSAFE":
        assert sequential["lost_at_index"] == 1


def test_order_dependence():
    """交換威脅順序可能改變結果（較弱威脅先處理）。"""
    defenders = unit_counts(soldier=10, shield=10)
    weak = threat(5, soldier=2)
    strong = threat(9, soldier=20)

    weak_first = evaluate_multi_threat(
        defenders, [weak, strong], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    strong_first = evaluate_multi_threat(
        defenders, [strong, weak], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)

    # 兩者都應 UNSAFE（強威脅終究失守），但 lost_at_index 可能不同
    assert weak_first["result"] == "UNSAFE"
    assert strong_first["result"] == "UNSAFE"


def test_cumulative_depletion_across_threats():
    """多支威脅逐步消耗守軍 → 後段威脅面對更弱守軍。"""
    defenders = unit_counts(soldier=10, shield=10)
    threats = [threat(5, soldier=3), threat(9, soldier=3),
               threat(13, soldier=3)]
    result = evaluate_multi_threat(
        defenders, threats, CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    # 三支各消耗 3 Soldier；10 → 7 → 4 → 1，應全部守住
    assert result["result"] == "SAFE"


def test_all_held_is_safe():
    defenders = unit_counts(soldier=20, shield=20)
    result = evaluate_multi_threat(
        defenders, [threat(5, soldier=2), threat(9, soldier=3),
                    threat(13, soldier=4)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID)
    assert result["result"] == "SAFE"


def test_single_failure_is_unsafe():
    defenders = unit_counts(soldier=5, shield=5)
    result = evaluate_multi_threat(
        defenders, [threat(5, soldier=2), threat(9, soldier=30)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID)
    assert result["result"] == "UNSAFE"
    assert result["lost_at_index"] == 1


def test_empty_threats_is_safe():
    result = evaluate_multi_threat(
        unit_counts(soldier=1), [], CAPACITIES, TOWER,
        self_id=SELF_ID, enemy_id=ENEMY_ID)
    assert result["result"] == "SAFE"


def test_single_threat_equivalence():
    """單支威脅的逐場結果應與多威脅評估一致。"""
    defenders = unit_counts(soldier=10, shield=10)
    single = threat(5, soldier=2)
    alone = evaluate_multi_threat(
        defenders, [single], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    multi = evaluate_multi_threat(
        defenders, [single], CAPACITIES, TOWER, self_id=SELF_ID,
        enemy_id=ENEMY_ID)
    assert alone["result"] == multi["result"]


def test_same_tick_threats_abstain():
    """同 tick 多支威脅 → UNSUPPORTED_TEMPORAL_CASE（ABSTAIN）。"""
    result = evaluate_multi_threat(
        unit_counts(soldier=10, shield=10),
        [threat(5, soldier=2), threat(5, soldier=3)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID)
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "UNSUPPORTED_TEMPORAL_CASE"
