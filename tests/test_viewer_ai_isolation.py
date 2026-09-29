"""LIVE VIEW（即時觀戰）顯示操作必須與 AI 執行狀態隔離。"""
import re
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
            encoding="utf-8")
VIEWER_START = "// ===== 觀戰器狀態（只存前端，幀更新不重設） ====="
VIEWER_END = "// ===== 戰術圖 ====="
start = HTML.index(VIEWER_START)
end = HTML.index(VIEWER_END, start)
VIEWER_CODE = HTML[start:end]


def _handler(source: str, element_id: str) -> str:
    marker = f"$('{element_id}').onclick="
    start = source.find(marker)
    assert start >= 0, f"missing handler for {element_id}"
    start += len(marker)
    braces = parens = brackets = 0
    quote = None
    escaped = False
    for pos in range(start, len(source)):
        char = source[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == ";" and braces == parens == brackets == 0:
            return source[start:pos]
    raise AssertionError(f"unterminated handler for {element_id}")


def _assert_frontend_only(source: str):
    # 這些操作只能變更 DOM／觀戰器狀態，不可觸及 AI 或遊戲控制介面。
    forbidden = re.compile(
        r"fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|/api/|"
        r"camera|executor|execute_move|sendInput|SendInput|"
        r"sent_actions|live_authorization|currentState",
        re.IGNORECASE,
    )
    assert forbidden.search(source) is None


def test_pan_zoom_and_reset_only_change_viewer_transform():
    _assert_frontend_only(VIEWER_CODE)
    assert "viewer.panX" in VIEWER_CODE
    assert "viewer.panY" in VIEWER_CODE
    assert "viewer.zoom" in VIEWER_CODE
    assert "applyGameTransform()" in VIEWER_CODE
    assert "img.style.transform" in VIEWER_CODE
    assert "setPointerCapture" in VIEWER_CODE


def test_fullscreen_only_targets_dashboard_game_viewer():
    handler = _handler(VIEWER_CODE, "frame-fullscreen")
    _assert_frontend_only(handler)
    assert "$('game-viewer')" in handler
    assert "requestFullscreen" in handler
    assert "document.exitFullscreen()" in handler


def test_mode_switches_only_change_dashboard_visibility_and_canvas():
    mode_handler = re.search(
        r"function setViewMode\(m\)\{(.*?)\}\n\$\('mode-game'\)",
        VIEWER_CODE, re.DOTALL)
    assert mode_handler is not None
    _assert_frontend_only(mode_handler.group(1))
    assert "viewer.mode=m" in mode_handler.group(1)
    assert "style.display" in mode_handler.group(1)
    assert "drawTactical()" in mode_handler.group(1)
    for element_id, mode in (("mode-game", "GAME"),
                             ("mode-tactical", "TACTICAL"),
                             ("mode-split", "SPLIT")):
        assert f"$('{element_id}').onclick=()=>setViewMode('{mode}')" in VIEWER_CODE


def test_follow_toggle_changes_dashboard_follow_state_only():
    handler = _handler(VIEWER_CODE, "follow-ai")
    _assert_frontend_only(handler)
    assert "viewer.follow" in handler
    assert "tac.follow" in handler
    assert "textContent" in handler


def test_display_controls_remain_separate_from_pause_and_watch_commands():
    _assert_frontend_only(VIEWER_CODE)
    assert 'button[data-command]' not in VIEWER_CODE
    assert "watch-toggle" not in VIEWER_CODE
