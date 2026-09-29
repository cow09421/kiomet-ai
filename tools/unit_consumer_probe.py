"""短暫觀察正式 Units::available 的參數與資料；只讀，不呼叫遊戲函式。"""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/research/units"
EXPECTED = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"
OFFSET = 0xF9203  # production func[1637] Units::available entry, wasm-objdump 確認


def status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=3))


async def read_value(session, prop):
    response = await session.send("Runtime.getProperties", {"objectId": prop["value"]["objectId"], "ownProperties": True})
    return next(p["value"]["value"] for p in response["result"] if p["name"] == "value")


async def main(samples=80):
    s = status()
    if s["game"]["state"] != "IN_MATCH":
        raise ValueError("目前不在對局")
    match_id = s["game"]["match"]["id"]
    ui = json.loads((OUT / f"unit-ui-series-{match_id}.json").read_text(encoding="utf8"))
    tower = next(t for t in ui["rounds"][0]["towers"]
                 if t["owner_candidate"] == "SELF" and t["info"]["rows"])
    result = {"match_id":match_id,"time":time.time(),"selected_tower":tower["packed_id"],
              "source_function":"Units::available","production_function":1637,"offset":OFFSET,
              "samples":[],"pause_seconds":[],"sent_actions":0}
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:"+port)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        await page.mouse.click(*tower["screen"])
        await asyncio.sleep(.15)
        result["ui_before"] = await page.evaluate("""() => [...document.querySelectorAll('p[title]')]
            .map(e=>({unit:e.title,count:e.innerText})).filter(e=>/^\\d+\\/\\d+$/.test(e.count.trim()))""")
        session = await page.context.new_cdp_session(page)
        scripts, queue = [], asyncio.Queue()
        session.on("Debugger.scriptParsed", lambda e: scripts.append(e))
        session.on("Debugger.paused", lambda e: queue.put_nowait(e))
        bp, paused = None, False
        try:
            proto = (await session.send("Runtime.evaluate", {"expression":"WebAssembly.Memory.prototype"}))["result"]["objectId"]
            objs = (await session.send("Runtime.queryObjects", {"prototypeObjectId":proto}))["objects"]["objectId"]
            await session.send("Debugger.enable")
            script = next(x for x in scripts if x.get("scriptLanguage") == "WebAssembly" and x.get("length") == 1744720)
            raw = await session.send("Debugger.getScriptSource", {"scriptId":script["scriptId"]})
            if hashlib.sha256(base64.b64decode(raw["bytecode"])).hexdigest() != EXPECTED:
                raise ValueError("正式 WASM 版本不同")
            response = await session.send("Debugger.setBreakpoint", {"location":{
                "scriptId":script["scriptId"],"lineNumber":0,"columnNumber":OFFSET}})
            bp = response["breakpointId"]
            if response["actualLocation"]["columnNumber"] != OFFSET:
                raise ValueError("斷點位置不符")
            for number in range(samples):
                if status()["game"]["match"]["id"] != match_id:
                    break
                event = await asyncio.wait_for(queue.get(), 4)
                paused = True
                started = time.monotonic()
                if bp not in event.get("hitBreakpoints", []):
                    raise ValueError("非本次斷點")
                frame = event["callFrames"][0]
                scope = next(x for x in frame["scopeChain"] if x["type"] == "local")
                props = (await session.send("Runtime.getProperties", {
                    "objectId":scope["object"]["objectId"],"ownProperties":True}))["result"]
                chosen = {p["name"]:p for p in props if p["name"] in ("$var0","$var1")}
                values = dict(zip(chosen,await asyncio.gather(*(read_value(session,p) for p in chosen.values()))))
                ptr = values.get("$var0")
                if isinstance(ptr,int) and ptr > 0:
                    memory = await session.send("Runtime.callFunctionOn", {"objectId":objs,"returnByValue":True,
                        "arguments":[{"value":ptr}],
                        "functionDeclaration":"function(p){return this.map(m=>Array.from(new Uint8Array(m.buffer,p,16)))}"})
                    bytes_ = memory["result"].get("value")
                else:
                    bytes_ = None
                result["samples"].append({"number":number,"values":values,"bytes":bytes_})
                await session.send("Debugger.resume")
                paused = False
                result["pause_seconds"].append(time.monotonic()-started)
            result["max_pause_seconds"] = max(result["pause_seconds"],default=0)
        finally:
            if bp:
                try:
                    await session.send("Debugger.removeBreakpoint", {"breakpointId":bp})
                except Exception:
                    pass
            if paused or not queue.empty():
                try:
                    await session.send("Debugger.resume")
                except Exception:
                    pass
            try:
                await session.send("Debugger.disable")
            finally:
                await session.detach()
        await page.mouse.click(40,300,button="right")
    result["after"] = {"state":status()["state"],"match":status()["game"]["match"]["id"],
                       "sent_actions":status()["sent_actions"]}
    (OUT / f"consumer-probe-{match_id}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"match":match_id,"hits":len(result["samples"]),
                      "max_pause":result.get("max_pause_seconds"),"ui_rows":result.get("ui_before"),
                      "after":result["after"]},ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
