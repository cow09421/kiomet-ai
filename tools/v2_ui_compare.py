"""Small independent official DOM comparisons; selections only, no dispatch."""
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import ClientExtractor, decode_many, connect_dedicated
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
        try:
            await ex.attach()
            _, first = await ex.sample()
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
            for relation in ("SELF", "NEUTRAL", None):
                chosen += [t for t in projected if t[0]["relation"] == relation][:3]
            for initial, _, _ in chosen:
                _, before = await ex.sample()
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
                _, after = await ex.sample()
                dom = await page.evaluate("""() => ({headings:[...document.querySelectorAll('h2')].map(e=>e.innerText),
                  rows:[...document.querySelectorAll('p[title]')].map(e=>({unit:e.title,text:e.innerText}))
                  .filter(r=>/^\\d+\\/\\d+$/.test(r.text.trim()))})""")
                target = next((t for t in after["towers"] if t["id"] == current["id"]), None)
                selected = after["selected_tower"] == current["id"]
                units = decode_many(target["units7"]) if target else None
                counts = dict(units.counts) if units else None
                comparisons = []
                for row in dom["rows"]:
                    name = UNIT_ZH.get(row["unit"], row["unit"])
                    if name in UNIT_NAMES and counts is not None:
                        unit = UNIT_NAMES.index(name)
                        comparisons.append({"unit": row["unit"], "ui": int(row["text"].split('/')[0]),
                                            "memory": counts[unit],
                                            "match": selected and int(row["text"].split('/')[0]) == counts[unit]})
                rows.append({"id": current["id"], "selected_id": after["selected_tower"],
                    "selection_confirmed": selected, "relation": current["relation"],
                    "type": TOWER_TYPES[target["type"]] if target else None,
                    "ui": dom, "comparisons": comparisons})
                print(json.dumps(rows[-1], ensure_ascii=True), flush=True)
        finally:
            await ex.close()
    report = {"status": "PARTIAL", "timestamp": time.time(), "rows": rows,
        "compared_fields": sum(len(r["comparisons"]) for r in rows),
        "matched_fields": sum(c["match"] for r in rows for c in r["comparisons"]),
        "tactical_commands": 0, "limits": "limited selections, candidate camera, not M1 gate evidence"}
    (out / "ui-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
