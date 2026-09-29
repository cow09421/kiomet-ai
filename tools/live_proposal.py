"""真實乾跑冒煙：錨點＋結構探測＋相機→狀態→排名→提案→預檢。

止於 WAITING_FOR_EXECUTE（等待執行授權），絕不產生滑鼠輸入。
輸出 runtime/state/first_move_candidate.json＋預覽證據幀。
用法：python tools/live_proposal.py [--top N]
"""
import argparse
import asyncio
import json
import statistics
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dry_rank import rank_expansion_targets
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    build_real_tower_states,
    decode_owner_ruler_flag,
    decode_tower_type,
    decode_tower_units,
)
from kiomet_ai.proposal import run_dry_cycle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from camera_transform import world_to_page
from live_page import find_live_playwright_page

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"
CANDIDATE = ROOT / "runtime/state/first_move_candidate.json"
PREVIEW_DIR = ROOT / "runtime/research/preview"


def api(path: str, token: str | None = None, timeout=8):
    headers = {"X-Control-Token": token} if token else {}
    req = urllib.request.Request(f"http://127.0.0.1:8765{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


async def fresh_screen_map(page, session, towers: list):
    """唯讀相機＋世界→頁面換算。失敗回空映射（預檢會拒絕）。"""
    try:
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
            cams = ret["result"]["value"]
            if not cams:
                return {}, None
            cam = cams[0]
        finally:
            await session.send("Runtime.releaseObject", {"objectId": objs})
            await session.send("Runtime.releaseObject", {"objectId": proto})
        view = await page.evaluate("""() => {let r=document.querySelector('canvas').getBoundingClientRect();
            return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
        screen, canvas = {}, {"w": view["viewport"][0], "h": view["viewport"][1]}
        for t in towers:
            x, y = world_to_page(*t["position"], *cam[1:], *view["viewport"],
                                 view["dpr"], view["canvas"][0], view["canvas"][1])
            screen[t["packed_id"]] = (round(x, 2), round(y, 2))
        return screen, canvas
    except Exception:
        return {}, None


async def main(top: int):
    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    match_id = anchor["match_id"]
    st = api("/api/status")
    if st["state"] != "RUNNING" or st["game"]["state"] != "IN_MATCH" \
            or st["game"]["match"]["id"] != match_id:
        raise SystemExit(f"對局不符或平台非運行中：{st['game']}")
    probe_path = ROOT / f"runtime/research/units/unit-struct-probe-{match_id}.json"
    if not probe_path.exists():
        raise SystemExit("缺少本局結構探測；先跑 unit_struct_probe.py")
    probe = json.loads(probe_path.read_text(encoding="utf8"))
    prows = {r["packed_id"]: r for r in probe["rows"]}
    towers, edges = [], []
    for t in anchor["towers"]:
        if t["packed_id"] not in prows:
            continue
        raw = prows[t["packed_id"]]["bytes"][32:32 + 48]
        units = decode_tower_units(raw, tower_ref=t["tower_ref"])
        towers.append(ObservedTower(
            tower_id=t["packed_id"], tower_ref=t["tower_ref"],
            world_x=t["position"][0], world_y=t["position"][1],
            owner=t["owner"], owner_ruler=decode_owner_ruler_flag(raw),
            tower_type=decode_tower_type(raw), units_detail=units))
    for a, b in anchor.get("edges", []):
        edges.append(ObservedEdge(a, b))
    obs = MatchObservation(match_id=match_id, timestamp=time.time(),
                           towers=tuple(towers), edges=tuple(edges))
    states = build_real_tower_states(obs)
    by_id = {s.tower_id: s for s in states}
    ranked = rank_expansion_targets(states, match_id)
    result = {"match_id": match_id, "candidates": len(ranked),
              "proposal": None, "cycle": None, "sent_actions": 0}
    if ranked:
        async with async_playwright() as pw:
            port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
            browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
            page = await find_live_playwright_page(browser)
            session = await page.context.new_cdp_session(page)
            try:
                screen_map, canvas = await fresh_screen_map(page, session, anchor["towers"])
            finally:
                await session.detach()
        canvas = canvas or {"w": 0, "h": 0}
        cycle = run_dry_cycle(ranked[0], by_id, screen_map, canvas, match_id)
        proposal = cycle["proposal"]
        result["cycle"] = {"phase": cycle["phase"], "trail": list(cycle["trail"]),
                           "preflight": list(cycle["preflight"]),
                           "gate": cycle["gate"], "sent": cycle["sent"]}
        if proposal is not None and hasattr(proposal, "status"):
            import dataclasses
            result["proposal"] = dataclasses.asdict(proposal)
    CANDIDATE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"match": match_id, "candidates": len(ranked),
                      "phase": (result["cycle"] or {}).get("phase"),
                      "gate": (result["cycle"] or {}).get("gate"),
                      "sent_actions": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=1)
    asyncio.run(main(parser.parse_args().top))
