"""PvP 防守评估必须保留观察到的己方玩家编号。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat, evaluate_source_safety


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


def test_multi_threat_uses_observed_self_id_and_carries_survivors():
    defenders = unit_counts(soldier=10, shield=10)
    light = {"eta_ticks": 5, "units": unit_counts(soldier=1)}
    later = {"eta_ticks": 9, "units": unit_counts(soldier=20)}

    # The later force alone is held; after the first arrival removes one Shield,
    # the second arrival is evaluated against the remaining garrison and wins.
    alone = evaluate_multi_threat(defenders, [later], CAPACITIES, "Cliff", 7, 12)
    assert alone["result"] == "SAFE"

    result = evaluate_multi_threat(
        defenders, [later, light], CAPACITIES, "Cliff", 7, 12
    )
    assert result["result"] == "UNSAFE"
    assert result["reason"] == "tower-lost"
    assert result["lost_at_index"] == 1
    assert result["eta_ticks"] == 9


def test_source_safety_uses_observed_self_id():
    result = evaluate_source_safety(
        unit_counts(soldier=10, shield=10),
        [{"eta_ticks": 5, "units": unit_counts(soldier=2)}],
        CAPACITIES,
        "Cliff",
        self_id=7,
        enemy_id=12,
    )
    assert result == {"result": "SAFE", "reason": "all-known-threats-held"}


def test_unknown_or_conflicting_owner_ids_do_not_become_safe():
    defenders = unit_counts(soldier=10, shield=10)
    threat = [{"eta_ticks": 5, "units": unit_counts(soldier=2)}]

    unknown = evaluate_multi_threat(defenders, threat, CAPACITIES, "Cliff", None, 12)
    conflict = evaluate_multi_threat(defenders, threat, CAPACITIES, "Cliff", 7, 7)
    assert unknown["result"] == "UNKNOWN"
    assert conflict["result"] == "UNKNOWN"
