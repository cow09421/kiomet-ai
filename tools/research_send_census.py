"""發送普查 v2：複製前 64B＋時序，idle／pan／zoom 三段。被動包裝，用完即拆。"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from playwright.async_api import async_playwright

OUT = ROOT / "runtime/research/websocket"
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=15000)
        try:
            pages = [p for p in browser.contexts[0].pages if "kiomet.com" in (p.url or "")]
            target = None
            for page in pages:
                n = await page.evaluate("() => document.body.innerText.length")
                menu = await page.evaluate(
                    "() => !!document.querySelector('#play_button') && "
                    "document.querySelector('#play_button').offsetParent !== null")
                if not menu and n > 300:
                    target = page
                    break
            if target is None:
                print(json.dumps({"error": "no match"}))
                return
            await target.evaluate("""() => {
                if (window.__kLog) return;
                window.__kLog = [];
                const proto = WebSocket.prototype;
                if (proto.__kW) return;
                const orig = proto.send;
                proto.__kO = orig;
                proto.send = function(data) {
                    try {
                        if (window.__kLog.length < 120) {
                            let bytes = null;
                            if (data instanceof ArrayBuffer) bytes = new Uint8Array(data);
                            else if (ArrayBuffer.isView(data)) bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
                            if (bytes) {
                                let hex = '';
                                const k = Math.min(bytes.length, 64);
                                for (let i = 0; i < k; i++) hex += bytes[i].toString(16).padStart(2, '0');
                                window.__kLog.push([Date.now(), bytes.length, hex]);
                            } else {
                                window.__kLog.push([Date.now(), -1, typeof data]);
                            }
                        }
                    } catch (e) {}
                    return orig.call(this, data);
                };
                proto.__kW = true;
            }""")
            print("phase=idle 25s", flush=True)
            await asyncio.sleep(25)
            box = await target.evaluate("""() => {
                const c = document.querySelector('canvas');
                const r = c.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height};
            }""")
            cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
            print("phase=pan", flush=True)
            await target.mouse.move(cx, cy)
            await target.mouse.down(button="right")
            for i in range(1, 7):
                await target.mouse.move(cx + 900 * i / 6, cy - 200 * i / 6, steps=3)
                await asyncio.sleep(0.08)
            await target.mouse.up(button="right")
            await asyncio.sleep(5)
            print("phase=zoom", flush=True)
            await target.mouse.move(cx, cy)
            for _ in range(8):
                await target.mouse.wheel(0, -240)
                await asyncio.sleep(0.25)
            await asyncio.sleep(8)
            log = await target.evaluate("() => window.__kLog.splice(0)")
            (OUT / "census2.json").write_text(json.dumps(
                {"phases": "idle/pan/zoom", "sends": log}, indent=1), encoding="utf-8")
            from collections import Counter
            print("n=", len(log), "sizes=", dict(Counter(s[1] for s in log)))
            await target.evaluate("""() => {
                try {
                    if (WebSocket.prototype.__kO) WebSocket.prototype.send = WebSocket.prototype.__kO;
                    delete window.__kLog;
                    delete WebSocket.prototype.__kW;
                    delete WebSocket.prototype.__kO;
                } catch (e) {}
            }""")
            print("unwrapped")
        finally:
            await browser.close()


asyncio.run(main())
