// Security boundary tests against a synthetic memory, never the real client.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('src/kiomet_ai/v2/observe/client_fae13.js','utf8');
const buffer=new ArrayBuffer(3_000_000),view=new DataView(buffer),reads=[];
const root=1_470_000,core=1_600_000,env=1_700_000,callback=1_710_000,broker=1_720_000;
const refs=1_860_000,players=1_870_000,tower=2_000_000;
const put=(p,n)=>view.setUint32(p,n,true),short=(p,n)=>view.setUint16(p,n,true);
class ObservedView extends DataView {
  getUint32(p,l){reads.push(p);return super.getUint32(p,l)}
  getUint16(p,l){reads.push(p);return super.getUint16(p,l)}
  getUint8(p){reads.push(p);return super.getUint8(p)}
}
const decode=vm.runInNewContext('('+source+')',{DataView:ObservedView,Uint8Array,
  document:{querySelector:()=>null},navigator:{onLine:true},performance:{timeOrigin:7},
  WebSocket:{OPEN:1},Date,Map,Set});
put(env,callback);put(env+4,1129128);put(callback,1);put(callback+12,broker);
put(broker,1);put(broker+68,root);put(broker+72,1079724);
put(root+45828,core);short(core+248,1);view.setUint8(core+105,2);
put(root+548,3);short(root+45732,10);
put(root+45760,1);put(root+45764,refs);put(root+45768,1);
put(root+664,0);put(root+700,tower);short(tower+36,2);
put(1365232,20_000);view.setUint8(1365236,3);
put(1365240,300_000);view.setUint8(1365244,3);
put(root+652,players);put(root+656,2);
const owners=[{a:env,b:1079544,cnt:1}],memories=[{buffer}],sockets=[{readyState:1}];
assert.throws(()=>decode.call(memories,'metadata',sockets,[]),/root missing/);
assert.equal(reads.length,0,'a stray root marker must never trigger a heap scan');
let r=decode.call(memories,'world',sockets,owners);
assert.equal(r.towers.length,0);
assert(!reads.some(p=>p>=tower&&p<tower+256*48),'hidden tower payload was read');
view.setUint8(root+45784,1);reads.length=0;
r=decode.call(memories,'world',sockets,owners);
assert.equal(r.world_unavailable,'current visibility cache pending');
assert(!reads.some(p=>p>=tower&&p<tower+256*48));
view.setUint8(root+45784,0);short(refs,1);
function setMember(entry,ctrl,id){
  put(entry+8,ctrl);put(entry+12,7);put(entry+20,1);
  new Uint8Array(buffer,ctrl,16).fill(255);
  const hash=Math.imul(id,656542357)>>>0,slot=hash&7,tag=hash>>>25;
  view.setUint8(ctrl+slot,tag);view.setUint8(ctrl+8+slot,tag);
  short(ctrl-2*(slot+1),id);
}
setMember(players,1_880_000,2);
r=decode.call(memories,'world',sockets,owners);
assert.equal(r.towers[0].relation,'ENEMY','one-way request is not an alliance');
setMember(players+64,1_890_000,1);
r=decode.call(memories,'world',sockets,owners);
assert.equal(r.towers[0].relation,'ALLY','bilateral membership must produce ally');
console.log('typed root, fog/dirty gate and bilateral alliance boundaries passed');
