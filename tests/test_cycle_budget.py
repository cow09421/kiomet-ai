"""週期預算守衛回歸（P1 §6）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.cycle_budget import (breached_reasons, check_budget,
                                    should_abstain)


def _ages(**over):
    base = {"observation_age_s": 2.0, "proposal_age_s": 3.0,
            "decision_age_s": 1.0, "dispatch_age_s": 1.0}
    base.update(over)
    return base


def test_all_fresh_proceeds():
    result = check_budget(_ages())
    assert result["action"] == "PROCEED"
    assert result["breaches"] == []
    assert should_abstain(_ages()) is False


def test_stale_observation_abstains():
    result = check_budget(_ages(observation_age_s=100))
    assert result["action"] == "ABSTAIN"
    assert "observation_age_s" in result["breaches"]


def test_unknown_age_abstains_fail_closed():
    result = check_budget(_ages(proposal_age_s=None))
    assert result["action"] == "ABSTAIN"
    assert "proposal_age_s" in result["breaches"]
    assert result["details"]["proposal_age_s"]["reason"] == "UNKNOWN"


def test_empty_ages_all_abstain():
    result = check_budget({})
    assert len(result["breaches"]) == 4
    assert result["action"] == "ABSTAIN"


def test_custom_budgets():
    assert check_budget(_ages(observation_age_s=25),
                        {"observation_age_s": 30})["action"] == "PROCEED"
    assert check_budget(_ages(observation_age_s=25),
                        {"observation_age_s": 10})["action"] == "ABSTAIN"


def test_boundary_exact_limit_is_fresh():
    assert check_budget(_ages(decision_age_s=10.0))["action"] == "PROCEED"


def test_breached_reasons_listing():
    result = check_budget(_ages(observation_age_s=None, dispatch_age_s=99))
    reasons = breached_reasons(result)
    assert "observation_age_s:UNKNOWN" in reasons
    assert "dispatch_age_s:STALE" in reasons


def test_none_input():
    assert check_budget(None)["action"] == "ABSTAIN"
