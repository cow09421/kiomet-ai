"""低成本崩潰遙測：短暫唯讀 CDP 連線，每 20 秒記一筆，檔案上限 5 MB。"""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request

import psutil
from live_page import find_live_target_id
from cdp_probe import ROOT, Session

STATUS = "http://127.0.0.1:8765/api/status"
OUTPUT = ROOT / "runtime/research/crash/resource-telemetry.jsonl"


def sample():
    stamp = time.time()
    report = {"time": stamp, "platform": None, "processes": [], "browser_processes": [],
              "page_count": None, "frame_count": None, "js_heap_used_bytes": None,
              "js_heap_total_bytes": None, "wasm_memory_bytes": None,
              "cdp_session_count": None, "debugger_attached_count": None,
              "screenshot_queue_length": 0, "live_frame_buffer_count": None,
              "artifact_queue_length": None, "errors": []}
    try:
        status = json.load(urllib.request.urlopen(STATUS, timeout=3))
        report["platform"] = {"state":status["state"], "game":status["game"]["state"],
                              "match_id":status["game"]["match"]["id"] if status["game"].get("match") else None,
                              "sent_actions":status["sent_actions"], "live_sequence":status["live"]["sequence"],
                              "live_capture_ms":status["live"]["capture_ms"],
                              "live_frame_bytes":status["live"]["frame_bytes"]}
        report["live_frame_buffer_count"] = int(status["live"]["frame_bytes"] > 0)
        parent = psutil.Process(status["process"]["pid"])
        for proc in [parent, *parent.children(recursive=True)]:
            try:
                report["processes"].append({"pid": proc.pid, "name": proc.name(),
                                            "rss_bytes": proc.memory_info().rss})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
    except Exception as exc:
        report["errors"].append("status/process: " + str(exc))
    try:
        with Session("browser", timeout=3) as cdp:
            rows = cdp.call("SystemInfo.getProcessInfo")["processInfo"]
            rss = {p["pid"]: p["rss_bytes"] for p in report["processes"]}
            report["browser_processes"] = [{"pid":p["id"], "type":p["type"],
                                             "rss_bytes":rss.get(p["id"]), "cpu_seconds":p.get("cpuTime")}
                                            for p in rows]
        port = int((ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0])
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3))
        report["page_count"] = sum(p.get("type") == "page" for p in targets)
    except Exception as exc:
        report["errors"].append("browser: " + str(exc))
    try:
        with Session("https://kiomet.com/", page_id=find_live_target_id(), timeout=3) as cdp:
            value = cdp.call("Runtime.evaluate", {"expression": """(() => ({frames:window.frames.length+1,
              used:performance.memory?.usedJSHeapSize??null,total:performance.memory?.totalJSHeapSize??null}))()""",
              "returnByValue": True})["result"]["value"]
            report["frame_count"] = value["frames"]
            report["js_heap_used_bytes"] = value["used"]
            report["js_heap_total_bytes"] = value["total"]
            proto = cdp.call("Runtime.evaluate", {"expression":"WebAssembly.Memory.prototype"})["result"]["objectId"]
            objects = cdp.call("Runtime.queryObjects", {"prototypeObjectId":proto})["objects"]["objectId"]
            try:
                lengths = cdp.call("Runtime.callFunctionOn", {"objectId":objects,"returnByValue":True,
                    "functionDeclaration":"function(){return this.map(m=>m.buffer.byteLength)}"})["result"].get("value", [])
                report["wasm_memory_bytes"] = lengths
            finally:
                cdp.call("Runtime.releaseObject", {"objectId":objects})
                cdp.call("Runtime.releaseObject", {"objectId":proto})
    except Exception as exc:
        report["errors"].append("page: " + str(exc))
    return report


def append_bounded(row):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists() and OUTPUT.stat().st_size > 5_000_000:
        previous = OUTPUT.with_suffix(".jsonl.1")
        OUTPUT.replace(previous)
    with OUTPUT.open("a", encoding="utf8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=20)
    parser.add_argument("--duration", type=float, default=3600)
    args = parser.parse_args()
    until = time.monotonic() + args.duration
    while time.monotonic() < until:
        started = time.monotonic()
        append_bounded(sample())
        time.sleep(max(0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
