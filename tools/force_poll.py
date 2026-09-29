"""MUSE force poller (read-only): learn numeric player ids from moving forces.

Polls inbound/outbound collections of all anchored towers via CDP.
Relation inference (conservative):
- outbound entry on a SELF tower, path[-1]==that tower => SELF id (our dispatch)
- entry from an ENEMY tower to a SELF tower => ENEMY id
- entry from an ALLY tower to a SELF tower => ALLY id
The anchor's render_color is authoritative for separating ALLY (2) and ENEMY (3).
Never fabricates ids. Prints JSON lines; stops early on SELF id discovery
if --stop-on-self.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from live_page import find_live_target_id  # noqa: E402
from cdp_probe import Session  # noqa: E402
from kiomet_ai.force import RealForceObserver  # noqa: E402
from kiomet_ai.observe import classify_owner  # noqa: E402

ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"


def tower_owner_relation(tower: dict) -> str | None:
    """保留色碼區分盟友與敵人；legacy OTHER 一律視為 UNKNOWN。"""
    if not isinstance(tower, dict):
        return None
    render_color = tower.get("render_color")
    if type(render_color) is int:
        return classify_owner(render_color)
    owner = tower.get("owner")
    return owner if owner in ("SELF", "NEUTRAL", "ALLY", "ENEMY") else None


def force_owner_relation(source_owner: str | None,
                         target_owner: str | None,
                         collection_role: str | None) -> str:
    """依明確塔色與集合方向分類；OTHER／缺欄不推測成敵人。"""
    if source_owner == "SELF" and collection_role == "OUTBOUND":
        return "SELF"
    if source_owner == "ENEMY" and target_owner == "SELF":
        return "ENEMY"
    if source_owner == "ALLY" and target_owner == "SELF":
        return "ALLY"
    return "UNKNOWN"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--stop-on-self", action="store_true")
    args = ap.parse_args()

    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    match = anchor["match_id"]
    owners = {t["packed_id"]: tower_owner_relation(t)
              for t in anchor["towers"]}
    refs = {t["packed_id"]: t["tower_ref"] for t in anchor["towers"]}
    positions = {t["packed_id"]: tuple(t["position"]) for t in anchor["towers"]}

    seen = {}
    self_ids, ally_ids, enemy_ids = set(), set(), set()
    deadline = time.time() + args.seconds
    events = []

    with Session("https://kiomet.com/", page_id=find_live_target_id(), timeout=12) as cdp:
        proto = cdp.call("Runtime.evaluate",
                         {"expression": "WebAssembly.Memory.prototype"})["result"]["objectId"]
        mem = cdp.call("Runtime.queryObjects",
                       {"prototypeObjectId": proto})["objects"]["objectId"]

        def read(addr, length):
            result = cdp.call("Runtime.callFunctionOn", {
                "objectId": mem, "returnByValue": True,
                "arguments": [{"value": addr}, {"value": length}],
                "functionDeclaration": """function(addr, len) {
                    if (this.length !== 1) throw Error('one wasm memory expected');
                    const v = new Uint8Array(this[0].buffer);
                    if (addr < 0 || addr + len > v.byteLength) throw Error('oob');
                    return Array.from(v.slice(addr, addr + len));
                }"""})
            if "exceptionDetails" in result:
                raise RuntimeError(str(result["exceptionDetails"])[:200])
            return bytes(result["result"]["value"])

        observer = RealForceObserver(read, positions)
        try:
            while time.time() < deadline:
                for tid, tref in refs.items():
                    try:
                        forces = observer.scan_tower(match, tid, tref, time.time())
                    except Exception:
                        continue
                    for f in forces:
                        key = (f.collection_role, f.raw_ref, tuple(f.path),
                               f.owner_id, tuple(sorted(f.units.counts.items()))
                               if f.units else None)
                        if key in seen:
                            continue
                        seen[key] = True
                        src, dst = f.current_source, f.current_destination
                        src_owner = owners.get(src)
                        dst_owner = owners.get(dst)
                        relation = force_owner_relation(
                            src_owner, dst_owner, f.collection_role)
                        if type(f.owner_id) is int and f.owner_id > 0:
                            if relation == "SELF":
                                self_ids.add(f.owner_id)
                            elif relation == "ALLY":
                                ally_ids.add(f.owner_id)
                            elif relation == "ENEMY":
                                enemy_ids.add(f.owner_id)
                        ev = {"t": round(time.time(), 1),
                              "anchor": tid, "role": f.collection_role,
                              "owner_id": f.owner_id, "relation": relation,
                              "src": src, "src_owner": src_owner,
                              "dst": dst, "dst_owner": dst_owner,
                              "progress": f.progress,
                              "units": f.units.counts if f.units else None,
                              "path": list(f.path)}
                        events.append(ev)
                        print(json.dumps(ev, ensure_ascii=False), flush=True)
                if args.stop_on_self and self_ids:
                    break
                time.sleep(args.interval)
        finally:
            cdp.call("Runtime.releaseObject", {"objectId": mem})
            cdp.call("Runtime.releaseObject", {"objectId": proto})

    summary = {"match_id": match, "events": len(events),
               "self_ids": sorted(self_ids), "ally_ids": sorted(ally_ids),
               "enemy_ids": sorted(enemy_ids)}
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": summary, "events": events},
                       ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
