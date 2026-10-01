"""Bounded ordinary camera-key experiment; no combat or semantic commands."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright


async def main():
    rows, errors, known, phases = [], [], set(), []
    path = ROOT/'runtime/research/v2'/f'camera-visibility-{uuid4().hex[:12]}.json'
    lease = json.loads((ROOT/'runtime/research/v2/headless-host.json').read_text())
    if lease['deadline_monotonic_ms'] < time.monotonic()*1000 + 45000:
        raise ValueError('owned browser lease cannot cover bounded camera experiment')
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/']
        if len(pages) != 1:
            raise ValueError('ambiguous official page')
        page = pages[0]
        # Never send a key into chat or another editable control.
        editable = await page.evaluate('''() => document.activeElement?.matches(
            'input,textarea,[contenteditable="true"]') || false''')
        if editable:
            raise ValueError('editable control focused; camera experiment refused')
        ex = ClientExtractor(page)
        await ex.attach()
        scope = None
        try:
            for phase, key, duration in [('baseline', None, 3),
                    ('camera_right', 'ArrowRight', 2), ('right_view', None, 4),
                    ('camera_left', 'ArrowLeft', 2), ('returned_view', None, 4)]:
                began = time.monotonic()
                if key:
                    await page.keyboard.down(key)
                try:
                    while time.monotonic()-began < duration:
                        try:
                            state, raw = await ex.sample()
                            if scope is None:
                                scope = state.match_id.value
                            if not scope or state.match_id.value != scope:
                                raise RuntimeError('match identity changed; experiment ended')
                            known.update(t['id'] for t in raw['towers'])
                            if len(known) > 4096:
                                raise RuntimeError('legal history exceeds bounded sensor query')
                            sensor = await ex.visibility(sorted(known))
                            if any(sensor[k] != raw[k] for k in
                                    ('tick', 'document_time_origin', 'player_id', 'root_candidate')):
                                continue
                            rows.append({'phase': phase, 'host_monotonic_ms': time.monotonic_ns()//1000000,
                                'origin': sensor['document_time_origin'], 'player': sensor['player_id'],
                                'match': scope, 'tick': raw['tick'],
                                'visible_tower_ids': [t['id'] for t in raw['towers']],
                                'watched_visibility': sensor['watched_visibility']})
                        except ValueError as error:
                            errors.append(str(error))
                        await asyncio.sleep(.05)
                finally:
                    if key:
                        await page.keyboard.up(key)
                phases.append({'phase': phase, 'elapsed_seconds': time.monotonic()-began})
                await page.screenshot(path=str(path.with_name(path.stem+'-'+phase+'.png')))
        finally:
            for key in ('ArrowRight', 'ArrowLeft'):
                await page.keyboard.up(key)
            await ex.close()
            previous, losses, recoveries = {}, [], []
            for row in rows:
                for item in row['watched_visibility']:
                    id, visible = item['id'], item['visible']
                    old = previous.get(id)
                    if old is True and visible is False:
                        losses.append({'id': id, 'phase': row['phase'], 'tick': row['tick']})
                    elif old is False and visible is True:
                        recoveries.append({'id': id, 'phase': row['phase'], 'tick': row['tick']})
                    previous[id] = visible
            report = {'status': 'RESEARCH', 'question': 'does ordinary camera movement alter current legal sensor coverage?',
                'client_sha256': CLIENT_SHA256,
                'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'tactical_commands': 0, 'camera_keys': ['ArrowRight', 'ArrowLeft'],
                'rows': rows, 'errors': errors, 'phases': phases,
                'sensor_losses': losses, 'sensor_recoveries': recoveries}
            path.write_text(json.dumps(report), encoding='utf8')
            print(json.dumps({'file': str(path), 'coherent_rows': len(rows),
                'losses': len(losses), 'recoveries': len(recoveries), 'errors': len(errors)}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
