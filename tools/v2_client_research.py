"""Bounded official-client research, reusing the v1 isolated browser only.

No tactical input; --join clicks the official Play button. No global input.
Runtime artifacts remain ignored. Stop with Ctrl+C; finally closes our browser.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime/browsers")
from kiomet_ai.browser import BrowserHost


class ResearchGate:
    async def dispatch(self, operation):
        return await operation()


async def main(args):
    out = ROOT / "runtime/research/v2"
    out.mkdir(parents=True, exist_ok=True)
    (ROOT / "runtime/logs").mkdir(parents=True, exist_ok=True)
    host = BrowserHost(ROOT, ResearchGate())
    try:
        await host.start("https://kiomet.com/", "about:blank")
        page = host.game_page
        for _ in range(30):
            await asyncio.sleep(1)
            if await page.locator("#play_button").is_visible():
                break
        print(json.dumps({"phase": "loaded", "url": page.url,
                          "guard": host.guard(),
                          "text": (await page.locator("body").inner_text())[:1800]}), flush=True)
        cdp = await page.context.new_cdp_session(page)
        scripts = []
        cdp.on("Debugger.scriptParsed", lambda event: scripts.append(event))
        await cdp.send("Debugger.enable")
        versions = []
        for s in scripts:
            if s.get("scriptLanguage") == "WebAssembly":
                result = await cdp.send("Debugger.getScriptSource", {"scriptId": s["scriptId"]})
                data = base64.b64decode(result["bytecode"])
                sha = hashlib.sha256(data).hexdigest()
                (out / f"{sha}.wasm").write_bytes(data)
                versions.append({"sha256": sha, "bytes": len(data), "script": s})
            elif s.get("url", "").startswith("https://kiomet.com/"):
                result = await cdp.send("Debugger.getScriptSource", {"scriptId": s["scriptId"]})
                source = result.get("scriptSource", "")
                if len(source) > 1000:
                    (out / f"script-{s['scriptId']}.js").write_text(source, encoding="utf8")
        await cdp.send("Debugger.disable")
        await cdp.detach()
        (out / "client-version.json").write_text(json.dumps(versions, indent=2), encoding="utf8")
        print(json.dumps({"phase": "version", "wasm": versions}), flush=True)
        if args.join:
            print(json.dumps(await host.enter_match(), ensure_ascii=False), flush=True)
        stop = out / "research-stop"
        stop.unlink(missing_ok=True)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline and not stop.exists():
            await asyncio.sleep(10)
            await host.sense_game_state()
            (out / "research-host.json").write_text(json.dumps({"session": host.session_id,
                "status": host.status, "game": host.game, "timestamp": time.time()}, indent=2), encoding="utf8")
            print(json.dumps({"phase": "alive", "game": host.game["state"],
                              "match": host.game["match"]["id"], "guard": host.guard()}), flush=True)
        stop.unlink(missing_ok=True)
    finally:
        await host.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--join", action="store_true")
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 1800:
        parser.error("seconds must be 1..1800")
    asyncio.run(main(args))
