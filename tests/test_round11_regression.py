"""Round 11 安全合約的精確多威脅迴歸案例。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat, evaluate_source_safety


def unit_counts(soldier: int = 0, shield: int = 0, **special: int) -> dict[str, int]:
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
        **special,
    }


def test_unknown_eta_abstains_in_source_and_multi_threat_gates():
    defenders = unit_counts(soldier=8, shield=4)
    threat = [{"eta_ticks": None, "units": unit_counts(soldier=2)}]

    source = evaluate_source_safety(defenders, threat, CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(defenders, threat, CAPACITIES, "Cliff", 7, 12)
    assert source == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
    assert multi == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}


def test_same_tick_threats_abstain_in_both_evaluators():
    defenders = unit_counts(soldier=8, shield=4)
    threats = [
        {"eta_ticks": 5, "units": unit_counts(soldier=1)},
        {"eta_ticks": 5, "units": unit_counts(soldier=2)},
    ]

    source = evaluate_source_safety(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert source == {"result": "UNKNOWN", "reason": "UNSUPPORTED_TEMPORAL_CASE"}
    assert multi["result"] == "UNKNOWN"
    assert multi["reason"] == "UNSUPPORTED_TEMPORAL_CASE"


def test_later_special_unit_threat_invalidates_the_whole_sequence():
    defenders = unit_counts(soldier=8, shield=4)
    threats = [
        {"eta_ticks": 5, "units": unit_counts(soldier=1)},
        {"eta_ticks": 9, "units": unit_counts(soldier=2, Nuke=1)},
    ]

    result = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert result == {
        "result": "UNKNOWN",
        "reason": "threat-special-units",
        "resolved_before": 1,
    }
