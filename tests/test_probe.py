import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai import imgutil
from kiomet_ai.browser import BrowserHost


def make_png(width, height, pixels):
    """pixels: 高 x 寬 x RGB；filter 0 裸寫。"""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes(pixels[y][x])
    idat = zlib.compress(bytes(raw))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(
            ">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def flat_grids(width=160, height=90, shift=(0, 0), blot=None):
    """合成亮度網格：非週期雜湊底圖＋可選平移＋可選局部亮斑。"""
    def base(x, y):
        return float((x * 73856093 ^ y * 19349663) % 200)
    before = [[base(x, y) for x in range(width)] for y in range(height)]
    after = [[base(x - shift[0], y - shift[1])
              if 0 <= x - shift[0] < width and 0 <= y - shift[1] < height
              else 0.0 for x in range(width)] for y in range(height)]
    if blot:
        (bx, by, r) = blot
        for y in range(height):
            for x in range(width):
                if (x - bx) ** 2 + (y - by) ** 2 < r * r:
                    after[y][x] = min(255.0, after[y][x] + 120.0)
    return before, after


def test_decode_roundtrip():
    pixels = [[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (10, 20, 30)]]
    width, height, rgb = imgutil.decode_png(make_png(2, 2, pixels))
    assert (width, height) == (2, 2)
    assert (rgb[0], rgb[1], rgb[2]) == (255, 0, 0)
    assert (rgb[9], rgb[10], rgb[11]) == (10, 20, 30)


def test_estimate_shift_detects_pan():
    before, after = flat_grids(shift=(4, 0))
    dx, dy, zero, best = imgutil.estimate_shift(before, after)
    assert (dx, dy) == (4, 0)
    assert best < 0.6 * zero


def test_estimate_shift_static():
    before, after = flat_grids()
    dx, dy, _, _ = imgutil.estimate_shift(before, after)
    assert (dx, dy) == (0, 0)


def test_corridor_localizes_change():
    W = H = 100
    before = [[50.0] * 20 for _ in range(20)]
    after = [row[:] for row in before]
    for y in range(9, 12):
        for x in range(5, 16):
            after[y][x] = 150.0
    corr = imgutil.corridor_change(before, after, (20, 50), (80, 50), W, H,
                                   radius_px=12.0)
    assert corr["inside_frac"] > 3 * corr["outside_frac"]
    assert corr["inside_frac"] > 0.3


def test_classify_pan_vs_success():
    before, panned = flat_grids(shift=(5, 0))
    verdict = BrowserHost._classify_drag(before, before, before, panned,
                                         (10, 10), (90, 10), 100, 100)
    assert verdict["result"] == "FAILED_CAMERA_PAN"
    static = [row[:] for row in before]
    blot_on_path = [row[:] for row in static]
    for y in range(40, 50):
        for x in range(40, 120):
            blot_on_path[y][x] = min(255.0, blot_on_path[y][x] + 120.0)
    verdict = BrowserHost._classify_drag(before, before, blot_on_path,
                                         blot_on_path, (40, 45), (120, 45),
                                         160, 90)
    assert verdict["result"] in ("SUCCESS", "UNKNOWN")


def test_render_centroid_finds_blob():
    base = [[50.0] * 20 for _ in range(20)]
    mid = [row[:] for row in base]
    for y in range(8, 12):
        for x in range(10, 14):
            mid[y][x] = 200.0
    centroid = BrowserHost._render_centroid(base, mid, 20, 20, 100, 100)
    assert centroid is not None
    # blob 中心約 (11.5, 9.5) 格 → 像素 (57.5, 47.5)。
    assert abs(centroid[0] - 57.5) < 6 and abs(centroid[1] - 47.5) < 6
    assert BrowserHost._render_centroid(base, base, 20, 20, 100, 100) is None


def test_classify_dst_weighted_success():
    before, _ = flat_grids()
    after1 = [row[:] for row in before]
    after2 = [row[:] for row in before]
    # 終點附近持續移動（after1→after2），其他區域靜止。
    for y in range(70, 85):
        for x in range(130, 155):
            after2[y][x] = min(255.0, after2[y][x] + 120.0)
    verdict = BrowserHost._classify_drag(before, before, after1, after2,
                                         (10, 75), (150, 75), 160, 90)
    assert verdict["result"] == "SUCCESS"
    assert verdict["evidence"]["dst_motion"] > 0.02
