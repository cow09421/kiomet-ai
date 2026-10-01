"""Bounded normal reads of the pinned own-session dateCreated setting.

No credential, session ID, other-player field, packet or actor payload read.
The numeric candidate is transient and omitted from the evidence artifact.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright


async def main():
    lease = json.loads((ROOT / "runtime/research/v2/headless-host.json").read_text())
    if lease["deadline_monotonic_ms"] - time.monotonic_ns() // 1000000 < 45000:
        raise ValueError("owned browser lease too short for bounded date research")
    rows, errors, first = [], [], None
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/kiomet_ai/v2').rglob('*'))
        if p.is_file() and p.suffix in ('.py', '.js', '.json')}
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/"]
        if len(pages) != 1:
            raise ValueError("ambiguous official page")
        ex = ClientExtractor(pages[0])
        try:
            await ex.attach()
            end = time.monotonic() + 10
            while time.monotonic() < end:
                raw = await ex.metadata()
                result = await ex.cdp.send("Runtime.callFunctionOn", {
                    "objectId": ex.memories_id, "returnByValue": True,
                    "arguments": [{"value": raw}], "functionDeclaration": """function(raw){
                      const ms=this.filter(m=>m.buffer.byteLength>1000000);
                      if(ms.length!==1)throw Error('ambiguous memory');
                      const v=new DataView(ms[0].buffer),r=raw.root_candidate;
                      if(performance.timeOrigin!==raw.document_time_origin ||
                        v.getUint32(raw.root_slot_candidate-4,true)!==r ||
                        v.getUint32(raw.root_slot_candidate,true)!==1079724 ||
                        v.getBigUint64(r,true)===2n || r+45944>v.byteLength)
                        throw Error('pinned context changed');
                      return v.getBigUint64(r+45936,true).toString();
                    }"""})
                if "exceptionDetails" in result:
                    raise ValueError("dateCreated ownership guard failed")
                candidate = int(result["result"]["value"])
                if first is None:
                    first = candidate
                rows.append({"at_ms": time.monotonic_ns() // 1000000,
                    "document_time_origin": raw["document_time_origin"], "player": raw["player_id"],
                    "tick": raw["tick"], "source_mode": raw["transport_mode"],
                    "unchanged_from_first": candidate == first,
                    "nonzero_unix_ms_2010_2040": 1262304000000 <= candidate <= 2240611200000})
                await asyncio.sleep(.1)
        except Exception as error:
            errors.append(str(error)[:180])
        finally:
            await ex.close()
    changed_world = len({r["tick"] for r in rows}) > 1
    stable_date = bool(rows) and all(r["unchanged_from_first"] for r in rows)
    report = {"question": "does current production dateCreated advance with each Game update?",
        "status": "FAIL" if changed_world and stable_date and not errors else "UNKNOWN",
        "rows": rows, "errors": errors, "world_revisions": len({r["tick"] for r in rows}),
        "client_sha256": CLIENT_SHA256,
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observer_source_manifest": manifest,
        "numeric_date_recorded": False, "credentials_read": False, "actor_payload_read": False,
        "debugger_pauses": False, "tactical_commands": 0,
        "limits": "Exact own dateCreated setting only; storage update at pinned socket_update "
                  "0x2bdbd. It cannot certify Game generation time without a per-Game causal "
                  "mapping. No absence claim about other encodings or private server sources."}
    path = ROOT / "runtime/research/v2" / f"session-date-{uuid4().hex[:12]}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps({"file": str(path), **{k: v for k, v in report.items() if k != "rows"}}))


if __name__ == "__main__":
    asyncio.run(main())
