"""人工遊戲控制輸入橋接（P0）。

把 Dashboard 的 click／move／drag／wheel／key 轉成對真正
AI game_page 的 Playwright 頁面事件，且僅在 control_owner==HUMAN 時允許。

禁止：任何實體輸入注入函式庫、全域游標、桌面焦點切換。
純 plan（可測試）＋ apply（可同步或 future/await 執行）。
"""
from __future__ import annotations

SUPPORTED = ("move", "down", "up", "click", "drag", "wheel", "key")


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def plan(action: str, **params) -> list:
    """把輸入動作轉成頁面操作序列（純函式）。

    每項：{"target": "mouse"|"keyboard", "method": str, "args": [...]}
    非法輸入回空 list（由 handle 轉成 BAD_INPUT）。
    """
    action = str(action or "").lower()
    if action == "move":
        x, y = _num(params.get("x")), _num(params.get("y"))
        if x is None or y is None:
            return []
        return [{"target": "mouse", "method": "move", "args": [x, y]}]
    if action == "down":
        return [{"target": "mouse", "method": "down", "args": []}]
    if action == "up":
        return [{"target": "mouse", "method": "up", "args": []}]
    if action == "click":
        x, y = _num(params.get("x")), _num(params.get("y"))
        if x is None or y is None:
            return []
        return [{"target": "mouse", "method": "click", "args": [x, y]}]
    if action == "drag":
        x1, y1 = _num(params.get("x1")), _num(params.get("y1"))
        x2, y2 = _num(params.get("x2")), _num(params.get("y2"))
        if None in (x1, y1, x2, y2):
            return []
        return [
            {"target": "mouse", "method": "move", "args": [x1, y1]},
            {"target": "mouse", "method": "down", "args": []},
            {"target": "mouse", "method": "move", "args": [x2, y2]},
            {"target": "mouse", "method": "up", "args": []},
        ]
    if action == "wheel":
        dx = _num(params.get("dx", 0)) or 0.0
        dy = _num(params.get("dy", 0)) or 0.0
        return [{"target": "mouse", "method": "wheel", "args": [dx, dy]}]
    if action == "key":
        key = params.get("key")
        if not isinstance(key, str) or not key:
            return []
        return [{"target": "keyboard", "method": "press", "args": [key]}]
    return []


class ManualControl:
    def __init__(self, page=None, owner=None):
        self.page = page
        self.owner = owner
        self.forwarded = 0
        self.errors = 0
        self.last_ops: list = []
        self.history: list = []

    def _allowed(self) -> bool:
        return (self.page is not None and self.owner is not None
                and self.owner.allow_manual_input())

    def handle(self, action: str, **params) -> dict:
        if not self._allowed():
            code = ("NO_PAGE" if self.page is None
                    else "MANUAL_NOT_ALLOWED")
            return {"ok": False, "code": code, "forwarded": 0}
        ops = plan(action, **params)
        if not ops:
            return {"ok": False, "code": "BAD_INPUT", "forwarded": 0}
        self.last_ops = ops
        done = 0
        for op in ops:
            target = self.page.mouse if op["target"] == "mouse" \
                else self.page.keyboard
            try:
                handler = getattr(target, op["method"])
                result = handler(*op["args"])
                # 支援 future/awaitable（Playwright async）；不在此強制同步。
                if hasattr(result, "__await__"):
                    self._pending = result
                done += 1
            except Exception:
                self.errors += 1
                return {"ok": False, "code": "PAGE_INPUT_ERROR",
                        "forwarded": done}
        self.forwarded += done
        self.history.append({"action": action, "ops": ops})
        return {"ok": True, "code": "FORWARDED", "forwarded": done,
                "ops": ops}
