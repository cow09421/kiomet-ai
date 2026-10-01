// Independent read-only decoder for one pinned official client version.
// Root/type discovery remains a RESEARCH CANDIDATE until cross-match validation.
// Tower payload decoding/export occurs only after live Visible.refs is positive.
function (mode = "world", watchedIds = [], ownerStates = []) {
  if (!["world", "metadata", "visibility"].includes(mode)) throw Error("invalid observation mode");
  const memories = this.filter(m => m.buffer.byteLength > 1000000);
  if (memories.length !== 1) throw Error("ambiguous official client memory");
  const memory = memories[0];
  const v = new DataView(memory.buffer);
  const u32 = p => v.getUint32(p, true);
  const u16 = p => v.getUint16(p, true);
  const u8 = p => v.getUint8(p);
  const range = (p, n) => Number.isInteger(p) && p > 0 && n >= 0 && p + n <= v.byteLength;
  const roots = new Map();
  // Pinned event environment -> Rc<event callback> -> ClientBroker Rc ->
  // RefCell data -> boxed game context. Ownership metadata only; no heap scan.
  for (const s of ownerStates) {
    if (![1079544,1079504].includes(s.b) || s.cnt <= 0 || !range(s.a,8)) continue;
    if (u32(s.a+4) !== (s.b === 1079544 ? 1129128 : 1127928)) continue;
    const callbackRc = u32(s.a);
    if (!range(callbackRc,24) || u32(callbackRc) === 0) continue;
    const broker = u32(callbackRc+12);
    if (!range(broker,88) || u32(broker) === 0 || u32(broker+8) !== 0) continue;
    const p = broker+72;
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
    roots.set(root, p);
  }
  if (roots.size !== 1) throw Error("context root missing or ambiguous: " + roots.size);
  const root = [...roots.keys()][0];
  const core = u32(root + 45828);
  const player = u16(core + 248);
  const play = document.querySelector('#play_button');
  // Transport::new_offline writes tag 2; ClientSession owns the network
  // transport Vec at +348/+352/+356. Follow only these typed entries.
  const offline = v.getBigUint64(root,true) === 2n;
  const transports = [];
  if (!offline) {
    const cap=u32(root+348),ptr=u32(root+352),len=u32(root+356);
    if (len>cap || cap>64 || (len>0 && !range(ptr,len*44)))
      throw Error("invalid owned transport vector");
    for (let i=0;i<len;i++) {
      const e=ptr+i*44,data=u32(e+24),table=u32(e+28);
      const layout={1115032:["WEBSOCKET",40,4],1114972:["WEBTRANSPORT",77,4],
                    1115092:["HTTP_POLL",155,8]}[table];
      if (!layout || !range(data,4)) throw Error("unsupported owned transport type");
      const rc=u32(data);
      // func6763 always reads a 32-bit borrow counter; HTTP's +12 is padding.
      if (!range(rc,layout[1]+1) || u32(rc)===0 || u32(rc+8)!==0)
        throw Error("owned transport unavailable or borrowed");
      const state=u8(rc+layout[1]);
      if (state>2) throw Error("unsupported owned transport state");
      transports.push({kind:layout[0],state});
    }
  }
  const metadata = {sampled_at_ms: Date.now(), document_time_origin: performance.timeOrigin,
    player_id: player, root_candidate: root, root_slot_candidate: roots.get(root),
    tick: u32(root + 45720) === 0x80000000 ? null : u16(root + 45732),
    // Pinned update_visible/Color::new use exactly this active-state condition.
    active: u32(root + 548) === 3,
    visible_pending: u8(root + 45784) !== 0,
    // update_visible's second all_visible path is cheats + keyboard B.
    expanded_visibility: u8(core + 105) !== 2 && (u8(core + 104) & 1) !== 0 && u32(root + 46480) !== 0,
    online: navigator.onLine,
    transport_mode: offline ? "OFFLINE" : "NETWORK",
    owned_transports: transports,
    transport_connected: !offline && transports.some(t=>t.state===1),
    play_text: play?.offsetParent !== null && play ? play.innerText : null};
  if (mode === "metadata") return metadata; // No tower/force payload reads.
  if (!metadata.online || !metadata.transport_connected || !metadata.active || metadata.play_text !== null || player === 0)
    return {...metadata, world_unavailable: "outside active connected match"};
  if (metadata.visible_pending) return {...metadata, world_unavailable: "current visibility cache pending"};
  if (metadata.expanded_visibility) return {...metadata, world_unavailable: "expanded visibility prohibited"};
  if (mode === "visibility") {
    // Sensor truth for previously observed IDs; never follow a hidden actor.
    // The research caller supplies only IDs from its legal observation history.
    if (!Array.isArray(watchedIds) || watchedIds.length > 4096 ||
        watchedIds.some(id => !Number.isInteger(id) || id < 0 || id > 0xffffffff ||
          (id & 65535) >= 512 || (id >>> 16) >= 512)) throw Error("invalid watched visibility IDs");
    const map=root+45760,ptr=u32(map+4),len=u32(map+8);
    const x0=u16(map+12),y0=u16(map+14),x1=u16(map+16),y1=u16(map+18),width=x1-x0+1;
    return {...metadata, watched_visibility: watchedIds.map(id => {
      const x=id&65535,y=id>>>16;
      return {id, visible:len>0 && x>=x0 && y>=y0 && x<=x1 && y<=y1 &&
        u16(ptr+2*(x-x0+(y-y0)*width))>0};
    })};
  }
  const relationCache = new Map();
  const playerEntry = id => {
    const ptr=u32(root+652),len=u32(root+656);
    if (!id || id>len || len>65535 || !range(ptr,len*64)) return null;
    const p=ptr+(id-1)*64;
    return u32(p)===2 ? null : p; // Exact World::player_inner presence discriminator.
  };
  const allianceMember = (entry,id) => {
    if (entry===null) return null;
    const set=entry+8, count=u32(set+12);
    if (!count) return false;
    const ctrl=u32(set),mask=u32(set+4),size=mask+1;
    if (size>65536 || (size&(size-1))!==0 || count>size ||
        !range(ctrl-size*2,size*2+size+8)) return null;
    const hash=Math.imul(id,656542357)>>>0,tag=hash>>>25;
    let offset=hash&mask,stride=0;
    for (let group=0;group<=Math.ceil(size/8);group++) {
      let empty=false;
      for (let j=0;j<8;j++) {
        const c=u8(ctrl+offset+j),slot=(offset+j)&mask;
        // Pinned hash lookup probes only membership needed by normal Color::new.
        // Never export unrelated alliance identifiers or any other player fields.
        if (c===tag && u16(ctrl-2*(slot+1))===id) return true;
        if ((c&0xc0)===0xc0) empty=true;
      }
      if (empty) return false;
      stride+=8;offset=(offset+stride)&mask;
    }
    return null;
  };
  const relationFor = owner => {
    if (owner===0) return "NEUTRAL";
    if (owner===player) return "SELF";
    if (relationCache.has(owner)) return relationCache.get(owner);
    const forward=allianceMember(playerEntry(player),owner);
    const reverse=forward===true ? allianceMember(playerEntry(owner),player) : forward;
    const relation=forward===null || reverse===null ? null : forward && reverse ? "ALLY" : "ENEMY";
    relationCache.set(owner,relation);return relation;
  };
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
      const relation = relationFor(owner);
      // Pinned normal owner overlay checks Tower+24's Option sentinel before
      // drawing its road. Observe presence only; no path pointer/length/entry.
      // Owner and positive current fog gates precede this read, even for allies.
      let supplyLinePresent = null;
      if (player > 0 && owner === player) {
        const tag = u32(tower + 24);
        supplyLinePresent = tag === 0x80000000 ? false : tag < 0x80000000 ? true : null;
      }
      towers.push({id: (x | y << 16) >>> 0, visible: true,
        visibility_source: "official Visible.refs positive + generated tower",
        owner, relation, type: u8(tower + 46), supply_line_present: supplyLinePresent,
        units7: Array.from(new Uint8Array(memory.buffer, tower + 38, 7)),
        morale: u8(tower + 45), delay_ticks: u8(tower + 47),
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
  const visibleRef = id => {
    const x = id & 65535, y = id >>> 16;
    return x >= bounds[0] && y >= bounds[1] && x <= bounds[2] && y <= bounds[3] &&
      u16(refs + 2 * (x - bounds[0] + (y - bounds[1]) * width)) > 0;
  };
  const forces = [];
  for (const t of towers) {
    // Follow the pinned normal renderer: inbound, plus outbound to non-visible
    // destinations. The inbound copy owns a visible-to-visible force.
    for (const vectorOffset of [0, 12]) {
      const cap = u32(t.research_ref + vectorOffset), ptr = u32(t.research_ref + vectorOffset + 4);
      const len = u32(t.research_ref + vectorOffset + 8);
      if (len > cap || (len > 0 && !range(ptr, len * 24))) throw Error("invalid visible force vector");
      for (let i = 0; i < len; i++) {
        const f = ptr + i * 24, path = u32(f + 4), pathLen = u32(f + 8);
        if (pathLen < 2 || pathLen > u32(f) || !range(path, pathLen * 4))
          throw Error("invalid visible force segment");
        // Read only the current leg needed by the normal renderer. Never read
        // future route entries, and never export a hidden endpoint identifier.
        const src = u32(path + (pathLen - 1) * 4), dst = u32(path + (pathLen - 2) * 4);
        if (vectorOffset === 12 && visibleRef(dst)) continue;
        if ((vectorOffset === 0 && dst !== t.id) || (vectorOffset === 12 && src !== t.id))
          throw Error("force does not belong to visible rendering tower");
        const owner = u16(f + 12), accelerated = u8(f + 21);
        if (accelerated > 1) throw Error("invalid acceleration flag");
        forces.push({visible: true,
          visibility_source: vectorOffset === 0 ? "normal renderer: visible tower inbound" : "normal renderer: visible tower outbound to non-visible endpoint",
          owner, relation: relationFor(owner),
          source: visibleIds.has(src) ? src : null, destination: visibleIds.has(dst) ? dst : null,
          units7: Array.from(new Uint8Array(memory.buffer, f + 14, 7)),
          progress: u8(f + 22), accelerated,
          // Diagnostics are not a stable force identity.
          research_ref: f});
      }
    }
  }
  // Own persistent Unlocks copied by the normal UI props builder. This is not
  // the effective ad/rank-dependent lock policy or permission to issue commands.
  const ownUnlocks = (() => {
    const p=root+46240,ctrl=u32(p),mask=u32(p+4),len=u32(p+12),size=mask+1;
    if (size>64 || (size&(size-1))!==0 || len>27 || len>size || !range(ctrl,size)) return null;
    const kinds=[];
    for (let slot=0;slot<size;slot++) if (u8(ctrl+slot)<128) {
        if (!range(ctrl-size,size)) return null;
        const kind=u8(ctrl-slot-1);
        if (kind>=27 || kinds.includes(kind)) return null;
        kinds.push(kind);
    }
    if (kinds.length!==len) return null;
    return {keys:u32(p+32),unlocked_types:kinds.sort((a,b)=>a-b)};
  })();
  // Normal Ctw props clone uses RewardedAd at context+48964. CoreState::rank
  // reads its direct enum at core+255; tag 0 uses a claims lookup which is not
  // read here. Preserve that path as UNKNOWN and never inspect claim storage.
  const adTag=u32(root+48964),rankTag=u8(core+255);
  const ownUpgradePolicy={rewarded_ad_available:adTag<=3 ? adTag!==0 : null,
    rank_requires_unlocks:rankTag>=1 && rankTag<=7 ? rankTag<3 || rankTag===7 : null};
  return {...metadata, towers, positive_refs: positiveRefs, own_unlocks:ownUnlocks,
    own_upgrade_policy:ownUpgradePolicy,
    // Normal current-player prerequisite presentation; no hidden tower IDs.
    own_tower_counts: Array.from({length:27},(_,i)=>u16(root+592+i*2)),
    camera_candidate: camera, status: "RESEARCH_CANDIDATE",
    selected_tower: u32(root + 47968) === 1 ? u32(root + 47972) : null,
    match_id: null, updated_at_ms: null,
    forces, coverage: positiveRefs === towers.length ? "PLAYER_VISIBLE_COMPLETE" : "PARTIAL"};
}
