"""Bounded comparisons with normal official force execution; never invoke WASM.

Debugger pauses are excluded from frequency/freshness cohorts. Payload is read
only after the current observer visibility gate, and only for matched forces.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated, decode_units
from kiomet_ai.v2.observe.forces import motion
from playwright.async_api import async_playwright

POINTS = {
    'speed': (0x9896d, 0x98b8e),
    'position': (0x1036c0, 0x10375f),
    'units': (0x9896d, 0x98b8e),
}


async def locals_at(cdp, frame, names):
    scope = next(s for s in frame['scopeChain'] if s['type'] == 'local')
    props = (await cdp.send('Runtime.getProperties', {
        'objectId': scope['object']['objectId'], 'ownProperties': True}))['result']
    result = {}
    for prop in props:
        if prop['name'] not in names:
            continue
        value = prop['value']
        if 'objectId' in value:
            members = (await cdp.send('Runtime.getProperties', {
                'objectId': value['objectId'], 'ownProperties': True}))['result']
            result[prop['name']] = next(p['value']['value'] for p in members if p['name'] == 'value')
        else:
            result[prop['name']] = value.get('value')
    return result


async def main(args):
    rows, errors = [], []
    unique = {}
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        page = next(p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/')
        ex = ClientExtractor(page)
        await ex.attach()
        cdp = ex.cdp
        scripts, pauses = [], asyncio.Queue()
        cdp.on('Debugger.scriptParsed', lambda event: scripts.append(event))
        cdp.on('Debugger.paused', lambda event: pauses.put_nowait(event))
        bp = None
        getter_bp = None
        paused = False
        started = time.monotonic()
        breakpoint_locations = {}
        async def breakpoint(offset):
            result = await cdp.send('Debugger.setBreakpoint', {'location': {
                'scriptId': wasm['scriptId'], 'lineNumber': 0, 'columnNumber': offset}})
            actual = result['actualLocation']['columnNumber']
            breakpoint_locations[hex(offset)] = hex(actual)
            if actual != offset:
                await cdp.send('Debugger.removeBreakpoint', {'breakpointId': result['breakpointId']})
                raise ValueError('official breakpoint instruction adjusted; comparison not established')
            return result['breakpointId']
        async def resume():
            nonlocal paused
            if paused:
                await cdp.send('Debugger.resume')
                paused = False
        try:
            await cdp.send('Debugger.enable')
            wasm = next(s for s in scripts if s.get('url') == 'https://kiomet.com/client_bg.wasm')
            entry, exit_offset = POINTS[args.mode]
            while len(unique) < args.samples and time.monotonic() - started < args.seconds:
                try:
                    # Obtain typed ownership and a coherent legal payload before
                    # the normal renderer acquires its exclusive RefCell borrow.
                    _, raw = await ex.sample()
                    eligible = [f for f in raw['forces'] if f['source'] is not None and f['destination'] is not None
                        and (args.unit_type is None or dict(decode_units(f['units7']).counts)[args.unit_type])]
                    if not eligible:
                        await asyncio.sleep(.15)
                        continue
                    target = eligible[len(unique)%len(eligible)]
                    bp = await breakpoint(entry)
                    event = await asyncio.wait_for(pauses.get(), 2)
                    paused = True
                    # Keep the entry breakpoint through this frame while seeking
                    # the preselected legal target. Re-arming only once per frame
                    # would repeatedly select its first force and bias coverage.
                    for _ in range(64):
                        values = await locals_at(cdp, event['callFrames'][0], {'$var0', '$var1', '$var2'})
                        render = args.mode == 'position' or any(
                            'Force::interpolated_position' in f['functionName'] or
                            f['functionName']=='$func1861' for f in event['callFrames'])
                        force_ptr = values['$var1'] if args.mode == 'position' else values['$var0']
                        if render and force_ptr==target['research_ref']:
                            force=target
                            break
                        await resume()
                        event = await asyncio.wait_for(pauses.get(), 2)
                        paused = True
                        if time.monotonic()-started>=args.seconds:
                            break
                    else:
                        raise ValueError('bounded renderer seek did not find preselected visible force')
                    if not render or force_ptr!=target['research_ref']:
                        continue
                    # Never relax the production observer's borrow guard. While
                    # paused in normal rendering, only reuse the prior payload if
                    # its exact document/revision and both current visible refs
                    # remain valid and the matched force bytes remain unchanged.
                    guard = await cdp.send('Runtime.callFunctionOn', {
                        'objectId': ex.memories_id, 'returnByValue': True,
                        'arguments': [{'value': raw}, {'value': force}],
                        'functionDeclaration': '''function(raw,f){
                          const m=this.filter(x=>x.buffer.byteLength>1000000);
                          if(m.length!==1)return false;const v=new DataView(m[0].buffer),r=raw.root_candidate;
                          const u32=p=>v.getUint32(p,true),u16=p=>v.getUint16(p,true),u8=p=>v.getUint8(p);
                          if(performance.timeOrigin!==raw.document_time_origin||!navigator.onLine||
                            v.getBigUint64(r,true)===2n||u32(r+548)!==3||u8(r+45784)||
                            u16(r+45732)!==raw.tick||u32(r+45720)===0x80000000||
                            document.querySelector('#play_button')?.offsetParent!=null)return false;
                          const c=u32(r+45828);
                          if(u16(c+248)!==raw.player_id||
                            (u8(c+105)!==2&&(u8(c+104)&1)&&u32(r+46480)))return false;
                          const b=r+45760,p=u32(b+4),n=u32(b+8),x0=u16(b+12),y0=u16(b+14),
                            x1=u16(b+16),y1=u16(b+18),w=x1-x0+1;
                          if(n!==w*(y1-y0+1)||n>u32(b)||p+2*n>v.byteLength)return false;
                          for(const id of [f.source,f.destination]){
                            const x=id&65535,y=id>>>16;
                            if(x<x0||y<y0||x>x1||y>y1||!u16(p+2*(x-x0+(y-y0)*w)))return false;
                          }
                          const q=f.research_ref;
                          return u16(q+12)===f.owner&&u8(q+22)===f.progress&&u8(q+21)===f.accelerated&&
                            f.units7.every((value,i)=>u8(q+14+i)===value);
                        }'''})
                    if not guard['result'].get('value'):
                        continue
                    positions = {t['id']: tuple(t['position']) for t in raw['towers']}
                    units = decode_units(force['units7'])
                    speed, required, eta = motion(units, positions.get(force['source']),
                        positions.get(force['destination']), force['accelerated'], force['progress'])
                    if args.mode == 'position' and required is None:
                        continue
                    await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
                    bp = await breakpoint(exit_offset)
                    official_counts = {}
                    getter_consistent = True
                    if args.mode == 'units':
                        getter_bp = await breakpoint(0xf92c2)
                    await resume()
                    end = await asyncio.wait_for(pauses.get(), 2)
                    paused = True
                    if args.mode == 'units':
                        for _ in range(32):
                            if end['callFrames'][0]['location']['columnNumber'] == exit_offset:
                                break
                            if end['callFrames'][0]['location']['columnNumber'] != 0xf92c2:
                                raise ValueError('unexpected official unit getter stop')
                            if not any(0x9896d <= f['location']['columnNumber'] <= 0x98b97
                                and f['location']['scriptId']==wasm['scriptId'] for f in end['callFrames'][1:]):
                                raise ValueError('unit getter escaped captured force speed execution')
                            getter = await locals_at(cdp, end['callFrames'][0], {'$var1', '$var3'})
                            unit, count = getter['$var1'] & 255, getter['$var3'] & 255
                            if not 0 <= unit < 10:
                                raise ValueError('invalid normal getter unit')
                            getter_consistent &= unit not in official_counts or official_counts[unit] == count
                            official_counts[unit] = count
                            await resume()
                            end = await asyncio.wait_for(pauses.get(), 2)
                            paused = True
                        else:
                            raise ValueError('too many getters in one force speed invocation')
                    end_values = await locals_at(cdp, end['callFrames'][0], {'$var0', '$var1', '$var2'})
                    # The captured invocation must reach its normal return.
                    if args.mode == 'position' and end_values['$var0'] != values['$var0']:
                        raise ValueError('interpolated-position output invocation changed')
                    row = {'tick': raw['tick'], 'document_id': ex.document_id,
                        'match_epoch': raw['derived_match_id'], 'relation': force['relation'],
                        'source': force['source'], 'destination': force['destination'],
                        'units7': force['units7'], 'progress': force['progress'],
                        'accelerated': force['accelerated'], 'mode': args.mode,
                        'normal_render_call': True, 'derived_speed': speed,
                        'derived_required': required, 'derived_eta_ms': eta}
                    if args.mode == 'speed':
                        actual = end_values['$var2'] & 255
                        row.update(official_speed=actual, match=actual == speed)
                    elif args.mode == 'units':
                        expected_counts = dict(units.counts)
                        row.update(official_unit_counts=sorted(official_counts.items()),
                            derived_unit_counts=[(unit,expected_counts[unit]) for unit in sorted(official_counts)],
                            complete_vector=len(official_counts)==10,
                            match=bool(official_counts) and getter_consistent and all(
                                expected_counts[unit]==count for unit,count in official_counts.items()))
                    else:
                        result = await cdp.send('Runtime.callFunctionOn', {
                            'objectId': ex.memories_id, 'returnByValue': True,
                            'arguments': [{'value': values['$var0']}],
                            'functionDeclaration': '''function(p){const m=this.filter(x=>x.buffer.byteLength>1000000);
                                if(m.length!==1)throw Error('ambiguous memory');const v=new DataView(m[0].buffer);
                                return [v.getFloat32(p,true),v.getFloat32(p+4,true)]}'''})
                        actual = result['result']['value']
                        fraction = min(1, (force['progress'] + 4 * speed * values['$var2']) / required)
                        src, dst = positions[force['source']], positions[force['destination']]
                        expected = [a * (1-fraction) + b * fraction for a, b in zip(src, dst)]
                        deviation = max(abs(a-b) for a, b in zip(actual, expected))
                        row.update(official_position=actual, derived_position=expected,
                            rendering_interpolation_seconds=values['$var2'], deviation=deviation,
                            match=deviation <= .001)
                    rows.append(row)
                    key = (row['document_id'], row['match_epoch'], row['tick'],
                        row['source'], row['destination'], tuple(row['units7']), row['progress'],
                        row['accelerated'], row['mode'])
                    unique[key] = unique.get(key, True) and row['match']
                    print(json.dumps({'sample': len(rows), 'mode': args.mode,
                        'match': row['match'], 'relation': row['relation']}), flush=True)
                except asyncio.TimeoutError:
                    errors.append('normal-execution breakpoint timeout')
                except ValueError as error:
                    errors.append(str(error)[:200])
                finally:
                    try:
                        if bp:
                            await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
                            bp = None
                        if getter_bp:
                            await cdp.send('Debugger.removeBreakpoint', {'breakpointId': getter_bp})
                            getter_bp = None
                    finally:
                        await resume()
                await asyncio.sleep(.15)
        finally:
            try:
                if bp:
                    await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
                if getter_bp:
                    await cdp.send('Debugger.removeBreakpoint', {'breakpointId': getter_bp})
            finally:
                try:
                    await resume()
                finally:
                    await ex.close()
            report = {'status': 'PARTIAL', 'mode': args.mode, 'rows': rows,
                'fields': len(rows), 'matched': sum(r['match'] for r in rows), 'errors': errors,
                'unique_fields':len(unique),'unique_matched':sum(unique.values()),
                'breakpoint_locations':breakpoint_locations,
                'unit_getter_fields':sum(len(r.get('official_unit_counts',())) for r in rows),
                'requested_positive_unit_type':args.unit_type,
                'debugger_pauses': True, 'performance_cohort': False, 'tactical_commands': 0,
                'limits': 'normal rendered visible forces only; no stable force ID or launch-time proof'}
            path = ROOT / 'runtime/research/v2' / f'force-render-comparison-{uuid4().hex[:12]}.json'
            path.write_text(json.dumps(report, indent=2), encoding='utf8')
            print(json.dumps({'file': str(path), **{k:v for k,v in report.items() if k not in ('rows','errors')},
                'error_count':len(errors),'errors':errors[:5]}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=POINTS, default='speed')
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--unit-type',type=int,default=None,
        help='Stratify only currently visible forces with a positive count of this enum; never select by match outcome')
    args = parser.parse_args()
    if not 1 <= args.samples <= 100 or not 1 <= args.seconds <= 120:
        parser.error('samples 1..100 and seconds 1..120 required')
    if args.unit_type is not None and not 0 <= args.unit_type < 10:
        parser.error('unit type must be 0..9')
    asyncio.run(main(args))
