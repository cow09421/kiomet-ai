"""真實觀戰攝影機服務（P0）。

設計原則：
- 與 AI（觀察器／規劃器／執行器／相機／座標映射）完全隔離。
  本模組只持有「觀戰相機」狀態，絕不觸碰 AI 任何狀態。
- 誠實：沒有真正可控制的觀戰頁面時，pan/zoom/focus 一律回 BLOCKED，
  絕不以 CSS 截圖平移冒充真攝影機。
- 可注入 driver（相機驅動）與 focus_provider（跟隨目標提供者），
  方便測試與未來整合，不需在此硬接 Playwright。

狀態：
- availability: AVAILABLE / UNAVAILABLE / BLOCKED / UNKNOWN
- same_match:   VERIFIED / BLOCKED / UNKNOWN
"""
from __future__ import annotations

import time

FOLLOW_MODES = ("OFF", "AI", "LAST_ACTION", "THREAT")
ZOOM_MIN = 0.25
ZOOM_MAX = 8.0


class SpectatorCamera:
    """獨立觀戰相機；與 AI 狀態無關。"""

    def __init__(self, driver=None, focus_provider=None,
                 match_provider=None, same_match: str = "UNKNOWN",
                 camera_driver_available: bool = False):
        self.driver = driver
        self.focus_provider = focus_provider
        self.match_provider = match_provider
        self.same_match = same_match
        self.camera_driver_available = bool(camera_driver_available)
        self.center = [0.0, 0.0]
        self.zoom_level = 1.0
        self.viewport = [0, 0]
        self.follow_mode = "OFF"
        self.last_frame_at = None
        self.last_camera_action = None
        self.spectator_match_id = None

    # ---- 能力判定 ----
    @property
    def available(self) -> bool:
        """只有驅動可用且同局已 VERIFIED 才算真的可用。"""
        return (self.camera_driver_available and self.driver is not None
                and self.same_match == "VERIFIED")

    def _availability(self) -> str:
        if self.available:
            return "AVAILABLE"
        if self.same_match == "BLOCKED":
            return "BLOCKED"
        if not self.camera_driver_available or self.driver is None:
            return "UNAVAILABLE"
        return "UNKNOWN"

    def status(self) -> dict:
        return {
            "available": self.available,
            "availability": self._availability(),
            "connected": bool(self.driver is not None),
            "match_id": self.spectator_match_id,
            "same_match": self.same_match,
            "camera_center": list(self.center),
            "camera_zoom": self.zoom_level,
            "viewport": list(self.viewport),
            "last_frame_at": self.last_frame_at,
            "last_camera_action": self.last_camera_action,
            "follow_mode": self.follow_mode,
            "layer": "REAL_CAMERA" if self.available else (
                "SPECTATOR_UNAVAILABLE" if self._availability() == "BLOCKED"
                else "IMAGE_ONLY"),
        }

    # ---- 內部：唯一出口 ----
    def _blocked(self, code: str, reason: str) -> dict:
        return {"ok": False, "code": code, "reason": reason,
                "applied": False, "applied_to": "SPECTATOR_ONLY",
                "camera_center": list(self.center),
                "camera_zoom": self.zoom_level}

    def _apply(self, action: str, **params):
        """經 driver 施加到觀戰頁；絕不觸及 AI。"""
        if not self.available:
            if self.same_match == "BLOCKED":
                return self._blocked("SAME_MATCH_BLOCKED",
                                     "無法確認同一對局，拒絕假攝影機")
            return self._blocked("SPECTATOR_UNAVAILABLE",
                                 "沒有可控制的觀戰頁面")
        try:
            result = self.driver(action, **params)
        except Exception as exc:  # 驅動失敗不得假裝成功
            return self._blocked("DRIVER_ERROR", f"驅動失敗：{exc}")
        if result is False:
            return self._blocked("DRIVER_REJECTED", "觀戰頁拒絕該相機動作")
        self.last_camera_action = {"action": action, "params": dict(params),
                                   "at": time.time()}
        return {"ok": True, "code": "APPLIED", "action": action,
                "applied": True, "applied_to": "SPECTATOR_ONLY",
                "camera_center": list(self.center),
                "camera_zoom": self.zoom_level}

    # ---- 對外操作 ----
    def pan(self, dx: float, dy: float) -> dict:
        """螢幕像素位移 → 世界位移（依 zoom 換算）。使用者手動拖曳會關閉 Follow。"""
        try:
            dx = float(dx)
            dy = float(dy)
        except (TypeError, ValueError):
            return self._blocked("BAD_INPUT", "dx/dy 必須是數值")
        self.follow_mode = "OFF"
        result = self._apply("pan", dx=dx, dy=dy)
        if result["ok"]:
            self.center[0] += dx / max(self.zoom_level, 1e-6)
            self.center[1] += dy / max(self.zoom_level, 1e-6)
            result["camera_center"] = list(self.center)
        return result

    def zoom(self, delta: float | None = None,
             target: float | None = None) -> dict:
        """delta（倍率）或 target（絕對值）擇一；範圍 25%–800%。"""
        if target is not None:
            try:
                new_zoom = float(target)
            except (TypeError, ValueError):
                return self._blocked("BAD_INPUT", "target 必須是數值")
        elif delta is not None:
            try:
                new_zoom = self.zoom_level * float(delta)
            except (TypeError, ValueError):
                return self._blocked("BAD_INPUT", "delta 必須是數值")
        else:
            return self._blocked("BAD_INPUT", "需提供 delta 或 target")
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        result = self._apply("zoom", target=new_zoom)
        if result["ok"]:
            self.zoom_level = new_zoom
            result["camera_zoom"] = self.zoom_level
        return result

    def focus(self, world_x: float, world_y: float) -> dict:
        """把觀戰相機移到指定世界座標。"""
        try:
            wx = float(world_x)
            wy = float(world_y)
        except (TypeError, ValueError):
            return self._blocked("BAD_INPUT", "world_x/world_y 必須是數值")
        result = self._apply("focus", world_x=wx, world_y=wy)
        if result["ok"]:
            self.center = [wx, wy]
            result["camera_center"] = list(self.center)
        return result

    def follow(self, mode: str) -> dict:
        """設定跟隨模式；目標由 focus_provider 提供。"""
        mode = str(mode).upper()
        if mode not in FOLLOW_MODES:
            return self._blocked("BAD_MODE",
                                 f"mode 必須是 {FOLLOW_MODES}")
        self.follow_mode = mode
        if mode == "OFF":
            return {"ok": True, "code": "FOLLOW_OFF", "follow_mode": mode,
                    "applied": False, "applied_to": "SPECTATOR_ONLY"}
        target = None
        if self.focus_provider is not None:
            try:
                target = self.focus_provider(mode)
            except Exception:
                target = None
        if not self.available:
            return self._blocked(
                "SPECTATOR_UNAVAILABLE",
                f"跟隨 {mode} 已記錄，但無可控制觀戰相機")
        if not target:
            return self._blocked("FOLLOW_TARGET_UNKNOWN",
                                 f"跟隨 {mode}：無可用世界座標")
        result = self._apply("focus", world_x=target[0], world_y=target[1])
        if result["ok"]:
            self.center = [float(target[0]), float(target[1])]
            result["camera_center"] = list(self.center)
        return result

    # ---- 整合用縮短入口（由 AI 端呼叫，非觀戰端）----
    def note_frame(self) -> None:
        self.last_frame_at = time.time()

    def note_same_match(self, same_match: str,
                        spectator_match_id: str | None = None) -> None:
        if same_match not in ("VERIFIED", "BLOCKED", "UNKNOWN"):
            raise ValueError("same_match 必須是 VERIFIED/BLOCKED/UNKNOWN")
        self.same_match = same_match
        self.spectator_match_id = spectator_match_id
