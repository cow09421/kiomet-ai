"""威脅快照 builder 回歸。

force-poll 原始列 → 威脅快照 → replay_threat_waves 全鏈。
真實樣本：owner 26 路由 16384182→16449718（forcepoll3.log）。

成功證據：同路由取最新樣本；損壞列跳過；OUTBOUND 排除；
缺 ETA 輸入即 ETA_UNKNOWN；CLI 可跑。
失敗證據：舊樣本覆蓋新樣本、損壞列中斷、OUTBOUND 混入。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (replay_threat_waves,
                              threat_snapshot_from_force_rows,
                              validate_threat_snapshot)

REAL_LOG = Path("E:/SteamLibrary/kiomet/runtime/tmp/forcepoll3.log")

requires_force_log = pytest.mark.skipif(
    not REAL_LOG.exists(),
    reason="force-poll log not present (gitignored)")


def _row(owner_id=26, src=16384182, dst=16449718, t=1790641578.9,
         progress=4, role="INBOUND", relation="UNKNOWN", **units):
    counts = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                             "Tank", "Soldier", "Shell", "Emp", "Nuke",
                             "Ruler")}
    counts.update(units)
    return {"t": t, "anchor": dst, "role": role, "owner_id": owner_id,
            "relation": relation, "src": src, "src_owner": None,
            "dst": dst, "dst_owner": "NEUTRAL", "progress": progress,
            "units": counts}


REAL_ROWS = [
    _row(t=1790639883.6, progress=18, Fighter=1, Bomber=1),
    _row(t=1790641395.4, progress=45, Shield=10),
    _row(t=1790641578.9, progress=4, Bomber=1, Tank=3),
]


def test_builder_takes_latest_sample_per_route():
    snap = threat_snapshot_from_force_rows(
        REAL_ROWS, "m1-1790639551", target_tower_id=16449718)
    assert len(snap["threats"]) == 1
    threat = snap["threats"][0]
    assert threat["progress"] == 4
    assert threat["units"]["Tank"] == 3
    assert threat["owner_relation"] == "UNKNOWN"
    assert snap["observed_at"] == 1790641578.9


def test_builder_skips_malformed_rows():
    rows = ["not json{{{", "", None, 42,
            _row(), {"role": "INBOUND"}]
    snap = threat_snapshot_from_force_rows(rows, "m1", 16449718)
    assert len(snap["threats"]) == 1


def test_builder_excludes_outbound_and_bad_owners():
    rows = [_row(role="OUTBOUND"),
            _row(owner_id=0),
            _row(owner_id="26"),
            _row()]
    snap = threat_snapshot_from_force_rows(rows, "m1", 16449718)
    assert len(snap["threats"]) == 1
    assert snap["threats"][0]["owner_id"] == 26


def test_builder_groups_distinct_routes():
    rows = [_row(src=1, dst=2), _row(src=3, dst=4)]
    snap = threat_snapshot_from_force_rows(rows, "m1", 16449718)
    assert len(snap["threats"]) == 2


def test_built_snapshot_replays_end_to_end():
    snap = threat_snapshot_from_force_rows(
        REAL_ROWS, "m1-1790639551", target_tower_id=16449718)
    checked = validate_threat_snapshot(snap)
    assert checked["valid"] is True, checked["errors"]
    out = replay_threat_waves(snap, now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_UNKNOWN"
    assert out["status"] == "REPLAYED"


def test_empty_build_is_invalid_not_empty_threats():
    snap = threat_snapshot_from_force_rows([], "m1", 16449718)
    assert snap["threats"] == []
    out = replay_threat_waves(snap, now=1790641578.9)
    assert out["status"] == "UNKNOWN"


@requires_force_log
def test_real_forcepoll_log_replays_without_fabrication():
    rows = REAL_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
    snap = threat_snapshot_from_force_rows(
        rows, "m1-1790639551", target_tower_id=16449718)
    assert len(snap["threats"]) == 59
    out = replay_threat_waves(snap, now=1790641600.0)
    assert out["status"] == "REPLAYED"
    assert all(v["eta_verdict"] == "ETA_UNKNOWN"
               for v in out["verdicts"])
    assert {v["owner_id"] for v in out["verdicts"]} == {22, 26}


def test_cli_threat_mode(tmp_path):
    import subprocess
    log = tmp_path / "force.log"
    log.write_text("\n".join(json.dumps(r) for r in REAL_ROWS),
                   encoding="utf-8")
    out = tmp_path / "threat-report.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1]
                             / "tools" / "replay_battle_differential.py"),
         "--threat-log", str(log), "--threat-match", "m1-1790639551",
         "--threat-target", "16449718", "--threat-out", str(out),
         "--threat-now", "1790641578.9"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "REPLAYED"
    assert len(report["verdicts"]) == 1
