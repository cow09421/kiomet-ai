// Independent read-only decoder for one pinned official client version.
// Root/type discovery remains a RESEARCH CANDIDATE until cross-match validation.
// The only tower reads occur AFTER the live Visible.refs entry is positive.
function (mode = "world", sockets = []) {
  if (!["world", "metadata"].includes(mode)) throw Error("invalid observation mode");
  const memories = this.filter(m => m.buffer.byteLength > 1000000);
  if (memories.length !== 1) throw Error("ambiguous official client memory");
  const memory = memories[0];
  const v = new DataView(memory.buffer);
  const u32 = p => v.getUint32(p, true);
  const u16 = p => v.getUint16(p, true);
  const u8 = p => v.getUint8(p);
  const range = (p, n) => Number.isInteger(p) && p > 0 && n >= 0 && p + n <= v.byteLength;
  const roots = new Set();
  // Exact callback type marker found in the pinned runtime, never a tower scan.
  // No game payload is copied during discovery. Validate all dependent metadata.
  for (let p = 1048576; p + 4 <= v.byteLength; p += 4) {
    if (u32(p) !== 1079724) continue;
    const root = u32(p - 4);
    if (!range(root, 49040)) continue;
    const m = root + 45760;
    const cap = u32(m), ptr = u32(m + 4), len = u32(m + 8);
    const x0 = u16(m + 12), y0 = u16(m + 14), x1 = u16(m + 16), y1 = u16(m + 18);
    const area = (x1 - x0 + 1) * (y1 - y0 + 1);
    if (len > cap || (len > 0 && (x1 >= 512 || y1 >= 512 || x1 < x0 ||
        y1 < y0 || len !== area || !range(ptr, 2 * len)))) continue;
    const core = u32(root + 45828);
    if (!range(core, 256)) continue;
    roots.add(root);
  }
  if (roots.size !== 1) throw Error("context root missing or ambiguous: " + roots.size);
  const root = [...roots][0];
  const core = u32(root + 45828);
  const player = u16(core + 248);
  const play = document.querySelector('#play_button');
  const metadata = {sampled_at_ms: Date.now(), document_time_origin: performance.timeOrigin,
    player_id: player, root_candidate: root,
    tick: u32(root + 45720) === 0x80000000 ? null : u16(root + 45732),
    // Pinned update_visible/Color::new use exactly this active-state condition.
    active: u32(root + 548) === 3,
    visible_pending: u8(root + 45784) !== 0,
    // update_visible's second all_visible path is cheats + keyboard B.
    expanded_visibility: u8(core + 105) !== 2 && (u8(core + 104) & 1) !== 0 && u32(root + 46480) !== 0,
    online: navigator.onLine,
    transport_connected: sockets.some(s => s.readyState === WebSocket.OPEN),
    play_text: play?.offsetParent !== null && play ? play.innerText : null};
  if (mode === "metadata") return metadata; // No tower/force payload reads.
  if (!metadata.online || !metadata.transport_connected || !metadata.active || metadata.play_text !== null || player === 0)
    return {...metadata, world_unavailable: "outside active connected match"};
  if (metadata.visible_pending) return {...metadata, world_unavailable: "current visibility cache pending"};
  if (metadata.expanded_visibility) return {...metadata, world_unavailable: "expanded visibility prohibited"};
  const map = root + 45760, refs = u32(map + 4);
  const bounds = [u16(map + 12), u16(map + 14), u16(map + 16), u16(map + 18)];
  const width = bounds[2] - bounds[0] + 1;
  const camera = [v.getFloat32(root + 48080, true), v.getFloat32(root + 48084, true), v.getFloat32(root + 48100, true)];
  const offsetPtr = u32(1365232);
  if (u8(1365236) !== 3 || !range(offsetPtr, 512 * 512)) throw Error("position table unavailable");
  const roadPtr = u32(1365240);
  if (u8(1365244) !== 3 || !range(roadPtr, 512 * 512)) throw Error("road table unavailable");
  const towers = [];
  let positiveRefs = 0;
  for (let y = bounds[1]; y <= bounds[3]; y++) {
    for (let x = bounds[0]; x <= bounds[2]; x++) {
      const count = u16(refs + 2 * (x - bounds[0] + (y - bounds[1]) * width));
      if (count === 0) continue; // Fog boundary BEFORE any tower payload read.
      positiveRefs++;
      const chunk = root + 664 + (y >> 4) * 1408 + (x >> 4) * 44;
      if (!range(chunk, 44) || u32(chunk) === 0x80000000) continue;
      const ptr = u32(chunk + 36);
      if (!range(ptr, 256 * 48)) throw Error("invalid chunk tower array");
      const tower = ptr + ((y & 15) * 16 + (x & 15)) * 48;
      if (u32(tower) === 0x80000000) continue;
      const offset = u8(offsetPtr + y * 512 + x);
      if ((offset & 15) > 4 || (offset >> 4) > 4) throw Error("invalid world-position offset");
      const owner = u16(tower + 36);
      // Ally/enemy distinction requires the actual alliance data path: unknown.
      const relation = owner === 0 ? "NEUTRAL" : owner === player ? "SELF" : null;
      towers.push({id: (x | y << 16) >>> 0, visible: true,
        visibility_source: "official Visible.refs positive + generated tower",
        owner, relation, type: u8(tower + 46),
        units7: Array.from(new Uint8Array(memory.buffer, tower + 38, 7)),
        position: [x * 5 + (offset & 15), y * 5 + (offset >> 4)],
        // A pointer is research diagnostics, never canonical identity.
        research_ref: tower});
    }
  }
  const visibleIds = new Set(towers.map(t => t.id));
  const directions = [[0,1],[1,1],[1,0],[1,-1],[0,-1],[-1,-1],[-1,0],[-1,1]];
  for (const t of towers) {
    const x = t.id & 65535, y = t.id >>> 16, mask = u8(roadPtr + y * 512 + x);
    t.neighbors = [];
    for (let bit = 0; bit < 8; bit++) {
      if (!(mask & (1 << bit))) continue;
      const [dx,dy] = directions[bit], nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= 512 || ny >= 512) continue;
      const id = (nx | ny << 16) >>> 0;
      if (visibleIds.has(id)) t.neighbors.push(id); // Never export hidden endpoint IDs.
    }
  }
  const towerById = new Map(towers.map(t => [t.id,t]));
  for (const t of towers) for (const neighbor of t.neighbors) {
    if (!towerById.get(neighbor).neighbors.includes(t.id)) throw Error("asymmetric visible road graph");
  }
  return {...metadata, towers, positive_refs: positiveRefs,
    camera_candidate: camera, status: "RESEARCH_CANDIDATE",
    selected_tower: u32(root + 47968) === 1 ? u32(root + 47972) : null,
    match_id: null, updated_at_ms: null,
    forces: null, coverage: "PARTIAL"};
}
