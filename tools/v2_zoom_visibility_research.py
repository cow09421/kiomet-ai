"""One bounded ordinary canvas-wheel experiment; current visibility gates only."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright


async def main():
    folder = ROOT/'runtime/research/v2'
    lease = json.loads((folder/'headless-host.json').read_text())
    if lease['deadline_monotonic_ms']-time.monotonic_ns()//1000000 < 60000:
        raise ValueError('owned browser lease insufficient')
    rows, errors, known, scope = [], [], set(), None
    tag = uuid4().hex[:12]
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/kiomet_ai/v2').rglob('*'))
        if p.is_file() and p.suffix in ('.py', '.js', '.json')}
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/']
        if len(pages) != 1:
            raise ValueError('ambiguous official page')
        page = pages[0]
        if await page.evaluate("() => document.activeElement?.matches('input,textarea,[contenteditable=true]') || false"):
            raise ValueError('editable control focused')
        if not await page.evaluate("() => document.elementFromPoint(640,300)?.tagName==='CANVAS'"):
            raise ValueError('normal wheel target is not canvas')
        ex = ClientExtractor(page)
        try:
            await ex.attach()
            await page.mouse.move(640,300)
            for phase, delta, seconds in [('baseline',0,3),('zoom_out',636,5),('reverse_wheel',-636,5)]:
                meta = await ex.metadata()
                if (meta.get('active') is not True or meta.get('transport_connected') is not True
                        or meta.get('expanded_visibility') or (meta.get('play_text') or '').strip()):
                    raise RuntimeError('ordinary active match unavailable; wheel experiment ended')
                if delta:
                    await page.mouse.wheel(0,delta)
                end = time.monotonic()+seconds
                while time.monotonic()<end:
                    try:
                        state, raw = await ex.sample()
                        current = (raw['document_time_origin'],raw['player_id'],state.match_id.value)
                        if scope is None:
                            scope = current
                        if current != scope or current[-1] is None:
                            raise RuntimeError('source scope changed')
                        known.update(t['id'] for t in raw['towers'])
                        if len(known)>4096:
                            raise RuntimeError('bounded legal history exceeded')
                        sensor = await ex.visibility(sorted(known))
                        if any(sensor[k]!=raw[k] for k in ('tick','document_time_origin','player_id','root_candidate')):
                            continue
                        rows.append({'phase':phase,'at_ms':time.monotonic_ns()//1000000,
                            'origin':raw['document_time_origin'],'player':raw['player_id'],
                            'match':state.match_id.value,'tick':raw['tick'],
                            'camera_candidate':raw['camera_candidate'],
                            'visible_tower_ids':[t['id'] for t in raw['towers']],
                            'watched_visibility':sensor['watched_visibility'],
                            'positive_special_towers':[{'id':t['id'],'units7':t['units7']}
                                for t in raw['towers'] if t['units7'][0]==1 and t['units7'][2] in (6,7,8)],
                            'positive_single_forces':[{'source':f['source'],'destination':f['destination'],
                                'units7':f['units7'],'accelerated':f['accelerated']} for f in raw['forces']
                                if f['units7'][0]==1],
                            'expanded_visibility':raw['expanded_visibility']})
                    except ValueError as error:
                        errors.append(str(error)[:160])
                        if str(error) == 'outside active connected match':
                            raise RuntimeError('active match ended; no later wheel phase')
                    await asyncio.sleep(.08)
                await page.screenshot(path=str(folder/f'zoom-{tag}-{phase}.png'))
        except Exception as error:
            errors.append(str(error)[:180])
        finally:
            await ex.close()
    report = {'question':'can ordinary zoom generate additional currently sensor-visible actors or Single forces?',
        'status':'RESEARCH','rows':rows,'errors':errors,'client_sha256':CLIENT_SHA256,
        'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'observer_source_manifest':manifest,
        'tactical_commands':0,'debugger_pauses':False,
        'limits':'Actor availability and sensor truth are separate. Reverse wheel may clamp; no exact camera return assumed. No hidden payload read.'}
    path = folder/f'zoom-visibility-{tag}.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'file':str(path),'rows':len(rows),'errors':errors[:5]}))


if __name__=='__main__':
    asyncio.run(main())
