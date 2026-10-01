"""Causal world-age experiment on a normal decoded Game update.

Delay normal execution without editing the client or reading packet/actor data.
The lower bound concerns the held update, never the age of a later snapshot.
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
    events, errors = [], []
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
            metadata = await ex.metadata()
            async def breakpoint(offset):
                result = await cdp.send('Debugger.setBreakpoint', {'location': {
                    'scriptId': wasm['scriptId'], 'lineNumber': 0, 'columnNumber': offset}})
                if result['actualLocation']['columnNumber'] != offset:
                    await cdp.send('Debugger.removeBreakpoint', {'breakpointId': result['breakpointId']})
                    raise ValueError('normal Game instruction adjusted')
                return result['breakpointId']
            async def world_sequence(frame):
                values = await locals_at(cdp, frame, {'$var0'})
                # Game-only branch: state argument is exactly context+512.
                if values['$var0'] != metadata['root_candidate']+512:
                    raise ValueError('Game update state ownership differs')
                result = await cdp.send('Runtime.callFunctionOn', {
                    'objectId': ex.memories_id, 'returnByValue': True,
                    'arguments': [{'value': metadata}], 'functionDeclaration': '''function(raw){
                      const ms=this.filter(m=>m.buffer.byteLength>1000000);
                      if(ms.length!==1)throw Error('ambiguous memory');
                      const v=new DataView(ms[0].buffer),r=raw.root_candidate;
                      if(performance.timeOrigin!==raw.document_time_origin ||
                        v.getUint32(raw.root_slot_candidate-4,true)!==r ||
                        v.getUint32(raw.root_slot_candidate,true)!==1079724 ||
                        v.getBigUint64(r,true)===2n ||
                        v.getUint32(r+45720,true)===0x80000000)throw Error('context changed');
                      return v.getUint16(r+45732,true);
                    }'''})
                if 'exceptionDetails' in result:
                    raise ValueError('metadata guard failed')
                return result['result']['value']

            bp = await breakpoint(0xd627)
            entry = await asyncio.wait_for(pauses.get(), 3)
            paused = True
            # Creation precedes rounded-up receipt; application follows
            # rounded-down resume send. These directions keep the bound safe.
            entry_receipt = (time.monotonic_ns()+999999)//1000000
            before = await world_sequence(entry['callFrames'][0])
            await cdp.send('Debugger.removeBreakpoint', {'breakpointId': bp})
            bp = await breakpoint(0x10745)
            await asyncio.sleep(1)
            resume_send = time.monotonic_ns()//1000000
            await cdp.send('Debugger.resume')
            paused = False
            end = await asyncio.wait_for(pauses.get(), 3)
            paused = True
            end_receipt = time.monotonic_ns()//1000000
            after = await world_sequence(end['callFrames'][0])
            events.append({'normal_game_entry': '0xd627', 'normal_game_end': '0x10745',
                'source_tick_before': before, 'source_tick_after': after,
                'source_tick_delta': (after-before)&65535,
                'entry_event_host_ms': entry_receipt, 'resume_send_host_ms': resume_send,
                'end_event_host_ms': end_receipt,
                'held_update_generation_age_lower_bound_at_apply_ms': resume_send-entry_receipt,
                'bound_reason': 'decoded Game update already exists at entry; application cannot run before resume',
                'canonical_snapshot_age_ms': None})
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
    path = ROOT/'runtime/research/v2'/f'delayed-apply-{uuid4().hex[:12]}.json'
    report = {'question': 'can a newly applied world sequence itself certify a young server update?',
        'status': 'RESEARCH', 'client_sha256': CLIENT_SHA256, 'events': events, 'errors': errors,
        'debugger_pauses': True, 'performance_cohort': False, 'packet_bytes_read': False,
        'actor_payload_read': False, 'tactical_commands': 0}
    path.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'file': str(path), 'events': events, 'errors': errors}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
