"""Dry Run 驗證器：構造 MoveForce(A,B)＋§25 全閘門校驗，絕不發送。"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime/research/source-map"

A = 12320993  # SELF [225,188]
B = 12386528  # SELF [224,189]


def main():
    anchor = json.loads((OUT / "verified-anchor-m2.json").read_text(encoding="utf-8"))
    towers = {t["packed_id"]: t for t in anchor["towers"]}
    edges = {tuple(e) for e in anchor["edges"]}
    status = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status"))
    checks = {}
    # 1. 同局新鮮度。
    checks["same_match"] = (status["game"]["match"]["id"] == anchor["match_id"]
                            and status["game"]["state"] == "IN_MATCH")
    # 2. A SELF（contiguity 证据链：anchor owner 栏）。
    checks["a_self"] = towers.get(A, {}).get("owner") == "SELF"
    # 3. B 為 A 鄰居（遮罩边）。
    checks["b_neighbor"] = (A, B) in edges
    # 4. AB 皆在觀察集合。
    checks["both_observed"] = A in towers and B in towers
    # 5. path＝[A,B] 語意。
    path = [A, B]
    checks["path_shape"] = (len(path) == 2 and path[0] == A and path[-1] == B)
    # 6. owner 非 UNKNOWN（A）。
    checks["owner_known"] = towers.get(A, {}).get("owner") in ("SELF", "OTHER")
    # 7. 平台 IN_MATCH（executor 門）。
    checks["executor_gate"] = status["game"]["state"] == "IN_MATCH"
    ok = all(checks.values())
    report = {
        "kind": "DRY_RUN", "send": False,
        "match_id": anchor["match_id"],
        "source": {"packed_id": A, "id": towers[A]["id"],
                   "position": towers[A]["position"],
                   "owner": towers[A]["owner"]},
        "target": {"packed_id": B, "id": towers[B]["id"],
                   "position": towers[B]["position"],
                   "owner": towers[B]["owner"]},
        "path": path, "variant": "DeployForce", "tower_id": A,
        "checks": checks, "result": "DRY_RUN_VALIDATED" if ok else "DRY_RUN_REJECTED",
        "time": time.time(),
    }
    (OUT / "dry-run-1.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"result": report["result"], "checks": checks}))


main()
