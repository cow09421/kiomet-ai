"""以官方 WABT 解析 WASM，輸出結構特徵及候選；分數不是正確率。"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


def parse_dump(details: str, disassembly: str) -> dict:
    types = {int(i): t for i, t in re.findall(r" - type\[(\d+)\] (.+)", details)}
    functions = {}
    for line in details.splitlines():
        m = re.match(r" - func\[(\d+)\] sig=(\d+)(?: <(.*)>)?", line)
        if m:
            i, sig, name = m.groups()
            functions[int(i)] = {"index": int(i), "name": name or "",
                                 "type": types[int(sig)], "imported": " <- " in line}
    for i, size in re.findall(r" - func\[(\d+)\] size=(\d+)", details):
        functions[int(i)]["size"] = int(size)
    current = None
    for line in disassembly.splitlines():
        header = re.match(r"([0-9a-f]+) func\[(\d+)\]", line)
        if header:
            current = functions[int(header[2])]
            current.update(offset=int(header[1], 16), instructions=[], calls=[],
                           constants=[], memory_ops=[], table_ops=[])
            continue
        m = re.match(r"\s*([0-9a-f]+):[^|]*\|\s*(\S+)(.*)", line)
        if not m or current is None:
            continue
        address, op, args = m.groups()
        if op.startswith("local["):
            continue
        args = args.strip()
        current["instructions"].append(op)
        if op in ("call", "return_call"):
            current["calls"].append(int(args.split()[0]))
        if op.endswith(".const"):
            current["constants"].append(op + " " + args)
        if ".load" in op or ".store" in op or op.startswith("memory."):
            current["memory_ops"].append(op + " " + args)
        if op.startswith("table.") or op in ("call_indirect", "return_call_indirect", "ref.func"):
            current["table_ops"].append(op + " " + args)
    for f in functions.values():
        f["callers"] = []
    for f in functions.values():
        if f["imported"]:
            continue
        if "instructions" not in f:
            raise ValueError(f"Missing disassembly for function {f['index']}")
        f["histogram"] = dict(Counter(f.pop("instructions")))
        f["constant_histogram"] = dict(Counter(f["constants"]))
        f["memory_histogram"] = dict(Counter(x.split()[0] for x in f["memory_ops"]))
        f["control_histogram"] = {k: v for k, v in f["histogram"].items()
                                  if k in {"block", "loop", "if", "else", "br", "br_if", "br_table", "return"}}
        for target in set(f["calls"]):
            functions[target]["callers"].append(f["index"])
    return {"functions": list(functions.values())}


def analyze(path: Path, objdump: Path) -> dict:
    def dump(flag):
        result = subprocess.run([str(objdump.resolve()), flag, str(path.resolve())],
                                capture_output=True, check=True, encoding="utf-8")
        return result.stdout
    result = parse_dump(dump("-x"), dump("-d"))
    result.update(file=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  tool=subprocess.check_output([str(objdump.resolve()), "--version"], text=True).strip())
    return result


def cosine(a: dict, b: dict) -> float:
    if not a and not b:
        return 1.0
    norm = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    return sum(v*b.get(k, 0) for k, v in a.items()) / norm if norm else 0.0


def similarity(a: dict, b: dict) -> tuple[float, dict]:
    ratio = lambda x, y: min(x+1, y+1) / max(x+1, y+1)
    features = {
        "instructions": cosine(a["histogram"], b["histogram"]),
        "constants": cosine(a["constant_histogram"], b["constant_histogram"]),
        "memory": cosine(a["memory_histogram"], b["memory_histogram"]),
        "control": cosine(a["control_histogram"], b["control_histogram"]),
        "size": ratio(a["size"], b["size"]),
        "calls": ratio(len(a["calls"]), len(b["calls"])),
        "type": float(a["type"] == b["type"]),
    }
    weights = dict(instructions=.25, constants=.20, memory=.15, control=.10,
                   size=.10, calls=.10, type=.10)
    return sum(features[k]*v for k, v in weights.items()), features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("wasm", type=Path)
    a.add_argument("--objdump", required=True, type=Path)
    a.add_argument("--out", required=True, type=Path)
    m = sub.add_parser("match")
    m.add_argument("local", type=Path)
    m.add_argument("production", type=Path)
    m.add_argument("--names", default="TowerId|World|Visible|ChunkMap|render|TowerState")
    m.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "analyze":
        result = analyze(args.wasm, args.objdump)
    else:
        local = json.loads(args.local.read_text(encoding="utf8"))
        prod = json.loads(args.production.read_text(encoding="utf8"))
        result = {"local_sha256": local["sha256"], "production_sha256": prod["sha256"],
                  "warning": "Heuristic similarity, not probability. Names and indices excluded from score. Inlining and ABI changes can invalidate matching.",
                  "matches": []}
        candidates = [f for f in prod["functions"] if not f["imported"]]
        for f in local["functions"]:
            if f["imported"] or not re.search(args.names, f["name"]):
                continue
            ranking = []
            for p in candidates:
                score, features = similarity(f, p)
                ranking.append({"index": p["index"], "name": p["name"], "score": round(score, 5), "features": features})
            ranking.sort(key=lambda x: x["score"], reverse=True)
            result["matches"].append({"local_index": f["index"], "local_name": f["name"], "top": ranking[:5]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"out": str(args.out), "count": len(result.get("functions", result.get("matches", [])))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
