"""每局觀察快照：一命令為當局建 MatchObservation（含屏座標＋新鮮度）。
重用錨點檔（须同局），鏡頭現讀，屏座標現算；舊局檔保留，current 指針切換。
只讀＋計算，不發送、不拖曳。"""
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from playwright.async_api import async_playwright
from kiomet_ai.observe import build_snapshot, gate_check
import camera_transform as ct

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"
STATE_DIR = ROOT / "runtime/state"


def status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status"))


async def read_camera(page):
    session = await page.context.new_cdp_session(page)
    try:
        proto = await session.send("Runtime.evaluate", {
            "expression": "WebAssembly.Memory.prototype", "returnByValue": False})
        objs = await session.send("Runtime.queryObjects", {
            "prototypeObjectId": proto["result"]["objectId"]})
        props = await session.send("Runtime.getProperties", {
            "objectId": objs["objects"]["objectId"], "ownProperties": True})
        ids = [p["value"]["objectId"] for p in props.get("result", [])
               if (p.get("value") or {}).get("objectId")]
        best, best_size = ids[0], -1
        for oid in ids:
            r = await session.send("Runtime.callFunctionOn", {
                "objectId": oid,
                "functionDeclaration": "function(){return this.buffer.byteLength}",
                "returnByValue": True})
            n = r.get("result", {}).get("value", 0)
            if n > best_size:
                best, best_size = oid, n
        r = await session.send("Runtime.callFunctionOn", {
            "objectId": best,
            "functionDeclaration": """function(){
              const v = new DataView(this.buffer);
              return {cx: v.getFloat32(0x171714, true), cy: v.getFloat32(0x171718, true),
                      zoom: v.getFloat32(0x1716FC, true)};
            }""",
            "returnByValue": True})
        return r.get("result", {}).get("value")
    finally:
        await session.detach()


async def main():
    s = status()
    if s["game"]["state"] != "IN_MATCH":
        raise ValueError(f"非對局中（{s['game']['state']}），拒絕建快照")
    match_id = s["game"]["match"]["id"]
    anchor = json.loads(ANCHOR.read_text(encoding="utf-8"))
    if anchor.get("match_id") != match_id:
        raise ValueError(f"錨點屬舊局（{anchor.get('match_id')}），須重跑錨點；拒絕混用")
    port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        pages = [p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/"]
        target = None
        for page in pages:
            n = await page.evaluate("() => document.body.innerText.length")
            menu = await page.evaluate(
                "() => !!document.querySelector('#play_button') && "
                "document.querySelector('#play_button').offsetParent !== null")
            if not menu and n > 300:
                target = page
                break
        if target is None:
            raise ValueError("找不到對局頁")
        cam = await read_camera(target)
        meta = await target.evaluate("""() => {
            const c = document.querySelector('canvas');
            const r = c.getBoundingClientRect();
            return {viewport: [innerWidth, innerHeight],
                    canvas: [r.left, r.top, r.width, r.height],
                    dpr: devicePixelRatio};
        }""")
        await browser.close()
    cx, cy, zoom = cam["cx"], cam["cy"], cam["zoom"]
    vw, vh = meta["viewport"]
    dpr = meta["dpr"]
    screen_map = {}
    for t in anchor["towers"]:
        wx, wy = t["position"]
        sx, sy = ct.world_to_page(wx, wy, cx, cy, zoom, vw, vh, dpr,
                                  meta["canvas"][0], meta["canvas"][1])
        screen_map[t["packed_id"]] = (sx, sy)
    edges = [(a, b) for a, b in anchor.get("edges", []) if isinstance(a, int)]
    obs = build_snapshot(match_id,
                         {"cx": cx, "cy": cy, "zoom": zoom},
                         {"viewport": meta["viewport"], "canvas": meta["canvas"]},
                         dpr, anchor["towers"], edges, screen_map)
    ok, reason = gate_check(obs, match_id)
    import dataclasses
    doc = {"match_id": obs.match_id, "timestamp": obs.timestamp,
           "freshness": "FRESH" if ok else reason,
           "camera": obs.camera, "viewport": obs.viewport, "dpr": obs.dpr,
           "towers": [dataclasses.asdict(t) for t in obs.towers],
           "edges": [{"source": e.source, "target": e.target} for e in obs.edges]}
    (STATE_DIR / f"match-observation-{match_id}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (STATE_DIR / "match-observation-current.json").write_text(
        json.dumps({"match_id": match_id,
                    "file": f"match-observation-{match_id}.json",
                    "time": time.time()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps({"match": match_id, "towers": len(doc["towers"]),
                      "edges": len(doc["edges"]), "gate": reason,
                      "camera": [cx, cy, zoom]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
