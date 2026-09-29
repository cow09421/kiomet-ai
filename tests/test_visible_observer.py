"""可見畫面候選解析測試；合成圖片不代表任何真實對局證據。"""
import asyncio
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.browser import BrowserHost
from kiomet_ai.visible_observer import (
    detect_visible_color_candidates,
    track_persistent_visible_candidates,
)


def _chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def _png(width, height, pixels):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y][x])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(bytes(raw)))
            + _chunk(b"IEND", b""))


def _synthetic_map():
    width, height = 220, 60
    pixels = [[(24, 28, 38) for _ in range(width)]
              for _ in range(height)]
    for y in range(8, 23):
        for x in range(10, 25):
            pixels[y][x] = (116, 185, 255)
    for y in range(30, 45):
        for x in range(55, 70):
            pixels[y][x] = (192, 57, 43)
    # Small troop-like specks and dim territory color stay below the
    # conservative visual-candidate thresholds.
    for y in range(8, 16):
        for x in range(90, 98):
            pixels[y][x] = (192, 57, 43)
    for y in range(30, 50):
        for x in range(120, 140):
            pixels[y][x] = (50, 80, 115)
    # 長邊界應被形狀與面積閘門排除。
    for x in range(5, 205):
        pixels[55][x] = (192, 57, 43)
    return _png(width, height, pixels)


def test_detector_returns_compact_pixel_candidates_only():
    result = detect_visible_color_candidates(_synthetic_map())

    assert result["status"] == "CANDIDATES_ONLY"
    assert result["source"] == "VISIBLE_PLAYWRIGHT_CANVAS_PNG"
    assert result["actionable"] is False
    assert len(result["markers"]) == 2
    assert [row["color_tone"] for row in result["markers"]] == [
        "BLUE_TONE", "RED_TONE"]
    assert all(row["kind"] == "VISUAL_MARKER_CANDIDATE"
               for row in result["markers"])
    assert all("tower_id" not in row and "owner" not in row
               and "units" not in row and "adjacency" not in row
               for row in result["markers"])


def test_candidate_detector_is_not_wired_to_live_dispatch():
    controller = (Path(__file__).resolve().parents[1]
                  / "src" / "kiomet_ai" / "live_controller.py").read_text(
                      encoding="utf-8")
    assert "visible_observer" not in controller
    assert "detect_visible_color_candidates" not in controller


@pytest.mark.parametrize("invalid", [b"", b"not-an-image"])
def test_detector_rejects_non_png_input(invalid):
    with pytest.raises(ValueError, match="Playwright canvas PNG"):
        detect_visible_color_candidates(invalid)


def test_detector_rejects_oversized_canvas_before_decoding():
    header = struct.pack(">IIBBBBB", 5000, 2000, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
           + _chunk(b"IDAT", zlib.compress(b""))
           + _chunk(b"IEND", b""))
    with pytest.raises(ValueError, match="尺寸超出觀察上限"):
        detect_visible_color_candidates(png)


def test_browser_captures_only_one_visible_canvas_in_memory():
    class Locator:
        def __init__(self):
            self.options = None

        async def count(self):
            return 1

        @property
        def first(self):
            return self

        async def is_visible(self):
            return True

        async def screenshot(self, **options):
            self.options = options
            return b"png-bytes"

    class Page:
        def __init__(self):
            self.canvas = Locator()

        def is_closed(self):
            return False

        def locator(self, selector):
            assert selector == "canvas"
            return self.canvas

    host = BrowserHost.__new__(BrowserHost)
    host.game_page = Page()
    guards = []
    host.guard = lambda: guards.append(True)

    png = asyncio.run(host.capture_visible_canvas_png())

    assert png == b"png-bytes"
    assert host.game_page.canvas.options == {"type": "png", "timeout": 5000}
    assert len(guards) == 2


def test_browser_rejects_ambiguous_canvas_count():
    class Locator:
        async def count(self):
            return 2

    class Page:
        def is_closed(self):
            return False

        def locator(self, _selector):
            return Locator()

    host = BrowserHost.__new__(BrowserHost)
    host.game_page = Page()
    host.guard = lambda: None

    with pytest.raises(RuntimeError, match="可見畫布數量未知"):
        asyncio.run(host.capture_visible_canvas_png())


