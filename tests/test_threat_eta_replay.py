"""威脅 ETA 公式 vs 真實到達時間回歸（runtime 證據重播）。

證據：runtime/research/forces/muse-threat-eta-001.json（match
m1-1790631842，3 波 inbound 攻 SELF 塔，owner_id=17）。
本檔內嵌最小 fixture，無 runtime 目錄依賴。

成功證據：以首樣本 progress＋真實世界距離重算 predicted arrival，
與最後觀測（消失）時間殘差 <= 輪詢容差 2.0 秒；
Tank（speed=1）與 Soldier（speed=2）兩分支都要被覆蓋。
失敗證據：任一波殘差超容差，或公式對該分支回 None。
"""
import math

from kiomet_ai.force import ForceUnits, eta_ticks, unit_speed

# 內嵌證據：src/dst world 座標（anchor verified-anchor-current.json）
SRC_XY = (1382.0, 1288.0)
DST_XY = (1387.0, 1287.0)
DIST = math.hypot(DST_XY[0] - SRC_XY[0], DST_XY[1] - SRC_XY[1])

# 3 波真實觀測（first_t, first_progress, last_seen, units）
WAVES = [
    {"name": "tank_wave", "first_t": 1790633575.9, "first_p": 3,
     "last_seen": 1790633597.0316818, "speed": 1,
     "units": {"Soldier": 14, "Tank": 1}},
    {"name": "soldier_wave_a", "first_t": 1790633579.3, "first_p": 0,
     "last_seen": 1790633589.0665905, "speed": 2,
     "units": {"Soldier": 12}},
    {"name": "soldier_wave_b", "first_t": 1790633651.8, "first_p": 12,
     "last_seen": 1790633660.2827582, "speed": 2,
     "units": {"Soldier": 12}},
]

TICK_SECONDS = 0.25
POLL_TOLERANCE_S = 2.0  # 輪詢間隔 1.5s + 取整


def _units(wave: dict) -> ForceUnits:
    counts = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                             "Tank", "Soldier", "Shell", "Emp", "Nuke",
                             "Ruler")}
    counts.update(wave["units"])
    return ForceUnits(tag=0, counts=counts)


def test_recorded_waves_cover_both_speed_branches():
    speeds = {w["speed"] for w in WAVES}
    assert speeds == {1, 2}
    for w in WAVES:
        assert unit_speed(_units(w)) == w["speed"]


def test_eta_formula_predicts_real_arrival_within_poll_tolerance():
    residuals = []
    for w in WAVES:
        ticks = eta_ticks(w["first_p"], w["speed"], DIST, 0)
        assert ticks is not None, w["name"]
        predicted = w["first_t"] + ticks * TICK_SECONDS
        residual = w["last_seen"] - predicted
        residuals.append(residual)
        assert abs(residual) <= POLL_TOLERANCE_S, (
            f"{w['name']} residual {residual:.2f}s exceeds tolerance")
    # 系統性負殘差 = 觀測在預測前一個輪詢內結束，屬預期方向
    assert all(r <= 0.5 for r in residuals)


def test_eta_monotonic_in_remaining_progress():
    """同一波內 progress 越高，剩餘 ETA 越短（公式單調）。"""
    low = eta_ticks(3, 1, DIST, 0)
    high = eta_ticks(80, 1, DIST, 0)
    assert low is not None and high is not None
    assert high < low


def test_eta_rejects_invalid_inputs_without_fabricating_ticks():
    assert eta_ticks(-1, 1, DIST, 0) is None
    assert eta_ticks(True, 1, DIST, 0) is None      # bool 不是 int 語意
    assert eta_ticks(10, 0, DIST, 0) is None        # speed 非法
    assert eta_ticks(10, 1, -5.0, 0) is None        # 距離非法
