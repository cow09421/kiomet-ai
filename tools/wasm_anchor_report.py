"""把限量渲染觀測轉為可核對摘要；只在已觀察塔之間建立道路。"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def owner_from_sample(row):
    """以正式 render_color 為準；只有舊資料缺欄位時沿用 owner。"""
    if "render_color" not in row:
        legacy_owner = row.get("owner")
        return (legacy_owner if isinstance(legacy_owner, str) and legacy_owner
                else "UNKNOWN")
    color = row.get("render_color")
    if type(color) is not int:
        return "UNKNOWN"
    return {0: "SELF", 1: "NEUTRAL", 2: "ALLY", 3: "ENEMY"}.get(
        color, "UNKNOWN")


def summarize(data):
    if data.get("error"):
        raise ValueError(data["error"])
    before, after = data["game_before"], data["game_after"]
    if before["state"] != "IN_MATCH" or after["state"] != "IN_MATCH":
        raise ValueError("僅接受對局中證據")
    if before["match"]["id"] != after["match"]["id"]:
        raise ValueError("觀測期間已換局")
    rows = defaultdict(list)
    for row in data["samples"]:
        x, y = row["id"]
        if not (0 <= x < 512 and 0 <= y < 512 and row["packed_id"] == x | y << 16):
            raise ValueError("塔編號超界或封裝不一致")
        if not row["tower_ref"]:
            raise ValueError("缺少塔引用")
        # 正式 integer_position 的格距為 5，偏移表輸出落在 0..4。
        if not all(0 <= p - 5 * coordinate <= 4 for coordinate, p in zip(row["id"], row["position"])):
            raise ValueError("塔座標與已核對格距不一致")
        rows[row["packed_id"]].append(row)
    stable = []
    for tower_id, samples in rows.items():
        witnesses = {(s["tower_ref"], tuple(s["position"]),
                      owner_from_sample(s))
                     for s in samples}
        rounds = {s["round"] for s in samples}
        if len(witnesses) == 1 and len(rounds) == 3:
            stable.append(tower_id)
    if len(stable) != len(rows):
        raise ValueError("部分塔未通過三輪重現")
    directions = data["graph"]["directions"]
    if len(directions) != 8 or set(map(tuple, directions)) != {(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if x or y}:
        raise ValueError("道路方向表不合法")
    edges = set()
    for node in data["graph"]["nodes"]:
        tower_id = node["id"]
        if tower_id not in rows:
            raise ValueError("拒絕未觀察塔的道路資料")
        x, y = tower_id & 65535, tower_id >> 16
        for bit, (dx, dy) in enumerate(directions):
            target = (x + dx) | ((y + dy) << 16)
            if node["mask"] & (1 << bit) and target in rows:
                edges.add((tower_id, target))
    if not all((b, a) in edges for a, b in edges):
        raise ValueError("道路雙向檢查失敗")
    towers = [dict(samples[0]) for samples in rows.values()]
    for tower in towers:
        tower["owner"] = owner_from_sample(tower)
    owned = {s["packed_id"] for s in towers if s.get("owner") == "SELF"}
    return {
        "sha256": data["sha256"], "match_id": after["match"]["id"],
        "anchor": "PASS", "decoded_towers": len(towers), "stable_towers": len(stable),
        "owner_counts": dict(Counter(s.get("owner", "UNKNOWN") for s in towers)),
        "graph": "PARTIAL", "undirected_edges": len(edges)//2,
        "edges": sorted(edges), "self_source_edges": sorted((a, b) for a, b in edges if a in owned),
        "max_pause_seconds": data["max_pause_seconds"],
        "total_pause_seconds": sum(data["pause_seconds"]),
        "towers": towers, "move_force": "NOT_READY",
        "limits": ["固定正式檔雜湊", "三輪短時間重現", "畫面邊緣過濾含渲染邊界", "顏色依照公開 Color::new 對照", "未接入持續觀察器"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(json.loads(args.input.read_text(encoding="utf8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({k: result[k] for k in ("anchor", "decoded_towers", "owner_counts", "graph", "undirected_edges")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
