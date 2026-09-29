"""UI 語意解析器測試：兵力／前置／註記／升級目標分流。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.ui_parse import (
    classify_row,
    has_king_proximity_note,
    parse_rows,
    parse_upgrade_targets,
)


def test_unit_rows():
    assert classify_row("戰鬥機", "4/4") == "UNIT_ROW"
    assert classify_row("護盾", "20/20") == "UNIT_ROW"
    assert classify_row("士兵", "12/12") == "UNIT_ROW"


def test_prereq_rows_not_units():
    # 升級前置列即使 current 非零也不是兵力。
    assert classify_row("工廠", "0/2") == "PREREQ_ROW"
    assert classify_row("村莊", "1/3") == "PREREQ_ROW"
    assert classify_row("發電機", "2/1") == "PREREQ_ROW"
    assert classify_row("雷達", "0/1") == "PREREQ_ROW"


def test_note_rows():
    assert classify_row("你的國王就在附近：產量加倍", "士氣高昂") == "NOTE_ROW"
    assert classify_row("護盾", "士氣高昂") == "NOTE_ROW"


def test_parse_rows_from_live_ground_truth():
    rows = [{"unit": "護盾", "count_text": "15/15"},
            {"unit": "士兵", "count_text": "4/4"},
            {"unit": "雷達", "count_text": "0/1"},
            {"unit": "發電機", "count_text": "2/1"},
            {"unit": "村莊", "count_text": "1/3"}]
    parsed = parse_rows(rows)
    assert [(u["unit_en"], u["current"], u["capacity"]) for u in parsed["units"]] == [
        ("Shield", 15, 15), ("Soldier", 4, 4)]
    assert [(p["name_zh"], p["have"], p["need"]) for p in parsed["prereqs"]] == [
        ("雷達", 0, 1), ("發電機", 2, 1), ("村莊", 1, 3)]
    assert parsed["unknown"] == []


def test_upgrade_targets():
    targets = parse_upgrade_targets([{"title": "Upgrade to 反應爐"},
                                     {"title": "Upgrade to 總部"},
                                     {"title": "Upgrade to 城鎮"}])
    assert [(t["target_zh"], t["target_en"]) for t in targets] == [
        ("反應爐", "Reactor"), ("總部", "Headquarters"), ("城鎮", "Town")]


def test_king_note_detection():
    parsed = parse_rows([{"unit": "你的國王就在附近：產量加倍，出發的單位在途中移動更快、作戰更猛",
                          "count_text": "士氣高昂"}])
    assert has_king_proximity_note(parsed) is True
    assert parse_rows([{"unit": "護盾", "count_text": "0/10"}])["notes"] == []
    assert has_king_proximity_note(
        parse_rows([{"unit": "護盾", "count_text": "0/10"}])) is False
