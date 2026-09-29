"""同局讀鏡頭並擷取塔點選畫面；只做點選與取消選取，不拖曳。"""
import asyncio
import json
from pathlib import Path
import time
import urllib.request

from playwright.async_api import async_playwright
from camera_transform import world_to_page

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/research/source-map/verified-anchor-current.json"
OUT = ROOT / "runtime/research/source-map/human-verification"


def status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status"))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = json.loads(SOURCE.read_text(encoding="utf8"))
    if status()["game"]["match"]["id"] != anchor["match_id"]:
        raise ValueError("對局與塔錨點不一致")
    report = {"match_id": anchor["match_id"], "time": time.time(), "towers": [], "send": False}
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        session = await page.context.new_cdp_session(page)
        try:
            proto = await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"})
            objs = await session.send("Runtime.queryObjects", {"prototypeObjectId": proto["result"]["objectId"]})
            properties = await session.send("Runtime.getProperties", {"objectId": objs["objects"]["objectId"], "ownProperties": True})
            memory_ids = [p["value"]["objectId"] for p in properties["result"] if p.get("value", {}).get("objectId")]
            async def camera():
                for oid in memory_ids:
                    ret = await session.send("Runtime.callFunctionOn", {
                        "objectId": oid, "returnByValue": True,
                        "functionDeclaration": """function(){const v=new DataView(this.buffer);if(v.byteLength<1513244)return null;
                            return [v.getFloat32(0x171714,true),v.getFloat32(0x171718,true),v.getFloat32(0x1716FC,true)]}"""})
                    value = ret["result"].get("value")
                    if value and 1 < value[2] < 500:
                        return value
                raise ValueError("找不到已確認的鏡頭值")
            cam = await camera()
            meta = await page.evaluate("""() => {const c=document.querySelector('canvas'),r=c.getBoundingClientRect();
                return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
            report["camera"] = cam
            report["view"] = meta
            await page.screenshot(path=str(OUT / "overview.png"), type="png", timeout=10000)
            candidates = []
            for tower in anchor["towers"]:
                x, y = world_to_page(*tower["position"], *cam, *meta["viewport"], meta["dpr"],
                                     meta["canvas"][0], meta["canvas"][1])
                if 65 < x < meta["viewport"][0]-65 and 65 < y < meta["viewport"][1]-65:
                    candidates.append((tower,x,y))
            own = [(t,x,y) for t,x,y in candidates if t["owner"] == "SELF"]
            other = [(t,x,y) for t,x,y in candidates if t["owner"] != "SELF"]
            chosen = own[:5] + other[:5]
            for number,(tower,x,y) in enumerate(chosen,1):
                if status()["game"]["match"]["id"] != anchor["match_id"]:
                    break
                now = await camera()
                if max(abs(a-b) for a,b in zip(cam,now)) > .05:
                    raise ValueError("鏡頭已移動，停止使用舊座標")
                rect = {"x":max(0,x-65),"y":max(0,y-65),"width":130,"height":130}
                await page.screenshot(path=str(OUT / f"tower_{number}_before.png"),clip=rect,type="png")
                await page.mouse.click(x,y,delay=100)
                await asyncio.sleep(.2)
                await page.screenshot(path=str(OUT / f"tower_{number}_selected.png"),clip=rect,type="png")
                await page.mouse.click(40,300,button="right")
                report["towers"].append({"number":number,"packed_id":tower["packed_id"],"id":tower["id"],
                                         "world":tower["position"],"screen":[round(x,2),round(y,2)],
                                         "owner_candidate":tower["owner"],"clip":rect,
                                         "camera":now})
            report["after"] = {"game":status()["game"],"browser":status()["browser"]}
        finally:
            await session.detach()
    (OUT / "verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"match":report["match_id"],"camera":report["camera"],"view":report["view"],"n":len(report["towers"]),"own":len(own),"other":len(other)},ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
