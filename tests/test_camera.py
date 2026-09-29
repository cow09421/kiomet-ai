import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import camera_transform as ct

# Ground truth 來自本地 Rust 鏡像（f32，同公式），見 docs/CAMERA_TRANSFORM_GROUND_TRUTH.md。
CASES = [
    ((1334.0, 1427.0), (1300.0, 1400.0), 60.0, (1264.0, 805.0), 1.0, (990.1333, 686.9000)),
    ((0.0, 0.0), (0.0, 0.0), 100.0, (1264.0, 805.0), 1.0, (632.0000, 402.5000)),
    ((1500.5, 999.25), (1400.0, 1000.0), 80.0, (1920.0, 1080.0), 2.0, (1083.0000, 265.5000)),
    ((42.0, 42.0), (42.0, 42.0), 50.0, (1264.0, 805.0), 1.0, (632.0000, 402.5000)),
    ((2000.0, 500.0), (1000.0, 1000.0), 120.0, (1264.0, 805.0), 1.25, (4718.9336, -1784.6667)),
    ((17.5, 88.5), (20.0, 90.0), 25.0, (800.0, 600.0), 1.0, (360.0000, 276.0000)),
    ((1600.0, 1600.0), (1600.0, 1600.0), 10.0, (1264.0, 805.0), 1.0, (632.0000, 402.5000)),
    ((666.0, 777.0), (600.0, 700.0), 77.0, (1152.0, 864.0), 1.0, (1069.7144, 1008.0001)),
]


def test_world_to_client_matches_rust_mirror():
    for w, c, z, v, d, (ex, ey) in CASES:
        x, y = ct.world_to_client(w[0], w[1], c[0], c[1], z, v[0], v[1], d)
        assert abs(x - ex) <= 1.0 and abs(y - ey) <= 1.0, (w, x, y, ex, ey)


def test_client_to_page_flips_y_and_adds_canvas_offset():
    assert ct.client_to_page(100.0, 200.0, 805.0, 10, 20) == (110.0, 625.0)
    assert ct.client_to_page(100.0, 200.0, 805.0) == (100.0, 605.0)


def test_world_to_page_matches_five_visual_tower_centers():
    center = (952.5089721679688, 1207.4920654296875)
    towers = [((949, 1201), (510, 629)), ((954, 1202), (684, 594)),
              ((947, 1207), (440, 420)), ((951, 1206), (579, 455)),
              ((954, 1211), (684, 280))]
    for world, expected in towers:
        actual = ct.world_to_page(*world, *center, 18.125, 1264, 805, 1)
        assert max(abs(a - b) for a, b in zip(actual, expected)) <= 1.5
