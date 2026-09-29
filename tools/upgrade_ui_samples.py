"""升級 UI 真值採樣：唯讀點選己方塔，讀升級按鈕列。

每塔保存 tower_id／tower_ref／tower_type／owner／UI upgrade rows
（title、disabled、🔒）／前置進度／timestamp／match_id。
禁止真升級：只讀 DOM，不點擊任何升級按鈕。
"""
import argparse
import asyncio
import json
import statistics
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

from camera_transform import world_to_page
from live_page import find_live_playwright_page

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/research/upgrade/ui"
ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"


def status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=3))


async def find_camera(session, towers):
    """與 unit_ui_samples 相同的 WASM 記憶體相機搜尋。"""
    mx = statistics.median(t["position"][0] for t in towers)
    my = statistics.median(t["position"][1] for t in towers)
    proto = (await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
    objs = (await session.send("Runtime.queryObjects", {"prototypeObjectId": proto}))["objects"]["objectId"]
    try:
        ret = await session.send("Runtime.callFunctionOn", {"objectId": objs, "returnByValue": True,
            "arguments": [{"value": mx}, {"value": my}],
            "functionDeclaration": """function(mx,my){return this.flatMap(m=>{const v=new DataView(m.buffer),out=[];
              for(let o=0x171680;o<0x171780;o+=4){if(o+32>=v.byteLength)break;
                let z=v.getFloat32(o,true),x=v.getFloat32(o+24,true),y=v.getFloat32(o+28,true);
                if(z>2&&z<150&&Math.abs(x-mx)<100&&Math.abs(y-my)<100)out.push([o,x,y,z]);}
              return out})}"""})
        candidates = ret["result"]["value"]
        if not candidates:
            raise ValueError("相機條件在已知位置失效；停止")
        chosen = candidates[0]
        if any(max(abs(a - b) for a, b in zip(chosen[1:], c[1:])) > .2 for c in candidates):
            raise ValueError(f"相機候選互相矛盾：{candidates}")
        return chosen
    finally:
        await session.send("Runtime.releaseObject", {"objectId": objs})
        await session.send("Runtime.releaseObject", {"objectId": proto})


async def main(limit):
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    match_id = anchor["match_id"]
    st = status()
    if st["game"]["state"] != "IN_MATCH" or st["game"]["match"]["id"] != match_id:
        raise ValueError("目標對局不符")
    report = {"match_id": match_id, "samples": [], "sent_actions": 0}
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        page = await find_live_playwright_page(browser)
        session = await page.context.new_cdp_session(page)
        try:
            towers = anchor["towers"]
            first_cam = await find_camera(session, towers)
            proto = (await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
            mems = (await session.send("Runtime.queryObjects", {"prototypeObjectId": proto}))["objects"]["objectId"]
            view = await page.evaluate("""() => {let r=document.querySelector('canvas').getBoundingClientRect();
                return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
            chosen = [t for t in towers if t.get("owner") == "SELF"][:limit]
            rest = limit - len(chosen)
            neutrals = [t for t in towers if t.get("owner") == "NEUTRAL"][:max(0, rest)]
            rest2 = rest - len(neutrals)
            others = [t for t in towers if t.get("owner") not in ("SELF", "NEUTRAL")][:max(0, rest2)]
            queue = chosen + neutrals + others
            for tower in queue:
                x, y = world_to_page(*tower["position"], *first_cam[1:],
                                     *view["viewport"], view["dpr"],
                                     view["canvas"][0], view["canvas"][1])
                await page.mouse.click(x, y)
                await asyncio.sleep(0.15)
                info = await page.evaluate("""() => ({
                  headings: [...document.querySelectorAll('h2')].map(e => e.innerText),
                  rows: [...document.querySelectorAll('p[title]')].map(e => ({unit: e.title, count_text: e.innerText})),
                  upgrades: [...document.querySelectorAll('div[title]')].map(e => ({title: e.title})),
                  notes: [...document.querySelectorAll('p[title]')].map(e => e.title)
                    .filter(t => t.length > 20)})""")
                memory = await session.send("Runtime.callFunctionOn", {
                    "objectId": mems, "returnByValue": True,
                    "arguments": [{"value": tower["tower_ref"]}],
                    "functionDeclaration": """function(p){if(this.length!==1)throw Error('memory count');
                      return Array.from(new Uint8Array(this[0].buffer,p,48))}"""})
                if "exceptionDetails" in memory:
                    raise ValueError(str(memory["exceptionDetails"]))
                await page.mouse.click(40, 300, button="right")
                report["samples"].append({
                    "tower_id": tower["packed_id"], "tower_ref": tower["tower_ref"],
                    "tower_type": tower.get("tower_type"),
                    "owner": tower.get("owner"), "screen": [round(x, 2), round(y, 2)],
                    "timestamp": time.time(), "match_id": match_id,
                    "struct_bytes": memory["result"]["value"],
                    "ui": info})
        finally:
            await session.send("Runtime.releaseObject", {"objectId": mems})
            await session.send("Runtime.releaseObject", {"objectId": proto})
            await session.detach()
    dest = OUT / f"upgrade_ui_ground_truth_{match_id}.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"match": match_id, "samples": len(report["samples"]),
                      "sent_actions": status()["sent_actions"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=4)
    main_args = parser.parse_args()
    asyncio.run(main(main_args.limit))
