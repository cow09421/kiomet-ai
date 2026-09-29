"""AI／真人控制權互斥（P0）。

硬閘門：AI 派送與人工頁面輸入不可同時。
control_owner ∈ {AI, HUMAN, REACQUIRING, NONE}

- AI 派送：只有 owner==AI
- 人工頁面輸入：只有 owner==HUMAN
- REACQUIRING / NONE：兩者皆禁

一般 UI 刷新不得改變 owner；換局時安全重置回 AI。
純邏輯，不觸碰 ActionGate／controller（外部施工路徑）。
"""
from __future__ import annotations

import time

OWNERS = ("AI", "HUMAN", "REACQUIRING", "NONE")
RETURN_CHECKS = ("fresh_observation", "fresh_camera", "mapping_rebuilt",
                 "match_verified")


class ControlOwner:
    def __init__(self, owner: str = "AI"):
        if owner not in OWNERS:
            raise ValueError(f"未知 owner：{owner}")
        self._owner = owner
        self.owner_since = time.time()
        self.match_id = None
        self.return_checks = {k: False for k in RETURN_CHECKS}
        self.history: list = []

    @property
    def owner(self) -> str:
        return self._owner

    def _set(self, owner: str, reason: str) -> None:
        self._owner = owner
        self.owner_since = time.time()
        self.history.append({"owner": owner, "reason": reason,
                             "at": self.owner_since})

    # ---- 硬閘門 ----
    def allow_ai_dispatch(self) -> bool:
        return self._owner == "AI"

    def allow_manual_input(self) -> bool:
        return self._owner == "HUMAN"

    # ---- 轉換 ----
    def request_manual(self, reason: str = "user") -> dict:
        if self._owner == "HUMAN":
            return {"ok": True, "code": "ALREADY_HUMAN", "owner": "HUMAN"}
        self._set("HUMAN", reason)
        return {"ok": True, "code": "MANUAL_ENGAGED", "owner": "HUMAN",
                "ai_dispatch_allowed": False}

    def request_return_to_ai(self, reason: str = "user") -> dict:
        self._set("REACQUIRING", reason)
        self.return_checks = {k: False for k in RETURN_CHECKS}
        return {"ok": True, "code": "REACQUIRING", "owner": "REACQUIRING"}

    def note_return_check(self, name: str, ok: bool = True) -> None:
        if name not in RETURN_CHECKS:
            raise ValueError(f"未知 return check：{name}")
        self.return_checks[name] = bool(ok)

    def complete_return(self) -> dict:
        if self._owner != "REACQUIRING":
            return {"ok": False, "code": "NOT_REACQUIRING",
                    "owner": self._owner}
        missing = [k for k, v in self.return_checks.items() if not v]
        if missing:
            return {"ok": False, "code": "RETURN_NOT_READY",
                    "missing": missing, "owner": "REACQUIRING"}
        self._set("AI", "return_complete")
        return {"ok": True, "code": "AUTONOMY_RESUMED", "owner": "AI"}

    def on_match_change(self, new_match_id) -> bool:
        """換局時安全重置回 AI 並清除舊 binding。回傳是否真的變更。"""
        changed = new_match_id != self.match_id
        self.match_id = new_match_id
        if changed:
            self.return_checks = {k: False for k in RETURN_CHECKS}
            self._set("AI", "match_change_reset")
        return changed

    # ---- 唯讀 ----
    def status(self) -> dict:
        return {
            "owner": self._owner,
            "ai_dispatch_allowed": self.allow_ai_dispatch(),
            "manual_input_allowed": self.allow_manual_input(),
            "match_id": self.match_id,
            "return_checks": dict(self.return_checks),
            "owner_since": self.owner_since,
        }
