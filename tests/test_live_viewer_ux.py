"""Live View 觀戰器 UX 回歸（P0 §5-6）。

縮放範圍 25%～800%；雙擊＝快速放大（非重置）；
Fullscreen API＋Esc 原生退出＋退出全螢幕按鈕文字；
新 frame 到達只換圖片，不重置 zoom/pan/follow。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_zoom_range_25_to_800_percent():
    assert "Math.min(8,Math.max(0.25," in HTML


def test_zoom_buttons_use_same_range():
    assert "viewer.zoom=Math.min(8,viewer.zoom*1.25)" in HTML
    assert "viewer.zoom=Math.max(0.25,viewer.zoom/1.25)" in HTML


def test_dblclick_is_zoom_in_not_reset():
    assert "Math.min(8,viewer.zoom*1.5)" in HTML


def test_fullscreen_button_and_exit_label():
    assert 'id="frame-fullscreen"' in HTML
    assert "fullscreenchange" in HTML
    assert "退出全螢幕" in HTML


def test_esc_not_hacked_f11_untouched():
    """Fullscreen API 原生 Esc；不攔截 F11。"""
    assert "requestFullscreen" in HTML
    assert "document.exitFullscreen" in HTML
    assert "F11" not in HTML


def test_frame_update_never_resets_viewer_state():
    """nextFrame 只換圖片；不得出現 viewer.zoom=/panX=/follow= 重設。"""
    start = HTML.find("async function nextFrame()")
    end = HTML.find("const viewer={", start)
    body = HTML[start:end]
    assert "viewer.zoom=" not in body
    assert "viewer.panX=" not in body
    assert "viewer.panY=" not in body
    assert "viewer.follow=" not in body


def test_pan_zoom_separate_from_ai_canvas():
    """觀戰器狀態只存前端（viewer/tac 物件），不觸及 AI camera。"""
    assert "const viewer={zoom:1,panX:0,panY:0,follow:false,mode:'GAME'}" in \
        HTML
