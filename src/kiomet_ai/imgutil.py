"""imgutil（影像工具）：只用標準庫的 PNG 解碼＋畫面比對。

用途：RealMoveProbe（真實調兵探針）區分 CAMERA_PAN（地圖平移）
與 MOVE_FORCE（局部部隊移動）。不做 OCR（文字辨識），只做像素統計，
並一律回報信心ados（此處為數值證據，非機率）。
"""
from __future__ import annotations

import struct
import zlib


def decode_png(data: bytes) -> tuple[int, int, bytearray]:
    """回 (寬, 高, RGB 位元組)。只支援 8-bit 真彩／RGBA。"""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "非 PNG"
    pos, width, height, depth, ctype, idat = 8, 0, 0, 0, 0, b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", chunk[:10])
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + length
    if depth != 8 or ctype not in (2, 6):
        raise ValueError(f"不支援的 PNG：depth={depth} ctype={ctype}")
    channels = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = width * channels
    out = bytearray(width * height * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        filtr = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if filtr == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif filtr == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif filtr == 3:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif filtr == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        for x in range(width):
            o = (y * width + x) * 3
            s = x * channels
            out[o], out[o + 1], out[o + 2] = line[s], line[s + 1], line[s + 2]
        prev = line
    return width, height, out


def luminance_grid(rgb: bytearray, width: int, height: int,
                   cols: int = 80, rows: int = 45) -> list[list[float]]:
    """降採樣亮度網格（網格平均），供平移估計與變化統計。"""
    grid = [[0.0] * cols for _ in range(rows)]
    counts = [[0] * cols for _ in range(rows)]
    for y in range(height):
        gy = min(rows - 1, y * rows // height)
        for x in range(width):
            gx = min(cols - 1, x * cols // width)
            o = (y * width + x) * 3
            grid[gy][gx] += 0.299 * rgb[o] + 0.587 * rgb[o + 1] + 0.114 * rgb[o + 2]
            counts[gy][gx] += 1
    for y in range(rows):
        for x in range(cols):
            if counts[y][x]:
                grid[y][x] /= counts[y][x]
    return grid


def estimate_shift(before: list[list[float]], after: list[list[float]],
                   max_shift: int = 6) -> tuple[int, int, float, float]:
    """暴力搜尋整體平移 (dx, dy)（格點單位）。回 (dx, dy, 零位移 SAD, 最佳 SAD)。

    若最佳位移非零且明顯優於零位移 → 整張圖一起動 = CAMERA_PAN 嫌疑。
    """
    rows, cols = len(before), len(before[0])
    best = (0, 0, float("inf"))
    zero = None
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            sad, n = 0.0, 0
            for y in range(max(0, -dy), min(rows, rows - dy)):
                row_b, row_a = before[y], after[y + dy]
                for x in range(max(0, -dx), min(cols, cols - dx)):
                    sad += abs(row_b[x] - row_a[x + dx])
                    n += 1
            sad = sad / max(1, n)
            if dx == 0 and dy == 0:
                zero = sad
            if sad < best[2]:
                best = (dx, dy, sad)
    return best[0], best[1], zero or 0.0, best[2]


def corridor_change(before: list[list[float]], after: list[list[float]],
                    p0: tuple[float, float], p1: tuple[float, float],
                    width: int, height: int, radius_px: float = 60.0,
                    thresh: float = 25.0) -> dict:
    """走廊內外變化比：路徑走廊內變化多、走廊外變化少 → 局部部隊移動。

    p0/p1 為像素座標；回傳走廊內／外變化比例與像素數。
    """
    rows, cols = len(before), len(before[0])
    x0, y0, x1, y1 = p0[0], p0[1], p1[0], p1[1]
    dx, dy = x1 - x0, y1 - y0
    seg = (dx * dx + dy * dy) ** 0.5 or 1.0
    inside_changed = inside_total = outside_changed = outside_total = 0
    for gy in range(rows):
        for gx in range(cols):
            px = (gx + 0.5) * width / cols
            py = (gy + 0.5) * height / rows
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (seg * seg)))
            cx, cy = x0 + t * dx, y0 + t * dy
            dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            changed = abs(before[gy][gx] - after[gy][gx]) > thresh
            if dist <= radius_px:
                inside_total += 1
                inside_changed += changed
            else:
                outside_total += 1
                outside_changed += changed
    return {
        "inside_frac": inside_changed / max(1, inside_total),
        "outside_frac": outside_changed / max(1, outside_total),
        "inside_n": inside_total, "outside_n": outside_total,
    }
