"""Read-only WASM disassembly of the dedicated official client; no breakpoints."""
import asyncio
import argparse
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main(args):
    port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        cdp = await page.context.new_cdp_session(page)
        scripts = []
        cdp.on("Debugger.scriptParsed", lambda e: scripts.append(e))
        try:
            if args.ui:
                print(json.dumps(await page.evaluate("""() => ({text:document.body.innerText,
                  play:document.querySelector('#play_button')?.outerHTML})""")))
                return
            if args.references:
                mp = (await cdp.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
                memories = (await cdp.send("Runtime.queryObjects", {"prototypeObjectId": mp}))["objects"]["objectId"]
                result = await cdp.send("Runtime.callFunctionOn", {"objectId": memories, "returnByValue": True,
                    "arguments": [{"value": args.references}], "functionDeclaration": """function(root){
                      const m=this.filter(m=>m.buffer.byteLength>1000000);if(m.length!==1)throw Error('Ambiguous memory');
                      const v=new Uint32Array(m[0].buffer);const refs=[];for(let i=0;i<v.length;i++){
                        if(v[i]===root||v[i]===root-16)refs.push({address:4*i,value:v[i],words:Array.from(v.slice(Math.max(0,i-4),i+5))});
                      }return refs;}"""})
                print(json.dumps(result))
                await cdp.send("Runtime.releaseObject", {"objectId": memories})
                await cdp.send("Runtime.releaseObject", {"objectId": mp})
                return
            if args.roots:
                proto = (await cdp.send("Runtime.evaluate", {"expression": "Object.prototype"}))["result"]["objectId"]
                objects = (await cdp.send("Runtime.queryObjects", {"prototypeObjectId": proto}))["objects"]["objectId"]
                result = await cdp.send("Runtime.callFunctionOn", {"objectId": objects,
                    "returnByValue": True, "functionDeclaration": """function(){return this.filter(o=>
                      Object.hasOwn(o,'a')&&Object.hasOwn(o,'b')&&Object.hasOwn(o,'cnt')&&
                      Number.isInteger(o.a)&&Number.isInteger(o.b)&&Number.isInteger(o.cnt)
                    ).map(o=>({a:o.a,b:o.b,cnt:o.cnt}));}"""})
                mp = (await cdp.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
                memories = (await cdp.send("Runtime.queryObjects", {"prototypeObjectId": mp}))["objects"]["objectId"]
                detail = await cdp.send("Runtime.callFunctionOn", {"objectId": memories, "returnByValue": True,
                    "arguments": [{"value": result["result"]["value"]}],
                    "functionDeclaration": """function(rows){const m=this.filter(m=>m.buffer.byteLength>1000000);
                      if(m.length!==1)throw Error('Ambiguous memory');const v=new DataView(m[0].buffer);
                      return rows.filter(r=>r.a>0&&r.cnt>0&&r.a+32<=v.byteLength).map(r=>({...r,
                        words:Array.from({length:8},(_,i)=>v.getUint32(r.a+4*i,true))}));}"""})
                await cdp.send("Runtime.releaseObject", {"objectId": memories})
                await cdp.send("Runtime.releaseObject", {"objectId": mp})
                result = detail
                (ROOT / "runtime/research/v2/closure-roots.json").write_text(json.dumps(result, indent=2), encoding="utf8")
                print(json.dumps(result)[:5000])
                await cdp.send("Runtime.releaseObject", {"objectId": objects})
                await cdp.send("Runtime.releaseObject", {"objectId": proto})
                return
            await cdp.send("Debugger.enable")
            wasm = next(s for s in scripts if s.get("url") == "https://kiomet.com/client_bg.wasm")
            if args.anchor:
                paused = asyncio.get_running_loop().create_future()
                cdp.on("Debugger.paused", lambda e: paused.set_result(e) if not paused.done() else None)
                bp = await cdp.send("Debugger.setBreakpoint", {"location": {
                    "scriptId": wasm["scriptId"], "lineNumber": 0, "columnNumber": 0xdcc00}})
                try:
                    event = await asyncio.wait_for(paused, 3)
                    scopes = []
                    for scope in event["callFrames"][0]["scopeChain"]:
                        props = await cdp.send("Runtime.getProperties", {
                            "objectId": scope["object"]["objectId"], "ownProperties": True})
                        if scope["type"] == "local":
                            values = {}
                            for prop in props["result"]:
                                if prop["name"] in {f"$var{i}" for i in range(39)} | {"$var74", "$var77"}:
                                    detail = await cdp.send("Runtime.getProperties", {
                                        "objectId": prop["value"]["objectId"], "ownProperties": True})
                                    values[prop["name"]] = detail
                            (ROOT / "runtime/research/v2/render-values.json").write_text(
                                json.dumps(values, indent=2), encoding="utf8")
                        scopes.append({"scope": scope, "props": props})
                    (ROOT / "runtime/research/v2/render-scope.json").write_text(
                        json.dumps({"event": event, "scopes": scopes}, indent=2), encoding="utf8")
                    print("Research scope saved; normal observation not yet implemented.")
                finally:
                    await cdp.send("Debugger.removeBreakpoint", {"breakpointId": bp["breakpointId"]})
                    if paused.done():
                        await cdp.send("Debugger.resume")
                return
            result = await cdp.send("Debugger.disassembleWasmModule", {"scriptId": wasm["scriptId"]})
            lines = result["chunk"]["lines"]
            offsets = result["chunk"]["bytecodeOffsets"]
            stream = result.get("streamId")
            while stream:
                chunk = (await cdp.send("Debugger.nextWasmDisassemblyChunk", {"streamId": stream}))["chunk"]
                if not chunk["lines"]:
                    break
                lines.extend(chunk["lines"])
                offsets.extend(chunk["bytecodeOffsets"])
            out = ROOT / "runtime/research/v2/disassembly.json"
            out.write_text(json.dumps({"lines": lines, "offsets": offsets}), encoding="utf8")
            print(json.dumps({"lines": len(lines), "file": str(out)}))
            print(json.dumps(await page.locator("body").inner_text(), ensure_ascii=True))
        finally:
            await cdp.send("Debugger.disable")
            await cdp.detach()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", action="store_true")
    parser.add_argument("--roots", action="store_true")
    parser.add_argument("--references", type=int)
    parser.add_argument("--ui", action="store_true")
    asyncio.run(main(parser.parse_args()))
