"""Observe real lifecycle/reload boundaries using only official UI join/menu."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import ObservationSession,connect_dedicated
from playwright.async_api import async_playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'runtime/browsers')
from kiomet_ai.browser import BrowserHost


class ResearchGate:
    async def dispatch(self,operation):
        return await operation()


async def main(args):
    out = ROOT/'runtime/research/v2'
    rows, events = [], []
    run=uuid4().hex[:12]
    host=None
    stream=(out/f'lifecycle-rows-{run}.jsonl').open('w',encoding='utf8')
    if args.launch:
        host=BrowserHost(ROOT,ResearchGate())
        await host.start('https://kiomet.com/','about:blank')
        await host.game_page.locator('#play_button').wait_for(state='visible',timeout=60000)
        for other in list(host.context.pages):
            if other!=host.game_page and other!=host.probe_page and other.url.startswith('https://kiomet.com/'):
                await other.close()
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw,ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/']
        if len(pages)!=1:
            raise ValueError('dedicated official page absent or ambiguous')
        page = pages[0]
        observer = ObservationSession(page)

        async def capture(phase,seconds):
            end = time.monotonic()+seconds
            while time.monotonic()<end:
                try:
                    raw = await observer.metadata()
                    raw['phase'] = phase
                    raw['host_at_ms'] = time.time_ns()//1000000
                    rows.append(raw)
                except Exception as e:
                    rows.append({'phase':phase,'error':str(e)[:300]})
                    if page.is_closed():
                        raise
                stream.write(json.dumps(rows[-1])+'\n')
                stream.flush()
                await asyncio.sleep(.1)
            if phase!='wait_result':
                print(json.dumps({'phase':phase,'last':rows[-1]}),flush=True)

        async def join():
            await observer.metadata()
            observer.extractor.lifecycle.begin_join()
            await page.locator('#play_button').click()
            await capture('official_join',8)

        try:
            await capture('initial',3)
            if rows[-1].get('derived_lifecycle')=='MENU':
                await join()
            if args.wait_result:
                end = time.monotonic()+args.wait_result
                while time.monotonic()<end:
                    await capture('wait_result',5)
                    if rows[-1].get('derived_lifecycle')=='RESULT':
                        break
            if rows[-1].get('derived_lifecycle')=='RESULT':
                # Only a normal result screen navigation, never a game command.
                menu = page.get_by_text('Back to menu',exact=False)
                if await menu.count()==1:
                    await menu.click()
                    await capture('result_to_menu',3)
                await join()
                await capture('new_match',10)
            previous = observer.extractor
            old_doc = previous.document_id
            old_id = previous.lifecycle.identity
            await page.reload(wait_until='domcontentloaded')
            await asyncio.sleep(3)
            try:
                await previous.sample()
                events.append({'event':'old_document_read','rejected':False})
            except Exception as e:
                events.append({'event':'old_document_read','rejected':True,'reason':str(e)[:300]})
            await capture('reload_reacquire',8)
            events.append({'event':'reload','old_document':old_doc,'new_document':observer.extractor.document_id,
                'old_identity':old_id,'new_identity':observer.extractor.lifecycle.identity,
                'reacquisitions':observer.document_reacquisitions})
            if rows[-1].get('derived_lifecycle') in ('MENU','RESULT'):
                await join()
            await capture('before_offline',5)
            await page.context.set_offline(True)
            await capture('offline',5)
            await page.context.set_offline(False)
            await capture('reconnect',10)
        finally:
            try:
                if not page.is_closed():
                    await page.context.set_offline(False)
                await observer.close()
            finally:
                stream.close()
                if host:
                    await host.close()
                path = out/f'lifecycle-research-{run}.json'
                path.write_text(json.dumps({'rows':rows,'events':events},indent=2),encoding='utf8')
                print(json.dumps({'file':str(path),'events':events,'states':sorted({r.get('derived_lifecycle','ERROR') for r in rows})}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wait-result',type=int,default=0)
    p.add_argument('--launch',action='store_true',help='Own an isolated project BrowserHost for this bounded experiment')
    args=p.parse_args()
    if not 0<=args.wait_result<=600:
        p.error('wait-result must be 0..600')
    asyncio.run(main(args))
