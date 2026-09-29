"""人工控制前端誠實契約回歸（P0）。"""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1]
      / "src" / "kiomet_ai" / "dashboard" / "manual_control.js").read_text(
    encoding="utf-8")


def test_modes_present():
    assert "AI VIEW" in JS
    assert "MANUAL CONTROL" in JS
    assert "RETURN TO AI" in JS


def test_api_paths_present():
    for p in ("/api/control/status", "/api/control/manual",
              "/api/control/return-to-ai", "/api/control/input"):
        assert p in JS


def test_return_states_present():
    assert "REACQUIRING CAMERA" in JS
    assert "REACQUIRING WORLD" in JS
    assert "AUTONOMY RESUMED" in JS
    assert "READY" in JS


def test_forwards_pointer_wheel_click():
    assert "onPointerDown" in JS
    assert "onPointerMove" in JS
    assert "onPointerUp" in JS
    assert "onWheel" in JS
    assert 'send("wheel"' in JS
    assert 'send("move"' in JS
    assert 'send("down"' in JS
    assert 'send("up"' in JS


def test_no_css_fake_pan():
    """禁止以 transform 平移冒充攝影機。"""
    assert "style.transform" not in JS
    assert "translate(" not in JS


def test_gated_by_human_owner():
    assert "state.owner === \"HUMAN\"" in JS or \
        "state.owner==='HUMAN'" in JS or "canInput" in JS


def test_fullscreen_api_used():
    assert "requestFullscreen" in JS
    assert "document.exitFullscreen" in JS


def test_no_physical_input_libs():
    for banned in ("pyautogui", "SendInput", "pynput", "SwitchDesktop"):
        assert banned not in JS
