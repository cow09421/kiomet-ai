"""新局 Units／TowerType spot-check（抽查）：正式 Observer 層 vs UI。

用已工程化的 observe.py 解碼函式（非研究工具 decode_units），
對新對局 UI 樣本驗證：新 match、新 tower_ref 之下仍與官方介面一致。
用法：python tools/spot_check_units.py <unit-ui-series-檔案>
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.observe import (
    TOWER_TYPE_ZH,
    decode_tower_type,
    decode_tower_units,
)

# 兵種中文詞彙：升級前置列（工廠=0/2、村莊=1/3 等）不是兵力列，
# 其 current 可能非零，UI 比對必須排除，否則誤判。
UNIT_ZH = {"護盾", "戰鬥機", "直升機", "直昇機", "轟炸機", "坦克",
           "士兵", "砲彈", "電磁脈衝", "核彈", "統治者"}
UNIT_EN = {"護盾": "Shield", "戰鬥機": "Fighter", "直升機": "Chopper",
           "直昇機": "Chopper", "轟炸機": "Bomber", "坦克": "Tank",
           "士兵": "Soldier", "砲彈": "Shell", "電磁脈衝": "Emp",
           "核彈": "Nuke", "統治者": "Ruler"}


def ui_positive_counts(rows):
    return Counter(int(r["count_text"].split("/")[0])
                   for r in rows
                   if r["unit"].strip() in UNIT_ZH
                   and int(r["count_text"].split("/")[0]))


def single_matches_ui(counts, rows) -> bool:
    """Single 型比對：UI 須有該兵種列且數字 == single_count；
    Ruler 無數字列時回 None（UI_NOT_VISIBLE，無法判定）。"""
    if counts.units_kind != "SINGLE":
        return None
    for r in rows:
        name = r["unit"].strip()
        if name in UNIT_ZH and UNIT_EN[name] == counts.single_unit_type:
            current = int(r["count_text"].split("/")[0])
            return current == counts.single_count
    return None


def spot_check(series_path: Path) -> dict:
    series = json.loads(series_path.read_text(encoding="utf8"))
    match = series["match_id"]
    rows = []
    for round_index, rnd in enumerate(series["rounds"], 1):
        for tower in rnd["towers"]:
            if not tower["info"]["rows"]:
                continue
            counts = decode_tower_units(tower["struct_bytes"],
                                        tower_ref=tower["tower_ref"],
                                        observed_at=rnd["time"])
            decoded = Counter(v for v in (counts.shield, counts.fighter,
                                         counts.chopper, counts.bomber,
                                         counts.tank, counts.soldier) if v)
            ui = ui_positive_counts(tower["info"]["rows"])
            if counts.units_kind == "SINGLE":
                verdict = single_matches_ui(counts, tower["info"]["rows"])
                # True=數字吻合；False=數字矛盾；None=UI 無此兵種列（UI_NOT_VISIBLE）
                units_ok = True if verdict is None else verdict
                single_truth = ("UI_NOT_VISIBLE" if verdict is None
                                else ("MATCH" if verdict else "MISMATCH"))
            else:
                units_ok = decoded == ui
                single_truth = None
            type_name = decode_tower_type(tower["struct_bytes"])
            zh = tower["info"]["headings"][0] if tower["info"]["headings"] else ""
            type_ok = (zh in TOWER_TYPE_ZH and type_name == TOWER_TYPE_ZH[zh])
            rows.append({
                "round": round_index, "packed_id": tower["packed_id"],
                "owner": tower["owner_candidate"],
                "units_kind": counts.units_kind,
                "units_match_ui": units_ok,
                "single_truth": single_truth,
                "tower_type": type_name, "ui_heading": zh,
                "type_match_ui": type_ok,
                "age_s": round(time.time() - (rnd["time"] or time.time()), 1),
            })
    matched_units = sum(r["units_match_ui"] for r in rows)
    matched_type = sum(r["type_match_ui"] for r in rows)
    return {"match_id": match, "sample_count": len(rows),
            "units_matched": matched_units,
            "type_matched": matched_type,
            "units_pass": matched_units == len(rows) and len(rows) >= 3,
            "type_pass": matched_type == len(rows) and len(rows) >= 3,
            "rows": rows}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    report = spot_check(Path(sys.argv[1]))
    dest = ROOT / "runtime/research/units" / f"spot-check-{report['match_id']}.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
