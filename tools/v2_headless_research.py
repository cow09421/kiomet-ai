"""Bounded normal official-client observation without any desktop window/input."""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'runtime/browsers')
from kiomet_ai.browser import find_orphan_browser_pids
from kiomet_ai.v2.observe.extractor import ClientExtractor
from playwright.async_api import async_playwright


INPUT_ENTRY_OBSERVER=ROOT/'src/kiomet_ai/v2/observe/input_entry.js'


def load_input_entry_observer(path=INPUT_ENTRY_OBSERVER):
    """Return the exact init-script text and its digest, failing closed if unavailable."""
    try:
        source_bytes=Path(path).read_bytes()
        source=source_bytes.decode('utf8')
    except (OSError,UnicodeError) as exc:
        raise RuntimeError(f'input-entry observer requested but source is unavailable: {path}') from exc
    if not source.strip():
        raise RuntimeError(f'input-entry observer requested but source is empty: {path}')
    return source,hashlib.sha256(source_bytes).hexdigest()


async def register_input_entry_before_controlled_page(context,source):
    """Install before the controlled page; tolerate only pre-existing blank pages."""
    initial_pages=list(context.pages)
    if any(page.url!='about:blank' for page in initial_pages):
        raise RuntimeError('input-entry observer requested after a nonblank page already exists')
    await context.add_init_script(script=source)
    return len(initial_pages)


async def read_controlled_document_observer_status(page):
    """Read and validate bootstrap status only; never ask for actor or world data."""
    observed=await page.evaluate('''() => {
      const observer=window[Symbol.for('kiomet.inputEntryObserver.v1')];
      return {controlled_document_observer_status:
        observer && typeof observer.status === 'function' ? observer.status() : null,
        document_time_origin_ms: performance.timeOrigin};
    }''')
    if not isinstance(observed,dict):
        raise RuntimeError('input-entry observer status response is malformed')
    status=observed.get('controlled_document_observer_status')
    if not isinstance(status,dict):
        raise RuntimeError('input-entry observer status is missing')
    if (status.get('installed') is not True or status.get('status')!='DISARMED' or
            status.get('armed_once') is not False or
            status.get('document_loading_at_install') is not True or
            status.get('ready_state_at_install')!='loading'):
        raise RuntimeError('input-entry observer bootstrap status failed closed validation')
    origin=observed.get('document_time_origin_ms')
    if (isinstance(origin,bool) or not isinstance(origin,(int,float)) or
            not math.isfinite(origin) or origin<=0):
        raise RuntimeError('controlled document time origin is malformed')
    return {'controlled_document_observer_status':status,
            'document_time_origin_ms':origin}


async def main(args):
    profile=ROOT/'runtime/browser-profile'
    if find_orphan_browser_pids(profile):
        raise RuntimeError('project profile already owned by another browser; close its owner normally first')
    observer_source=None
    observer_sha256=None
    if args.input_entry_observer:
        observer_source,observer_sha256=load_input_entry_observer()
    input_entry_metadata={
        'observer_requested':bool(args.input_entry_observer),
        'registered_before_controlled_page_creation':False,
        'initial_blank_page_count':None,
        'source_sha256':observer_sha256,
    }
    out=ROOT/'runtime/research/v2'
    stop=out/'headless-stop'
    lease=out/'headless-host.json'
    stop.unlink(missing_ok=True)
    async with async_playwright() as pw:
        context=await pw.chromium.launch_persistent_context(str(profile),
        executable_path=pw.chromium.executable_path,headless=True,
            viewport={'width':1280,'height':900},device_scale_factor=1,
            args=['--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
                  '--mute-audio','--disable-background-timer-throttling',
                  '--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'])
        try:
            if observer_source is not None:
                input_entry_metadata['initial_blank_page_count'] = (
                    await register_input_entry_before_controlled_page(context,observer_source))
                input_entry_metadata['registered_before_controlled_page_creation']=True
            print(json.dumps({'phase':'startup','input_entry_observer':input_entry_metadata}),flush=True)
            page=await context.new_page()
            await page.goto('https://kiomet.com/',wait_until='domcontentloaded')
            if args.input_entry_observer:
                status_metadata=await read_controlled_document_observer_status(page)
                input_entry_metadata.update(status_metadata)
                print(json.dumps({'phase':'input_entry_status',**status_metadata}),flush=True)
            await page.locator('#play_button').wait_for(state='visible',timeout=60000)
            for other in list(context.pages):
                if other!=page:
                    await other.close()
            ex=ClientExtractor(page)
            try:
                await ex.attach()
                print(json.dumps({'phase':'pinned','metadata':await ex.metadata()}),flush=True)
            finally:
                await ex.close()
            raf=await page.evaluate('''() => new Promise(resolve=>{const a=[];
                function frame(t){a.push(t);if(a.length<21)requestAnimationFrame(frame);
                else resolve(a.slice(1).map((v,i)=>v-a[i]))}requestAnimationFrame(frame)})''')
            print(json.dumps({'phase':'normal_raf','intervals_ms':raf}),flush=True)
            if args.join:
                await page.locator('#play_button').click()
                await page.locator('#play_button').wait_for(state='hidden',timeout=60000)
            end=time.monotonic()+args.seconds
            lease.write_text(json.dumps({'pid':os.getpid(),'deadline_monotonic_ms':int(end*1000),
                                        'profile':str(profile),
                                        'input_entry_observer':input_entry_metadata}),encoding='utf8')
            while time.monotonic()<end and not stop.exists():
                await asyncio.sleep(10)
                print(json.dumps({'phase':'alive','play_visible':await page.locator('#play_button').is_visible(),
                                  'time':time.time()}),flush=True)
        finally:
            if lease.exists() and json.loads(lease.read_text())['pid']==os.getpid():
                lease.unlink()
            stop.unlink(missing_ok=True)
            await context.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--join',action='store_true')
    p.add_argument('--seconds',type=int,default=600)
    p.add_argument('--input-entry-observer',action='store_true',
                   help='install the opt-in input-entry observer before creating the host page')
    args=p.parse_args()
    if not 1<=args.seconds<=1800:
        p.error('seconds must be 1..1800')
    asyncio.run(main(args))
