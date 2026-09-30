"""Pinned client observation; no WASM calls, heap writes or command dispatch."""
import base64
from dataclasses import replace
import hashlib
from pathlib import Path
import time
from uuid import uuid4
import psutil

from ..state import Fact, GameState, Knowledge, Relation, Tower, Units
from .source_clock import SourceClock
from .lifecycle import MatchLifecycle
from .forces import ForceTracker
from . import rules

CLIENT_SHA256 = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"


async def connect_dedicated(pw, root):
    """Authenticate the local control port by its owning browser profile."""
    profile = (root / "runtime/browser-profile").resolve()
    port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
    listeners = [c for c in psutil.net_connections(kind="tcp")
                 if c.status == psutil.CONN_LISTEN and c.laddr.port == port
                 and c.laddr.ip in ("127.0.0.1", "::1") and c.pid]
    owners = {c.pid for c in listeners}
    if len(owners) != 1:
        raise ValueError("dedicated browser port owner absent or ambiguous")
    proc = psutil.Process(owners.pop())
    profiles = [arg.split("=", 1)[1] for arg in proc.cmdline()
                if arg.startswith("--user-data-dir=")]
    if not proc.name().lower().endswith(("chrome.exe", "chromium.exe")) or len(profiles) != 1 or Path(profiles[0]).resolve() != profile:
        raise ValueError("control port is not owned by the project browser")
    return await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")


def observed(value, source, at):
    return Fact(value, Knowledge.OBSERVED, source, at) if value is not None else Fact()


def decode_many(raw):
    if not isinstance(raw, list) or len(raw) != 7 or any(type(n) is not int or not 0 <= n <= 255 for n in raw):
        raise ValueError("malformed units")
    # Single layout is still independently unverified: retain UNKNOWN.
    if raw[0] == 1:
        return None
    if raw[0] != 0:
        raise ValueError("unknown units tag")
    return Units(tuple((i, raw[6] if i == 0 else raw[i] if i < 6 else 0) for i in range(10)))


def decode_units(raw):
    """Pinned Units::available: Single count +1, enum +2, shield +6."""
    many = decode_many(raw)
    if many is not None:
        return many
    count,unit = raw[1],raw[2]
    if not 6<=unit<=9 or count==0:
        raise ValueError("invalid Single units")
    return Units(tuple((i,raw[6] if i==0 else count if i==unit else 0) for i in range(10)))


