"""Correlate source tick with public transport events; never record wire payload/URLs."""
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import ClientExtractor,connect_dedicated
from playwright.async_api import async_playwright


async def transport_promises(cdp):
    handles=[]
    try:
        proto=(await cdp.send('Runtime.evaluate',{'expression':
            "typeof WebTransport==='function'?WebTransport.prototype:null"}))['result']
        if 'objectId'not in proto:return []
        pid=proto['objectId'];handles.append(pid)
        tid=(await cdp.send('Runtime.queryObjects',{'prototypeObjectId':pid}))['objects']['objectId'];handles.append(tid)
        oid=(await cdp.send('Runtime.callFunctionOn',{'objectId':tid,
            'functionDeclaration':'function(){return this.flatMap(t=>[t.ready,t.closed]);}'}))['result']['objectId'];handles.append(oid)
        props=(await cdp.send('Runtime.getProperties',{'objectId':oid,'ownProperties':True}))['result'];states=[]
        for p in props:
            if not p['name'].isdigit():continue
            handle=p['value']['objectId'];handles.append(handle)
            result=await cdp.send('Runtime.getProperties',{'objectId':handle,'ownProperties':True})
            for x in result.get('internalProperties',[]):
                if x.get('value',{}).get('objectId'):handles.append(x['value']['objectId'])
            state=next(x['value']['value'] for x in result['internalProperties'] if x['name']=='[[PromiseState]]')
            states.append((int(p['name']),state))
        states=dict(states)
        return [{'ready':states[i],'closed':states[i+1]} for i in range(0,len(states),2)]
    finally:
        for handle in reversed(list(dict.fromkeys(handles))):
            await cdp.send('Runtime.releaseObject',{'objectId':handle})


async def main():
    run=uuid4().hex[:12];out=ROOT/'runtime/research/v2';rows=[]
    counts={k:0 for k in ('ws_created','ws_closed','ws_frames_received','wt_created','wt_established','wt_closed',
                         'fetch_requests','fetch_responses','fetch_finished')}
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        page=next(p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/')
        ex=ClientExtractor(page,diagnostic_sockets=True);await ex.attach()
        def increment(key):counts[key]+=1
        for event,key in [('webSocketCreated','ws_created'),('webSocketClosed','ws_closed'),
                          ('webSocketFrameReceived','ws_frames_received'),('webTransportCreated','wt_created'),
                          ('webTransportConnectionEstablished','wt_established'),('webTransportClosed','wt_closed')]:
            ex.cdp.on('Network.'+event,lambda _,key=key:increment(key))
        fetch_ids=set()
        def request(event):
            if event.get('type') in ('Fetch','XHR'):
                fetch_ids.add(event['requestId']);increment('fetch_requests')
        def response(event):
            if event.get('requestId') in fetch_ids:increment('fetch_responses')
        def finished(event):
            if event.get('requestId') in fetch_ids:
                fetch_ids.remove(event['requestId']);increment('fetch_finished')
        ex.cdp.on('Network.requestWillBeSent',request)
        ex.cdp.on('Network.responseReceived',response)
        ex.cdp.on('Network.loadingFinished',finished)
        try:
            stream=(out/f'transport-rows-{run}.jsonl').open('w',encoding='utf8')
            wt=[];next_wt=0
            for phase,seconds in [('online_before',3),('offline',5),('reconnect',30)]:
                await page.context.set_offline(phase=='offline')
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    row=await ex.metadata()
                    states=(await ex.cdp.send('Runtime.callFunctionOn',{'objectId':ex.sockets_id,
                        'returnByValue':True,'functionDeclaration':'function(){return this.map(s=>s.readyState);}'}))['result']['value']
                    if time.monotonic()>=next_wt:
                        wt=await transport_promises(ex.cdp);next_wt=time.monotonic()+1
                    row.update(phase=phase,host_monotonic_ms=time.monotonic_ns()//1000000,
                               ws_ready_states=states,wt_promise_states=wt,network_event_counts=dict(counts))
                    row['ui_rows']=await page.evaluate("() => [...document.querySelectorAll('p[title]')].map(e=>({title:e.title,text:e.innerText})).filter(r=>/^\\d+\\/\\d+$/.test(r.text))")
                    rows.append(row);stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                    await asyncio.sleep(.05)
                print(json.dumps({'phase':phase,'last':rows[-1]},ensure_ascii=True),flush=True)
        finally:
            await page.context.set_offline(False)
            await ex.close()
            if 'stream'in locals():stream.close()
            path=out/f'transport-research-{run}.json'
            path.write_text(json.dumps({'rows':rows,'counts':counts},indent=2),encoding='utf8')
            print(json.dumps({'file':str(path),'counts':counts}),flush=True)


if __name__=='__main__':asyncio.run(main())
