"""人工控制 API 契約（P0）。

純函式，供 dashboard 路由呼叫；以 getattr(app, "control_owner") 與
getattr(app, "manual_control") 取得服務，未掛載時回 CONTROL_UNAVAILABLE。

路由：
  GET  /api/control/status
  POST /api/control/manual
  POST /api/control/return-to-ai
  POST /api/control/input   {action, params}
"""
from __future__ import annotations

GET_ROUTES = ("/api/control/status",)
POST_ROUTES = ("/api/control/manual", "/api/control/return-to-ai",
               "/api/control/input")

_UNAVAILABLE = {
    "owner": "NONE",
    "available": False,
    "ai_dispatch_allowed": False,
    "manual_input_allowed": False,
    "match_id": None,
    "return_checks": {},
    "reason": "control_owner not attached",
}


def get_owner(app):
    return getattr(app, "control_owner", None)


def get_manual(app):
    return getattr(app, "manual_control", None)


def control_status(app, kpi: dict | None = None,
                   idle: dict | None = None) -> dict:
    owner = get_owner(app)
    if owner is None:
        return dict(_UNAVAILABLE)
    status = owner.status()
    status["available"] = True
    if kpi is not None:
        status["kpi"] = kpi
    if idle is not None:
        status["idle"] = idle
    return status


def control_command(app, command: str, payload: dict | None) -> dict:
    owner = get_owner(app)
    if owner is None:
        return {"ok": False, "code": "CONTROL_UNAVAILABLE"}
    if command == "manual":
        return owner.request_manual()
    if command == "return-to-ai":
        payload = payload if isinstance(payload, dict) else {}
        if payload.get("checks"):
            for name, ok in payload["checks"].items():
                try:
                    owner.note_return_check(name, ok)
                except ValueError:
                    continue
        if payload.get("complete"):
            return owner.complete_return()
        return owner.request_return_to_ai()
    if command == "input":
        manual = get_manual(app)
        if manual is None:
            return {"ok": False, "code": "MANUAL_UNAVAILABLE"}
        payload = payload if isinstance(payload, dict) else {}
        action = payload.get("action")
        params = payload.get("params")
        params = params if isinstance(params, dict) else {}
        return manual.handle(action, **params)
    return {"ok": False, "code": "BAD_COMMAND", "reason": command}
