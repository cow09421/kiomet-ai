"""首次 UI 派兵的只讀演練；不按鍵、不點選、不拖曳、不送命令。"""
import asyncio
import json
from pathlib import Path
import time

from playwright.async_api import async_playwright
from camera_transform import world_to_page
from verify_tower_screen import ROOT, SOURCE, OUT, status


async def main():
    anchor = json.loads(SOURCE.read_text(encoding="utf8"))
    neighbors = json.loads((OUT / "neighbor-verification.json").read_text(encoding="utf8"))
    if neighbors["match_id"] != anchor["match_id"]:
        raise ValueError("道路證據與塔錨點不屬於同一局")
    edge = neighbors["edges"][0]
    ids = (edge["from"], edge["to"])
    by_id = {t["packed_id"]: t for t in anchor["towers"]}
    prior = json.loads((OUT / "verification.json").read_text(encoding="utf8"))
    cam, view = prior["camera"], prior["view"]
    s = status()
    now = time.time()
    checks = {
        "platform_running": s["state"] == "RUNNING" and s["mode"] == "live",
        "same_active_match": s["game"]["state"] == "IN_MATCH" and s["game"]["match"]["id"] == anchor["match_id"],
        "status_fresh": now - s["game"]["updated_at"] < 10,
        "both_self_at_anchor": all(by_id[i]["owner"] == "SELF" for i in ids),
        "graph_neighbor": tuple(ids) in [tuple(e) for e in anchor["edges"]],
        "road_visual_confirmed": edge["road_visible"] is True,
        "no_prior_real_actions": s["sent_actions"] == 0,
        "isolated_browser": s["browser"]["mode"] == "headed-isolated-desktop" and s["browser"]["user_desktop_window_count"] == 0,
    }
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        session = await page.context.new_cdp_session(page)
        try:
            proto = await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"})
            objs = await session.send("Runtime.queryObjects", {"prototypeObjectId": proto["result"]["objectId"]})
            props = await session.send("Runtime.getProperties", {"objectId": objs["objects"]["objectId"], "ownProperties": True})
            ids_mem = [p["value"]["objectId"] for p in props["result"] if p.get("value", {}).get("objectId")]
            live_cam = None
            for oid in ids_mem:
                ret = await session.send("Runtime.callFunctionOn", {
                    "objectId": oid, "returnByValue": True,
                    "functionDeclaration": """function(){const v=new DataView(this.buffer);if(v.byteLength<1513244)return null;
                      return [v.getFloat32(0x171714,true),v.getFloat32(0x171718,true),v.getFloat32(0x1716FC,true)]}"""})
                value = ret["result"].get("value")
                if value and 1 < value[2] < 500:
                    live_cam = value
                    break
            checks["camera_readable_unchanged"] = live_cam is not None and max(abs(a-b) for a,b in zip(cam, live_cam)) < .05
            actual_view = await page.evaluate("""() => {const r=document.querySelector('canvas').getBoundingClientRect();
                return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
            checks["viewport_unchanged"] = actual_view == view
            if all(checks.values()):
                xy = [world_to_page(*by_id[i]["position"], *live_cam, *view["viewport"], view["dpr"],
                                    view["canvas"][0], view["canvas"][1]) for i in ids]
                x0,y0 = xy[0]; x1,y1 = xy[1]
                clip = {"x":min(x0,x1)-65,"y":min(y0,y1)-65,"width":abs(x0-x1)+130,"height":abs(y0-y1)+130}
                await page.screenshot(path=str(OUT / "final-dry-run.png"), clip=clip, type="png")
            else:
                xy = None
        finally:
            await session.detach()
    after = status()
    checks["same_match_after"] = after["game"]["match"]["id"] == anchor["match_id"] and after["game"]["state"] == "IN_MATCH"
    checks["zero_actions_after"] = after["sent_actions"] == 0
    report = {"time":time.time(),"match_id":anchor["match_id"],"checks":checks,
              "source":{"packed_id":ids[0],"world":by_id[ids[0]]["position"],"owner":"SELF", "screen":xy[0] if xy else None},
              "target":{"packed_id":ids[1],"world":by_id[ids[1]]["position"],"owner":"SELF", "screen":xy[1] if xy else None},
              "expected_path":[ids[0],ids[1]],"move_force_sent":False,
              "result":"PASS" if all(checks.values()) else "FAIL"}
    (OUT / "final-dry-run.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(report,ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
