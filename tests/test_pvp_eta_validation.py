"""多威脅安全評估只接受有效的 ETA 整數。"""
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


@pytest.mark.parametrize("eta", [True, False, -1, -20, 1.0, "5"])
def test_invalid_eta_never_produces_safe_result(eta):
    defenders = unit_counts(soldier=8, shield=4)
    threats = [{"eta_ticks": eta, "units": unit_counts(soldier=1)}]

    source = evaluate_source_safety(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert source == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
    assert multi == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}


def test_zero_eta_is_a_valid_immediate_arrival():
    defenders = unit_counts(soldier=8, shield=4)
    threats = [{"eta_ticks": 0, "units": unit_counts(soldier=1)}]

    source = evaluate_source_safety(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(defenders, threats, CAPACITIES, "Cliff", 7, 12)
    assert source["result"] == "SAFE"
    assert multi["result"] == "SAFE"


def test_malformed_threat_entry_abstains_instead_of_crashing():
    source = evaluate_source_safety(unit_counts(soldier=8, shield=4), [None], CAPACITIES, "Cliff", 7, 12)
    multi = evaluate_multi_threat(unit_counts(soldier=8, shield=4), [None], CAPACITIES, "Cliff", 7, 12)
    assert source == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
    assert multi == {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
