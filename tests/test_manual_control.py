"""人工控制輸入橋接回歸（P0）。

只有 HUMAN 能送頁面輸入；AI/REACQUIRING/NONE 被拒；
pan/wheel/drag 產生真實頁面事件；無假 CSS 平移。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.control_owner import ControlOwner
from kiomet_ai.manual_control import ManualControl, plan


class FakeMouse:
    def __init__(self, log):
        self.log = log

    def move(self, x, y): self.log.append(("move", x, y))
    def down(self): self.log.append(("down",))
    def up(self): self.log.append(("up",))
    def click(self, x, y): self.log.append(("click", x, y))
    def wheel(self, dx, dy): self.log.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def press(self, key): self.log.append(("press", key))


class FakePage:
    def __init__(self):
        self.log = []
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)


def _human():
    owner = ControlOwner()
    owner.request_manual()
    return owner


def test_plan_pan_is_move_sequence():
    ops = plan("drag", x1=10, y1=20, x2=30, y2=40)
    assert [o["method"] for o in ops] == ["move", "down", "move", "up"]


def test_plan_wheel():
    assert plan("wheel", dx=0, dy=120) == [
        {"target": "mouse", "method": "wheel", "args": [0.0, 120.0]}]


def test_plan_click_and_key():
    assert plan("click", x=5, y=6)[0]["method"] == "click"
    assert plan("key", key="ArrowUp") == [
        {"target": "keyboard", "method": "press", "args": ["ArrowUp"]}]


def test_plan_bad_input_empty():
    assert plan("move", x="a", y=1) == []
    assert plan("key", key="") == []
    assert plan("warp") == []


def test_manual_pan_sends_real_page_input():
    page = FakePage()
    ctl = ManualControl(page=page, owner=_human())
    result = ctl.handle("drag", x1=1, y1=2, x2=3, y2=4)
    assert result["ok"] is True
    assert page.log == [("move", 1.0, 2.0), ("down",), ("move", 3.0, 4.0),
                        ("up",)]


def test_manual_wheel_sends_real_page_input():
    page = FakePage()
    ctl = ManualControl(page=page, owner=_human())
    ctl.handle("wheel", dx=0, dy=240)
    assert ("wheel", 0.0, 240.0) in page.log


def test_ai_owner_blocks_manual_input():
    page = FakePage()
    ctl = ManualControl(page=page, owner=ControlOwner())  # AI
    result = ctl.handle("click", x=1, y=1)
    assert result["ok"] is False
    assert result["code"] == "MANUAL_NOT_ALLOWED"
    assert page.log == []


def test_reacquiring_blocks_manual_input():
    owner = _human()
    owner.request_return_to_ai()
    page = FakePage()
    ctl = ManualControl(page=page, owner=owner)
    assert ctl.handle("move", x=1, y=1)["code"] == "MANUAL_NOT_ALLOWED"


def test_no_page_returns_no_page():
    ctl = ManualControl(page=None, owner=_human())
    assert ctl.handle("move", x=1, y=1)["code"] == "NO_PAGE"


def test_page_error_counted_not_faked():
    class BadMouse:
        def move(self, x, y): raise RuntimeError("boom")
    class BadPage:
        mouse = BadMouse()
        keyboard = FakeKeyboard([])
    ctl = ManualControl(page=BadPage(), owner=_human())
    result = ctl.handle("move", x=1, y=1)
    assert result["ok"] is False
    assert result["code"] == "PAGE_INPUT_ERROR"
    assert ctl.errors == 1


def test_module_has_no_physical_input_tokens():
    import inspect
    import kiomet_ai.manual_control as mod
    src = inspect.getsource(mod)
    for banned in ("pyautogui", "SendInput", "pynput", "SwitchDesktop",
                   "SetCursorPos", "style.transform"):
        assert banned not in src


def test_fake_css_pan_not_used():
    """橋接只送頁面事件，不做圖片 transform。"""
    import inspect
    import kiomet_ai.manual_control as mod
    src = inspect.getsource(mod)
    assert "transform" not in src
