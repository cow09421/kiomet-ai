"""安全評估不可把錯誤兵力資料默認為 0 或轉成整數。"""
import sys
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    "incoming",
    [
        {"Soldier": True},
        {"Soldier": 2, "Unknown": 50},
        {"Soldier": -1},
        {"Soldier": 256},
        {"Soldier": "2"},
    ],
)
def test_malformed_incoming_vector_never_becomes_safe(incoming):
    result = evaluate_multi_threat(
        unit_counts(soldier=10, shield=10),
        [{"eta_ticks": 5, "units": incoming}],
        CAPACITIES,
        "Cliff",
        7,
        12,
    )
    assert result["result"] == "UNKNOWN"


@pytest.mark.parametrize(
    "defenders",
    [
        {**unit_counts(soldier=10, shield=10), "Shield": True},
        {**unit_counts(soldier=10, shield=10), "Soldier": -1},
        {**unit_counts(soldier=10, shield=10), "Unknown": 50},
    ],
)
def test_malformed_defender_vector_never_becomes_safe(defenders):
    threat = [{"eta_ticks": 5, "units": unit_counts(soldier=2)}]
    source = evaluate_source_safety(defenders, threat, CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(defenders, threat, CAPACITIES, "Cliff", 7, 12)
    assert source["result"] == "UNKNOWN"
    assert multi["result"] == "UNKNOWN"


def test_unknown_incoming_unit_is_not_silently_dropped_by_source_gate():
    threat = [{"eta_ticks": 5, "units": {"Soldier": 2, "Unknown": 50}}]
    result = evaluate_source_safety(
        unit_counts(soldier=10, shield=10), threat, CAPACITIES, "Cliff", 7, 12
    )
    assert result["result"] == "UNKNOWN"
