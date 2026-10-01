"""Bounded official response metadata probe; no payload, URL or credential export.

Date/RTT are hypotheses, never promoted to Game-generation timestamps. Ordinary
offline/reconnect is a research phase, excluded from performance acceptance.
"""
import asyncio
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright

TIME_HEADERS = frozenset(('date', 'age', 'last-modified', 'x-held', 'x-server-time',
    'x-servertime', 'x-world-tick', 'x-update-time', 'x-update-timestamp',
    'x-generated-at'))


async def main(args):
    lease = ROOT/'runtime/research/v2/headless-host.json'
    if not lease.exists() or json.loads(lease.read_text())['deadline_monotonic_ms'] - time.monotonic_ns()//1000000 < 90000:
        raise ValueError('owned host must cover probe and normal teardown')
    rows, responses, errors = [], [], []
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/kiomet_ai/v2').rglob('*'))
        if p.is_file() and p.suffix in ('.py', '.js', '.json')}
    manifest[str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    requests = set()
    phase = 'online_before'
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/']
        if len(pages) != 1:
            raise ValueError('ambiguous official page')
        page = pages[0]
        ex = ClientExtractor(page)
        try:
            await ex.attach()
            def request(event):
                if event.get('type') not in ('Fetch', 'XHR'):
                    return
                parsed = urlsplit(event['request']['url'])
                host = parsed.hostname or ''
                if parsed.scheme == 'https' and (host == 'kiomet.com' or host.endswith('.kiomet.com')):
                    requests.add(event['requestId'])
            def response(event):
                if event['requestId'] not in requests:
                    return
                headers = event['response'].get('headers', {})
                names = sorted(k.lower() for k in headers)
                allowed = {k.lower(): str(v)[:160] for k, v in headers.items()
                    if k.lower() in TIME_HEADERS}
                responses.append({'phase': phase, 'host_monotonic_ms': time.monotonic_ns()//1000000,
                    'status': event['response']['status'], 'header_names': names,
                    'paged_header_present': 'x-paged' in names,
                    'time_header_values': allowed, 'game_association': 'UNKNOWN'})
            ex.cdp.on('Network.requestWillBeSent', request)
            ex.cdp.on('Network.responseReceived', response)
            ex.cdp.on('Network.loadingFinished', lambda e: requests.discard(e['requestId']))
            ex.cdp.on('Network.loadingFailed', lambda e: requests.discard(e['requestId']))
            phases = (('online', 40),) if args.online_only else (('online_before', 3), ('offline', 5), ('reconnect', 40))
            for phase, seconds in phases:
                await page.context.set_offline(phase == 'offline')
                end = time.monotonic()+seconds
                while time.monotonic() < end:
                    try:
                        raw = await ex.metadata()
                        rows.append({'phase': phase, 'tick': raw.get('tick'),
                            'document_time_origin': raw['document_time_origin'],
                            'player_id': raw['player_id'], 'transport_connected': raw['transport_connected'],
                            'owned_transports': raw['owned_transports'], 'active': raw['active']})
                    except ValueError as error:
                        errors.append(str(error)[:160])
                    await asyncio.sleep(.2)
        finally:
            try:
                await page.context.set_offline(False)
            finally:
                await ex.close()
                report = {'status': 'UNKNOWN', 'question': 'Do ordinary official response headers bind Game generation time?',
                    'client_sha256': CLIENT_SHA256, 'observer_source_manifest': manifest,
                    'offline_phase': not args.online_only,
                    'responses': responses, 'rows': rows, 'errors': errors,
                    'payload_reads': 0, 'tactical_commands': 0, 'performance_cohort': False,
                    'limits': 'Official-domain Fetch/XHR metadata only; no per-Game association established.'}
                path = ROOT/'runtime/research/v2'/('transport-headers-'+uuid4().hex[:12]+'.json')
                path.write_text(json.dumps(report, indent=2), encoding='utf8')
                print(json.dumps({'file': str(path), 'responses': len(responses),
                    'time_header_names': sorted({n for r in responses for n in r['time_header_values']}),
                    'errors': len(errors), 'status': 'UNKNOWN'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online-only', action='store_true')
    asyncio.run(main(parser.parse_args()))
