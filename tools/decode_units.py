"""解碼塔參照 +38 的 Units 結構，並與選塔介面樣本核對。"""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
         "Shell", "Emp", "Nuke", "Ruler"]
# 兵種中文詞彙：升級前置列（工廠=0/2、村莊=1/3 等）不是兵力列，
# 其 current 可能非零，UI 比對必須排除，否則誤判。
UNIT_ZH = {"護盾", "戰鬥機", "直升機", "直昇機", "轟炸機", "坦克",
           "士兵", "砲彈", "電磁脈衝", "核彈", "統治者"}


def decode(struct_bytes):
    if len(struct_bytes) < 45:
        raise ValueError("塔結構長度不足")
    tag, a, b, c, d, e, shield = struct_bytes[38:45]
    units = {name: 0 for name in NAMES}
    units["Shield"] = shield
    if tag == 0:
        units.update(zip(NAMES[1:6], [a, b, c, d, e]))
    elif tag == 1:
        if b not in range(6, 10) or a == 0:
            raise ValueError(f"無效的 Single 單位：{[tag,a,b,c,d,e,shield]}")
        units[NAMES[b]] = a
    else:
        raise ValueError(f"未知 UnitsEither 標籤：{tag}")
    return units


def validate(series):
    results = []
    for round_index, rnd in enumerate(series["rounds"], 1):
        for tower in rnd["towers"]:
            if not tower["info"]["rows"]:
                continue
            units = decode(tower["struct_bytes"])
            # 正式 UI 對 Ruler 沒有顯示 N/M；因此只比較 Shield 與五種 Many。
            expected = Counter(value for value in [units[n] for n in NAMES[:6]] if value)
            visible = Counter(int(row["count_text"].split("/")[0])
                              for row in tower["info"]["rows"]
                              if row["unit"].strip() in UNIT_ZH
                              and int(row["count_text"].split("/")[0]))
            ok = expected == visible
            results.append({"round":round_index,"packed_id":tower["packed_id"],
                            "owner":tower["owner_candidate"],"units":units,
                            "ui_positive_counts":dict(visible),"matches_ui":ok})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series", type=Path, help="包含 UI 與 struct_bytes 的取樣 JSON")
    args = parser.parse_args()
    series = json.loads(args.series.read_text(encoding="utf8"))
    rows = validate(series)
    report = {"match_id":series["match_id"],"tower_count":len({r["packed_id"] for r in rows}),
              "round_count":len(series["rounds"]),"sample_count":len(rows),
              "matched":sum(r["matches_ui"] for r in rows),"rows":rows}
    dest = ROOT / "runtime/research/units" / f"decoded-units-{series['match_id']}.json"
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},ensure_ascii=False))
    if report["sample_count"] != report["matched"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
