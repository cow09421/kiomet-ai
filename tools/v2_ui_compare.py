"""Small independent official DOM comparisons; selections only, no dispatch."""
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import ClientExtractor, decode_units, connect_dedicated
from kiomet_ai.camera import world_to_page
from kiomet_ai.observe import TOWER_TYPES
from kiomet_ai.ui_parse import UNIT_ZH
from playwright.async_api import async_playwright

UNIT_NAMES = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier", "Shell", "Emp", "Nuke", "Ruler")


async def main():
    out = ROOT / "runtime/research/v2"
    rows = []
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        ex = ClientExtractor(page)
        async def sample_ready():
            deadline=time.monotonic()+2
            while True:
                try:
                    return await ex.sample()
                except ValueError as e:
                    if str(e)!='current visibility cache pending' or time.monotonic()>=deadline:
                        raise
                    await asyncio.sleep(.01)
        try:
            await ex.attach()
            _, first = await sample_ready()
            view = await page.evaluate("""() => {const c=document.querySelector('canvas');
              const r=c.getBoundingClientRect();return {w:c.width,h:c.height,dpr:devicePixelRatio,
                left:r.left,top:r.top,cw:r.width,ch:r.height}}""")
            if view["dpr"] != 1 or view["left"] != 0 or view["top"] != 0:
                raise ValueError("only previously validated full-canvas DPR=1 projection allowed")
            cam = first["camera_candidate"]
            if not all(isinstance(v, (int, float)) for v in cam) or not 2 < cam[2] < 150:
                raise ValueError("camera candidate invalid")
            projected = []
            for tower in first["towers"]:
                x, y = world_to_page(*tower["position"], *cam, view["w"], view["h"], 1)
                if 80 < x < view["cw"] - 160 and 90 < y < view["ch"] - 110:
                    projected.append((tower, x, y))
            # Stratify limited diagnostic comparisons by owner; no PASS claim.
            chosen = []
            for relation in ("SELF", "NEUTRAL", "ENEMY", "ALLY", None):
                candidates=[t for t in projected if t[0]["relation"] == relation]
                candidates.sort(key=lambda t:t[0]['units7'][0]!=1)
                chosen += candidates[:5]
            for initial, _, _ in chosen:
                _, before = await sample_ready()
                if before["document_time_origin"] != first["document_time_origin"] or before["player_id"] != first["player_id"]:
                    raise ValueError("document/player changed")
                current = next((t for t in before["towers"] if t["id"] == initial["id"]), None)
                if current is None:
                    continue
                x, y = world_to_page(*current["position"], *before["camera_candidate"], view["w"], view["h"], 1)
                clear = await page.evaluate("([x,y])=>document.elementFromPoint(x,y)?.tagName==='CANVAS'", [x, y])
                if not clear:
                    continue
                await page.mouse.click(x, y)
                await asyncio.sleep(.15)
                _, after = await sample_ready()
                dom = await page.evaluate("""() => {const img=document.querySelector('h2 img');let svg='';
                  if(img?.src.startsWith('data:image/svg+xml;base64,'))svg=atob(img.src.split(',')[1]);
                  else if(img?.src.startsWith('data:image/svg+xml'))svg=decodeURIComponent(img.src.split(',').slice(1).join(','));
                  return {headings:[...document.querySelectorAll('h2')].map(e=>e.innerText),
                  heading_fill:svg.match(/fill=['\"]([^'\"]+)['\"]/)?.[1]??null,
                  rows:[...document.querySelectorAll('p[title]')].map(e=>({unit:e.title,text:e.innerText})),
                  titles:[...document.querySelectorAll('[title]')].filter(e=>e.getBoundingClientRect().width>0)
                    .map(e=>({tag:e.tagName,title:e.title,text:e.innerText})).slice(0,80)}}""")
                _, bracket_end=await sample_ready()
                target = next((t for t in after["towers"] if t["id"] == current["id"]), None)
                end_target=next((t for t in bracket_end['towers'] if t['id']==current['id']),None)
                selected = after["selected_tower"] == current["id"] == bracket_end['selected_tower']
                stable=target is not None and end_target is not None and target['units7']==end_target['units7'] and target['type']==end_target['type']
                units = decode_units(target["units7"]) if target else None
                counts = dict(units.counts) if units else None
                expected_fill={'SELF':'#74b9ffff','NEUTRAL':'none','ENEMY':'#c0392bff','ALLY':'#8644fcff'}.get(target['relation']) if target else None
                relation_check={'ui_fill':dom['heading_fill'],'expected_fill':expected_fill,
                    'coherent':selected and stable,'match':selected and stable and expected_fill is not None and dom['heading_fill']==expected_fill}
                comparisons = []
                for row in dom["rows"]:
                    name = UNIT_ZH.get(row["unit"], row["unit"])
                    if name in UNIT_NAMES and counts is not None and '/' in row['text']:
                        unit = UNIT_NAMES.index(name)
                        comparisons.append({"unit": row["unit"], "ui": int(row["text"].split('/')[0]),
                                            "memory": counts[unit],
                                            "capacity_ui":int(row['text'].split('/')[1]),
                                            "coherent":selected and stable,
                                            "match": selected and stable and int(row["text"].split('/')[0]) == counts[unit]})
                rows.append({"id": current["id"], "selected_id": after["selected_tower"],
                    "selection_confirmed": selected, "relation": current["relation"],
                    "type": TOWER_TYPES[target["type"]] if target else None,
                    "type_id":target['type'] if target else None,
                    "units7":target['units7'] if target else None,
                    "morale":target['morale'] if target else None,
                    "delay_ticks":target['delay_ticks'] if target else None,
                    "tick_bracket":[after['tick'],bracket_end['tick']],
                    "sample_bracket":[after['sampled_at_ms'],bracket_end['sampled_at_ms']],
                    "relation_check":relation_check,
                    "ui": dom, "comparisons": comparisons})
                print(json.dumps(rows[-1], ensure_ascii=True), flush=True)
        finally:
            await ex.close()
    report = {"status": "PARTIAL", "timestamp": time.time(), "rows": rows,
        "compared_fields": sum(len(r["comparisons"]) for r in rows),
        "matched_fields": sum(c["match"] for r in rows for c in r["comparisons"]),
        "coherent_fields":sum(c['coherent'] for r in rows for c in r['comparisons']),
        "relation_fields":sum(r['relation_check']['coherent'] for r in rows),
        "matched_relations":sum(r['relation_check']['match'] for r in rows),
        "tactical_commands": 0, "limits": "limited selections, candidate camera, not M1 gate evidence"}
    (out / "ui-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    (out / f"ui-comparison-{uuid4().hex[:12]}.json").write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
