"""Bounded source-tick semantics experiment; read-only memory, no game commands."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright

PROBE = """function(root) {
 const m=this.filter(m=>m.buffer.byteLength>1000000);
 if(m.length!==1)throw Error('ambiguous memory');
 const v=new DataView(m[0].buffer),u32=p=>v.getUint32(p,true);
 if(root+49040>v.byteLength)throw Error('root out of range');
 const core=u32(root+45828);
 return {origin:performance.timeOrigin,at:performance.now(),wall:Date.now(),
  singleton_present:u32(root+45720)!==0x80000000,
  tick:v.getUint16(root+45732,true),player:v.getUint16(core+248,true),
  life_candidate:u32(root+548),visible_pending:v.getUint8(root+45784),
  interpolation:v.getFloat32(root+45800,true),online:navigator.onLine,
  play:document.querySelector('#play_button')?.innerText ?? null,
  body:document.body.innerText.slice(0,1800)};
}"""


async def main(args):
    out = ROOT / "runtime/research/v2"
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        extractor = ClientExtractor(page)
        rows, snapshots = [], []
        began = time.monotonic()
        try:
            await extractor.attach()
            if args.join:
                button = page.locator("#play_button")
                if await button.is_visible():
                    await button.click()
                    await button.wait_for(state="hidden",timeout=60000)
                    await asyncio.sleep(2)
            root = (await extractor.metadata())['root_candidate']
            for phase, seconds in (("online_before", args.seconds), ("offline", 5), ("online_after", args.seconds)):
                if args.offline:
                    await page.context.set_offline(phase == "offline")
                elif phase == "offline":
                    continue
                end = time.monotonic() + seconds
                next_snapshot = 0
                while time.monotonic() < end:
                    start_ms = time.time_ns() // 1000000
                    r = await extractor.cdp.send("Runtime.callFunctionOn", {
                        "objectId": extractor.memories_id, "returnByValue": True,
                        "arguments": [{"value": root}], "functionDeclaration": PROBE})
                    if "exceptionDetails" in r:
                        raise ValueError(str(r["exceptionDetails"]))
                    row = r["result"]["value"]
                    row.update(phase=phase,host_start=start_ms,host_end=time.time_ns()//1000000)
                    if row["origin"] != extractor.time_origin:
                        raise ValueError("document changed")
                    rows.append(row)
                    if time.monotonic() >= next_snapshot:
                        try:
                            _, raw = await extractor.sample()
                            snapshots.append({"at": row["at"], "tick": row["tick"],
                                "towers": [{"id": t["id"], "owner": t["owner"], "units7": t["units7"]} for t in raw["towers"]]})
                        except ValueError as e:
                            snapshots.append({"at": row["at"], "error": str(e)})
                        next_snapshot = time.monotonic() + 1
                    await asyncio.sleep(.02)
        finally:
            if args.offline:
                await page.context.set_offline(False)
            await extractor.close()
        summaries = []
        for phase in dict.fromkeys(r["phase"] for r in rows):
            a = [r for r in rows if r["phase"] == phase]
            changes = [b["at"] for p,b in zip(a,a[1:]) if p["tick"] != b["tick"]]
            intervals = [y-x for x,y in zip(changes,changes[1:])]
            summaries.append({"phase": phase,"samples":len(a),"first_tick":a[0]["tick"],
                "last_tick":a[-1]["tick"],"changes":len(changes),"intervals_ms":intervals,
                "life_values":sorted({r["life_candidate"] for r in a}),
                "online":sorted({r["online"] for r in a}),
                "interpolation_first_last":[a[0]["interpolation"],a[-1]["interpolation"]]})
        report = {"status":"RESEARCH_CANDIDATE","seconds":time.monotonic()-began,
            "summary":summaries,"rows":rows,"snapshots":snapshots}
        path = out / f"tick-research-{uuid4().hex[:12]}.json"
        path.write_text(json.dumps(report,indent=2),encoding="utf8")
        print(json.dumps({"file":str(path),"summary":summaries}),flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds",type=int,default=15)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--join",action="store_true",help="Official Play/Play Again only")
    args = p.parse_args()
    if not 1<=args.seconds<=60:
        p.error("seconds must be 1..60")
    asyncio.run(main(args))
