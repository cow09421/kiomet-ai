"""行動仲裁優先級契約測試（P1-D）。

優先級：
1. Verified imminent defense（REINFORCE_SELF）
2. Safe verified attack（ATTACK_ENEMY）
3. Neutral expansion（EXPAND_NEUTRAL）
4. ABSTAIN

不得為了「一定要有動作」而選 unsupported action。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.pvp import arbitrate_pvp_action


def _defense(supported=True, tower_lost=False, **over):
    base = {
        "support_status": "SUPPORTED" if supported else "UNSUPPORTED",
        "tower_lost": tower_lost,
        "enemy_eta": 5,
        "target_tower_id": 9,
    }
    base.update(over)
    return base


def _attack(safe=False, **over):
    base = {"safe_attack_candidate": safe, "support_status": "SUPPORTED"}
    base.update(over)
    return base


def _neutral(validated=False, **over):
    base = {"validated": validated, "target_tower_id": 3}
    base.update(over)
    return base


def test_defense_wins_over_attack():
    """有防守損失時，REINFORCE_SELF 優先於 ATTACK_ENEMY。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(
            tower_lost=True,
            minimum_sufficient_reinforcement={
                "source_tower_id": 42, "unit_count": 5,
                "command_validated": True},
            reinforcement_command_validated=True)],
        attack_evaluations=[_attack(safe=True)],
        neutral_expansion_candidate=_neutral(validated=True),
    )
    assert result["action"] == "REINFORCE_SELF"


def test_attack_wins_over_neutral():
    """無防守損失時，ATTACK_ENEMY 優先於 EXPAND_NEUTRAL。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(tower_lost=False)],
        attack_evaluations=[_attack(safe=True)],
        neutral_expansion_candidate=_neutral(validated=True),
    )
    assert result["action"] == "ATTACK_ENEMY"


def test_neutral_wins_over_abstain():
    """無防守損失且無安全攻擊時，EXPAND_NEUTRAL 優先於 ABSTAIN。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(tower_lost=False)],
        attack_evaluations=[_attack(safe=False)],
        neutral_expansion_candidate=_neutral(validated=True),
    )
    assert result["action"] == "EXPAND_NEUTRAL"


def test_no_supported_action_abstains():
    """無任何已驗證候選時 → ABSTAIN（不得選 unsupported）。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(tower_lost=False)],
        attack_evaluations=[_attack(safe=False)],
        neutral_expansion_candidate=_neutral(validated=False),
    )
    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "SUPPORTED"


def test_unresolved_threat_blocks_everything():
    """未解決威脅存在時，即使有安全攻擊與中立擴張也 → ABSTAIN。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[{
            "support_status": "RUNTIME_VALIDATION_NEEDED",
            "tower_lost": None,
            "enemy_eta": 8,
            "target_tower_id": 9}],
        attack_evaluations=[_attack(safe=True)],
        neutral_expansion_candidate=_neutral(validated=True),
    )
    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "UNKNOWN"


def test_unsupported_defense_abstains():
    """防守評估為 UNSUPPORTED 時 → ABSTAIN（不得選其他）。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(supported=False, tower_lost=True)],
        attack_evaluations=[_attack(safe=True)],
        neutral_expansion_candidate=_neutral(validated=True),
    )
    assert result["action"] == "ABSTAIN"
    assert result["evaluation_status"] == "UNSUPPORTED"


def test_empty_evaluations_abstains():
    result = arbitrate_pvp_action(
        defense_evaluations=[],
        attack_evaluations=[],
        neutral_expansion_candidate=None,
    )
    assert result["action"] == "ABSTAIN"


def test_defense_without_loss_ignores_reinforce():
    """防守無損失時，REINFORCE_SELF 不觸發（不浪費援軍）。"""
    result = arbitrate_pvp_action(
        defense_evaluations=[_defense(
            tower_lost=False,
            minimum_sufficient_reinforcement={
                "source_tower_id": 42, "unit_count": 5,
                "command_validated": True},
            reinforcement_command_validated=True)],
        attack_evaluations=[],
        neutral_expansion_candidate=None,
    )
    assert result["action"] == "ABSTAIN"
