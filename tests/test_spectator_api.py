"""觀戰 API 契約回歸（P0）。

未掛載服務→UNAVAILABLE（不假裝）；已掛載→正確委派；
輸入驗證；路由清單正確。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai import spectator_api


class FakeService:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"available": True, "availability": "AVAILABLE",
                "connected": True, "match_id": "m1", "same_match": "VERIFIED",
                "camera_center": [1.0, 2.0], "camera_zoom": 1.5,
                "viewport": [800, 600], "last_frame_at": 123.0,
                "last_camera_action": None, "follow_mode": "OFF",
                "layer": "REAL_CAMERA"}

    def pan(self, dx, dy):
        self.calls.append(("pan", dx, dy))
        return {"ok": True, "code": "APPLIED", "applied": True}

    def zoom(self, delta=None, target=None):
        self.calls.append(("zoom", delta, target))
        return {"ok": True, "code": "APPLIED", "applied": True}

    def focus(self, wx, wy):
        self.calls.append(("focus", wx, wy))
        return {"ok": True, "code": "APPLIED", "applied": True}

    def follow(self, mode):
        self.calls.append(("follow", mode))
        return {"ok": True, "code": "FOLLOW_OFF"}


class App:
    pass


def test_no_service_reports_unavailable_not_fake():
    app = App()
    status = spectator_api.spectator_status(app)
    assert status["available"] is False
    assert status["availability"] == "UNAVAILABLE"
    assert status["layer"] == "IMAGE_ONLY"
    result = spectator_api.spectator_command(app, "pan", {"dx": 1, "dy": 1})
    assert result["ok"] is False
    assert result["code"] == "SPECTATOR_UNAVAILABLE"


def test_status_delegates_to_service():
    app = App()
    app.spectator = FakeService()
    status = spectator_api.spectator_status(app)
    assert status["same_match"] == "VERIFIED"
    assert status["camera_center"] == [1.0, 2.0]


def test_commands_delegate_with_conversion():
    svc = FakeService()
    app = App()
    app.spectator = svc
    assert spectator_api.spectator_command(app, "pan", {"dx": 3, "dy": -4})["ok"]
    assert spectator_api.spectator_command(app, "zoom", {"target_zoom": 2})["ok"]
    assert spectator_api.spectator_command(app, "focus",
                                           {"world_x": 5, "world_y": 6})["ok"]
    assert spectator_api.spectator_command(app, "follow", {"mode": "AI"})["ok"]
    assert ("pan", 3.0, -4.0) in svc.calls
    assert ("zoom", None, 2.0) in svc.calls
    assert ("focus", 5.0, 6.0) in svc.calls
    assert ("follow", "AI") in svc.calls


def test_bad_input_rejected_without_calling_service():
    svc = FakeService()
    app = App()
    app.spectator = svc
    for cmd, payload in (("pan", {"dx": "x", "dy": 1}),
                         ("pan", {}),
                         ("zoom", {}),
                         ("focus", {"world_x": 1}),
                         ("focus", {})):
        result = spectator_api.spectator_command(app, cmd, payload)
        assert result["ok"] is False
        assert result["code"] == "BAD_INPUT"
    assert svc.calls == []


def test_bool_is_not_accepted_as_number():
    app = App()
    app.spectator = FakeService()
    result = spectator_api.spectator_command(app, "pan", {"dx": True, "dy": 1})
    assert result["code"] == "BAD_INPUT"


def test_unknown_command_rejected():
    app = App()
    app.spectator = FakeService()
    assert spectator_api.spectator_command(app, "warp", {})["code"] == \
        "BAD_COMMAND"


def test_route_manifest():
    assert "/api/spectator/status" in spectator_api.GET_ROUTES
    for path in ("/api/spectator/pan", "/api/spectator/zoom",
                 "/api/spectator/focus", "/api/spectator/follow"):
        assert path in spectator_api.POST_ROUTES
