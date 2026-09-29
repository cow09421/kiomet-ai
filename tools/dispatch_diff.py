"""被動派兵差分分析：比較兩次結構探測，找自然 Units 下降事件。

對每座塔：若 +39..+44 下降，計算下降向量；以舊狀態＋塔型
算 mirror_force_units（鏡像）；下降向量 == 鏡像組成
（全部可派一次取走）者列為 2031 自然輸出候選。
只讀離線分析，不碰平台。
用法：python tools/dispatch_diff.py <舊探測> <新探測>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.force_units import mirror_force_units
from kiomet_ai.observe import (
    decode_tower_type,
    decode_tower_units,
)

NAMES6 = ["Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier"]


def load_probe(path: Path):
    data = json.loads(path.read_text(encoding="utf8"))
    return data, {r["packed_id"]: r for r in data["rows"]}


def analyze(old_row, new_row):
    old_raw = old_row["bytes"][32:32 + 48]
    new_raw = new_row["bytes"][32:32 + 48]
    try:
        old_counts = decode_tower_units(old_raw, tower_ref=old_row["ref"])
        new_counts = decode_tower_units(new_raw, tower_ref=new_row["ref"])
    except ValueError:
        return None
    if old_counts.units_kind != "MANY" or new_counts.units_kind != "MANY":
        return None
    tower_type = decode_tower_type(old_raw)
    drop = {n: getattr(old_counts, n.lower()) - getattr(new_counts, n.lower())
            for n in NAMES6}
    if not any(v != 0 for v in drop.values()):
        return None
    mirror = (mirror_force_units(old_counts, tower_type)
              if tower_type else None)
    mirror_counts = mirror.counts if mirror else None
    exact = (mirror_counts is not None
             and all(drop[n] == mirror_counts[n] for n in NAMES6))
    return {"packed_id": new_row["packed_id"],
            "owner": new_row.get("owner"),
            "tower_type": tower_type,
            "pure_drop": all(v >= 0 for v in drop.values()),
            "drop": drop,
            "mirror": mirror_counts,
            "mirror_match": exact}


def diff_probes(old_path: Path, new_path: Path) -> dict:
    old_data, old_rows = load_probe(old_path)
    new_data, new_rows = load_probe(new_path)
    events = []
    for pid, new_row in new_rows.items():
        if pid not in old_rows:
            continue
        result = analyze(old_rows[pid], new_row)
        if result:
            events.append(result)
    return {"old_match": old_data.get("match_id"),
            "new_match": new_data.get("match_id"),
            "changed_towers": len(events),
            "mirror_matches": sum(1 for e in events if e["mirror_match"]),
            "events": events}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(json.dumps(diff_probes(Path(sys.argv[1]), Path(sys.argv[2])),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
