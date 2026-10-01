"""Bounded live continuity-gap regression; no tactical commands or heap writes."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ObservationSession, connect_dedicated
from playwright.async_api import async_playwright


async def main():
    lease = json.loads((ROOT/'runtime/research/v2/headless-host.json').read_text())
    if lease['deadline_monotonic_ms']-time.monotonic_ns()//1000000 < 90000:
        raise ValueError('owned browser cannot cover bounded regression and teardown')
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/kiomet_ai/v2').rglob('*'))
        if p.is_file() and p.suffix in ('.py', '.js', '.json')}
    manifest[str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows, errors, checks = [], [], {}
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/']
        if len(pages) != 1:
            raise ValueError('ambiguous official page')
        page = pages[0]
        observer = ObservationSession(page)
        try:
            for phase, seconds in (('baseline', 3), ('offline', 3), ('reconnect', 15)):
                await page.context.set_offline(phase == 'offline')
                end = time.monotonic()+seconds
                while time.monotonic() < end:
                    try:
                        raw = await observer.metadata()
                        rows.append({'phase': phase, 'at_ms': time.monotonic_ns()//1000000,
                            'origin': raw['document_time_origin'], 'player': raw['player_id'],
                            'tick': raw['tick'], 'lifecycle': raw['derived_lifecycle'],
                            'match_id': raw['derived_match_id'], 'source_mode': raw['transport_mode'],
                            'transport_connected': raw['transport_connected']})
                    except ValueError as error:
                        # The production gate remains closed for transient or
                        # unsupported transport states. Retry within this phase
                        # deadline rather than interpreting a rejection as live.
                        errors.append(phase+': '+str(error)[:160])
                    await asyncio.sleep(.1)
            baseline = [r for r in rows if r['phase'] == 'baseline']
            if not baseline:
                raise ValueError('no valid live baseline; continuity test not established')
            epochs = {r['match_id'] for r in baseline}
            prior = baseline[-1]['match_id']
            checks['baseline_stable_nonempty_epoch'] = len(epochs) == 1 and prior is not None
            reconnect = [r for r in rows if r['phase'] == 'reconnect' and r['lifecycle'] == 'IN_MATCH']
            checks['reconnected_world_changes'] = len({r['tick'] for r in reconnect}) > 1
            checks['old_epoch_not_resumed'] = bool(reconnect) and all(r['match_id'] is None for r in reconnect)
            checks['document_player_scope_retained'] = bool(reconnect) and all(
                (r['origin'], r['player']) == (baseline[-1]['origin'], baseline[-1]['player']) for r in reconnect)
            for _ in range(20):
                try:
                    state, _ = await observer.sample()
                    break
                except ValueError as error:
                    if str(error) != 'current visibility cache pending':
                        raise
                    await asyncio.sleep(.05)
            else:
                raise ValueError('no coherent reconnected canonical snapshot')
            checks['canonical_epoch_unknown'] = state.match_id.value is None and state.match_id.knowledge.value == 'UNKNOWN'
            checks['canonical_match_readiness_gap'] = 'match_id' in state.readiness_gaps(state.received_at_ms)
            forces = state.forces.value
            checks['force_ids_not_promoted'] = all(f.id.value is None for f in forces) if forces else None
            force_count = len(forces) if forces is not None else None
            old_origin = observer.extractor.time_origin
            old_handle = observer.extractor.memories_id
            await page.reload(wait_until='domcontentloaded')
            deadline = time.monotonic()+20
            renewed = None
            while time.monotonic() < deadline:
                try:
                    renewed = await observer.metadata()
                    if renewed['derived_match_id']:
                        break
                except ValueError as error:
                    errors.append(str(error)[:160])
                await asyncio.sleep(.1)
            checks['new_document_epoch'] = bool(renewed and renewed['derived_match_id'] and
                renewed['document_time_origin'] != old_origin and renewed['derived_match_id'] != prior)
            checks['new_document_memory_handle'] = observer.extractor is not None and observer.extractor.memories_id != old_handle
        except Exception as error:
            errors.append(str(error)[:180])
        finally:
            try:
                await page.context.set_offline(False)
            finally:
                await observer.close()
    report = {'question': 'Does repeated unavailable metadata falsely preserve a world epoch?',
        'status': 'PASS' if len(checks) == 9 and all(v for v in checks.values() if v is not None) else 'UNKNOWN', 'checks': checks,
        'rows': rows, 'errors': errors, 'reconnected_force_count': locals().get('force_count'),
        'client_sha256': CLIENT_SHA256, 'observer_source_manifest': manifest,
        'performance_cohort': False, 'tactical_commands': 0,
        'limits': 'Observation epochs only; zero forces provide no live force-ID cases; reload is not proof of another game life; server age remains unknown.'}
    path = ROOT/'runtime/research/v2'/('identity-gap-'+uuid4().hex[:12]+'.json')
    path.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'file': str(path), 'status': report['status'], 'checks': checks,
        'errors': errors[:5], 'reconnected_force_count': report['reconnected_force_count']}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
