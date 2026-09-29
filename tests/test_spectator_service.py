"""觀戰相機服務回歸（P0）。

誠實性：不可用時 pan/zoom/focus 回 BLOCKED 且不改相機；
隔離性：服務只動觀戰狀態，AI 狀態完全不變；
範圍：zoom 夾在 25%–800%；手動 pan 關閉 Follow。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.spectator import SpectatorCamera


def _calls():
    seen = []

    def driver(action, **params):
        seen.append((action, params))
        return True
    return seen, driver


def _available():
    seen, driver = _calls()
    cam = SpectatorCamera(driver=driver, camera_driver_available=True,
                          same_match="VERIFIED", match_provider=lambda: "m1",
                          focus_provider=lambda mode: (10.0, 20.0))
    return cam, seen


def test_default_unavailable_blocked_operations():
    cam = SpectatorCamera()  # same_match UNKNOWN, no driver
    assert cam.available is False
    assert cam.status()["availability"] == "UNAVAILABLE"
    for result in (cam.pan(5, 5), cam.zoom(delta=1.2),
                   cam.focus(1, 2), cam.follow("AI")):
        assert result["ok"] is False
        assert result["applied"] is False
    assert cam.center == [0.0, 0.0]
    assert cam.zoom_level == 1.0


def test_same_match_blocked_never_fakes_camera():
    seen, driver = _calls()
    cam = SpectatorCamera(driver=driver, camera_driver_available=True,
                          same_match="BLOCKED")
    assert cam.available is False
    assert cam.status()["availability"] == "BLOCKED"
    result = cam.pan(50, 0)
    assert result["code"] == "SAME_MATCH_BLOCKED"
    assert seen == []  # 驅動絕不被呼叫
    assert cam.center == [0.0, 0.0]


def test_available_pan_moves_center_and_calls_driver():
    cam, seen = _available()
    assert cam.available is True
    result = cam.pan(20, -10)
    assert result["ok"] is True
    assert seen == [("pan", {"dx": 20.0, "dy": -10.0})]
    assert cam.center == [20.0, -10.0]


def test_zoom_clamped_25_to_800_percent():
    cam, seen = _available()
    cam.zoom(target=100.0)
    assert cam.zoom_level == 8.0
    cam.zoom(target=0.01)
    assert cam.zoom_level == 0.25


def test_zoom_requires_delta_or_target():
    cam, _ = _available()
    assert cam.zoom()["code"] == "BAD_INPUT"
    assert cam.zoom(delta="x")["code"] == "BAD_INPUT"


def test_focus_sets_center_only_when_available():
    cam, seen = _available()
    result = cam.focus(3, 4)
    assert result["ok"] is True
    assert cam.center == [3.0, 4.0]
    assert seen[-1] == ("focus", {"world_x": 3.0, "world_y": 4.0})


def test_manual_pan_turns_follow_off():
    cam, _ = _available()
    cam.follow("AI")
    assert cam.follow_mode == "AI"
    cam.pan(1, 1)
    assert cam.follow_mode == "OFF"


def test_follow_modes_and_bad_mode():
    cam, _ = _available()
    assert cam.follow("OFF")["ok"] is True
    assert cam.follow("THREAT")["ok"] is True
    assert cam.follow("NOPE")["code"] == "BAD_MODE"


def test_follow_without_target_is_blocked_not_faked():
    seen, driver = _calls()
    cam = SpectatorCamera(driver=driver, camera_driver_available=True,
                          same_match="VERIFIED", focus_provider=lambda m: None)
    result = cam.follow("AI")
    assert result["ok"] is False
    assert result["code"] == "FOLLOW_TARGET_UNKNOWN"


def test_driver_failure_never_reports_success():
    def bad_driver(action, **params):
        raise RuntimeError("boom")
    cam = SpectatorCamera(driver=bad_driver, camera_driver_available=True,
                          same_match="VERIFIED")
    result = cam.pan(5, 5)
    assert result["ok"] is False
    assert result["code"] == "DRIVER_ERROR"
    assert cam.center == [0.0, 0.0]


def test_service_never_touches_ai_state():
    """服務只持有觀戰狀態；AI 狀態物件完全不受影響。"""
    ai_state = {"camera": {"center": [1.0, 2.0], "zoom": 1.5},
                "sent_actions": 4, "world_to_screen": "v1"}
    snapshot = {k: (dict(v) if isinstance(v, dict) else v)
                for k, v in ai_state.items()}
    cam, _ = _available()
    cam.pan(100, 100)
    cam.zoom(target=3.0)
    cam.focus(9, 9)
    cam.follow("AI")
    assert ai_state["camera"] == snapshot["camera"]
    assert ai_state["sent_actions"] == 4
    assert ai_state["world_to_screen"] == "v1"


def test_status_layer_labels():
    cam = SpectatorCamera(same_match="BLOCKED", camera_driver_available=True,
                          driver=lambda **k: True)
    assert cam.status()["layer"] == "SPECTATOR_UNAVAILABLE"
    cam2, _ = _available()
    assert cam2.status()["layer"] == "REAL_CAMERA"
    cam3 = SpectatorCamera()
    assert cam3.status()["layer"] == "IMAGE_ONLY"


def test_note_same_match_validates():
    cam = SpectatorCamera()
    cam.note_same_match("VERIFIED", "m1-1")
    assert cam.status()["same_match"] == "VERIFIED"
    try:
        cam.note_same_match("MAYBE")
        assert False, "should reject"
    except ValueError:
        pass
