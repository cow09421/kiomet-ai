"""威脅證據重播管線回歸（P0-B）。

真實 fixture：forcepoll3.log owner 26 同路由 6 樣本
（16384182→16449718；注意兵種簽名變化＝同路由多支部隊，非單一波）。
合成案例覆蓋：ETA 一致／不一致／未知、過期、多波排序、非法 schema。

UNKNOWN 永不轉成假值；缺記錄 ETA 或缺距離即為 ETA_UNKNOWN。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (replay_threat_waves,
                              validate_threat_snapshot)


def _u(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier", "Shell", "Emp", "Nuke",
                          "Ruler")}
    out.update(kw)
    return out


# 真實樣本：owner 26，路由 16384182→16449718（t 遞增）
REAL_WAVE_26 = [
    {"t": 1790639883.6, "progress": 18,
     "units": _u(Fighter=1, Bomber=1)},
    {"t": 1790641225.3, "progress": 3,
     "units": _u(Shield=10)},
    {"t": 1790641395.4, "progress": 45,
     "units": _u(Shield=10)},
    {"t": 1790641489.1, "progress": 36,
     "units": _u(Bomber=4)},
    {"t": 1790641578.9, "progress": 4,
     "units": _u(Bomber=1, Tank=3)},
    {"t": 1790641578.9, "progress": 0,
     "units": _u(Bomber=1)},
]


def _snap(**over):
    base = {"match_id": "m1-1790639551", "observed_at": 1790641578.9,
            "target_tower_id": 16449718, "threats": []}
    base.update(over)
    return base


def _threat(**over):
    base = {"owner_id": 26, "owner_relation": "UNKNOWN",
            "units": _u(Bomber=1, Tank=3), "progress": 4,
            "speed_flag": None, "eta_ticks": None, "distance_m": None,
            "samples": None}
    base.update(over)
    return base


def test_real_wave_schema_valid_and_speeds():
    from kiomet_ai.force import ForceUnits, unit_speed
    snap = _snap(threats=[_threat(samples=REAL_WAVE_26)])
    checked = validate_threat_snapshot(snap)
    assert checked["valid"] is True, checked["errors"]
    # 速度：Fighter+Bomber→3；純 Shield→2（預設）；Bomber+Tank→1
    speeds = [unit_speed(ForceUnits(tag=0, counts=dict(s["units"])))
              for s in REAL_WAVE_26]
    assert speeds[0] == 3
    assert speeds[3] == 3
    assert speeds[4] == 1


def test_real_wave_route_conflated_not_single_wave():
    out = replay_threat_waves(_snap(threats=[_threat(
        samples=REAL_WAVE_26)]), now=1790641578.9)
    assert out["verdicts"][0]["wave"]["identity"] == "ROUTE_CONFLATED"
    assert out["verdicts"][0]["owner_relation"] == "UNKNOWN"
    assert out["status"] == "REPLAYED"


def test_recorded_eta_match():
    from kiomet_ai.force import eta_ticks
    ticks = eta_ticks(10, 2, 90.0, 0)
    assert ticks is not None
    out = replay_threat_waves(_snap(threats=[_threat(
        units=_u(Soldier=4), progress=10,
        distance_m=90.0, eta_ticks=ticks)]),
        now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_MATCH"
    assert out["status"] == "REPLAYED"


def test_recorded_eta_mismatch_flagged():
    out = replay_threat_waves(_snap(threats=[_threat(
        progress=10, distance_m=90.0, eta_ticks=1)]),
        now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_MISMATCH"
    assert out["status"] == "FLAGGED"


def test_missing_eta_stays_unknown_not_zero():
    out = replay_threat_waves(_snap(threats=[_threat(
        progress=10, distance_m=90.0, eta_ticks=None)]),
        now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_UNKNOWN"
    assert out["verdicts"][0]["recomputed_eta_ticks"] is not None
    assert out["status"] == "REPLAYED"


def test_stale_observation():
    out = replay_threat_waves(
        _snap(observed_at=1790641000.0, threats=[_threat()]),
        now=1790641578.9)
    assert out["stale"] is True
    assert out["status"] == "STALE"


def test_multi_wave_ordered_by_eta():
    fast = _threat(owner_id=21, progress=80, distance_m=90.0)
    slow = _threat(owner_id=22, progress=5, distance_m=90.0)
    out = replay_threat_waves(_snap(threats=[slow, fast]),
                              now=1790641578.9)
    assert out["ordered_by_eta"] == [1, 0]


def test_invalid_schema_rejected():
    out = replay_threat_waves({"match_id": "m1"})
    assert out["status"] == "UNKNOWN"
    assert out["reason"] == "EVIDENCE_INVALID"


def test_non_list_threats_rejected():
    out = replay_threat_waves(_snap(threats="not-a-list"))
    assert out["status"] == "UNKNOWN"
    assert any("threats-must-be-list" in e for e in out["errors"])


def test_non_object_snapshot_rejected():
    out = replay_threat_waves(None)
    assert out["status"] == "UNKNOWN"
    assert out["reason"] == "EVIDENCE_INVALID"


def test_unknown_owner_rejected_not_guessed():
    out = replay_threat_waves(_snap(threats=[_threat(owner_id=0)]),
                              now=1790641578.9)
    assert out["status"] == "UNKNOWN"
    assert any("owner-unknown" in e for e in out["errors"])
