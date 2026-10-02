// Diagnostic boundaries for positive Visible.refs slots. This synthetic
// fixture exercises only the pinned normal decoder, never a live client.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/kiomet_ai/v2/observe/client_fae13.js', 'utf8');
const buffer = new ArrayBuffer(3_000_000);
const view = new DataView(buffer), reads = [];
const root = 1_470_000, core = 1_600_000, env = 1_700_000;
const callback = 1_710_000, broker = 1_720_000, refs = 1_860_000;
const players = 1_870_000, transport = 1_740_000;
const transportData = 1_741_000, transportRc = 1_742_000;
const arrays = [2_000_000, 2_020_000, 2_040_000];
const put = (p, n) => view.setUint32(p, n, true);
const short = (p, n) => view.setUint16(p, n, true);
class ObservedView extends DataView {
  getUint32(p, little) { reads.push(p); return super.getUint32(p, little); }
  getUint16(p, little) { reads.push(p); return super.getUint16(p, little); }
  getUint8(p) { reads.push(p); return super.getUint8(p); }
}
const decode = vm.runInNewContext('(' + source + ')', {
  DataView: ObservedView, Uint8Array, document: {querySelector: () => null},
  navigator: {onLine: true}, performance: {timeOrigin: 7}, Date, Map, Set
});

// The normal owned root and connected-session gates.
put(env, callback); put(env + 4, 1129128); put(callback, 1);
put(callback + 12, broker); put(broker, 1); put(broker + 68, root);
put(broker + 72, 1079724); put(root + 45828, core); short(core + 248, 1);
view.setUint8(core + 105, 2); put(root + 548, 3);
short(root + 45732, 10); view.setBigUint64(root, 1n, true);
put(root + 348, 1); put(root + 352, transport); put(root + 356, 1);
put(transport + 24, transportData); put(transport + 28, 1115032);
put(transportData, transportRc); put(transportRc, 1); view.setUint8(transportRc + 40, 1);
put(root + 652, players); put(root + 656, 2);

// 49 visible-map cells at x=0..48. Positive refs occur at x=0,16,48:
// absent chunk, present chunk with Option::None, and a real tower. x=32 has
// an actor slot but zero sensor refs, proving the fog guard avoids that slot.
put(root + 45760, 49); put(root + 45764, refs); put(root + 45768, 49);
short(root + 45772, 0); short(root + 45774, 0);
short(root + 45776, 48); short(root + 45778, 0);
short(refs, 1); short(refs + 2 * 16, 1); short(refs + 2 * 32, 0); short(refs + 2 * 48, 1);

const chunk0 = root + 664, chunk1 = root + 664 + 44;
const chunk2 = root + 664 + 88, chunk3 = root + 664 + 132;
put(chunk0, 0x80000000); // absent chunk Option
put(chunk1, 1); put(chunk1 + 36, arrays[0]); put(arrays[0], 0x80000000); // tower Option None
put(chunk2, 1); put(chunk2 + 36, arrays[1]); put(arrays[1], 1); // hidden at x=32
put(chunk3, 1); put(chunk3 + 36, arrays[2]); put(arrays[2], 1); // real at x=48
short(arrays[2] + 36, 1); put(arrays[2] + 24, 0x80000000);
put(1365232, 20_000); view.setUint8(1365236, 3);
put(1365240, 300_000); view.setUint8(1365244, 3);

const owners = [{a: env, b: 1079544, cnt: 1}];
const memories = [{buffer}], sockets = [{readyState: 1}];
let result = decode.call(memories, 'world', sockets, owners);
assert.equal(result.positive_refs, 3);
assert.equal(result.towers.length, 1);
assert.equal(result.towers[0].id, 48);
assert.equal(result.coverage, 'PARTIAL', 'coverage rule remains positive refs versus decoded towers');
assert.deepEqual(JSON.parse(JSON.stringify(result.visible_slot_gaps)), [
  {id: 0, reason: 'CHUNK_ABSENT'}, {id: 16, reason: 'TOWER_NONE'}
]);
assert(!reads.includes(chunk0 + 36), 'absent chunk was not followed');
assert(!reads.some(p => p >= arrays[0] + 4 && p < arrays[0] + 48),
  'empty tower slot was not payload-read beyond its already-read Option tag');
assert(!reads.some(p => p >= arrays[1] && p < arrays[1] + 48),
  'zero-sensor cell actor slot was not read');
assert(reads.includes(arrays[0]), 'tower Option tag was read once under positive visibility');

// With only the real tower positively sensed, empty/unread cells emit no gap,
// and the existing coverage equation still reports complete coverage.
short(refs, 0); short(refs + 2 * 16, 0); reads.length = 0;
result = decode.call(memories, 'world', sockets, owners);
assert.equal(result.positive_refs, 1);
assert.equal(result.towers.length, 1);
assert.deepEqual(JSON.parse(JSON.stringify(result.visible_slot_gaps)), []);
assert.equal(result.coverage, 'PLAYER_VISIBLE_COMPLETE');
assert(!reads.some(p => p >= arrays[1] && p < arrays[1] + 48),
  'zero-sensor cell remained outside tower memory reads');

console.log('positive visible slot gap diagnostics passed');
