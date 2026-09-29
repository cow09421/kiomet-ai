"""觀戰前端誠實契約回歸（P0 §14）。

JS 模組：正確 API 路徑、誠實標籤、無假 CSS 平移、
圖片縮放僅在 IMAGE_ONLY 且有標示。
"""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1]
      / "src" / "kiomet_ai" / "dashboard" / "spectator.js").read_text(
    encoding="utf-8")


def test_api_paths_present():
    for path in ("/api/spectator/status", "/api/spectator/pan",
                 "/api/spectator/zoom", "/api/spectator/focus",
                 "/api/spectator/follow"):
        assert path in JS


def test_honest_labels_present():
    assert "REAL CAMERA" in JS
    assert "IMAGE ONLY" in JS
    assert "SPECTATOR UNAVAILABLE" in JS
    assert "IMAGE ZOOM ONLY" in JS


def _function_body(name):
    marker = "function " + name + "("
    start = JS.find(marker)
    if start < 0:
        marker = "async function " + name + "("
        start = JS.find(marker)
    assert start >= 0, name
    depth = 0
    began = False
    for i in range(start, len(JS)):
        ch = JS[i]
        if ch == "{":
            depth += 1
            began = True
        elif ch == "}":
            depth -= 1
            if began and depth == 0:
                return JS[start:i + 1]
    raise AssertionError("unterminated " + name)


def test_pan_never_uses_css_transform():
    """假平移被禁止：pan 函式不得出現 transform／style。"""
    body = _function_body("pan")
    assert "transform" not in body
    assert "style" not in body


def test_zoom_never_uses_css_transform():
    body = _function_body("zoom")
    assert "transform" not in body


def test_pan_checks_availability_before_calling_api():
    body = _function_body("pan")
    assert "status.available" in body
    assert "SPECTATOR_UNAVAILABLE" in body


def test_image_zoom_guarded_and_labeled():
    body = _function_body("imageZoom")
    assert "IMAGE_ONLY" in body
    assert "IMAGE_ZOOM_ONLY" in body
    assert "transform" in body


def test_real_camera_label_only_when_available():
    assert "st.available" in JS
    assert "BLOCKED" in JS
