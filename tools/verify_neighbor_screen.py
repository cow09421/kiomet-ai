"""同一局擷取相鄰邊畫面，供人工核對道路；不發送遊戲行動。"""
import asyncio
import json
from pathlib import Path
import time

from playwright.async_api import async_playwright
from camera_transform import world_to_page
from verify_tower_screen import ROOT, SOURCE, OUT, status


async def main():
    anchor = json.loads(SOURCE.read_text(encoding="utf8"))
    match_id = anchor["match_id"]
    if status()["game"]["match"]["id"] != match_id:
        raise ValueError("對局已更換")
    prior = json.loads((OUT / "verification.json").read_text(encoding="utf8"))
    cam, view = prior["camera"], prior["view"]
    by_id = {t["packed_id"]: t for t in anchor["towers"]}
    edges = sorted({tuple(sorted(edge)) for edge in anchor["edges"]})
    candidates = []
    for a, b in edges:
        if a not in by_id or b not in by_id:
            continue
        ta, tb = by_id[a], by_id[b]
        xy = [world_to_page(*t["position"], *cam, *view["viewport"], view["dpr"],
                            view["canvas"][0], view["canvas"][1]) for t in (ta, tb)]
        if all(95 < x < view["viewport"][0] - 95 and 95 < y < view["viewport"][1] - 95 for x, y in xy):
            mid = ((xy[0][0] + xy[1][0]) / 2, (xy[0][1] + xy[1][1]) / 2)
            priority = (0 if ta["owner"] == "SELF" or tb["owner"] == "SELF" else 1,
                        abs(mid[0] - view["viewport"][0] / 2) + abs(mid[1] - view["viewport"][1] / 2))
            candidates.append((priority, a, b, xy))
    candidates.sort()
    chosen = candidates[:12]
    if len(chosen) < 10:
        raise ValueError("可視邊不足十條")
    report = {"match_id": match_id, "time": time.time(), "camera": cam, "view": view,
              "edges": [], "sent_actions": 0, "visual_assessment": "PENDING"}
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        session = await page.context.new_cdp_session(page)
        try:
            proto = await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"})
            objs = await session.send("Runtime.queryObjects", {"prototypeObjectId": proto["result"]["objectId"]})
            props = await session.send("Runtime.getProperties", {"objectId": objs["objects"]["objectId"], "ownProperties": True})
            ids = [p["value"]["objectId"] for p in props["result"] if p.get("value", {}).get("objectId")]
            async def camera():
                for oid in ids:
                    ret = await session.send("Runtime.callFunctionOn", {
                        "objectId": oid, "returnByValue": True,
                        "functionDeclaration": """function(){const v=new DataView(this.buffer);if(v.byteLength<1513244)return null;
                          return [v.getFloat32(0x171714,true),v.getFloat32(0x171718,true),v.getFloat32(0x1716FC,true)]}"""})
                    value = ret["result"].get("value")
                    if value and 1 < value[2] < 500:
                        return value
                raise ValueError("鏡頭不可讀")
            now = await camera()
            if max(abs(a-b) for a,b in zip(cam, now)) > .05:
                raise ValueError("鏡頭已移動")
            for number, (_, a, b, xy) in enumerate(chosen, 1):
                if status()["game"]["match"]["id"] != match_id:
                    raise ValueError("對局已更換")
                now = await camera()
                if max(abs(a-b) for a,b in zip(cam, now)) > .05:
                    raise ValueError("鏡頭已移動")
                x0, y0 = xy[0]
                x1, y1 = xy[1]
                clip = {"x": max(0, min(x0, x1) - 55), "y": max(0, min(y0, y1) - 55),
                        "width": abs(x0-x1)+110, "height": abs(y0-y1)+110}
                await page.evaluate("""xy => {const root=document.createElement('div');root.id='codex-edge-overlay';
                    root.style='position:fixed;inset:0;z-index:2147483647;pointer-events:none';
                    xy.forEach((p,i)=>{const dot=document.createElement('div');dot.textContent=i?'B':'A';
                      dot.style=`position:absolute;left:${p[0]-8}px;top:${p[1]-8}px;width:16px;height:16px;
                        border:2px solid #ffff00;border-radius:50%;color:#ffff00;font:bold 13px Arial;
                        text-shadow:0 0 2px #000;line-height:16px;text-align:center`;
                      root.appendChild(dot)});document.body.appendChild(root)}""", xy)
                try:
                    await page.screenshot(path=str(OUT / f"neighbor_{number:02d}.png"), clip=clip, type="png")
                finally:
                    await page.evaluate("() => document.querySelector('#codex-edge-overlay')?.remove()")
                report["edges"].append({"number": number, "from": a, "to": b, "screen": xy,
                                         "world": [by_id[a]["position"], by_id[b]["position"]],
                                         "owners": [by_id[a]["owner"], by_id[b]["owner"]],
                                         "image": f"neighbor_{number:02d}.png", "road_visible": None})
        finally:
            await session.detach()
    (OUT / "neighbor-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"match": match_id, "edges": len(report["edges"]), "camera": cam}))


if __name__ == "__main__":
    asyncio.run(main())
