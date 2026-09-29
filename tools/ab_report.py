"""A/B（對照）實驗收尾彙整：由遙測＋傾印目錄自動產生 run 報告。

唯讀；不碰平台。供 A1/B1/A2/B2 各組收尾時呼叫。
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELEM = ROOT / "runtime/research/crash/resource-telemetry.jsonl"
DUMPS = ROOT / "runtime/browser-profile/Crashpad/reports"
OUT = ROOT / "runtime/research/crash/ab"


def summarize_window(start_iso: str, end_iso: str, label: str,
                     capture: bool, note: str = ""):
    start = datetime.fromisoformat(start_iso).timestamp()
    end = datetime.fromisoformat(end_iso).timestamp()
    rows = [json.loads(l) for l in TELEM.read_text(encoding="utf8")
            .strip().splitlines() if l.strip()]
    win = [r for r in rows if start <= r["time"] <= end]
    matches, seen = [], set()
    for r in win:
        mid = (r.get("platform") or {}).get("match_id")
        if mid and mid not in seen:
            seen.add(mid)
            matches.append(mid)
    renderer = [p["rss_bytes"] for r in win
                for p in (r.get("browser_processes") or [])
                if p["type"] == "renderer" and p.get("rss_bytes")]
    js = [r["js_heap_used_bytes"] for r in win
          if r.get("js_heap_used_bytes")]
    sent = {(r.get("platform") or {}).get("sent_actions") for r in win} - {None}
    new_dumps = [p.name for p in DUMPS.glob("*.dmp")
                 if start <= p.stat().st_mtime <= end]
    crash = bool(new_dumps)
    duration_min = round((end - start) / 60, 1)
    result = (f"CRASH_{new_dumps[0][:8].upper()}" if crash
              else f"NO_CRASH_{int(duration_min)}M")
    report = {
        "arm": label, "capture": capture,
        "start": start_iso, "end": end_iso,
        "duration_minutes": duration_min,
        "result": result, "crash": crash,
        "new_dumps": new_dumps,
        "matches": matches,
        "telemetry_summary": {
            "samples": len(win),
            "renderer_rss_max_mb": round(max(renderer) / 1048576, 1) if renderer else None,
            "js_heap_max_mb": round(max(js) / 1048576, 1) if js else None,
            "sent_actions_all": sorted(sent),
        },
        "notes": note,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    dest = OUT / f"{label}-run.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf8")
    return report


def judge_pair(a: dict, b: dict) -> str:
    """依判讀狀態機（兩組各 60+ 分鐘）回結論。"""
    if not a or not b:
        return "INCOMPLETE"
    if a["crash"] and not b["crash"]:
        return "SCREENSHOT_STRONG_SUSPECT"
    if a["crash"] and b["crash"]:
        return "CAPTURE_NOT_REQUIRED_FOR_CRASH"
    if not a["crash"] and b["crash"]:
        return "DATA_DOES_NOT_SUPPORT_SCREENSHOT_AS_CAUSE"
    return "INCONCLUSIVE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="ISO 開始時間")
    parser.add_argument("--end", required=True, help="ISO 結束時間")
    parser.add_argument("--label", required=True, help="A1/B1/A2/B2")
    parser.add_argument("--capture", type=lambda v: v.lower() == "true",
                        required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    report = summarize_window(args.start, args.end, args.label,
                             args.capture, args.note)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
