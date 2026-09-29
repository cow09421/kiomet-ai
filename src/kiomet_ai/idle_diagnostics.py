"""防發呆診斷（P0）。

若 IN_MATCH + world fresh + self_towers>0 + controller running，
且連續 10 cycles actions_sent==0 → IDLE_DIAGNOSTIC；
連續 30 cycles → AUTONOMY_STALLED（視為工程問題，不是綠色正常）。

輸出每類（EXPAND／ATTACK／REINFORCE）的
candidate_count／first_rejection_reason／next_required_data；
缺資料為 UNKNOWN（不假 0）。純函式。
"""
from __future__ import annotations

IDLE_THRESHOLD = 10
STALLED_THRESHOLD = 30
KINDS = ("EXPAND", "ATTACK", "REINFORCE")


def _trailing_idle(cycles) -> int:
    count = 0
    for row in reversed(cycles or []):
        if not isinstance(row, dict):
            break
        if row.get("actions_sent"):
            break
        count += 1
    return count


def _kind_detail(context: dict, kind: str) -> dict:
    kinds = context.get("kinds") if isinstance(context, dict) else None
    entry = kinds.get(kind) if isinstance(kinds, dict) else None
    if isinstance(entry, dict):
        return {
            "candidate_count": entry.get("candidate_count", "UNKNOWN"),
            "first_rejection_reason":
                entry.get("first_rejection_reason", "UNKNOWN"),
            "next_required_data":
                entry.get("next_required_data", "UNKNOWN"),
        }
    return {"candidate_count": "UNKNOWN",
            "first_rejection_reason": "UNKNOWN",
            "next_required_data": "UNKNOWN"}


def evaluate(context: dict | None, cycles) -> dict:
    context = context if isinstance(context, dict) else {}
    preconditions = {
        "in_match": context.get("in_match") is True,
        "world_fresh": context.get("world_fresh") is True,
        "self_towers": (isinstance(context.get("self_towers"), (int, float))
                        and context.get("self_towers") > 0),
        "controller_running": context.get("controller_running") is True,
    }
    active = all(preconditions.values())
    idle_cycles = _trailing_idle(cycles)
    if not active:
        missing = [k for k, v in preconditions.items() if not v]
        return {"status": "NOT_APPLICABLE", "active": False,
                "idle_cycles": idle_cycles, "stalled": False,
                "reason": "precondition_failed", "missing": missing,
                "kinds": {}}
    if idle_cycles >= STALLED_THRESHOLD:
        status = "AUTONOMY_STALLED"
    elif idle_cycles >= IDLE_THRESHOLD:
        status = "IDLE_DIAGNOSTIC"
    else:
        return {"status": "OK", "active": True, "idle_cycles": idle_cycles,
                "stalled": False, "reason": None, "kinds": {}}
    return {
        "status": status,
        "active": True,
        "idle_cycles": idle_cycles,
        "stalled": status == "AUTONOMY_STALLED",
        "reason": "no_actions_for_n_cycles",
        "kinds": {kind: _kind_detail(context, kind) for kind in KINDS},
    }
