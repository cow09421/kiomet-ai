"""多斷點觀測：5068/5078/5065/1126/1125 同時監聽＋視角動作，看誰是活的發送路徑。"""
import asyncio
import base64
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime/research/source-map"
EXPECTED = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"
FUNCS = [5068, 5078, 5065, 1126, 1125]


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status"))
    report = {"sha256": EXPECTED, "funcs": FUNCS, "hits": [],
              "game_before": before["game"], "utc_epoch": time.time(),
              "pause_seconds": []}
    lines = (OUT / "production-disassembly.txt").read_text(
        encoding="utf-8", errors="ignore").splitlines()
    offsets = {}
    for line in lines:
        m = re.match(r"([0-9a-f]+) func\[(\d+)\]", line)
        if m and int(m.group(2)) in FUNCS:
            offsets[int(m.group(2))] = int(m.group(1), 16)
    print("offsets:", {k: hex(v) for k, v in offsets.items()}, flush=True)
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        scored = []
        for p in browser.contexts[0].pages:
            if p.url != "https://kiomet.com/":
                continue
            menu = await p.evaluate(
                "() => !!document.querySelector('#play_button') && "
                "document.querySelector('#play_button').offsetParent !== null")
            n = await p.evaluate("() => document.body.innerText.length")
            scored.append((not menu, n, p))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        if not scored or not scored[0][0]:
            raise ValueError("找不到對局頁")
        page = scored[0][2]
        session = await page.context.new_cdp_session(page)
        scripts, queue = [], asyncio.Queue()
        session.on("Debugger.scriptParsed", lambda e: scripts.append(e))
        session.on("Debugger.paused", lambda e: queue.put_nowait(e))
        bps, paused = {}, False
        mem_oid = None
        try:
            await session.send("Debugger.enable")
            script = next(s for s in scripts if s.get("scriptLanguage") == "WebAssembly" and s.get("length") == 1744720)
            raw = await session.send("Debugger.getScriptSource", {"scriptId": script["scriptId"]})
            if hashlib.sha256(base64.b64decode(raw["bytecode"])).hexdigest() != EXPECTED:
                raise ValueError("正式版本已變更；拒絕觀測")
            for fi in FUNCS:
                r = await session.send("Debugger.setBreakpoint", {"location": {
                    "scriptId": script["scriptId"], "lineNumber": 0,
                    "columnNumber": offsets[fi]}})
                bps[r["breakpointId"]] = fi
            # WASM Memory 物件（讀參數指向位元組用）。
            proto = await session.send("Runtime.evaluate", {
                "expression": "WebAssembly.Memory.prototype", "returnByValue": False})
            objs = await session.send("Runtime.queryObjects", {
                "prototypeObjectId": proto["result"]["objectId"]})
            props = await session.send("Runtime.getProperties", {
                "objectId": objs["objects"]["objectId"], "ownProperties": True})
            ids = [p["value"]["objectId"] for p in props.get("result", [])
                   if (p.get("value") or {}).get("objectId")]
            best_size = -1
            for oid in ids:
                rr = await session.send("Runtime.callFunctionOn", {
                    "objectId": oid,
                    "functionDeclaration": "function(){return this.buffer.byteLength}",
                    "returnByValue": True})
                nn = rr.get("result", {}).get("value", 0)
                if nn > best_size:
                    best_size, mem_oid = nn, oid
            box = await page.evaluate("""() => {
                const c = document.querySelector('canvas');
                const r = c.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height};
            }""")
            cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
            await page.mouse.move(cx, cy)
            await page.mouse.down(button="right")
            for i in range(1, 7):
                await page.mouse.move(cx + 350 * i / 6, cy, steps=2)
                await asyncio.sleep(0.05)
            await page.mouse.up(button="right")
            await page.mouse.move(cx, cy)
            for _ in range(3):
                await page.mouse.wheel(0, -240)
                await asyncio.sleep(0.3)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and len(report["hits"]) < 12:
                try:
                    event = await asyncio.wait_for(queue.get(), 2)
                except asyncio.TimeoutError:
                    continue
                paused = True
                started = time.monotonic()
                try:
                    hits = [bps[b] for b in event.get("hitBreakpoints", []) if b in bps]
                    if not hits:
                        await session.send("Debugger.resume")
                        paused = False
                        continue
                    frame = event["callFrames"][0]
                    scope = next(s for s in frame["scopeChain"] if s["type"] == "local")
                    props = (await session.send("Runtime.getProperties", {
                        "objectId": scope["object"]["objectId"],
                        "ownProperties": True}))["result"]
                    vals = {}
                    for p in props:
                        if not p.get("name", "").startswith("$var"):
                            continue
                        v = p.get("value", {})
                        if "value" in v:
                            vals[p["name"]] = v["value"]
                        elif "objectId" in v:
                            inner = await session.send("Runtime.getProperties", {
                                "objectId": v["objectId"], "ownProperties": True})
                            got = next((q["value"]["value"] for q in inner["result"]
                                        if q["name"] == "value"
                                        and "value" in q.get("value", {})), None)
                            vals[p["name"]] = got if got is not None else {"ref": v.get("type")}
                    mem = {}
                    try:
                        for slot, base in (("p0", vals.get("$var0")),
                                           ("p2", vals.get("$var2"))):
                            if not isinstance(base, int):
                                continue
                            mr = await session.send("Runtime.callFunctionOn", {
                                "objectId": mem_oid,
                                "functionDeclaration": f"""function(){{
                                  const u8 = new Uint8Array(this.buffer, {base}, 128);
                                  return Array.from(u8, b => b.toString(16).padStart(2, '0')).join('');
                                }}""",
                                "returnByValue": True})
                            mem[slot] = mr.get("result", {}).get("value")
                    except Exception as em:
                        mem["error"] = str(em)[:80]
                    report["hits"].append({"funcs": hits, "t": time.time(),
                                           "locals": vals, "mem": mem})
                finally:
                    await session.send("Debugger.resume")
                    paused = False
                    report["pause_seconds"].append(time.monotonic() - started)
            for bid in list(bps):
                await session.send("Debugger.removeBreakpoint", {"breakpointId": bid})
            bps.clear()
            await session.send("Debugger.disable")
        except Exception as exc:
            report["error"] = str(exc)
        finally:
            for bid in list(bps):
                try:
                    await session.send("Debugger.removeBreakpoint", {"breakpointId": bid})
                except Exception:
                    pass
            if paused or not queue.empty():
                try:
                    await session.send("Debugger.resume")
                except Exception:
                    pass
            await session.send("Debugger.disable")
            await session.detach()
    after = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status"))
    report["game_after"] = after["game"]
    report["max_pause_seconds"] = max(report["pause_seconds"], default=0)
    (OUT / "command-observe-multi.json").write_text(json.dumps(report, indent=1), encoding="utf8")
    print(json.dumps({"hits": [(h["funcs"], len(h["locals"])) for h in report["hits"]],
                      "max_pause": report["max_pause_seconds"],
                      "error": report.get("error")}))


if __name__ == "__main__":
    asyncio.run(main())
