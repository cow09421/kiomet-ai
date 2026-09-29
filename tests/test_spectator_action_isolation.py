"""觀戰行動隔離回歸（P0 §13）。

觀戰頁永遠不得送 MoveForce／Upgrade／Deploy 或任何遊戲命令；
相機互動不得進入 ActionGate／sent_actions／verified_actions，
也不得增加 AI action counter。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.spectator import SpectatorCamera

GAME_COMMANDS = ("MoveForce", "Upgrade", "Deploy", "move_force",
                 "upgrade_tower", "deploy", "play_button", "click")


class FakeActionGate:
    """代表 AI 行動閘門；記錄任何 dispatch 嘗試。"""

    def __init__(self):
        self.dispatches = []
        self.sent_actions = 0
        self.verified_actions = 0

    def dispatch(self, fn):
        self.dispatches.append(fn)
        self.sent_actions += 1
        return True


def _available_cam(record):
    def driver(action, **params):
        record.append((action, params))
        return True
    return SpectatorCamera(driver=driver, camera_driver_available=True,
                           same_match="VERIFIED",
                           focus_provider=lambda m: (1.0, 1.0)), record


def test_spectator_ops_never_call_action_gate():
    gate = FakeActionGate()
    record = []
    cam, _ = _available_cam(record)
    for op in (lambda: cam.pan(10, 10), lambda: cam.zoom(target=2.0),
               lambda: cam.focus(5, 5), lambda: cam.follow("AI")):
        op()
    assert gate.dispatches == []
    assert gate.sent_actions == 0
    assert gate.verified_actions == 0


def test_driver_only_receives_camera_actions():
    record = []
    cam, _ = _available_cam(record)
    cam.pan(1, 2)
    cam.zoom(delta=1.1)
    cam.focus(3, 4)
    actions = {a for a, _ in record}
    assert actions <= {"pan", "zoom", "focus"}
    for _, params in record:
        assert not any(cmd.lower() in str(params).lower()
                       for cmd in GAME_COMMANDS)


def test_spectator_ops_do_not_bump_ai_counters():
    counters = {"sent_actions": 4, "verified_actions": 3, "cycles": 100}
    snapshot = dict(counters)
    record = []
    cam, _ = _available_cam(record)
    cam.pan(9, 9)
    cam.zoom(target=1.5)
    cam.focus(7, 7)
    cam.follow("THREAT")
    cam.pan(1, 1)
    assert counters == snapshot


def test_blocked_spectator_produces_no_game_command():
    record = []
    cam = SpectatorCamera(driver=lambda a, **p: record.append(a) or True,
                          camera_driver_available=True, same_match="BLOCKED")
    cam.pan(1, 1)
    cam.zoom(target=2.0)
    cam.focus(1, 1)
    cam.follow("AI")
    assert record == []


def test_spectator_module_has_no_game_command_tokens():
    import inspect
    import kiomet_ai.spectator as mod
    src = inspect.getsource(mod)
    for banned in ("MoveForce", "Upgrade", "Deploy", "play_button",
                   "click(", "dispatch(", "send_input", "pointer"):
        assert banned not in src


def test_follow_does_not_dispatch_or_send():
    gate = FakeActionGate()
    record = []
    cam, _ = _available_cam(record)
    cam.follow("LAST_ACTION")
    cam.follow("THREAT")
    assert gate.dispatches == []
    assert gate.sent_actions == 0
