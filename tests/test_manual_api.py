"""人工控制 API 契約回歸（P0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.control_owner import ControlOwner
from kiomet_ai.manual_api import (control_command, control_status,
                                  get_manual, get_owner)
from kiomet_ai.manual_control import ManualControl


class FakeMouse:
    def __init__(self, log): self.log = log
    def move(self, x, y): self.log.append(("move", x, y))
    def down(self): self.log.append(("down",))
    def up(self): self.log.append(("up",))
    def wheel(self, dx, dy): self.log.append(("wheel", dx, dy))


class FakePage:
    def __init__(self): self.log = []; self.mouse = FakeMouse(self.log)
    keyboard = None


class App:
    pass


def test_no_service_unavailable():
    app = App()
    assert control_status(app)["owner"] == "NONE"
    assert control_status(app)["available"] is False
    assert control_command(app, "manual", {})["code"] == "CONTROL_UNAVAILABLE"


def test_manual_transition_delegates():
    app = App()
    app.control_owner = ControlOwner()
    result = control_command(app, "manual", {})
    assert result["owner"] == "HUMAN"
    assert app.control_owner.allow_manual_input() is True


def test_return_to_ai_requires_checks():
    app = App()
    app.control_owner = ControlOwner()
    control_command(app, "manual", {})
    control_command(app, "return-to-ai", {"checks": {"fresh_observation": True}})
    result = control_command(app, "return-to-ai", {"complete": True})
    assert result["ok"] is False
    assert result["code"] == "RETURN_NOT_READY"


def test_input_blocked_when_ai():
    app = App()
    app.control_owner = ControlOwner()  # AI
    app.manual_control = ManualControl(page=FakePage(), owner=app.control_owner)
    result = control_command(app, "input",
                             {"action": "move", "params": {"x": 1, "y": 2}})
    assert result["ok"] is False
    assert result["code"] == "MANUAL_NOT_ALLOWED"


def test_input_forwarded_when_human():
    app = App()
    app.control_owner = ControlOwner()
    page = FakePage()
    app.manual_control = ManualControl(page=page, owner=app.control_owner)
    control_command(app, "manual", {})
    result = control_command(app, "input",
                             {"action": "move", "params": {"x": 3, "y": 4}})
    assert result["ok"] is True
    assert page.log == [("move", 3.0, 4.0)]


def test_status_includes_kpi_and_idle():
    app = App()
    app.control_owner = ControlOwner()
    status = control_status(app, kpi={"ACTION_RATE": 0.2},
                            idle={"status": "OK"})
    assert status["kpi"]["ACTION_RATE"] == 0.2
    assert status["idle"]["status"] == "OK"


def test_route_manifest():
    from kiomet_ai import manual_api
    assert "/api/control/status" in manual_api.GET_ROUTES
    for p in ("/api/control/manual", "/api/control/return-to-ai",
              "/api/control/input"):
        assert p in manual_api.POST_ROUTES


def test_getters():
    app = App()
    assert get_owner(app) is None
    assert get_manual(app) is None
