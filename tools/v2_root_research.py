"""Test the typed normal-event closure to ClientBroker owner chain; no heap scan."""
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import ClientExtractor,connect_dedicated
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        page=next(p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/')
        observer=ClientExtractor(page);await observer.attach()
        cdp=observer.cdp;handles=[]
        try:
            async def instances(expression):
                proto=(await cdp.send('Runtime.evaluate',{'expression':expression}))['result']['objectId'];handles.append(proto)
                objs=(await cdp.send('Runtime.queryObjects',{'prototypeObjectId':proto}))['objects']['objectId'];handles.append(objs)
                return objs
            objects=await instances('Object.prototype')
            states=(await cdp.send('Runtime.callFunctionOn',{'objectId':objects,'returnByValue':True,
                'functionDeclaration':'''function(){return this.filter(o=>Object.hasOwn(o,'a')&&Object.hasOwn(o,'b')&&
                    Object.hasOwn(o,'cnt')&&[1079544,1079504].includes(o.b)&&o.cnt>0&&o.a>0)
                    .map(o=>({a:o.a,b:o.b,cnt:o.cnt}));}'''}))['result']['value']
            memories=await instances('WebAssembly.Memory.prototype')
            result=await cdp.send('Runtime.callFunctionOn',{'objectId':memories,'returnByValue':True,
                'arguments':[{'value':states}],
                'functionDeclaration':'''function(states){const m=this.filter(m=>m.buffer.byteLength>1000000);
                    if(m.length!==1)throw Error('ambiguous memory');const v=new DataView(m[0].buffer);
                    const u=p=>v.getUint32(p,true),ok=(p,n)=>p>0&&p+n<=v.byteLength;
                    return states.map(s=>{if(!ok(s.a,8))throw Error('bad event environment');
                        const type=u(s.a+4),rc=u(s.a);if(type!==(s.b===1079544?1129128:1127928)||!ok(rc,24))throw Error('bad event Rc type');
                        const broker=u(rc+12);if(!ok(broker,88))throw Error('bad broker Rc');
                        const slot=broker+72,root=u(slot-4);return {...s,type,broker,slot,
                            root,root_type:u(slot),strong:u(broker),borrow:u(broker+8),
                            document_time_origin:performance.timeOrigin,play:document.querySelector('#play_button')?.innerText};});}'''} )
            if 'exceptionDetails'in result:raise ValueError(result['exceptionDetails'])
            rows=result['result']['value'];path=ROOT/'runtime/research/v2'/f'root-chain-{uuid4().hex[:12]}.json'
            path.write_text(json.dumps(rows,indent=2),encoding='utf8');print(json.dumps({'file':str(path),'rows':rows}))
        finally:
            for h in reversed(handles):
                await cdp.send('Runtime.releaseObject',{'objectId':h})
            await observer.close()


if __name__=='__main__':asyncio.run(main())
