"""One bounded ordinary Party UI scene and passive arrival recording.

Uses the already qualified normal UI selectors and the existing owned host.
No troop gesture, input-entry observer, hidden read or command injection.
"""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from playwright.async_api import async_playwright
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated, is_official_client_url
from tools.v2_controlled_transition_capture import _sample_ready


async def main():
    output = ROOT/'runtime/research/v2'/('ordinary-arrival-scene-'+uuid4().hex[:12]+'.json')
    lease = json.loads((ROOT/'runtime/research/v2/headless-host.json').read_text(encoding='utf8'))
    resume = sys.argv[1:] == ['--resume-party-dialog']
    if sys.argv[1:] and not resume:
        raise ValueError('only --resume-party-dialog is supported')
    if lease['deadline_monotonic_ms'] - int(time.monotonic()*1000) < (40000 if resume else 60000):
        raise ValueError('owned host must cover finite scene and cleanup margin')
    report = {'ui_actions': [], 'observations': [], 'troop_dispatch_attempts': 0,
              'scope': 'ONE_NORMAL_PARTY_UI_FLOW_AND_20_SECONDS_PASSIVE', 'formal_credit': 0}
    def save():
        output.write_text(json.dumps(report, separators=(',', ':'))+'\n', encoding='utf8')
    async def action(kind, fn):
        report['ui_actions'].append({'kind': kind, 'host_monotonic_ms': int(time.monotonic()*1000),
                                     'status': 'ATTEMPTED'})
        save()
        await fn()
        report['ui_actions'][-1]['status'] = 'COMPLETED'
        save()
    def scene(browser):
        pattern = re.compile(r'https://kiomet\.com/(?:[A-Z]{6}/)?(?:play-with-friends/)?')
        pages = [p for c in browser.contexts for p in c.pages if pattern.fullmatch(p.url)]
        if len(pages) != 1:
            raise ValueError('exactly one owned ordinary official scene required')
        return pages[0]
    extractor = None
    try:
        async with async_playwright() as pw:
            browser = await connect_dedicated(pw, ROOT)
            page = scene(browser)
            if not resume and (page.url != 'https://kiomet.com/' or not await page.locator('#play_button').is_visible()):
                raise ValueError('normal root menu required')
            if not resume:
                await action('OPEN_FRIENDS', lambda: page.locator('#play_with_friends_button').click(timeout=5000))
            party = page.locator('input#party[type=radio]')
            if not await party.is_visible():
                raise ValueError('normal Party choice absent')
            if not resume and not await party.is_checked():
                await action('SELECT_PARTY', lambda: party.check(timeout=5000))
            if not await party.is_checked():
                raise ValueError('Party selection not confirmed')
            if not resume:
                await page.wait_for_timeout(1800)
            page = scene(browser)
            play = page.locator('#play_button')
            dialog = page.get_by_role('heading', name='Play with friends', exact=True)
            if await dialog.is_visible():
                play = page.locator('button:not(#play_button)').filter(has_text=re.compile(r'^Play$'))
            elif resume:
                raise ValueError('resume requires the same visible Party dialog')
            if await play.count() != 1 or not await play.is_visible() or not await play.is_enabled():
                raise ValueError('single ordinary Play required')
            await action('NORMAL_PLAY', lambda: play.click(timeout=5000))
            await page.wait_for_timeout(500)
            page = scene(browser)
            if not is_official_client_url(page.url):
                raise ValueError('joined client route unsupported')
            extractor = ClientExtractor(page)
            await extractor.attach()
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                state, _ = await _sample_ready(extractor)
                if state.source_mode.value != 'NETWORK':
                    raise ValueError('NETWORK required')
                report['observations'].append(asdict(state))
                await asyncio.sleep(.1)
            report['status'] = 'PASSIVE_SCENE_RECORDED_NOT_CERTIFIED'
    except Exception as exc:
        report['status'] = 'REFUSED_OR_FAILED_ZERO_TROOPS'
        report['error_type'] = type(exc).__name__
        report['error'] = re.sub(r'https://kiomet\.com/[A-Z]{6}/', 'https://kiomet.com/<REDACTED_PARTY>/', str(exc))
    finally:
        if extractor is not None:
            await extractor.close()
        save()
    print(json.dumps({'output': str(output.relative_to(ROOT)), 'status': report['status'],
                      'samples': len(report['observations']), 'troop_dispatch_attempts': 0}))


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=45))
