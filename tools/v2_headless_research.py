"""Bounded normal official-client observation without any desktop window/input."""
import argparse
import asyncio
import json
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


async def main(args):
    profile=ROOT/'runtime/browser-profile'
    if find_orphan_browser_pids(profile):
        raise RuntimeError('project profile already owned by another browser; close its owner normally first')
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
            page=await context.new_page()
            await page.goto('https://kiomet.com/',wait_until='domcontentloaded')
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
                                        'profile':str(profile)}),encoding='utf8')
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
    args=p.parse_args()
    if not 1<=args.seconds<=1800:
        p.error('seconds must be 1..1800')
    asyncio.run(main(args))
