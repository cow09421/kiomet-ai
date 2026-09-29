"""只讀分析 Kiomet 可見畫面；輸出色彩群集候選，不輸出遊戲狀態。

候選來自 Playwright 對單一可見 canvas 的 PNG 截圖。這個模組不推斷
塔 ID、所有者、兵力、鄰接、威脅或可執行動作；候選不可接入派兵管線。
"""
from __future__ import annotations

import math
import struct

from kiomet_ai.imgutil import decode_png

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PIXELS = 8_388_608
MIN_DISPLAY_INTENSITY = 180
MIN_COMPONENT_PIXELS = 150


def _color_tone(r: int, g: int, b: int) -> str | None:
    """以顯示像素的色彩關係標記紅／藍色調，不把它當成玩家身分。"""
    if (r >= MIN_DISPLAY_INTENSITY and r >= g * 1.30
            and r >= b * 1.18):
        return "RED_TONE"
    if (b >= MIN_DISPLAY_INTENSITY and b >= r * 1.15
            and b >= g * 1.10):
        return "BLUE_TONE"
    return None


def _components(mask: bytearray, width: int, height: int,
                tone: str) -> list[dict]:
    visited = bytearray(len(mask))
    markers = []
    for seed, active in enumerate(mask):
        if not active or visited[seed]:
            continue
        visited[seed] = 1
        stack = [seed]
        count = 0
        min_x = width
        min_y = height
        max_x = max_y = 0
        while stack:
            offset = stack.pop()
            x, y = offset % width, offset // width
            count += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                row = ny * width
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row + nx
                    if mask[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)

        box_w, box_h = max_x - min_x + 1, max_y - min_y + 1
        aspect = box_w / box_h
        fill = count / (box_w * box_h)
        # 長邊界、大片區域與稀疏色點不能成為緊湊 marker 候選。
        if (count < MIN_COMPONENT_PIXELS or count > 700
                or box_w < 3 or box_h < 3
                or box_w > 48 or box_h > 48
                or aspect < 0.4 or aspect > 2.5 or fill < 0.08):
            continue
        markers.append({
            "color_tone": tone,
            "center_px": [round((min_x + max_x) / 2, 1),
                          round((min_y + max_y) / 2, 1)],
            "bounds_px": [min_x, min_y, box_w, box_h],
            "colored_pixels": count,
            "fill_ratio": round(fill, 3),
            "kind": "VISUAL_MARKER_CANDIDATE",
        })
    return markers


def detect_visible_color_candidates(png: bytes) -> dict:
    """從可見 canvas PNG 找緊湊的紅／藍色調像素群集。

    回傳值只描述 screenshot（截圖）的像素位置與色調。輸入不合法或尺寸
    超出上限時會拒絕；呼叫者必須把失敗視為 UNKNOWN。
    """
    if not isinstance(png, bytes) or len(png) < 24 or png[:8] != PNG_SIGNATURE:
        raise ValueError("需要 Playwright canvas PNG 畫面")
    width, height = struct.unpack(">II", png[16:24])
    if (width < 1 or height < 1 or width * height > MAX_PIXELS
            or width > 4096 or height > 4096):
        raise ValueError("canvas PNG 尺寸超出觀察上限")
    width, height, rgb = decode_png(png)
    masks = {"RED_TONE": bytearray(width * height),
             "BLUE_TONE": bytearray(width * height)}
    for pixel in range(width * height):
        offset = pixel * 3
        tone = _color_tone(rgb[offset], rgb[offset + 1], rgb[offset + 2])
        if tone is not None:
            masks[tone][pixel] = 1
    markers = []
    for tone, mask in masks.items():
        markers.extend(_components(mask, width, height, tone))
    markers.sort(key=lambda row: (row["center_px"][1],
                                  row["center_px"][0], row["color_tone"]))
    return {
        "status": "CANDIDATES_ONLY",
        "source": "VISIBLE_PLAYWRIGHT_CANVAS_PNG",
        "width": width,
        "height": height,
        "markers": markers,
        "actionable": False,
    }


