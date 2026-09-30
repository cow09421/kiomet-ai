"""Pinned client observation; no WASM calls, heap writes or command dispatch."""
import base64
import hashlib
from pathlib import Path
import time
from uuid import uuid4
import psutil

from ..state import Fact, GameState, Knowledge, Relation, Tower, Units

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


def normalize(raw, session_id, document_id, sequence, received_ms, sample_started_ms=None):
    # Browser and host wall clocks are different clock domains on Windows.
    # Host send time is a conservative lower bound on this synchronous read.
    at = raw["sampled_at_ms"] if sample_started_ms is None else sample_started_ms
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
        towers.append(Tower(row["id"], observed(True, row["visibility_source"], at),
            owner=observed(owner, "Tower.owner+36", at),
            relation=observed(relation, "client player identity comparison", at),
            tower_type=observed(typ, "Tower.type+46", at),
            units=observed(decode_many(row["units7"]), "Tower.units+38 (Many)", at),
            neighbors=(Fact(tuple(sorted(row["neighbors"])), Knowledge.DERIVED,
                            "official neighbor table intersect current Visible.refs", at)
                       if "neighbors" in row else Fact()),
            position=Fact(tuple(row["position"]), Knowledge.DERIVED,
                          "official integer-position offset table", at)))
    # Match/update time and moving-force coverage have NOT been verified.
    # Explicitly do not turn the host's inferred match label into an observed ID.
    return GameState(session_id, document_id, Fact(), sequence, at, received_ms,
        CLIENT_SHA256, client_sampled_at_ms=observed(raw["sampled_at_ms"], "browser clock (separate domain)", at),
        player_id=observed(raw["player_id"], "client.player_id", at),
        towers=tuple(sorted(towers, key=lambda t: t.id)))


class ClientExtractor:
    """One document-bound CDP observer. Reattach after any document change."""

    def __init__(self, page, session_id=None):
        self.page = page
        self.session_id = session_id or uuid4().hex
        self.document_id = uuid4().hex
        self.sequence = 0
        self.cdp = None
        self.memories_id = None
        self.time_origin = None

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

    async def sample(self):
        if self.memories_id is None:
            raise RuntimeError("extractor is not attached")
        began_ms = time.time_ns() // 1000000
        result = await self.cdp.send("Runtime.callFunctionOn", {
            "objectId": self.memories_id, "returnByValue": True,
            "functionDeclaration": Path(__file__).with_name("client_fae13.js").read_text(encoding="utf8")})
        if "exceptionDetails" in result:
            raise ValueError(result["exceptionDetails"].get("exception", {}).get("description", "client decode failed"))
        raw = result["result"]["value"]
        if raw["document_time_origin"] != self.time_origin:
            raise ValueError("document changed; discard observer and reattach")
        state = normalize(raw, self.session_id, self.document_id,
                          self.sequence + 1, time.time_ns() // 1000000, began_ms)
        self.sequence += 1
        return state, raw

    async def close(self):
        if self.cdp:
            try:
                if self.memories_id:
                    await self.cdp.send("Runtime.releaseObject", {"objectId": self.memories_id})
                await self.cdp.send("Debugger.disable")
            finally:
                await self.cdp.detach()
                self.cdp = self.memories_id = None
