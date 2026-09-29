"""Units Observer（兵力觀察器）＋Owner Classifier（所有權分類器）正式層測試。

覆蓋：Many 解碼、Single 候選處理、短結構拒絕、未知 tag 拒絕、
tower_ref／新鮮度語意、render_color（渲染顏色值）映射、
UNKNOWN 永不升 SELF、快照接受 ALLY／ENEMY。
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (
    TOWER_TYPE_ZH,
    TowerUnitCounts,
    build_snapshot,
    classify_owner,
    decode_tower_type,
    decode_tower_units,
)

ROOT = Path(__file__).resolve().parents[1]


def test_many_layout_decodes_current_counts():
    raw = [0] * 48
    raw[38:45] = [0, 4, 0, 0, 0, 12, 20]
    got = decode_tower_units(raw, tower_ref=2898912, observed_at=100.0)
    assert got.units_kind == "MANY"
    assert (got.fighter, got.chopper, got.bomber, got.tank,
            got.soldier, got.shield) == (4, 0, 0, 0, 12, 20)
    assert got.tower_ref == 2898912
    assert got.single_unit_type is None and got.single_count is None


def test_gpt_ground_truth_roundtrip_thirty_of_thirty():
    """GPT 交接的 30 筆 UI↔Runtime 配對，走正式層重算仍 30/30。"""
    series = json.loads(
        (ROOT / "runtime/research/units/units_ground_truth.json")
        .read_text(encoding="utf8"))
    matched = total = 0
    for rnd in series["rounds"]:
        for tower in rnd["towers"]:
            if not tower["info"]["rows"]:
                continue
            total += 1
            got = decode_tower_units(tower["struct_bytes"])
            positives = sorted(v for v in (
                got.shield, got.fighter, got.chopper, got.bomber,
                got.tank, got.soldier) if v)
            ui = sorted(int(r["count_text"].split("/")[0])
                        for r in tower["info"]["rows"]
                        if int(r["count_text"].split("/")[0]))
            if positives == ui:
                matched += 1
    assert total == 30
    assert matched == 30


def test_single_ruler_is_candidate_not_pass():
    """Single(Ruler,1)＋護盾 30：結構收容為 CANDIDATE，不代表 UI 已配對。"""
    raw = [0] * 48
    raw[38:45] = [1, 1, 9, 0, 0, 0, 30]
    got = decode_tower_units(raw)
    assert got.units_kind == "SINGLE"
    assert got.single_unit_type == "Ruler"
    assert got.single_count == 1
    assert got.shield == 30
    # Many 欄位在此型別下無意義，保持 UNKNOWN（未知）。
    assert got.fighter is None


def test_malformed_single_collapses_to_unknown():
    raw = [0] * 48
    raw[38:45] = [1, 0, 9, 0, 0, 0, 5]  # count=0：非法 Single
    got = decode_tower_units(raw)
    assert got.units_kind == "UNKNOWN"
    assert got.fighter is None
    assert got.shield == 5  # 護盾欄位仍可讀


def test_single_residue_bytes_ignored():
    """樣本 #3（m1-1790523816 塔 14745828）：Single 塔 +43=5 殘留，
    不得污染解碼；只讀 +39／+40／+44。"""
    raw = [0] * 48
    raw[38:45] = [1, 1, 9, 0, 0, 5, 15]
    got = decode_tower_units(raw)
    assert got.units_kind == "SINGLE"
    assert got.single_unit_type == "Ruler"
    assert got.single_count == 1
    assert got.shield == 15
    assert got.soldier is None  # +43=5 是殘留，不是士兵 5
    assert got.fighter is None


def test_short_struct_and_bad_tag_rejected():
    with pytest.raises(ValueError):
        decode_tower_units([0] * 44)
    bad = [0] * 48
    bad[38] = 7
    with pytest.raises(ValueError):
        decode_tower_units(bad)


def test_units_carries_ref_and_age():
    now = time.time()
    got = decode_tower_units([0] * 48, tower_ref=123, observed_at=now - 5)
    assert got.tower_ref == 123
    assert got.age(now) == pytest.approx(5.0, abs=0.5)
    assert TowerUnitCounts().age() is None


def test_owner_color_mapping():
    assert classify_owner(0) == "SELF"
    assert classify_owner(1) == "NEUTRAL"
    assert classify_owner(2) == "ALLY"
    assert classify_owner(3) == "ENEMY"
    assert classify_owner(4) is None
    assert classify_owner(-1) is None
    assert classify_owner(None) is None


def test_snapshot_accepts_ally_enemy_and_never_upgrades_unknown():
    obs = build_snapshot(
        "m1", {}, {}, 1.0,
        [{"packed_id": 1, "position": [0, 0], "owner": "ALLY"},
         {"packed_id": 2, "position": [1, 1], "owner": "ENEMY"},
         {"packed_id": 3, "position": [2, 2], "owner": "BOGUS"}],
        [], {})
    by_id = {t.tower_id: t for t in obs.towers}
    assert by_id[1].owner == "ALLY"
    assert by_id[2].owner == "ENEMY"
    assert by_id[3].owner is None


def test_tower_type_matches_seven_verified_ui_names():
    """10 塔 7 型的中文 UI 塔名 ↔ +46 解碼 ↔ 來源 enum 全吻合。"""
    series = json.loads(
        (ROOT / "runtime/research/units/units_ground_truth.json")
        .read_text(encoding="utf8"))
    seen = {}
    for rnd in series["rounds"]:
        for tower in rnd["towers"]:
            zh = tower["info"]["headings"][0]
            assert zh in TOWER_TYPE_ZH
            got = decode_tower_type(tower["struct_bytes"])
            assert got == TOWER_TYPE_ZH[zh]
            seen[zh] = got
    assert len(seen) == 7


def test_tower_type_rejects_bad_input():
    assert decode_tower_type([0] * 46) is None
    bad = [0] * 48
    bad[46] = 27  # 超出 27 型範圍
    assert decode_tower_type(bad) is None