def normalize(raw, session_id, document_id, sequence, received_ms, sample_started_ms=None,
              update_window=None, match_identity=None, lifecycle=None, force_tracker=None):
    # Browser epoch time and host monotonic time are different clock domains.
    # Host send time is a conservative lower bound on this synchronous read.
    at = raw["sampled_at_ms"] if sample_started_ms is None else sample_started_ms
    if raw.get('transport_mode') not in (None,'NETWORK'):
        raise ValueError('canonical world requires network source mode')
    own_counts=raw.get('own_tower_counts')
    if own_counts is not None:
        if not isinstance(own_counts,list) or len(own_counts)!=27 or any(type(n)is not int or not 0<=n<=65535 for n in own_counts):
            raise ValueError('invalid own prerequisite tower counts')
        own_counts=tuple(own_counts)
    towers = []
    for row in raw["towers"]:
        if row.get("visible") is not True or not row.get("visibility_source"):
            raise ValueError("missing current visibility evidence")
        typ = row["type"]
        if type(typ) is not int or not 0 <= typ < 27:
            raise ValueError("invalid tower type")
        owner = row["owner"]
        if type(owner) is not int or not 0 <= owner <= 65535:
            raise ValueError("invalid owner")
        relation = Relation(row["relation"]) if row["relation"] is not None else None
        units=decode_units(row['units7'])
        morale,delay=row.get('morale'),row.get('delay_ticks')
        if morale is not None and (type(morale) is not int or morale not in (0,1)):
            raise ValueError('invalid visible morale flag')
        if delay is not None and (type(delay) is not int or not 0<=delay<=255):
            raise ValueError('invalid visible delay')
        towers.append(Tower(row["id"], observed(True, row["visibility_source"], at),
            owner=observed(owner, "Tower.owner+36", at),
            relation=(Fact(relation,Knowledge.DERIVED,'pinned normal Color::new bilateral alliance membership',at)
                      if relation in (Relation.ALLY,Relation.ENEMY) else observed(relation, "client player identity comparison", at)),
            tower_type=observed(typ, "Tower.type+46", at),
            units=observed(units, "Tower.units+38; pinned Units::available Many/Single", at),
            capacity=Fact(rules.capacity(typ,morale),Knowledge.DERIVED,
                'pinned Units::capacity: raw type table + visible morale shield boost',at) if morale is not None else Fact(),
            production=Fact(rules.production(typ,units,owner,delay,morale),Knowledge.DERIVED,
                'potential source-tick generation intervals; pinned type/ruler/delay/morale rules; not guaranteed output',at)
                if morale is not None and delay is not None else Fact(),
            effects=observed((('MORALE_BOOST',bool(morale)),),'visible Tower.morale+45; normal UI morale note',at) if morale is not None else Fact(),
            delay_ticks=observed(delay,'Tower.delay+47; upgrade or EMP cause unspecified',at),
            upgrade_candidates=Fact(rules.upgrade_candidates(typ,own_counts,delay),Knowledge.DERIVED,
                'pinned normal prerequisite targets/counts; unlock and final command eligibility unknown',at)
                if relation==Relation.SELF and own_counts is not None and delay is not None else Fact(),
            deployable=Fact(rules.mobile_inventory(typ,units),Knowledge.DERIVED,
                'pinned Tower::force_units mobile inventory; route/command legality is separate and unverified',at)
                if relation==Relation.SELF else Fact(),
            neighbors=(Fact(tuple(sorted(row["neighbors"])), Knowledge.DERIVED,
                            "official neighbor table intersect current Visible.refs", at)
                       if "neighbors" in row else Fact()),
            position=Fact(tuple(row["position"]), Knowledge.DERIVED,
                          "official integer-position offset table", at)))
    forces = Fact()
    if raw.get("forces") is not None:
        tracker = force_tracker or ForceTracker()
        decoded = tracker.update(raw["forces"],towers,match_identity,raw.get("tick"),at,decode_units)
        forces = observed(decoded,"normal-rendered force vectors after current visibility gate",at)
    rulers=[('SELF_ALIVE_AT_TOWER',t.id) for t in towers
            if t.owner.value==raw['player_id'] and dict(t.units.value.counts)[9]>0]
    for f in forces.value or ():
        if f.owner.value==raw['player_id'] and dict(f.units.value.counts)[9]>0:
            rulers.append(('SELF_ALIVE_IN_VISIBLE_FORCE',f.id.value,f.source.value,f.destination.value))
    king=observed(rulers[0],'currently visible self Ruler units; absence never implies death',at) if len(rulers)==1 else Fact()
    return GameState(session_id, document_id,
        Fact(match_identity, Knowledge.DERIVED,
             "document + player identity + observed lifecycle / official join epoch", at) if match_identity else Fact(),
        sequence, at, received_ms,
        CLIENT_SHA256, client_sampled_at_ms=observed(raw["sampled_at_ms"], "browser clock (separate domain)", at),
        tick=observed(raw.get("tick"), "pinned displayed World.Singleton sequence u16; transport mode separately verified; server timestamp unknown", at),
        source_mode=observed(raw.get("transport_mode"),"pinned Transport enum / typed ClientSession ownership",at),
        source_update_window_ms=(Fact(update_window, Knowledge.DERIVED,
            "source tick transition bracketed by previous read start / current read finish; host clock", at)
            if update_window is not None else Fact()),
        lifecycle=Fact(lifecycle, Knowledge.DERIVED,
            "official active condition + Play UI + typed owned ClientSession transport state", at) if lifecycle else Fact(),
        player_id=observed(raw["player_id"], "client.player_id", at),
        upgrade_resources=observed(tuple(enumerate(own_counts)) if own_counts is not None else None,
            'own NonActor active tower counts; normal upgrade prerequisite UI; no enemy aggregates',at),
        king=king,
        forces=forces,
        towers=tuple(sorted(towers, key=lambda t: t.id)))


