"""自主行動產能 KPI（P0）。

計數：cycles／decision_cycles／safe_proposal_cycles／actions_attempted／
actions_sent／verified_*／abstains／no_safe_proposal／blocked_by_unknown。

比率：
  ACTION_RATE  = actions_sent / cycles
  DECISION_RATE = safe_proposal_cycles / cycles
cycles 缺失或為 0 → 比率為 None（不得假 0）。
純函式。
"""
from __future__ import annotations

COUNTERS = (
    "cycles", "decision_cycles", "safe_proposal_cycles",
    "actions_attempted", "actions_sent", "verified_moves",
    "verified_expansions", "verified_reinforcements",
    "verified_enemy_attacks", "abstains", "no_safe_proposal",
    "blocked_by_unknown",
)


def _num(value):
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _rate(numerator, denominator):
    num = _num(numerator)
    den = _num(denominator)
    if num is None or den in (None, 0):
        return None
    return round(num / den, 4)


def compute_kpi(counters: dict | None) -> dict:
    counters = counters if isinstance(counters, dict) else {}
    out = {name: _num(counters.get(name)) for name in COUNTERS}
    out["ACTION_RATE"] = _rate(out["actions_sent"], out["cycles"])
    out["DECISION_RATE"] = _rate(out["safe_proposal_cycles"], out["cycles"])
    out["VERIFY_RATE"] = _rate(out["verified_moves"], out["actions_sent"])
    out["idle"] = (out["actions_sent"] == 0
                   if out["actions_sent"] is not None else None)
    return out


def from_journal(journal: dict | None, actions: list | None = None) -> dict:
    """由控制器 journal 與行動記錄推導計數；缺欄位 → None。"""
    journal = journal if isinstance(journal, dict) else {}
    counters = {
        "cycles": _num(journal.get("cycles")),
        "actions_sent": _num(journal.get("sent_actions")),
        "verified_moves": _num(journal.get("verified_moves")),
        "verified_expansions": _num(journal.get("verified_expansions")),
        "decision_cycles": _num(journal.get("decision_cycles")),
        "safe_proposal_cycles": _num(journal.get("safe_proposal_cycles")),
        "abstains": _num(journal.get("no_safe_proposals")),
        "no_safe_proposal": _num(journal.get("no_safe_proposals")),
    }
    if isinstance(actions, list):
        counters["actions_attempted"] = sum(
            1 for a in actions if isinstance(a, dict))
    return compute_kpi(counters)
