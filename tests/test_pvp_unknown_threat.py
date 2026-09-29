"""未知威脅集合不能被誤當成「沒有威脅」。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_source_safety


DEFENDERS = {"Shield": 8, "Fighter": 0, "Chopper": 0,
             "Bomber": 0, "Tank": 0, "Soldier": 3,
             "Ruler": 0, "Shell": 0, "Emp": 0, "Nuke": 0}


def test_unknown_or_malformed_threat_collection_never_returns_safe():
    for threats in (None, (), False, 0, ""):
        result = evaluate_source_safety(
            DEFENDERS, threats, CAPACITIES, "Cliff", 7, 12)

        assert result == {"result": "UNKNOWN",
                          "reason": "threat-list-unknown"}


def test_known_empty_threat_collection_can_be_safe():
    result = evaluate_source_safety(
        DEFENDERS, [], CAPACITIES, "Cliff", 7, 12)

    assert result == {"result": "SAFE", "reason": "no-known-threats"}
