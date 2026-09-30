"""Bounded official reload/automatic resume ownership validation; no tactics."""
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import connect_dedicated,ObservationSession
from playwright.async_api import async_playwright


async def ready_sample(observer):
    end=time.monotonic()+3
    while True:
        try:return await observer.sample()
        except ValueError as error:
            if str(error)!='current visibility cache pending' or time.monotonic()>=end:
                raise
            await asyncio.sleep(.01)


async def main():
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        page=next(p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/')
        observer=ObservationSession(page)
        try:
            before,raw_before=await ready_sample(observer)
            old=observer.extractor;old_memory=old.memories_id
            await page.reload(wait_until='domcontentloaded',timeout=30000)
            rejected=False
            try:await old.metadata()
            except Exception:rejected=True
            end=time.monotonic()+30
            clicked=False
            while True:
                try:
                    metadata=await observer.metadata()
                    if metadata['derived_lifecycle']=='IN_MATCH':break
                    button=page.locator('#play_button')
                    if not clicked and await button.is_visible():
                        observer.extractor.lifecycle.begin_join()
                        try:
                            await button.click(timeout=2000);clicked=True
                        except Exception:
                            # Normal automatic resume can remove the button.
                            if (await observer.metadata())['derived_lifecycle']!='IN_MATCH':raise
                except ValueError:
                    if time.monotonic()>=end:raise
                if time.monotonic()>=end:raise RuntimeError('normal reload/resume timeout')
                await asyncio.sleep(.1)
            after,raw_after=await ready_sample(observer)
            report={'old_reader_rejected':rejected,'same_session':before.session_id==after.session_id,
                'new_document':before.document_id!=after.document_id,'new_observation_epoch':before.match_id.value!=after.match_id.value,
                'fresh_memory_handle':old_memory!=observer.extractor.memories_id,
                'document_reacquisitions':observer.document_reacquisitions,'official_play_clicked':clicked,
                'old_king':before.king.value,'new_king':after.king.value,
                'allocator_reused_numeric_root':raw_before['root_candidate']==raw_after['root_candidate'],
                'source_mode':after.source_mode.value,'tactical_commands':0,
                'limits':'a reload epoch is not proof of an independent new game life'}
            assert all(report[k]for k in ('old_reader_rejected','same_session','new_document',
                                         'new_observation_epoch','fresh_memory_handle'))
            path=ROOT/'runtime/research/v2'/('reload-reacquisition-'+uuid4().hex[:12]+'.json')
            path.write_text(json.dumps(report,indent=2),encoding='utf8')
            print(json.dumps({'file':str(path),**report}),flush=True)
        finally:await observer.close()


if __name__=='__main__':asyncio.run(main())
