"""觀戰 API 契約（P0）。

純函式，供 dashboard 路由呼叫；以 getattr(app, "spectator") 取得服務，
未掛載時優雅回報 UNAVAILABLE，絕不假裝可用。

路由：
  GET  /api/spectator/status
  POST /api/spectator/pan     {dx, dy}
  POST /api/spectator/zoom    {delta} 或 {target_zoom}
  POST /api/spectator/focus   {world_x, world_y}
  POST /api/spectator/follow  {mode}
"""
from __future__ import annotations

GET_ROUTES = ("/api/spectator/status",)
POST_ROUTES = ("/api/spectator/pan", "/api/spectator/zoom",
               "/api/spectator/focus", "/api/spectator/follow")

_UNAVAILABLE = {
    "available": False,
    "availability": "UNAVAILABLE",
    "connected": False,
    "match_id": None,
    "same_match": "UNKNOWN",
    "camera_center": [0.0, 0.0],
    "camera_zoom": 1.0,
    "viewport": [0, 0],
    "last_frame_at": None,
    "last_camera_action": None,
    "follow_mode": "OFF",
    "layer": "IMAGE_ONLY",
    "reason": "spectator service not attached",
}


def get_service(app):
    return getattr(app, "spectator", None)


def spectator_status(app) -> dict:
    service = get_service(app)
    if service is None:
        return dict(_UNAVAILABLE)
    status = service.status()
    status.setdefault("reason", None)
    return status


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def spectator_command(app, command: str, payload: dict | None) -> dict:
    service = get_service(app)
    if service is None:
        return {"ok": False, "code": "SPECTATOR_UNAVAILABLE",
                "reason": "spectator service not attached",
                "applied": False}
    payload = payload if isinstance(payload, dict) else {}
    if command == "pan":
        dx = _num(payload.get("dx"))
        dy = _num(payload.get("dy"))
        if dx is None or dy is None:
            return {"ok": False, "code": "BAD_INPUT",
                    "reason": "dx/dy 必須是數值", "applied": False}
        return service.pan(dx, dy)
    if command == "zoom":
        target = _num(payload.get("target_zoom"))
        delta = _num(payload.get("delta"))
        if target is None and delta is None:
            return {"ok": False, "code": "BAD_INPUT",
                    "reason": "需提供 delta 或 target_zoom", "applied": False}
        return service.zoom(delta=delta, target=target)
    if command == "focus":
        wx = _num(payload.get("world_x"))
        wy = _num(payload.get("world_y"))
        if wx is None or wy is None:
            return {"ok": False, "code": "BAD_INPUT",
                    "reason": "world_x/world_y 必須是數值", "applied": False}
        return service.focus(wx, wy)
    if command == "follow":
        mode = payload.get("mode", "OFF")
        return service.follow(mode)
    return {"ok": False, "code": "BAD_COMMAND", "reason": command,
            "applied": False}
