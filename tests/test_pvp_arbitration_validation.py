"""Malformed defense evidence must never unlock a fallback action."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.pvp import arbitrate_pvp_action


@pytest.mark.parametrize("row", [
    {"support_status": "SUPPORTED", "tower_lost": 0,
     "enemy_eta": 5, "target_tower_id": 9},
    {"support_status": "SUPPORTED", "tower_lost": "false",
     "enemy_eta": 5, "target_tower_id": 9},
    {"support_status": "SUPPORTED", "tower_lost": False,
     "enemy_eta": True, "target_tower_id": 9},
    {"support_status": "SUPPORTED", "tower_lost": False,
     "enemy_eta": 5.0, "target_tower_id": 9},
    {"support_status": "SUPPORTED", "tower_lost": False,
     "enemy_eta": 5, "target_tower_id": True},
])
def test_malformed_defense_evidence_blocks_attack_and_expansion(row):
    result = arbitrate_pvp_action(
        defense_evaluations=[row],
        attack_evaluations=[{"safe_attack_candidate": True}],
        neutral_expansion_candidate={"validated": True},
    )

    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "UNKNOWN"


def test_non_dictionary_defense_row_abstains_instead_of_crashing():
    result = arbitrate_pvp_action(
        defense_evaluations=[None], attack_evaluations=[],
        neutral_expansion_candidate={"validated": True},
    )

    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "UNKNOWN"


def test_malformed_validated_rescue_command_does_not_emit_reinforcement():
    result = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "SUPPORTED", "tower_lost": True,
            "enemy_eta": 5, "target_tower_id": 9,
            "minimum_sufficient_reinforcement": {
                "command_validated": True,
            },
            "reinforcement_command_validated": True,
        }],
        attack_evaluations=[], neutral_expansion_candidate=None,
    )

    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "UNKNOWN"