class ClientExtractor:
    """One document-bound CDP observer. Reattach after any document change."""

    def __init__(self, page, session_id=None, diagnostic_sockets=False):
        self.page = page
        self.session_id = session_id or uuid4().hex
        self.document_id = uuid4().hex
        self.sequence = 0
        self.cdp = None
        self.memories_id = None
        self.time_origin = None
        self.source_clock = SourceClock()
        self.force_tracker = ForceTracker()
        self.lifecycle = MatchLifecycle(self.document_id)
        self.sockets_id = None
        self.sockets_dirty = True
        self.owner_states_id = None
        self.sockets_checked_at = 0
        self.diagnostic_sockets = diagnostic_sockets
        self.decoder_source = Path(__file__).with_name("client_fae13.js").read_text(encoding="utf8")

    async def _refresh_sockets(self):
        proto = (await self.cdp.send("Runtime.evaluate", {
            "expression": "WebSocket.prototype"}))["result"]["objectId"]
        try:
            new = (await self.cdp.send("Runtime.queryObjects", {
                "prototypeObjectId":proto}))["objects"]["objectId"]
            if self.sockets_id:
                await self.cdp.send("Runtime.releaseObject", {"objectId":self.sockets_id})
            self.sockets_id = new
            self.sockets_dirty = False
            self.sockets_checked_at = time.monotonic()
        finally:
            await self.cdp.send("Runtime.releaseObject", {"objectId":proto})

    async def _attach_owners(self):
        proto=(await self.cdp.send('Runtime.evaluate',{'expression':'Object.prototype'}))['result']['objectId']
        objects=None
        try:
            objects=(await self.cdp.send('Runtime.queryObjects',{'prototypeObjectId':proto}))['objects']['objectId']
            result=await self.cdp.send('Runtime.callFunctionOn',{'objectId':objects,
                'functionDeclaration':'''function(){return this.filter(o=>Object.hasOwn(o,'a')&&
                    Object.hasOwn(o,'b')&&Object.hasOwn(o,'cnt')&&[1079544,1079504].includes(o.b)&&
                    Number.isInteger(o.a)&&Number.isInteger(o.cnt)&&o.a>0&&o.cnt>0);}'''})
            if 'exceptionDetails'in result:
                raise ValueError('normal event owner discovery failed')
            self.owner_states_id=result['result']['objectId']
            count=(await self.cdp.send('Runtime.callFunctionOn',{
                'objectId':self.owner_states_id,'returnByValue':True,
                'functionDeclaration':'function(){return this.length;}'
            }))['result']['value']
            if count==0:
                raise ValueError('normal event owners not ready')
        finally:
            if objects:
                await self.cdp.send('Runtime.releaseObject',{'objectId':objects})
            await self.cdp.send('Runtime.releaseObject',{'objectId':proto})

    async def attach(self):
        if self.cdp is not None:
            raise RuntimeError("extractor already attached")
        if self.page.url != "https://kiomet.com/":
            raise ValueError("official client page required")
        self.cdp = await self.page.context.new_cdp_session(self.page)
        scripts = []
        self.cdp.on("Debugger.scriptParsed", lambda event: scripts.append(event))
        try:
            await self.cdp.send("Debugger.enable")
            clients = [s for s in scripts if s.get("url") == "https://kiomet.com/client_bg.wasm"]
            if len(clients) != 1:
                raise ValueError("official WASM absent or ambiguous")
            source = await self.cdp.send("Debugger.getScriptSource", {"scriptId": clients[0]["scriptId"]})
            digest = hashlib.sha256(base64.b64decode(source["bytecode"])).hexdigest()
            if digest != CLIENT_SHA256:
                raise ValueError("unsupported official client version: " + digest)
            await self.cdp.send("Debugger.disable")
            self.cdp.on("Network.webSocketCreated", lambda _: setattr(self,"sockets_dirty",True))
            await self.cdp.send("Network.enable")
            if self.diagnostic_sockets:
                await self._refresh_sockets()
            await self._attach_owners()
            self.time_origin = await self.page.evaluate("performance.timeOrigin")
            proto = (await self.cdp.send("Runtime.evaluate", {
                "expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
            try:
                self.memories_id = (await self.cdp.send("Runtime.queryObjects", {
                    "prototypeObjectId": proto}))["objects"]["objectId"]
            finally:
                await self.cdp.send("Runtime.releaseObject", {"objectId": proto})
        except BaseException:
            await self.close()
            raise

    async def _read(self, mode):
        if self.memories_id is None:
            raise RuntimeError("extractor is not attached")
        if self.diagnostic_sockets and (self.sockets_dirty or time.monotonic()-self.sockets_checked_at>=1):
            await self._refresh_sockets()
        began_monotonic = time.monotonic_ns() / 1000000
        began_ms = int(began_monotonic)
        result = await self.cdp.send("Runtime.callFunctionOn", {
            "objectId": self.memories_id, "returnByValue": True,
            "arguments": [{"value": mode}, {"value": []}, {"objectId":self.owner_states_id}],
            "functionDeclaration": self.decoder_source})
        if "exceptionDetails" in result:
            raise ValueError(result["exceptionDetails"].get("exception", {}).get("description", "client decode failed"))
        raw = result["result"]["value"]
        if raw["document_time_origin"] != self.time_origin:
            self.source_clock.clear()
            raise ValueError("document changed; discard observer and reattach")
        received_ms = time.monotonic_ns() // 1000000
        life, identity = self.lifecycle.observe(raw, received_ms)
        raw["derived_lifecycle"] = life
        raw["derived_match_id"] = identity
        window = None
        if identity:
            window = self.source_clock.observe(
                (self.document_id, identity, raw["root_candidate"], raw["player_id"],raw.get("transport_mode")),
                raw.get("tick"), began_ms, received_ms, began_monotonic)
        else:
            self.source_clock.clear()
            self.force_tracker.clear()
        return raw, began_ms, received_ms, window

    async def metadata(self):
        """Only normal-client lifecycle/tick metadata; no world payload."""
        return (await self._read("metadata"))[0]

    async def sample(self):
        raw, began_ms, received_ms, window = await self._read("world")
        if raw.get("world_unavailable"):
            raise ValueError(raw["world_unavailable"])
        state = normalize(raw, self.session_id, self.document_id,
                          self.sequence + 1, received_ms, began_ms, update_window=window,
                          match_identity=raw["derived_match_id"],lifecycle=raw["derived_lifecycle"],
                          force_tracker=self.force_tracker)
        # Timestamp when the complete canonical state becomes available, after
        # normalization/tracking; never hide that work from downstream age.
        state=replace(state,received_at_ms=time.monotonic_ns()//1000000)
        self.sequence += 1
        return state, raw

    async def close(self):
        self.source_clock.clear()
        self.force_tracker.clear()
        if self.cdp:
            try:
                for oid in (self.memories_id,self.sockets_id,self.owner_states_id):
                    if oid:
                        try:
                            await self.cdp.send("Runtime.releaseObject", {"objectId":oid})
                        except Exception:
                            pass  # The old document may already have destroyed its handles.
                for command in ("Network.disable","Debugger.disable"):
                    try:
                        await self.cdp.send(command)
                    except Exception:
                        pass
            finally:
                try:
                    await self.cdp.detach()
                except Exception:
                    pass  # Closed documents/browsers have already disposed it.
                finally:
                    self.cdp = self.memories_id = self.sockets_id = None
                    self.owner_states_id = None


class ObservationSession:
    """Reacquire a pinned observer after a real document reload; never send input."""
    def __init__(self,page):
        self.page = page
        self.session_id = uuid4().hex
        self.extractor = None
        self.document_reacquisitions = 0
        self.document_dirty = True
        self.last_document_check = 0
        self._navigation_handler = self._document_navigated
        self.page.on("framenavigated",self._navigation_handler)

    def _document_navigated(self,frame):
        if frame == self.page.main_frame:
            self.document_dirty = True

    async def _ensure_document(self):
        # The memory read itself checks document origin. Browser navigation
        # events trigger immediate reacquisition; periodic verification is a
        # fallback, avoiding an extra page round trip on every source read.
        if self.extractor is not None and not self.document_dirty and time.monotonic()-self.last_document_check<.5:
            return
        origin = await self.page.evaluate("performance.timeOrigin")
        self.last_document_check=time.monotonic()
        self.document_dirty=False
        if self.extractor is not None and origin != self.extractor.time_origin:
            await self.extractor.close()
            self.extractor = None
        if self.extractor is None:
            ex = ClientExtractor(self.page,self.session_id)
            await ex.attach()
            self.extractor = ex
            self.document_reacquisitions += 1

    async def metadata(self):
        await self._ensure_document()
        return await self.extractor.metadata()

    async def sample(self):
        await self._ensure_document()
        return await self.extractor.sample()

    async def close(self):
        self.page.remove_listener("framenavigated",self._navigation_handler)
        if self.extractor:
            await self.extractor.close()
            self.extractor = None
