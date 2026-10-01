"""Finite own-tower hover evidence; no clicks, keys, dispatch or path reads."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.camera import world_to_page
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright


async def main():
    folder=ROOT/'runtime/research/v2'
    run=uuid4().hex[:12]
    rows=[]
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT/'src/kiomet_ai/v2').rglob('*'))
              if p.is_file() and p.suffix in ('.py','.js','.json')}
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        pages=[p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/']
        if len(pages)!=1: raise ValueError('dedicated official page absent or ambiguous')
        page=pages[0]
        ex=ClientExtractor(page)
        async def sample_ready():
            deadline=time.monotonic()+2
            while True:
                try: return await ex.sample()
                except ValueError as exc:
                    if str(exc)!='current visibility cache pending' or time.monotonic()>=deadline: raise
                    await asyncio.sleep(.01)
        try:
            await ex.attach()
            state,raw=await sample_ready()
            identity=(state.document_id,state.match_id.value,state.player_id.value)
            view=await page.evaluate("""() => {const c=document.querySelector('canvas'),r=c.getBoundingClientRect();
              return {w:c.width,h:c.height,cw:r.width,ch:r.height,left:r.left,top:r.top,dpr:devicePixelRatio}}""")
            if view['dpr']!=1 or view['left']!=0 or view['top']!=0: raise ValueError('unsupported projection')
            ids=[t.id for t in state.towers if t.owner.value==state.player_id.value][:4]
            for ident in ids:
                before,raw=await sample_ready()
                if (before.document_id,before.match_id.value,before.player_id.value)!=identity:
                    raise ValueError('cohort identity changed')
                tower=next((t for t in before.towers if t.id==ident and t.owner.value==before.player_id.value),None)
                if tower is None: continue
                x,y=world_to_page(*tower.position.value,*raw['camera_candidate'],view['w'],view['h'],1)
                if not 80<x<view['cw']-160 or not 90<y<view['ch']-110: continue
                clear=await page.evaluate("([x,y])=>document.elementFromPoint(x,y)?.tagName==='CANVAS'",[x,y])
                if not clear: continue
                path=folder/f'supply-line-ui-{run}-{ident}.png'
                # Hover alone cannot configure a line or dispatch a force.
                await page.mouse.move(x,y)
                await asyncio.sleep(.2)
                after,after_raw=await sample_ready()
                current=next((t for t in after.towers if t.id==ident and t.owner.value==after.player_id.value),None)
                if current is None or (after.document_id,after.match_id.value,after.player_id.value)!=identity:
                    raise ValueError('own hover anchor disappeared or changed identity')
                await page.screenshot(path=str(path))
                hovered=await page.evaluate("() => document.querySelector('canvas').matches(':hover')")
                rows.append({'tower':ident,'player':before.player_id.value,'before_sequence':before.sequence,
                    'after_sequence':after.sequence,'before_tick':before.tick.value,'after_tick':after.tick.value,
                    'before_flag':tower.supply_line_present.value,'after_flag':current.supply_line_present.value,
                    'selected_tower':after_raw['selected_tower'],'page_hover':[x,y],'canvas_hovered':hovered,
                    'screenshot':str(path.relative_to(ROOT)),'screenshot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'canonical_source':current.supply_line_present.source})
            await page.mouse.move(20,20)
        finally:
            await ex.close()
            if not page.is_closed(): await page.mouse.move(20,20)
    report={'status':'UI_EVIDENCE_CANDIDATE','rows':rows,'identity':identity,
        'client_sha256':state.client_sha256,'source_manifest':manifest,
        'limits':'Normal own-tower hover screenshot only. No independent Boolean correctness credit without visual review; no positive-line case manufactured.',
        'input_policy':'hover only; zero clicks, keys, commands, semantic WASM calls or path reads',
        'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path=folder/f'supply-line-ui-{run}.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'report':str(path),'rows':rows}),flush=True)


if __name__=='__main__': asyncio.run(main())
