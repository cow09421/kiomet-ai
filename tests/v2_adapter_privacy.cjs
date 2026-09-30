// Security boundary tests against a synthetic memory, never the real client.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('src/kiomet_ai/v2/observe/client_fae13.js','utf8');
const buffer=new ArrayBuffer(3_000_000),view=new DataView(buffer),reads=[];
const root=1_470_000,core=1_600_000,env=1_700_000,callback=1_710_000,broker=1_720_000;
const refs=1_860_000,players=1_870_000,tower=2_000_000;
const transport=1_740_000,transportData=1_741_000,transportRc=1_742_000;
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
view.setBigUint64(root,1n,true);put(root+348,1);put(root+352,transport);put(root+356,1);
put(transport+24,transportData);put(transport+28,1115032);
put(transportData,transportRc);put(transportRc,1);view.setUint8(transportRc+40,1);
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
reads.length=0;
r=decode.call(memories,'visibility',[0],owners);
assert.deepEqual(JSON.parse(JSON.stringify(r.watched_visibility)),[{id:0,visible:true}]);
assert(!reads.some(p=>p>=tower&&p<tower+256*48),'sensor mode read actor payload');
assert(!reads.some(p=>p>=players&&p<players+128),'sensor mode queried unrelated player fields');
short(refs,0);reads.length=0;
r=decode.call(memories,'visibility',[0],owners);
assert.equal(r.watched_visibility[0].visible,false,'lost sensor coverage must be false, not an old observed tower');
assert(!reads.some(p=>p>=tower&&p<tower+256*48),'hidden sensor query read tower payload');
assert.throws(()=>decode.call(memories,'visibility',[512],owners),/watched visibility IDs/);
view.setUint8(root+45784,1);
r=decode.call(memories,'visibility',[0],owners);
assert.equal(r.world_unavailable,'current visibility cache pending');
assert.equal(r.watched_visibility,undefined,'dirty visibility must remain unavailable, not false');
view.setUint8(root+45784,0);short(refs,1);
view.setUint8(transportRc+40,2);reads.length=0;
r=decode.call(memories,'world',sockets,owners);
assert.equal(r.world_unavailable,'outside active connected match');
assert(!reads.some(p=>p>=tower&&p<tower+256*48),'orphan OPEN socket must not authorize payload');
put(transport+28,1115092);view.setUint8(transportRc+155,1);
put(transportRc+12,0xdeadbeef); // HTTP alignment padding is not its borrow count.
r=decode.call(memories,'world',[],owners);
assert.equal(r.transport_connected,true,'owned HTTP polling must count without any WebSocket');
// Own persistent unlock set: empty is known, unavailable is null; seeds stay private.
const unlock=root+46240,unlockCtrl=1_900_000;
put(unlock,unlockCtrl);put(unlock+4,7);put(unlock+12,2);put(unlock+32,3);
new Uint8Array(buffer,unlockCtrl,8).fill(255);
view.setUint8(unlockCtrl+1,42);view.setUint8(unlockCtrl-2,1);
view.setUint8(unlockCtrl+5,9);view.setUint8(unlockCtrl-6,19);
reads.length=0;r=decode.call(memories,'world',[],owners);
assert.deepEqual(JSON.parse(JSON.stringify(r.own_unlocks)),{keys:3,unlocked_types:[1,19]});
assert(!reads.some(p=>p>=unlock+16&&p<unlock+32),'private unlock hash seeds were read');
put(unlock+12,0);put(unlock+32,0);
r=decode.call(memories,'world',[],owners);
assert.equal(r.own_unlocks,null,'set length disagreement must remain unknown');
new Uint8Array(buffer,unlockCtrl,8).fill(255);
r=decode.call(memories,'world',[],owners);
assert.deepEqual(JSON.parse(JSON.stringify(r.own_unlocks)),{keys:0,unlocked_types:[]});
put(unlock,0);r=decode.call(memories,'world',[],owners);
assert.equal(r.own_unlocks,null,'invalid unlock storage must remain unknown');
view.setBigUint64(root,2n,true);reads.length=0;
r=decode.call(memories,'world',sockets,owners);
assert.equal(r.transport_mode,'OFFLINE');assert.equal(r.transport_connected,false);
assert(!reads.some(p=>p>=tower&&p<tower+256*48),'offline simulation must not enter network gate');
console.log('typed root, fog/dirty gate and bilateral alliance boundaries passed');
