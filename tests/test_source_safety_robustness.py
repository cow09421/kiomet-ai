"""來源安全閘門健壯化回歸（P1-A 缺口）。

既有測試已覆蓋：多威脅排序、owner flip、stale、UNSUPPORTED_TEMPORAL。
本檔補強以下未覆蓋路徑：

- 威脅清單含 UNKNOWN ETA → UNKNOWN（不得假裝可評估）
- 派兵後殘留為空（全員被消耗）→ UNKNOWN（不可建案例）
- 派兵後殘留不足以阻擋已知威脅 → UNSAFE（來源失守）
- 前次行動已消耗多數兵力（reservation 衝突）→ 殘留判定須反映消耗
- 第一支守住但第二支失守 → UNSAFE 且 lost_at_index=1（殘兵帶入下一場）

所有 UNKNOWN 案例必須 ABSTAIN，不得猜值。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat, evaluate_source_safety


def unit_counts(soldier=0, shield=0, fighter=0, chopper=0, bomber=0,
                tank=0) -> dict:
    return {
        "Shield": shield, "Fighter": fighter, "Chopper": chopper,
        "Bomber": bomber, "Tank": tank, "Soldier": soldier,
        "Ruler": 0, "Shell": 0, "Emp": 0, "Nuke": 0,
    }


def threat(eta_ticks, soldier=1, shield=0, fighter=0, chopper=0, bomber=0,
           tank=0) -> dict:
    return {"eta_ticks": eta_ticks,
            "units": unit_counts(soldier=soldier, shield=shield, fighter=fighter,
                                 chopper=chopper, bomber=bomber, tank=tank)}


SELF_ID = 7
ENEMY_ID = 12
TOWER = "Cliff"


def test_unknown_eta_in_threat_list_abstains():
    result = evaluate_source_safety(
        unit_counts(soldier=10, shield=10),
        [{"eta_ticks": None, "units": unit_counts(soldier=2)}],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-eta-unknown"


def test_empty_post_dispatch_defenders_abstains():
    result = evaluate_source_safety(
        unit_counts(),
        [threat(5, soldier=2)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "case-unbuildable"


def test_source_tower_falls_after_dispatch_is_unsafe():
    result = evaluate_source_safety(
        unit_counts(soldier=2, shield=2),
        [threat(5, soldier=10)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNSAFE"
    assert result["reason"] == "SOURCE_WOULD_BECOME_UNSAFE"
    assert result["eta_ticks"] == 5


def test_reservation_conflict_reduces_defenders():
    """前次行動消耗多數兵力 → 殘留不足以阻擋已知威脅 → UNSAFE。"""
    result = evaluate_source_safety(
        unit_counts(soldier=1),
        [threat(5, soldier=6)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNSAFE"
    assert result["reason"] == "SOURCE_WOULD_BECOME_UNSAFE"


def test_multi_threat_first_holds_second_falls():
    defenders = unit_counts(soldier=10, shield=10)
    light = threat(5, soldier=1)
    heavy = threat(9, soldier=20)
    result = evaluate_multi_threat(
        defenders, [light, heavy], CAPACITIES, TOWER,
        self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNSAFE"
    assert result["lost_at_index"] == 1
    assert result["eta_ticks"] == 9


def test_multi_threat_all_held_is_safe():
    defenders = unit_counts(soldier=20, shield=20)
    result = evaluate_multi_threat(
        defenders, [threat(5, soldier=2), threat(9, soldier=3)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "SAFE"


def test_no_known_threats_is_safe():
    result = evaluate_source_safety(
        unit_counts(soldier=1),
        [],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "SAFE"
    assert result["reason"] == "no-known-threats"


def test_unknown_eta_in_multi_threat_abstains():
    result = evaluate_multi_threat(
        unit_counts(soldier=10, shield=10),
        [threat(None, soldier=2)],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNKNOWN"


def test_threat_with_special_units_abstains():
    special = unit_counts(soldier=2)
    special["Ruler"] = 1
    result = evaluate_source_safety(
        unit_counts(soldier=10, shield=10),
        [{"eta_ticks": 5, "units": special}],
        CAPACITIES, TOWER, self_id=SELF_ID, enemy_id=ENEMY_ID,
    )
    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "threat-special-units"
