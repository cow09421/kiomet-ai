"""週期預算守衛（P1 §6）。

檢查 observation / proposal / decision / dispatch 的資料時效；
任一過期或未知 → ABSTAIN（fail closed），不派送。

純 helper；不接線控制器（正式路徑為外部施工中）。
"""
from __future__ import annotations

DEFAULT_BUDGETS = {
    "observation_age_s": 15.0,
    "proposal_age_s": 15.0,
    "decision_age_s": 10.0,
    "dispatch_age_s": 10.0,
}

STAGES = tuple(DEFAULT_BUDGETS)


def _fresh(age, limit):
    return isinstance(age, (int, float)) and age <= limit


def check_budget(ages: dict | None, budgets: dict | None = None) -> dict:
    """回傳各階段是否新鮮與最終建議。

    ages: {stage_name: seconds_or_None}
    """
    ages = ages if isinstance(ages, dict) else {}
    limits = dict(DEFAULT_BUDGETS)
    if isinstance(budgets, dict):
        limits.update(budgets)
    details = {}
    breaches = []
    for stage in STAGES:
        age = ages.get(stage)
        limit = limits[stage]
        if age is None:
            details[stage] = {"age_s": None, "limit_s": limit,
                              "fresh": False, "reason": "UNKNOWN"}
            breaches.append(stage)
        elif _fresh(age, limit):
            details[stage] = {"age_s": float(age), "limit_s": limit,
                              "fresh": True, "reason": "FRESH"}
        else:
            details[stage] = {"age_s": float(age), "limit_s": limit,
                              "fresh": False, "reason": "STALE"}
            breaches.append(stage)
    return {
        "action": "ABSTAIN" if breaches else "PROCEED",
        "abstain": bool(breaches),
        "breaches": breaches,
        "details": details,
    }


def should_abstain(ages: dict | None, budgets: dict | None = None) -> bool:
    return check_budget(ages, budgets)["abstain"]


def breached_reasons(result: dict) -> list:
    return [f"{stage}:{result['details'][stage]['reason']}"
            for stage in result.get("breaches", [])]
