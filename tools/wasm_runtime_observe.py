"""唯讀取得已載入 WASM 與短時間 CPU 取樣；不重載、不中斷、不送出遊戲輸入。"""
import asyncio
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/research/source-map"


async def main():
    port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
    report = {"utc_epoch": time.time(), "pages": [],
              "note": "CPU samples are not invocation counts. No breakpoint, reload or game input."}
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        for number, page in enumerate(browser.contexts[0].pages):
            if "kiomet.com" not in page.url:
                continue
            session = await page.context.new_cdp_session(page)
            scripts = []
            session.on("Debugger.scriptParsed", lambda event: scripts.append(event))
            entry = {"page": number, "url": page.url, "wasm": []}
            try:
                entry["menu"] = await page.evaluate("() => !!document.querySelector('#play_button')?.offsetParent")
                await session.send("Debugger.enable")
                for script in scripts:
                    if script.get("scriptLanguage") != "WebAssembly":
                        continue
                    source = await session.send("Debugger.getScriptSource", {"scriptId": script["scriptId"]})
                    data = base64.b64decode(source.get("bytecode", ""))
                    item = {k: script.get(k) for k in ("scriptId", "url", "codeOffset", "length", "hash")}
                    item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                    if data:
                        name = f"runtime-page{number}-script{script['scriptId']}.wasm"
                        (OUT / name).write_bytes(data)
                        item["file"] = name
                    entry["wasm"].append(item)
                await session.send("Debugger.disable")
                await session.send("Profiler.enable")
                await session.send("Profiler.setSamplingInterval", {"interval": 1000})
                await session.send("Profiler.start")
                await asyncio.sleep(5)
                profile = (await session.send("Profiler.stop"))["profile"]
                (OUT / f"runtime-page{number}-profile.json").write_text(json.dumps(profile), encoding="utf8")
                samples = Counter(profile.get("samples", []))
                rows = []
                for node in profile["nodes"]:
                    frame = node["callFrame"]
                    if "wasm" in frame.get("url", "") or "wasm" in frame.get("functionName", ""):
                        rows.append({"frame": frame, "samples": samples[node["id"]]})
                entry["wasm_samples"] = sorted(rows, key=lambda r: r["samples"], reverse=True)[:35]
                entry["total_samples"] = len(profile.get("samples", []))
            except Exception as exc:
                entry["error"] = str(exc)
            finally:
                await session.detach()
            report["pages"].append(entry)
    (OUT / "runtime-observation.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, indent=2)[:18000])


if __name__ == "__main__":
    asyncio.run(main())
