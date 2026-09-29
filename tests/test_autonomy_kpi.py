"""自主產能 KPI 回歸（P0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.autonomy_kpi import compute_kpi, from_journal


def test_rates_computed():
    kpi = compute_kpi({"cycles": 100, "actions_sent": 20,
                       "safe_proposal_cycles": 40, "verified_moves": 10})
    assert kpi["ACTION_RATE"] == 0.2
    assert kpi["DECISION_RATE"] == 0.4
    assert kpi["VERIFY_RATE"] == 0.5


def test_zero_cycles_rate_none_not_fake_zero():
    kpi = compute_kpi({"cycles": 0, "actions_sent": 0})
    assert kpi["ACTION_RATE"] is None
    assert kpi["DECISION_RATE"] is None
    assert kpi["ACTION_RATE"] != 0


def test_missing_cycles_rate_none():
    kpi = compute_kpi({"actions_sent": 5})
    assert kpi["ACTION_RATE"] is None
    assert kpi["cycles"] is None


def test_missing_counter_is_none():
    kpi = compute_kpi({"cycles": 10})
    assert kpi["actions_sent"] is None
    assert kpi["verified_enemy_attacks"] is None


def test_idle_flag():
    assert compute_kpi({"cycles": 10, "actions_sent": 0})["idle"] is True
    assert compute_kpi({"cycles": 10, "actions_sent": 3})["idle"] is False
    assert compute_kpi({"cycles": 10})["idle"] is None


def test_no_fake_zero_for_verify_rate():
    kpi = compute_kpi({"cycles": 10, "actions_sent": 0, "verified_moves": 0})
    assert kpi["VERIFY_RATE"] is None


def test_from_journal_mapping():
    journal = {"cycles": 50, "sent_actions": 5, "verified_moves": 4,
               "verified_expansions": 3, "no_safe_proposals": 45}
    kpi = from_journal(journal, actions=[{}, {}, {}])
    assert kpi["cycles"] == 50
    assert kpi["actions_sent"] == 5
    assert kpi["abstains"] == 45
    assert kpi["actions_attempted"] == 3
    assert kpi["ACTION_RATE"] == 0.1


def test_from_journal_empty():
    kpi = from_journal(None)
    assert kpi["cycles"] is None
    assert kpi["ACTION_RATE"] is None
