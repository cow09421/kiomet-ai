// Read-only pinned normal-render guard. No hidden endpoint/path reads.
function(raw,f){
  const m=this.filter(x=>x.buffer.byteLength>1000000);
  if(m.length!==1)return false;const v=new DataView(m[0].buffer),r=raw.root_candidate;
  const u32=p=>v.getUint32(p,true),u16=p=>v.getUint16(p,true),u8=p=>v.getUint8(p);
  if(performance.timeOrigin!==raw.document_time_origin||!navigator.onLine||
    u32(raw.root_slot_candidate-4)!==r||u32(raw.root_slot_candidate)!==1079724||
    v.getBigUint64(r,true)===2n||u32(r+548)!==3||u8(r+45784)||
    u16(r+45732)!==raw.tick||u32(r+45720)===0x80000000||
    document.querySelector('#play_button')?.offsetParent!=null)return false;
  const c=u32(r+45828);
  if(u16(c+248)!==raw.player_id||
    (u8(c+105)!==2&&(u8(c+104)&1)&&u32(r+46480)))return false;
  const tc=u32(r+348),tp=u32(r+352),tn=u32(r+356);
  if(tn>tc||tc>64||!tp||tp+tn*44>v.byteLength)return false;
  let connected=false;
  for(let i=0;i<tn;i++){
    const e=tp+i*44,d=u32(e+24),table=u32(e+28);
    const stateOffset={1115032:40,1114972:77,1115092:155}[table];
    if(!stateOffset||!d||d+4>v.byteLength)return false;
    const rc=u32(d);
    if(!rc||rc+stateOffset+1>v.byteLength||!u32(rc)||u32(rc+8))return false;
    const state=u8(rc+stateOffset);
    if(state>2)return false;
    connected ||= state===1;
  }
  if(!connected)return false;
  const b=r+45760,p=u32(b+4),n=u32(b+8),x0=u16(b+12),y0=u16(b+14),
    x1=u16(b+16),y1=u16(b+18),w=x1-x0+1;
  if(n!==w*(y1-y0+1)||n>u32(b)||p+2*n>v.byteLength)return false;
  for(const id of [f.source,f.destination]){
    if(id===null)continue; // Never read a hidden path/actor.
    const x=id&65535,y=id>>>16;
    if(x<x0||y<y0||x>x1||y>y1||!u16(p+2*(x-x0+(y-y0)*w)))return false;
  }
  const inbound=f.visibility_source==='normal renderer: visible tower inbound';
  const outbound=f.visibility_source==='normal renderer: visible tower outbound to non-visible endpoint';
  if(!inbound&&!outbound)return false;
  const anchorId=inbound?f.destination:f.source;
  const t=raw.towers.find(t=>t.id===anchorId);
  if(!t)return false;
  const x=anchorId&65535,y=anchorId>>>16;
  const chunk=r+664+(y>>>4)*1408+(x>>>4)*44;
  if(u32(chunk)===0x80000000)return false;
  const tower=u32(chunk+36)+((y&15)*16+(x&15))*48;
  if(tower!==t.research_ref||u32(tower)===0x80000000)return false;
  const a=tower+(inbound?0:12),fp=u32(a+4),count=u32(a+8),cap=u32(a);
  const offset=f.research_ref-fp;
  if(count>cap||count>4096||fp<=0||fp+count*24>v.byteLength||
    offset<0||offset%24||offset/24>=count)return false;
  const q=f.research_ref;
  return u16(q+12)===f.owner&&u8(q+22)===f.progress&&u8(q+21)===f.accelerated&&
    f.units7.every((value,i)=>u8(q+14+i)===value);
}
