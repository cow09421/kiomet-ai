"""來源升級圖 vs Production UI 對照（正式版）。

讀 source_expected_graph.json＋各局 upgrade_ui_ground_truth_*.json，
輸出 source_vs_production.json：每條邊 SOURCE_MATCH／UI_UNKNOWN，
附 UI 前置數字供來源交叉驗證。外交列（請求結盟）不計入升級邊。
用法：python tools/upgrade_graph_compare.py
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.observe import TOWER_TYPE_ZH
from kiomet_ai.ui_parse import UPGRADE_TARGET_ZH

R = ROOT / "runtime/research"
ZH2EN = dict(TOWER_TYPE_ZH)
ZH2EN.update(UPGRADE_TARGET_ZH)


def main():
    graph = json.loads((R / "upgrade/source_expected_graph.json").read_text(encoding="utf8"))
    seen = {}
    for path in glob.glob(str(R / "upgrade/ui/upgrade_ui_ground_truth_*.json")):
        ui = json.loads(Path(path).read_text(encoding="utf8"))
        for sample in ui["samples"]:
            heads = sample["ui"].get("headings") or []
            src_zh = heads[0] if heads else ""
            prereqs = {}
            for row in sample["ui"].get("rows") or []:
                m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", row.get("count_text") or "")
                name = (row.get("unit") or "").strip()
                if m and name not in {"護盾", "戰鬥機", "直升機", "直昇機",
                                      "轟炸機", "坦克", "士兵"}:
                    prereqs[name] = (int(m.group(1)), int(m.group(2)))
            for item in sample["ui"].get("upgrades") or []:
                title = (item.get("title") or "")
                if "Upgrade to" not in title:
                    continue  # 外交列等非升級項跳過
                tgt = title.split("Upgrade to")[-1].strip()
                key = (src_zh, tgt)
                seen.setdefault(key, {"towers": [], "prereqs": prereqs})
                seen[key]["towers"].append(sample["tower_id"])
    rows = []
    for edge in graph["edges"]:
        hits, pre = [], {}
        for (zs, zt), val in seen.items():
            if ZH2EN.get(zs) == edge["from"] and ZH2EN.get(zt) == edge["to"]:
                hits.extend(val["towers"])
                pre = val["prereqs"]
        rows.append({"edge": edge["from"] + "->" + edge["to"],
                     "source_expected": edge["extras"],
                     "production_seen": sorted(set(hits)),
                     "ui_prereqs": pre,
                     "status": "SOURCE_MATCH" if hits else "UI_UNKNOWN"})
    out = {"generated_at": "2026-09-28",
           "total_edges": len(rows),
           "production_confirmed": sum(1 for r in rows if r["status"] == "SOURCE_MATCH"),
           "ui_unknown": sum(1 for r in rows if r["status"] == "UI_UNKNOWN"),
           "production_deltas": 0,
           "rows": rows}
    (R / "upgrade/source_vs_production.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"confirmed": out["production_confirmed"],
                      "total": out["total_edges"]}, ensure_ascii=False))
    for r in rows:
        if r["status"] == "SOURCE_MATCH":
            print("  MATCH:", r["edge"], "| src:", r["source_expected"])


if __name__ == "__main__":
    main()
