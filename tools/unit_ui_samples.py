"""同局點選塔讀 UI 兵力數字；不拖曳、不升級、不發送命令。"""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import time
import urllib.request

from playwright.async_api import async_playwright
from camera_transform import world_to_page
from live_page import find_live_playwright_page

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/research/units"
ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"


def status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=3))


async def camera(session, towers):
    mx = statistics.median(t["position"][0] for t in towers)
    my = statistics.median(t["position"][1] for t in towers)
    proto = (await session.send("Runtime.evaluate", {"expression":"WebAssembly.Memory.prototype"}))["result"]["objectId"]
    objs = (await session.send("Runtime.queryObjects", {"prototypeObjectId":proto}))["objects"]["objectId"]
    try:
        ret = await session.send("Runtime.callFunctionOn", {"objectId":objs,"returnByValue":True,
            "arguments":[{"value":mx},{"value":my}],
            "functionDeclaration":"""function(mx,my){return this.flatMap(m=>{const v=new DataView(m.buffer),out=[];
              for(let o=0x171680;o<0x171780;o+=4){if(o+32>=v.byteLength)break;
                let z=v.getFloat32(o,true),x=v.getFloat32(o+24,true),y=v.getFloat32(o+28,true);
                if(z>2&&z<150&&Math.abs(x-mx)<100&&Math.abs(y-my)<100)out.push([o,x,y,z]);}
              return out})}"""})
        candidates = ret["result"]["value"]
        if not candidates:
            raise ValueError("鏡頭物件未在已知位置附近；停止點選")
        chosen = candidates[0]
        if any(max(abs(a-b) for a,b in zip(chosen[1:], c[1:])) > .2 for c in candidates):
            raise ValueError(f"鏡頭候選互相矛盾：{candidates}")
        return chosen, candidates
    finally:
        await session.send("Runtime.releaseObject", {"objectId":objs})
        await session.send("Runtime.releaseObject", {"objectId":proto})


async def main(rounds, interval):
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    match_id = anchor["match_id"]
    if status()["game"]["state"] != "IN_MATCH" or status()["game"]["match"]["id"] != match_id:
        raise ValueError("錨點與目前對局不符")
    report = {"match_id":match_id,"rounds":[],"sent_actions":0,"method":"UI selection and passive WASM memory read"}
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:"+port)
        page = await find_live_playwright_page(browser)
        session = await page.context.new_cdp_session(page)
        proto = None
        objs = None
        try:
            proto = (await session.send("Runtime.evaluate", {"expression":"WebAssembly.Memory.prototype"}))["result"]["objectId"]
            objs = (await session.send("Runtime.queryObjects", {"prototypeObjectId":proto}))["objects"]["objectId"]
            first_cam, candidates = await camera(session, anchor["towers"])
            view = await page.evaluate("""() => {let r=document.querySelector('canvas').getBoundingClientRect();
                return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
            report["camera_candidates"] = candidates
            report["view"] = view
            projected = []
            for tower in anchor["towers"]:
                x,y = world_to_page(*tower["position"], *first_cam[1:], *view["viewport"], view["dpr"],
                                    view["canvas"][0], view["canvas"][1])
                if 80 < x < view["viewport"][0]-130 and 80 < y < view["viewport"][1]-100:
                    projected.append((tower,x,y))
            own = [row for row in projected if row[0]["owner"] == "SELF"]
            other = [row for row in projected if row[0]["owner"] != "SELF"]
            chosen = own[:5] + other[:6]
            if len(chosen) < 5:
                raise ValueError("可見塔不足五座")
            for turn in range(rounds):
                if turn:
                    await asyncio.sleep(interval)
                if status()["game"]["match"]["id"] != match_id or status()["game"]["state"] != "IN_MATCH":
                    break
                now, _ = await camera(session, anchor["towers"])
                if max(abs(a-b) for a,b in zip(first_cam[1:],now[1:])) > .1:
                    raise ValueError("鏡頭已移動，停止使用舊畫面座標")
                sample = {"time":time.time(),"camera":now,"towers":[]}
                for number,(tower,x,y) in enumerate(chosen,1):
                    if status()["game"]["match"]["id"] != match_id:
                        break
                    await page.mouse.click(x,y)
                    await asyncio.sleep(.12)
                    info = await page.evaluate("""() => ({headings:[...document.querySelectorAll('h2')].map(e=>e.innerText),
                      rows:[...document.querySelectorAll('p[title]')].map(e=>({unit:e.title,count_text:e.innerText}))
                      .filter(e=>/^\\d+\\/\\d+$/.test(e.count_text.trim()))})""")
                    memory = await session.send("Runtime.callFunctionOn", {
                        "objectId":objs,"returnByValue":True,
                        "arguments":[{"value":tower["tower_ref"]}],
                        "functionDeclaration":"""function(p){if(this.length!==1)throw Error('memory count');
                          return Array.from(new Uint8Array(this[0].buffer,p,48))}"""})
                    if "exceptionDetails" in memory:
                        raise ValueError(str(memory["exceptionDetails"]))
                    image = f"ui-r{turn+1}-tower{number}.png"
                    if turn == 0 and number <= 6:
                        await page.screenshot(path=str(OUT/image),type="png")
                    await page.mouse.click(40,300,button="right")
                    sample["towers"].append({"packed_id":tower["packed_id"],"world":tower["position"],
                        "owner_candidate":tower["owner"],"screen":[round(x,2),round(y,2)],
                        "tower_ref":tower["tower_ref"],"struct_bytes":memory["result"]["value"],
                        "info":info,"screenshot":image if turn==0 and number<=6 else None})
                report["rounds"].append(sample)
                (OUT / f"unit-ui-series-{match_id}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        finally:
            if objs:
                await session.send("Runtime.releaseObject", {"objectId":objs})
            if proto:
                await session.send("Runtime.releaseObject", {"objectId":proto})
            await session.detach()
    report["after"] = {"state":status()["state"],"match":status()["game"]["match"],
                       "sent_actions":status()["sent_actions"]}
    (OUT / f"unit-ui-series-{match_id}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"match":match_id,"rounds":len(report["rounds"]),
                      "towers":[len(r["towers"]) for r in report["rounds"]],"after":report["after"]},ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds",type=int,default=3,help="同局取樣輪數，預設 3")
    parser.add_argument("--interval",type=float,default=15,help="每輪間隔秒數，預設 15")
    args = parser.parse_args()
    asyncio.run(main(args.rounds,args.interval))
