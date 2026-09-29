"""靜態抽取公開來源升級圖：TowerType prerequisite 屬性→升級邊。

首 token 為降級源（downgrade），其餘為額外前置。
輸出 runtime/research/upgrade/source_expected_graph.json，
全邊標 SOURCE_EXPECTED（來源預期），不冒充 Production 確認。
用法：python tools/extract_upgrade_graph.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vendor/kiomet-ref/common/src/tower.rs"
OUT = ROOT / "runtime/research/upgrade/source_expected_graph.json"


def extract():
    body_src = SRC.read_text(encoding="utf-8")
    i = body_src.find("pub enum TowerType")
    j = body_src.find("impl TowerType")
    body = body_src[i:j]
    blocks = re.findall(r"((?:#\[[^\]]*\]\s*)+)([A-Z][A-Za-z]*),", body)
    edges = []
    for attrs, name in blocks:
        m = re.search(r"#\[prerequisite\(([^]]*)\)\]", attrs)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split(",")]
        if not parts or not re.match(r"^[A-Z]", parts[0]):
            continue
        src = re.match(r"^([A-Z][A-Za-z]*)", parts[0]).group(1)
        extras = {}
        for part in parts[1:]:
            mm = re.match(r"^([A-Z][A-Za-z]*)\s*=\s*(\d+)$", part)
            if mm:
                extras[mm.group(1)] = int(mm.group(2))
        edges.append({"from": src, "to": name, "extras": extras,
                      "status": "SOURCE_EXPECTED"})
    return edges


def main():
    edges = extract()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "extracted_at": "2026-09-28",
        "source": "vendor/kiomet-ref/common/src/tower.rs TowerType prerequisite attributes",
        "note": "首 token 為降級源；其餘為額外前置。狀態全為 SOURCE_EXPECTED，待 Production UI 驗證。",
        "edges": edges}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"edges": len(edges)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
