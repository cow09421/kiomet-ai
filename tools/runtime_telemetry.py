"""有界執行期遙測彙整（§12H）。

唯讀彙整 runtime/logs/metrics.jsonl 與 errors.jsonl：
記憶體／運行時間 p50/p95/max、state 分佈、browser 連線比例、錯誤分類、
最新樣本時效。缺資料標 UNKNOWN，不編造；不刪任何資料。
輸出 runtime/state/runtime_telemetry.json。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER_S = 300.0


def percentile(values, pct):
    """最近排名百分位；空輸入回 None。"""
    nums = sorted(v for v in values if isinstance(v, (int, float)))
    if not nums:
        return None
    if len(nums) == 1:
        return float(nums[0])
    rank = max(0, min(len(nums) - 1,
                      int((pct / 100.0) * (len(nums) - 1))))
    return float(nums[rank])


def _load_jsonl(path: Path, limit: int | None = None) -> list:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return rows
    if limit:
        lines = lines[-limit:]
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _stat(values):
    return {"count": len(values),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "max": max(values) if values else None}


def summarize_metrics(rows: list) -> dict:
    memory = [r.get("memory_mb") for r in rows
              if isinstance(r.get("memory_mb"), (int, float))]
    elapsed = [r.get("elapsed") for r in rows
               if isinstance(r.get("elapsed"), (int, float))]
    states: dict = {}
    connected_true = 0
    browser_seen = 0
    for r in rows:
        st = r.get("state")
        if st is not None:
            states[st] = states.get(st, 0) + 1
        b = r.get("browser")
        if isinstance(b, dict) and "connected" in b:
            browser_seen += 1
            if b.get("connected") is True:
                connected_true += 1
    times = [r.get("time") for r in rows
             if isinstance(r.get("time"), (int, float))]
    latest = rows[-1] if rows else {}
    return {
        "samples": len(rows),
        "window_start": min(times) if times else None,
        "window_end": max(times) if times else None,
        "memory_mb": _stat(memory),
        "uptime_elapsed": {"latest": (elapsed[-1] if elapsed else None)},
        "states": states,
        "latest_state": latest.get("state"),
        "browser_connected_ratio": (round(connected_true / browser_seen, 3)
                                    if browser_seen else None),
        "latest_sample_at": latest.get("time"),
    }


def summarize_errors(rows: list) -> dict:
    by_type: dict = {}
    for r in rows:
        t = r.get("type") or "UNKNOWN"
        by_type[t] = by_type.get(t, 0) + 1
    latest = rows[-1] if rows else None
    return {
        "count": len(rows),
        "by_type": by_type,
        "latest": ({"time": latest.get("time"),
                    "type": latest.get("type"),
                    "message": (latest.get("message") or "")[:160]}
                   if latest else None),
    }


def build(root: Path = ROOT, now: float | None = None,
          limit: int = 5000) -> dict:
    now = now if isinstance(now, (int, float)) else time.time()
    metrics = _load_jsonl(root / "runtime/logs/metrics.jsonl", limit=limit)
    errors = _load_jsonl(root / "runtime/logs/errors.jsonl", limit=limit)
    summary = summarize_metrics(metrics)
    summary["errors"] = summarize_errors(errors)
    last = summary.get("latest_sample_at")
    age = (now - last) if isinstance(last, (int, float)) else None
    summary["latest_age_s"] = age
    summary["verdict"] = ("UNKNOWN" if age is None else
                          "STALE" if age > STALE_AFTER_S else "LIVE")
    summary["generated_at"] = now
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(
        ROOT / "runtime/state/runtime_telemetry.json"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = build(Path(args.root))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"verdict={summary['verdict']} samples={summary['samples']} "
              f"latest_state={summary['latest_state']} "
              f"errors={summary['errors']['count']} "
              f"mem_p95={summary['memory_mb']['p95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
