"""容量推導規則測試：兩局 UI 分母全量驗證。

規則：capacity = 來源 #[capacity] raw ＋（盾且 +45=1 時 +10）。
對 GPT 真值局（m1-1790487672）與新局（m1-1790506322）的每個
UI 單位列「N/M」斷言 M==推導值。升級前置列（工廠=0/2 等）
用兵種詞彙過濾排除。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (
    decode_owner_ruler_flag,
    decode_tower_type,
    unit_capacity,
)

ROOT = Path(__file__).resolve().parents[1]
UNIT_ZH = {"護盾": "Shield", "戰鬥機": "Fighter", "直昇機": "Chopper",
           "直升機": "Chopper", "轟炸機": "Bomber", "坦克": "Tank",
           "士兵": "Soldier", "砲彈": "Shell", "電磁脈衝": "Emp",
           "核彈": "Nuke", "統治者": "Ruler"}


def ui_capacity_rows(tower):
    """取 UI 單位列（單位中文名, 分母）。非單位列（升級前置）排除。"""
    rows = []
    for row in tower["info"]["rows"]:
        name = row["unit"].strip()
        if name in UNIT_ZH and "/" in row["count_text"]:
            rows.append((UNIT_ZH[name], int(row["count_text"].split("/")[1])))
    return rows


def assert_series_capacities(series):
    for rnd in series["rounds"]:
        for tower in rnd["towers"]:
            if not tower["info"]["rows"]:
                continue
            raw = tower["struct_bytes"]
            tower_type = decode_tower_type(raw)
            ruler = decode_owner_ruler_flag(raw)
            assert tower_type is not None, tower["packed_id"]
            assert ruler is not None, tower["packed_id"]
            for unit_en, cap in ui_capacity_rows(tower):
                got = unit_capacity(unit_en, tower_type, ruler)
                assert got == cap, (
                    f"{tower['packed_id']} {tower_type} {unit_en}: "
                    f"UI={cap} 推導={got} ruler={ruler}")


def test_capacity_gpt_match():
    series = json.loads(
        (ROOT / "runtime/research/units/units_ground_truth.json")
        .read_text(encoding="utf8"))
    assert series["match_id"] == "m1-1790487672"
    assert_series_capacities(series)


def test_capacity_new_match():
    series = json.loads(
        (ROOT / "runtime/research/units/unit-ui-series-m1-1790506322.json")
        .read_text(encoding="utf8"))
    assert series["match_id"] == "m1-1790506322"
    assert_series_capacities(series)


def test_ruler_flag_semantics():
    # SELF 塔全為 1；中立全為 0（兩局皆然）
    gpt = json.loads(
        (ROOT / "runtime/research/units/units_ground_truth.json")
        .read_text(encoding="utf8"))
    for tower in gpt["rounds"][0]["towers"]:
        flag = decode_owner_ruler_flag(tower["struct_bytes"])
        if tower["owner_candidate"] == "SELF":
            assert flag is True, tower["packed_id"]
        elif tower["owner_candidate"] in ("OTHER", "UNKNOWN"):
            assert flag is False, tower["packed_id"]


def test_capacity_unknown_handling():
    assert unit_capacity("Shield", None, True) is None
    assert unit_capacity("Shield", "Runway", None) is None
    assert unit_capacity("Shield", "NoSuchType", True) is None
    assert unit_capacity("Shield", "Runway", True) == 15   # 5+10
    assert unit_capacity("Shield", "Runway", False) == 5
    assert unit_capacity("Fighter", "Runway", False) == 4
    assert unit_capacity("Nuke", "Village", False) == 0    # 無容量＝0
