"""Observe normal TowerOverlay lock predicates; never invoke a game command.

Debugger pauses exclude this bounded research from performance acceptance.
Only an already currently visible own tower may authorize its UI props copy.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tools'))
from kiomet_ai.camera import world_to_page
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated, CLIENT_SHA256
from v2_force_render_compare import locals_at
from playwright.async_api import async_playwright


PROBE = r'''function(raw, target, stack, props, uiCore){
  const ms=this.filter(m=>m.buffer.byteLength>1000000);
  if(ms.length!==1)throw Error('ambiguous memory');
  const v=new DataView(ms[0].buffer),r=raw.root_candidate;
  const u32=p=>v.getUint32(p,true),u16=p=>v.getUint16(p,true),u8=p=>v.getUint8(p);
  if(performance.timeOrigin!==raw.document_time_origin ||
    u32(raw.root_slot_candidate-4)!==r || u32(raw.root_slot_candidate)!==1079724 ||
    v.getBigUint64(r,true)===2n || u32(r+548)!==3 || u8(r+45784)!==0 ||
    u16(r+45732)!==raw.tick || document.querySelector('#play_button')?.offsetParent!=null ||
    !navigator.onLine || u32(r+45720)===0x80000000)throw Error('source guard');
  const core=u32(r+45828);
  if(core!==uiCore || u16(core+248)!==raw.player_id || target.owner!==raw.player_id)throw Error('own source');
  if(u8(core+105)!==2 && (u8(core+104)&1) && u32(r+46480))throw Error('expanded visibility');
  const tc=u32(r+348),tp=u32(r+352),tn=u32(r+356);let connected=false;
  if(tn>tc || tc>64 || !tp || tp+44*tn>v.byteLength)throw Error('transport vector');
  for(let i=0;i<tn;i++){
    const e=tp+44*i,d=u32(e+24),off={1115032:40,1114972:77,1115092:155}[u32(e+28)];
    if(!off || !d || d+4>v.byteLength)throw Error('transport type');
    const rc=u32(d);
    if(!rc || rc+off+1>v.byteLength || !u32(rc) || u32(rc+8))throw Error('transport borrow');
    const state=u8(rc+off);if(state>2)throw Error('transport state');connected ||= state===1;
  }
  if(!connected)throw Error('disconnected');
  // Only sensor metadata is touched before authorizing the known UI tower copy.
  const m=r+45760,x=target.id&65535,y=target.id>>>16;
  const cap=u32(m),ptr=u32(m+4),len=u32(m+8);
  const x0=u16(m+12),y0=u16(m+14),x1=u16(m+16),y1=u16(m+18);
  if(len>cap || len!==(x1-x0+1)*(y1-y0+1) || x<x0 || x>x1 || y<y0 || y>y1 ||
    ptr+len*2>v.byteLength || u16(ptr+2*((y-y0)*(x1-x0+1)+x-x0))===0)
    throw Error('currently invisible');
  if(props<16 || props+174>v.byteLength || stack<16 || stack+218>v.byteLength ||
    u32(props)===0)throw Error('invalid normal props');
  // func463 var5 is Rc<TowerOverlayProps>; the data starts at Rc+8.
  const p=props+8;
  if(u16(p+104)!==x || u16(p+106)!==y)throw Error('different normal overlay');
  if(u16(p+36)!==target.owner || u8(p+46)!==target.type ||
    u8(p+47)!==target.delay_ticks ||
    target.units7.some((n,i)=>u8(p+38+i)!==n))throw Error('stale UI copy');
  const available=u8(stack+216),restricted=u8(stack+217);
  if(available>1 || restricted>1)throw Error('invalid policy booleans');
  const policy=raw.own_upgrade_policy;
  return {rewarded_ad_available:!!available, rank_requires_unlocks:!!restricted,
    source_policy:policy??null,
    source_ad_match:policy && typeof policy.rewarded_ad_available==='boolean' ?
      policy.rewarded_ad_available===!!available : null,
    source_rank_match:policy && typeof policy.rank_requires_unlocks==='boolean' ?
      policy.rank_requires_unlocks===!!restricted : null,
    source_policy_match:policy && policy.rewarded_ad_available!==null &&
      policy.rank_requires_unlocks!==null ?
      policy.rewarded_ad_available===!!available && policy.rank_requires_unlocks===!!restricted : null,
    tower_id:target.id, source_tick:raw.tick};
}'''


async def main():
    rows, errors, root_rows = [], [], []
    lease=ROOT/'runtime/research/v2/headless-host.json'
    if lease.exists() and json.loads(lease.read_text())['deadline_monotonic_ms']-time.monotonic_ns()//1000000<60000:
        raise ValueError('owned browser cannot cover bounded probe and teardown')
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        pages=[p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/']
        if len(pages)!=1:raise ValueError('ambiguous official page')
        page=pages[0];ex=ClientExtractor(page);await ex.attach();cdp=ex.cdp
        scripts,pauses=[],asyncio.Queue();bp=None
        cdp.on('Debugger.scriptParsed',lambda e:scripts.append(e))
        cdp.on('Debugger.paused',lambda e:pauses.put_nowait(e))
        try:
            await cdp.send('Debugger.enable')
            wasm=next(s for s in scripts if s.get('url')=='https://kiomet.com/client_bg.wasm')
            try:
                raw=await ex.metadata()
                result=await cdp.send('Debugger.setBreakpoint',{'location':{
                    'scriptId':wasm['scriptId'],'lineNumber':0,'columnNumber':0x143e4}})
                bp=result['breakpointId']
                if result['actualLocation']['columnNumber']!=0x143e4:raise ValueError('root clone point adjusted')
                event=await asyncio.wait_for(pauses.get(),3)
                loc=await locals_at(cdp,event['callFrames'][0],{'$var1'})
                delta=loc['$var1']-raw['root_candidate']
                row={'normal_ui_context_offset':delta}
                if delta==0:
                    value=await cdp.send('Runtime.callFunctionOn',{'objectId':ex.memories_id,'returnByValue':True,
                        'arguments':[{'value':raw}], 'functionDeclaration':'''function(raw){
                          const ms=this.filter(m=>m.buffer.byteLength>1000000);if(ms.length!==1)throw Error('memory');
                          const v=new DataView(ms[0].buffer),r=raw.root_candidate;
                          if(performance.timeOrigin!==raw.document_time_origin ||
                            v.getUint32(raw.root_slot_candidate-4,true)!==r ||
                            v.getUint32(raw.root_slot_candidate,true)!==1079724)throw Error('context');
                          const tag=v.getUint32(r+48964,true);
                          if(tag>3)throw Error('unsupported rewarded-ad variant');
                          return {rewarded_ad_available:tag!==0};
                        }'''})
                    if 'exceptionDetails' in value:raise ValueError('root ad guard')
                    row.update(value['result']['value'])
                root_rows.append(row)
            except Exception as e:errors.append('root clone: '+str(e)[:120])
            finally:
                if bp:await cdp.send('Debugger.removeBreakpoint',{'breakpointId':bp});bp=None
                try:await cdp.send('Debugger.resume')
                except Exception:pass
            for _ in range(4):
                try:
                    _,raw=await ex.sample()
                    view=await page.evaluate('''()=>{const c=document.querySelector('canvas'),r=c.getBoundingClientRect();
                      return {w:c.width,h:c.height,dpr:devicePixelRatio,left:r.left,top:r.top,cw:r.width,ch:r.height}}''')
                    if view['dpr']!=1 or view['left']!=0 or view['top']!=0:raise ValueError('unsupported projection')
                    candidates=[]
                    for t in raw['towers']:
                        x,y=world_to_page(*t['position'],*raw['camera_candidate'],view['w'],view['h'],1)
                        if t['owner']==raw['player_id'] and t['id']!=raw['selected_tower'] and 80<x<view['cw']-160 and 90<y<view['ch']-110:
                            if await page.evaluate('([x,y])=>document.elementFromPoint(x,y)?.tagName==="CANVAS"',[x,y]):
                                candidates.append((t,x,y))
                    if not candidates:raise ValueError('no eligible ordinary own selection')
                    target,x,y=candidates[0]
                    await page.mouse.click(x,y)
                    result=await cdp.send('Debugger.setBreakpoint',{'location':{
                        'scriptId':wasm['scriptId'],'lineNumber':0,'columnNumber':0x32354}})
                    bp=result['breakpointId']
                    if result['actualLocation']['columnNumber']!=0x32354:raise ValueError('policy point adjusted')
                    event=await asyncio.wait_for(pauses.get(),3)
                    # Current read-only source sample while normal UI execution is
                    # paused. No WASM function is invoked by the adapter.
                    _,raw=await ex.sample()
                    target=next((t for t in raw['towers'] if t['id']==target['id'] and
                        t['owner']==raw['player_id']),None)
                    if target is None:raise ValueError('own target no longer observed')
                    loc=await locals_at(cdp,event['callFrames'][0],{'$var2','$var5','$var22'})
                    probe=await cdp.send('Runtime.callFunctionOn',{'objectId':ex.memories_id,'returnByValue':True,
                        'arguments':[{'value':a} for a in (raw,target,loc['$var2'],loc['$var5'],loc['$var22'])],
                        'functionDeclaration':PROBE})
                    if 'exceptionDetails' in probe:
                        detail=probe['exceptionDetails']
                        raise ValueError(detail.get('exception',{}).get('description',detail.get('text','policy guard failed')).split('\n')[0])
                    rows.append(probe['result']['value'])
                except Exception as e:
                    errors.append(str(e)[:160])
                finally:
                    if bp:
                        await cdp.send('Debugger.removeBreakpoint',{'breakpointId':bp});bp=None
                    try:await cdp.send('Debugger.resume')
                    except Exception:pass
                await asyncio.sleep(.1)
        finally:
            if bp:
                try:await cdp.send('Debugger.removeBreakpoint',{'breakpointId':bp})
                except Exception:pass
            try:await cdp.send('Debugger.resume')
            except Exception:pass
            await ex.close()
    report={'client_sha256':CLIENT_SHA256,'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'root_rows':root_rows,'rows':rows,'errors':errors,'performance_cohort':False,'tactical_commands':0,
        'conclusion':'normal UI predicates only; final command eligibility remains UNKNOWN'}
    path=ROOT/'runtime/research/v2'/f'upgrade-policy-{uuid4().hex[:12]}.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'file':str(path),**report}),flush=True)


if __name__=='__main__':asyncio.run(main())
