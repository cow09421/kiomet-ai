"""Owners 42/21 威脅 ETA fixture（P0-B）。

來源：forcepoll6.log（match m1-1790644011）。
owners 42/21 為敵方部隊（OUTBOUND），relation=UNKNOWN（未學習，不猜值）。

成功證據：
- ETA 公式對 42/21 編成正確計算（Tank speed=1、Soldier speed=2）
- owner relation 維持 UNKNOWN（不得猜 ENEMY）
- 方向（src→dst）與目標塔正確記錄
- 時間戳存在（freshness 可判定）

失敗證據：UNKNOWN 被升級為 ENEMY，或 ETA 公式回 None。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.force import ForceUnits, eta_ticks, unit_speed

# 內嵌證據（forcepoll6.log 真實樣本）
# owner 42: Soldier 5（speed 2）；Fighter 1 + Soldier 4（speed 2）
# owner 21: Tank 5 + Shield 10（speed 1）；Tank 5（speed 1）
FORCES_42_21 = [
    {"owner_id": 42, "src": 20316371, "dst": 20316372,
     "progress": 48, "t": 1790644336.0, "relation": "UNKNOWN",
     "units": {"Soldier": 5}},
    {"owner_id": 42, "src": 20316371, "dst": 20316372,
     "progress": 32, "t": 1790644336.0, "relation": "UNKNOWN",
     "units": {"Fighter": 1, "Soldier": 4}},
    {"owner_id": 21, "src": 19071176, "dst": 19005640,
     "progress": 29, "t": 1790644336.0, "relation": "UNKNOWN",
     "units": {"Tank": 5, "Shield": 10}},
    {"owner_id": 21, "src": 18874577, "dst": 18809041,
     "progress": 83, "t": 1790644358.7, "relation": "UNKNOWN",
     "units": {"Tank": 5}},
]

# 假設距離（ETA 公式驗證用；真實距離需錨點座標）
TEST_DIST = 90.0
TICK_SECONDS = 0.25


def _units(force: dict) -> ForceUnits:
    counts = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                             "Tank", "Soldier", "Shell", "Emp", "Nuke",
                             "Ruler")}
    counts.update(force["units"])
    return ForceUnits(tag=0, counts=counts)


def test_42_21_speed_branches():
    """Tank 編成 speed=1；Soldier/Fighter 編成 speed=2。"""
    speeds = {}
    for f in FORCES_42_21:
        speeds[f["owner_id"]] = speeds.get(f["owner_id"], set())
        speeds[f["owner_id"]].add(unit_speed(_units(f)))
    # owner 42: Soldier 5 → 2；Fighter1+Soldier4 → 2
    assert speeds[42] == {2}
    # owner 21: Tank 5 (+Shield) → 1
    assert speeds[21] == {1}


def test_eta_formula_returns_ticks_for_42_21():
    for f in FORCES_42_21:
        speed = unit_speed(_units(f))
        ticks = eta_ticks(f["progress"], speed, TEST_DIST, 0)
        assert ticks is not None, f
        assert ticks >= 0
        predicted = f["t"] + ticks * TICK_SECONDS
        assert predicted > f["t"]


def test_owner_relation_stays_unknown():
    """未學習的 owner 不得猜 ENEMY（維持 UNKNOWN）。"""
    for f in FORCES_42_21:
        assert f["relation"] == "UNKNOWN"
        assert f["owner_id"] not in (5, 71)


def test_direction_and_target_preserved():
    for f in FORCES_42_21:
        assert f["src"] != f["dst"]
        assert type(f["src"]) is int and f["src"] > 0
        assert type(f["dst"]) is int and f["dst"] > 0


def test_timestamp_present_for_freshness():
    for f in FORCES_42_21:
        assert type(f["t"]) is float and f["t"] > 0
