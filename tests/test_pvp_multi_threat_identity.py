"""Threat-row identity must agree with the enemy bound to the whole batch."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.pvp_live import evaluate_multi_threat


def vector(**counts):
    names = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
             "Ruler", "Shell", "Emp", "Nuke")
    return {name: counts.get(name, 0) for name in names}


@pytest.mark.parametrize("identity", [
    {"owner_id": 13, "owner_relation": "ENEMY"},
    {"owner_id": 12, "owner_relation": "ALLY"},
    {"owner_id": 7, "owner_relation": "ENEMY"},
    {"owner_id": True, "owner_relation": "ENEMY"},
    {"owner_id": 12, "owner_relation": "UNKNOWN"},
])
def test_conflicting_or_non_enemy_row_identity_is_unknown(identity):
    threat = {"eta_ticks": 5, "units": vector(Soldier=2), **identity}

    result = evaluate_multi_threat(
        vector(Shield=20, Soldier=20), [threat], CAPACITIES, "Cliff",
        self_id=7, enemy_id=12)

    assert result["result"] == "UNKNOWN"


def test_explicit_matching_enemy_identity_remains_supported():
    threat = {"eta_ticks": 5, "units": vector(Soldier=2),
              "owner_id": 12, "owner_relation": "ENEMY"}

    result = evaluate_multi_threat(
        vector(Shield=20, Soldier=20), [threat], CAPACITIES, "Cliff",
        self_id=7, enemy_id=12)

    assert result["result"] == "SAFE"
