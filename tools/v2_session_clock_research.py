"""Observe normal receive ownership and classify bootstrap clock hypotheses.

No packet bytes, credentials, bootstrap values or actor payload are exported.
Normal debugger pauses make this a research cohort, never a performance cohort.
"""
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tools'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ClientExtractor, connect_dedicated
from v2_force_render_compare import locals_at
from playwright.async_api import async_playwright


async def main():
    rows, errors = [], []
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == 'https://kiomet.com/']
        if len(pages) != 1:
            raise ValueError('ambiguous official page')
        ex = ClientExtractor(pages[0])
        await ex.attach()
        cdp = ex.cdp
        scripts, pauses = [], asyncio.Queue()
        cdp.on('Debugger.scriptParsed', lambda event: scripts.append(event))
        cdp.on('Debugger.paused', lambda event: pauses.put_nowait(event))
        bp, paused = None, False
        try:
            await cdp.send('Debugger.enable')
            wasm = next(s for s in scripts if s.get('url') == 'https://kiomet.com/client_bg.wasm')
            for _ in range(3):
                raw = await ex.metadata()
                result = await cdp.send('Debugger.setBreakpoint', {'location': {
                    'scriptId': wasm['scriptId'], 'lineNumber': 0, 'columnNumber': 0x47ad0}})
                bp = result['breakpointId']
                if result['actualLocation']['columnNumber'] != 0x47ad0:
                    raise ValueError('receive entry adjusted; ownership not verified')
                event = await asyncio.wait_for(pauses.get(), 3)
                paused = True
                values = await locals_at(cdp, event['callFrames'][0], {'$var0'})
                delta = values['$var0']-raw['root_candidate']
                row = {'normal_receive_context_offset': delta,
                    'document_time_origin': raw['document_time_origin'],
                    'player_id': raw['player_id'], 'source_tick': raw['tick']}
                # The hypothesis must first prove that this function owns the
                # exact pinned network context. Other layouts are excluded.
                if delta == 0:
                    probe = await cdp.send('Runtime.callFunctionOn', {
                        'objectId': ex.memories_id, 'returnByValue': True,
                        'arguments': [{'value': raw}], 'functionDeclaration': '''function(raw){
                          const ms=this.filter(m=>m.buffer.byteLength>1000000);
                          if(ms.length!==1)throw Error('ambiguous memory');
                          const v=new DataView(ms[0].buffer),r=raw.root_candidate;
                          if(performance.timeOrigin!==raw.document_time_origin ||
                            v.getUint32(raw.root_slot_candidate-4,true)!==r ||
                            v.getUint32(raw.root_slot_candidate,true)!==1079724 ||
                            v.getBigUint64(r,true)===2n)throw Error('context changed');
                          const classify=n=>{
                            const lo=1262304000000n,hi=2240611200000n;
                            return {unix_seconds_2010_2040:n*1000n>=lo&&n*1000n<=hi,
                              unix_milliseconds_2010_2040:n>=lo&&n<=hi,
                              unix_microseconds_2010_2040:n/1000n>=lo&&n/1000n<=hi,
                              unix_nanoseconds_2010_2040:n/1000000n>=lo&&n/1000000n<=hi};
                          };
                          return {local_bootstrap_epoch_class:classify(v.getBigUint64(r+248,true)),
                            peer_bootstrap_epoch_class:classify(v.getBigUint64(r+256,true))};
                        }'''})
                    if 'exceptionDetails' in probe:
                        raise ValueError('bootstrap classification guard failed')
                    row.update(probe['result']['value'])
                rows.append(row)
                await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
                bp = None
                await cdp.send('Debugger.resume')
                paused = False
                await asyncio.sleep(.4)
        except Exception as error:
            errors.append(str(error)[:180])
        finally:
            if bp:
                try:
                    await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
                except Exception as error:
                    errors.append('breakpoint cleanup: '+str(error)[:120])
            try:
                await cdp.send('Debugger.resume')
            except Exception as error:
                if paused:
                    errors.append('resume cleanup: '+str(error)[:120])
            await ex.close()
    path = ROOT/'runtime/research/v2'/f'session-clock-{uuid4().hex[:12]}.json'
    report = {'question': 'can a normal receive bootstrap certify world-generation time?',
        'status': 'RESEARCH', 'client_sha256': CLIENT_SHA256, 'rows': rows, 'errors': errors,
        'debugger_pauses': True, 'performance_cohort': False,
        'packet_bytes_read': False, 'bootstrap_values_exported': False,
        'tactical_commands': 0, 'created_at': time.time()}
    path.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'file': str(path), 'rows': rows, 'errors': errors}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