def _candidate(tone, x, y):
    return {
        "color_tone": tone,
        "center_px": [x, y],
        "bounds_px": [int(x) - 2, int(y) - 2, 5, 5],
        "colored_pixels": 150,
        "fill_ratio": 0.8,
        "kind": "VISUAL_MARKER_CANDIDATE",
    }


def _candidate_frame(markers, *, width=100, height=80, source="fixture"):
    return {
        "status": "CANDIDATES_ONLY",
        "source": source,
        "width": width,
        "height": height,
        "markers": markers,
        "actionable": False,
    }


def test_temporal_tracker_keeps_only_repeated_pixel_candidates():
    frames = [
        _candidate_frame([
            _candidate("BLUE_TONE", 20, 20),
            _candidate("RED_TONE", 60, 30),
            _candidate("RED_TONE", 10, 10),
        ]),
        _candidate_frame([
            _candidate("BLUE_TONE", 21, 19),
            _candidate("RED_TONE", 61, 31),
            _candidate("RED_TONE", 40, 10),
        ]),
        _candidate_frame([
            _candidate("BLUE_TONE", 19, 22),
            _candidate("RED_TONE", 59, 31),
            _candidate("RED_TONE", 70, 10),
        ]),
        _candidate_frame([
            _candidate("BLUE_TONE", 20, 21),
            _candidate("RED_TONE", 62, 29),
            _candidate("RED_TONE", 90, 10),
        ]),
    ]

    result = track_persistent_visible_candidates(
        frames, min_hits=3, tolerance_px=4)

    assert result["status"] == "CANDIDATES_ONLY"
    assert result["actionable"] is False
    assert result["frame_count"] == 4
    assert [(row["color_tone"], row["persistence_frames"])
            for row in result["markers"]] == [
                ("BLUE_TONE", 4), ("RED_TONE", 4)]
    assert all("owner" not in row and "tower_id" not in row
               and "units" not in row and "adjacency" not in row
               for row in result["markers"])


def test_temporal_tracker_never_reuses_one_frame_candidate_for_two_tracks():
    frames = [
        _candidate_frame([_candidate("RED_TONE", 20, 20),
                          _candidate("RED_TONE", 26, 20)]),
        _candidate_frame([_candidate("RED_TONE", 23, 20)]),
        _candidate_frame([_candidate("RED_TONE", 23, 20)]),
    ]

    result = track_persistent_visible_candidates(
        frames, min_hits=3, tolerance_px=4)

    assert result["frame_count"] == 3
    assert len(result["markers"]) == 1
    assert result["markers"][0]["persistence_frames"] == 3


@pytest.mark.parametrize("frames", [
    [_candidate_frame([_candidate("BLUE_TONE", 10, 10)])],
    [_candidate_frame([]), _candidate_frame([], width=101)],
    [_candidate_frame([]), {
        **_candidate_frame([]), "status": "UNKNOWN",
    }],
])
def test_temporal_tracker_fails_closed_on_insufficient_or_inconsistent_frames(
        frames):
    result = track_persistent_visible_candidates(frames)

    assert result["status"] == "UNKNOWN"
    assert result["actionable"] is False
    assert result["markers"] == []


@pytest.mark.parametrize("kwargs", [
    {"min_hits": 1},
    {"min_hits": True},
    {"tolerance_px": -1},
    {"tolerance_px": float("nan")},
])
def test_temporal_tracker_rejects_invalid_thresholds(kwargs):
    frames = [_candidate_frame([]), _candidate_frame([])]
    with pytest.raises(ValueError):
        track_persistent_visible_candidates(frames, **kwargs)


def test_temporal_tracker_returns_unknown_when_required_hits_are_unavailable():
    frames = [_candidate_frame([]), _candidate_frame([])]

    result = track_persistent_visible_candidates(frames, min_hits=3)

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "insufficient-frames"
    assert result["markers"] == []
