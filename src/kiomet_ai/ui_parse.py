"""UI 資訊框語意化解析器：兵力列／容量列／升級前置列／升級目標列分流。

核心規則：看到 N/M 不得全部當兵力。兵種詞彙（UNIT_ZH）內才是
兵力列；其他 N/M 列是升級前置進度；長標題列是狀態註記
（如國王鄰近加成）；其餘為未知列。
"""
from __future__ import annotations

import re

UNIT_ZH = {"護盾": "Shield", "戰鬥機": "Fighter", "直升機": "Chopper",
           "直昇機": "Chopper", "轟炸機": "Bomber", "坦克": "Tank",
           "士兵": "Soldier", "砲彈": "Shell", "電磁脈衝": "Emp",
           "核彈": "Nuke", "統治者": "Ruler"}

NM_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")

# 升級目標中文名→英文。Runway→Airfield、Mine→Bunker、
# Generator→Reactor、Village→Headquarters/Town、Barracks→Armory、
# Factory→Centrifuge/Refinery 八條鏈已由 UI 目標＋前置數字↔
# 來源 prerequisite 屬性交叉驗證。
UPGRADE_TARGET_ZH = {"機場": "Airfield", "碉堡": "Bunker",
                     "反應爐": "Reactor", "總部": "Headquarters",
                     "城鎮": "Town", "軍械庫": "Armory",
                     "離心機": "Centrifuge", "煉油廠": "Refinery"}

# 來源驗證過的升級鏈：來源塔型→（目標，前置 {型別：需求}）。
UPGRADE_CHAINS_SOURCE = {
    "Runway": [("Airfield", {"Factory": 2, "Radar": 1})],
    "Mine": [("Bunker", {"Headquarters": 1, "Ews": 1})],
    "Generator": [("Reactor", {"Centrifuge": 1})],
    "Village": [("Headquarters", {"Radar": 1}),
                ("Town", {"Generator": 1, "Village": 3})],
}


def classify_row(unit_name: str, count_text: str) -> str:
    """UNIT_ROW／PREREQ_ROW／NOTE_ROW／UNKNOWN_ROW。"""
    name = (unit_name or "").strip()
    text = (count_text or "").strip()
    if len(name) > 20:
        return "NOTE_ROW"
    if not NM_PATTERN.match(text):
        return "NOTE_ROW" if name else "UNKNOWN_ROW"
    if name in UNIT_ZH:
        return "UNIT_ROW"
    return "PREREQ_ROW"


def parse_rows(rows: list) -> dict:
    """資訊框列分流。回傳 units／prereqs／notes／unknown 四類。"""
    out = {"units": [], "prereqs": [], "notes": [], "unknown": []}
    for row in rows:
        name = (row.get("unit") or "").strip()
        text = (row.get("count_text") or "").strip()
        kind = classify_row(name, text)
        if kind == "UNIT_ROW":
            current, capacity = (int(v) for v in NM_PATTERN.match(text).groups())
            out["units"].append({"unit_zh": name, "unit_en": UNIT_ZH[name],
                                 "current": current, "capacity": capacity})
        elif kind == "PREREQ_ROW":
            have, need = (int(v) for v in NM_PATTERN.match(text).groups())
            out["prereqs"].append({"name_zh": name, "have": have, "need": need})
        elif kind == "NOTE_ROW":
            out["notes"].append({"title": name, "text": text})
        else:
            out["unknown"].append({"unit": name, "count_text": text})
    return out


def parse_upgrade_targets(upgrades: list) -> list:
    """升級目標列：title 如 'Upgrade to 反應爐'→目標中英文。"""
    targets = []
    for item in upgrades or []:
        title = (item.get("title") or "").strip()
        zh = title.split("Upgrade to")[-1].strip() if "Upgrade to" in title else ""
        targets.append({"title": title, "target_zh": zh,
                        "target_en": UPGRADE_TARGET_ZH.get(zh)})
    return targets


def has_king_proximity_note(parsed: dict) -> bool:
    """國王鄰近加成註記是否存在（與 +45=1 應同步）。"""
    return any("國王" in n.get("title", "") for n in parsed["notes"])