def track_persistent_visible_candidates(frames: list[dict], *,
                                       min_hits: int = 3,
                                       tolerance_px: float = 4.0) -> dict:
    """Correlate repeated pixel candidates without assigning game meaning.

    All frames must come from the same screenshot source and have the same
    dimensions. A candidate is retained only when a same-tone cluster stays
    within ``tolerance_px`` of its first-frame position in ``min_hits`` frames.
    The result remains non-actionable geometry; it is not a tower or owner map.
    """
    if not isinstance(frames, (list, tuple)) or len(frames) < 2:
        return _unknown_temporal_result("insufficient-frames", frames)
    if (isinstance(min_hits, bool) or not isinstance(min_hits, int)
            or min_hits < 2):
        raise ValueError("min_hits 必須至少為 2")
    if (isinstance(tolerance_px, bool)
            or not isinstance(tolerance_px, (int, float))
            or not math.isfinite(tolerance_px) or tolerance_px < 0):
        raise ValueError("tolerance_px 必須是有限的非負數")

    first = frames[0]
    if not _valid_candidate_frame(first):
        return _unknown_temporal_result("invalid-candidate-frame", frames)
    width, height, source = first["width"], first["height"], first["source"]
    if any(not _valid_candidate_frame(frame)
           or frame["width"] != width
           or frame["height"] != height
           or frame["source"] != source
           for frame in frames):
        return _unknown_temporal_result("inconsistent-candidate-frames", frames)
    if min_hits > len(frames):
        return _unknown_temporal_result("insufficient-frames", frames)

    tracks = []
    used_by_frame = [set() for _ in frames]
    tolerance_squared = tolerance_px * tolerance_px
    for marker in first["markers"]:
        tone = marker["color_tone"]
        anchor = marker["center_px"]
        positions = [anchor]
        for frame_index, frame in enumerate(frames[1:], start=1):
            candidates = frame["markers"]
            choices = [
                (index, candidate)
                for index, candidate in enumerate(candidates)
                if candidate["color_tone"] == tone
                and index not in used_by_frame[frame_index]
            ]
            # Greedy one-to-one nearest match prevents one pixel blob from
            # increasing several candidates' persistence counts.
            available = []
            for index, candidate in choices:
                dx = candidate["center_px"][0] - anchor[0]
                dy = candidate["center_px"][1] - anchor[1]
                distance_squared = dx * dx + dy * dy
                if distance_squared <= tolerance_squared:
                    available.append((distance_squared, index, candidate))
            if available:
                _, match_index, match = min(available, key=lambda item: item[0])
                used_by_frame[frame_index].add(match_index)
                positions.append(match["center_px"])
        if len(positions) < min_hits:
            continue
        tracks.append({
            "color_tone": tone,
            "center_px": [
                round(sum(point[axis] for point in positions) / len(positions), 1)
                for axis in (0, 1)
            ],
            "persistence_frames": len(positions),
            "observed_frames": len(frames),
            "kind": "PERSISTENT_VISUAL_MARKER_CANDIDATE",
        })
    tracks.sort(key=lambda row: (row["center_px"][1],
                                 row["center_px"][0], row["color_tone"]))
    return {
        "status": "CANDIDATES_ONLY",
        "source": "VISIBLE_SCREENSHOT_TEMPORAL_CANDIDATES",
        "width": width,
        "height": height,
        "frame_count": len(frames),
        "markers": tracks,
        "actionable": False,
    }


def _valid_candidate_frame(frame: object) -> bool:
    if not isinstance(frame, dict):
        return False
    if (frame.get("status") != "CANDIDATES_ONLY"
            or frame.get("actionable") is not False
            or not isinstance(frame.get("source"), str)
            or not frame.get("source")):
        return False
    width, height = frame.get("width"), frame.get("height")
    if (isinstance(width, bool) or not isinstance(width, int) or width < 1
            or isinstance(height, bool) or not isinstance(height, int)
            or height < 1 or not isinstance(frame.get("markers"), list)):
        return False
    for marker in frame["markers"]:
        if not isinstance(marker, dict):
            return False
        if marker.get("color_tone") not in ("RED_TONE", "BLUE_TONE"):
            return False
        center = marker.get("center_px")
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            return False
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in center):
            return False
    return True


def _unknown_temporal_result(reason: str, frames: object) -> dict:
    return {
        "status": "UNKNOWN",
        "source": "VISIBLE_SCREENSHOT_TEMPORAL_CANDIDATES",
        "frame_count": len(frames) if isinstance(frames, (list, tuple)) else 0,
        "markers": [],
        "actionable": False,
        "reason": reason,
    }
