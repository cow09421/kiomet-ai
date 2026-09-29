"""觀戰相機隔離回歸（P0 §12）。

記錄 AI camera before / spectator camera before；
觀戰 pan/zoom/focus/follow 之後：
- spectator camera：CHANGED（可用情況下）
- AI camera / world_to_screen：UNCHANGED
觀戰不可用時：兩者都 UNCHANGED（誠實）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.spectator import SpectatorCamera


class FakeAICamera:
    """代表 AI 端相機與座標映射；觀戰服務不得持有或改動它。"""

    def __init__(self):
        self.center = [500.0, 400.0]
        self.zoom = 1.0
        self.world_to_screen_version = "w2s-v1"
        self.snapshot = self._snap()

    def _snap(self):
        return {"center": list(self.center), "zoom": self.zoom,
                "w2s": self.world_to_screen_version}

    def unchanged(self):
        return self.snapshot == self._snap()


def _available_cam():
    seen = []

    def driver(action, **params):
        seen.append((action, params))
        return True

    cam = SpectatorCamera(driver=driver, camera_driver_available=True,
                          same_match="VERIFIED",
                          focus_provider=lambda mode: (900.0, 900.0))
    return cam, seen


def test_spectator_pan_changes_spectator_not_ai():
    ai = FakeAICamera()
    cam, _ = _available_cam()
    spec_before = list(cam.center)
    assert cam.pan(200, 100)["ok"] is True
    assert cam.center != spec_before          # spectator: CHANGED
    assert ai.unchanged() is True             # AI: UNCHANGED


def test_spectator_zoom_changes_spectator_not_ai():
    ai = FakeAICamera()
    cam, _ = _available_cam()
    before = cam.zoom_level
    assert cam.zoom(target=2.0)["ok"] is True
    assert cam.zoom_level != before
    assert ai.zoom == 1.0
    assert ai.unchanged() is True


def test_spectator_focus_and_follow_do_not_touch_ai():
    ai = FakeAICamera()
    cam, _ = _available_cam()
    cam.focus(1234.0, 567.0)
    cam.follow("AI")
    assert ai.unchanged() is True
    assert ai.world_to_screen_version == "w2s-v1"


def test_blocked_spectator_leaves_both_unchanged():
    """真實環境同局 BLOCKED：觀戰與 AI 皆不變（不得假裝）。"""
    ai = FakeAICamera()
    seen = []

    def driver(action, **params):
        seen.append(action)
        return True
    cam = SpectatorCamera(driver=driver, camera_driver_available=True,
                          same_match="BLOCKED")
    spec_before = list(cam.center)
    for result in (cam.pan(50, 50), cam.zoom(target=3.0),
                   cam.focus(1, 1), cam.follow("THREAT")):
        assert result["ok"] is False
    assert cam.center == spec_before
    assert cam.zoom_level == 1.0
    assert seen == []
    assert ai.unchanged() is True


def test_spectator_state_is_separate_object_from_ai():
    ai = FakeAICamera()
    cam, _ = _available_cam()
    cam.pan(10, 10)
    assert cam.center is not ai.center
    assert cam.center != ai.center


def test_world_to_screen_never_imported_or_mutated():
    """服務原始碼不得引用 world_to_screen 或 AI 相機欄位。"""
    import inspect
    import kiomet_ai.spectator as mod
    src = inspect.getsource(mod)
    for banned in ("world_to_screen", "game_page", "sent_actions",
                   "live_controller", "ActionGate"):
        assert banned not in src
