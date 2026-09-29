"""GPU／Chromium 崩潰遙測索引（唯讀）。

彙整專用 Chromium 的啟動／崩潰日誌與 crash incidents，
產出 GPU fallback 事件的機器可讀索引，協助 P0
PVP-ISOLATED-CHROMIUM-GPU-FALLBACK 診斷。

只讀；不刪任何資料；不觸碰 browser.py。
輸出 runtime/research/crash/gpu-incident-index.json。
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GPU_EXIT = re.compile(r"GPU process exited unexpectedly: exit_code=(-?\d+)")
GPU_CRASHED = re.compile(r"The GPU process has crashed (\d+) time")
GPU_UNUSABLE = re.compile(r"GPU process isn't usable\. Goodbye")
SANDBOX_DENY = re.compile(r"Sandbox cannot access executable (.+?)\. Check")
NETWORK_CRASH = re.compile(r"Network service crashed")
DEVTOOLS = re.compile(r"DevTools listening on (ws://\S+)")
FATAL_ANY = re.compile(r":FATAL:")


def decode_exit_code(code: int) -> str:
    return "0x%08X" % (code & 0xFFFFFFFF)


def parse_chromium_log(text: str) -> dict:
    """解析單一日誌文字，抽出 GPU fallback 證據。"""
    gpu_exits = []
    gpu_crashed_max = 0
    gpu_unusable = False
    sandbox_denials = []
    network_crashes = 0
    fatals = 0
    devtools = []
    for line in text.splitlines():
        m = GPU_EXIT.search(line)
        if m:
            code = int(m.group(1))
            gpu_exits.append({"exit_code": code,
                              "exit_code_hex": decode_exit_code(code)})
        m = GPU_CRASHED.search(line)
        if m:
            gpu_crashed_max = max(gpu_crashed_max, int(m.group(1)))
        if GPU_UNUSABLE.search(line):
            gpu_unusable = True
        m = SANDBOX_DENY.search(line)
        if m:
            sandbox_denials.append(m.group(1))
        if NETWORK_CRASH.search(line):
            network_crashes += 1
        if FATAL_ANY.search(line):
            fatals += 1
        m = DEVTOOLS.search(line)
        if m:
            devtools.append(m.group(1))
    return {
        "gpu_exit_count": len(gpu_exits),
        "gpu_exit_codes": sorted({e["exit_code_hex"] for e in gpu_exits}),
        "gpu_crashed_max": gpu_crashed_max,
        "gpu_unusable_fatal": gpu_unusable,
        "sandbox_denials": sandbox_denials,
        "network_crashes": network_crashes,
        "fatal_lines": fatals,
        "devtools_endpoints": devtools,
        "gpu_fallback_confirmed": bool(gpu_exits and gpu_unusable),
    }


def scan_logs(log_dir: Path) -> dict:
    """掃描日誌目錄；只讀。"""
    files = []
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("chromium*.log")):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            parsed = parse_chromium_log(text)
            parsed["file"] = path.name
            parsed["bytes"] = len(text)
            files.append(parsed)
    return files


def scan_incidents(crash_dir: Path) -> dict:
    incidents = []
    base = crash_dir / "incidents"
    if base.is_dir():
        for path in sorted(base.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            incidents.append({"file": path.name,
                              "incident_id": doc.get("incident_id"),
                              "signature": doc.get("signature")
                              or doc.get("kind") or "UNKNOWN"})
    return {"incident_count": len(incidents),
            "incidents": incidents}


def build_index(root: Path = ROOT) -> dict:
    logs = scan_logs(root / "runtime/logs")
    incidents = scan_incidents(root / "runtime/research/crash")
    total_gpu_exits = sum(f["gpu_exit_count"] for f in logs)
    any_fallback = any(f["gpu_fallback_confirmed"] for f in logs)
    return {
        "generated_at": time.time(),
        "logs_scanned": len(logs),
        "total_gpu_exits": total_gpu_exits,
        "gpu_fallback_confirmed": any_fallback,
        "gpu_exit_codes": sorted({c for f in logs
                                  for c in f["gpu_exit_codes"]}),
        "crashes": incidents["incident_count"],
        "files": logs,
        "incidents": incidents["incidents"],
        "verdict": ("GPU_FALLBACK_CONFIRMED" if any_fallback
                    else "NO_GPU_FALLBACK_EVIDENCE"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(
        ROOT / "runtime/research/crash/gpu-incident-index.json"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    index = build_index(Path(args.root))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(index, ensure_ascii=False))
    else:
        print(f"verdict={index['verdict']} "
              f"gpu_exits={index['total_gpu_exits']} "
              f"codes={index['gpu_exit_codes']} "
              f"crashes={index['crashes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
