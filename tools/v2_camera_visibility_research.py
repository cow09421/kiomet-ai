"""Bounded ordinary camera-key experiment; no combat or semantic commands."""
import asyncio
import argparse
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


def actor_transitions(rows):
    """Separate generated-actor availability from sensor truth; no hidden reads."""
    previous, scope, lost = set(), None, {}
    losses, recoveries = [], []
    for row in rows:
        current_scope = (row['origin'], row['player'], row['match'])
        current = set(row['visible_tower_ids'])
        sensor = {v['id']: v['visible'] for v in row['watched_visibility']}
        if current_scope != scope:
            previous, scope, lost = current, current_scope, {}
            continue
        for ident in sorted(previous-current):
            event = {'id': ident, 'phase': row['phase'], 'tick': row['tick'],
                'at_ms': row['host_monotonic_ms'], 'sensor_visible': sensor.get(ident)}
            losses.append(event)
            lost[ident] = event
        for ident in sorted(current-previous):
            prior = lost.pop(ident, None)
            if prior is not None:
                recoveries.append({'id': ident, 'phase': row['phase'], 'tick': row['tick'],
                    'at_ms': row['host_monotonic_ms'], 'sensor_visible': sensor.get(ident),
                    'loss_tick': prior['tick'], 'loss_at_ms': prior['at_ms'],
                    'same_scope_new_source': row['tick'] != prior['tick'] and
                        row['host_monotonic_ms'] > prior['at_ms']})
        previous = current
    return {'actor_availability_losses': losses, 'actor_availability_recoveries': recoveries,
        'same_scope_new_source_actor_recoveries': sum(x['same_scope_new_source'] for x in recoveries)}


async def main(args):
    rows, errors, known, phases = [], [], set(), []
    path = ROOT/'runtime/research/v2'/f'camera-visibility-{uuid4().hex[:12]}.json'
    lease = json.loads((ROOT/'runtime/research/v2/headless-host.json').read_text())
    if lease['deadline_monotonic_ms'] < time.monotonic()*1000 + (41+2*args.hold_seconds)*1000:
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
                    ('camera_right', 'ArrowRight', args.hold_seconds), ('right_view', None, 4),
                    ('camera_left', 'ArrowLeft', args.hold_seconds), ('returned_view', None, 4)]:
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
                        losses.append({'id': id, 'phase': row['phase'], 'tick': row['tick'],
                            'at_ms': row['host_monotonic_ms'], 'current_actor_observed': id in row['visible_tower_ids']})
                    elif old is False and visible is True:
                        recoveries.append({'id': id, 'phase': row['phase'], 'tick': row['tick'],
                            'at_ms': row['host_monotonic_ms'], 'current_actor_observed': id in row['visible_tower_ids']})
                    previous[id] = visible
            report = {'status': 'RESEARCH', 'question': 'does ordinary camera movement alter current legal sensor coverage?',
                'client_sha256': CLIENT_SHA256,
                'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'tactical_commands': 0, 'camera_keys': ['ArrowRight', 'ArrowLeft'],
                'hold_seconds': args.hold_seconds,
                'rows': rows, 'errors': errors, 'phases': phases,
                **actor_transitions(rows),
                'sensor_losses': losses, 'sensor_recoveries': recoveries}
            path.write_text(json.dumps(report), encoding='utf8')
            print(json.dumps({'file': str(path), 'coherent_rows': len(rows),
                'losses': len(losses), 'recoveries': len(recoveries), 'errors': len(errors)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold-seconds', type=int, default=2)
    args = parser.parse_args()
    if not 2 <= args.hold_seconds <= 12:
        parser.error('hold seconds must be 2..12')
    asyncio.run(main(args))
