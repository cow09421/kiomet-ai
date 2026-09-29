import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8766"

def request(path, method="GET", token=None, origin=None, host=None):
    headers = {}
    if token: headers["X-Control-Token"] = token
    if origin: headers["Origin"] = origin
    if host: headers["Host"] = host
    req = urllib.request.Request(URL+path, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)

async def expect_state(page, expected):
    for _ in range(50):
        if await page.locator("#state").inner_text() == expected:
            return
        await asyncio.sleep(.1)
    raise AssertionError("監控頁狀態未更新：" + expected)

async def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT/"src"), PYTHONUTF8="1", PLAYWRIGHT_BROWSERS_PATH=str(ROOT/"runtime/browsers"), TEMP=str(ROOT/"runtime/tmp"), TMP=str(ROOT/"runtime/tmp"))
    process = subprocess.Popen([sys.executable, "-m", "kiomet_ai.app", "--port", "8766", "--duration", "120", "--exit-after-stop"], cwd=ROOT, env=env)
    checks = {}
    try:
        for _ in range(150):
            try:
                _, status = request("/api/status")
                if status["state"] == "ERROR": raise RuntimeError(status["errors"])
                if status["plan_count"] >= 3: break
            except urllib.error.URLError:
                pass
            await asyncio.sleep(.5)
        else: raise RuntimeError("平台未就緒")
        assert status["browser"]["user_desktop_window_count"] == 0
        assert status["browser"]["isolated_window_count"] > 0
        checks["desktop_isolation"] = True
        token = json.loads((ROOT/"runtime/state/control.json").read_text())["token"]
        assert request("/api/stop", "POST")[0] == 403
        assert request("/api/stop", "POST", token, "https://example.invalid")[0] == 403
        assert request("/api/status", host="evil.invalid")[0] == 403
        checks["control_authentication"] = True
        for _ in range(100):
            _, status = request("/api/status")
            if status.get("live", {}).get("sequence", 0) >= 2:
                break
            await asyncio.sleep(.1)
        with urllib.request.urlopen(URL+"/api/live.jpg") as frame:
            assert frame.headers["Content-Type"] == "image/jpeg"
            assert frame.read().startswith(b"\xff\xd8")
        checks["live_image_endpoint"] = True
        _, low_before = request("/api/status")
        await asyncio.sleep(5)
        _, low_after = request("/api/status")
        assert low_after["live"]["sequence"]-low_before["live"]["sequence"] >= 4
        checks["live_one_fps"] = True
        async with async_playwright() as pw:
            port = (ROOT/"runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            session = await browser.new_browser_cdp_session()
            async with context.expect_page() as pending_page:
                await session.send("Target.createTarget", {"url":"about:blank", "newWindow":True, "background":True, "windowState":"normal"})
            page = await pending_page.value
            await session.detach()
            console_errors = []
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            await page.goto(URL)
            await page.get_by_role("button", name="暫停 AI").first.click()
            await expect_state(page, "PAUSED（已暫停）")
            _, before = request("/api/status")
            await asyncio.sleep(2)
            _, after = request("/api/status")
            assert before["plan_count"] == after["plan_count"]
            assert before["browser"]["probe_inputs"] == after["browser"]["probe_inputs"]
            assert after["observation_count"] > before["observation_count"]
            assert after["live"]["sequence"] > before["live"]["sequence"]
            checks["paused_observer_and_live_continue"] = True
            checks["dashboard_pause"] = True
            for _ in range(40):
                if await page.locator("#game-image").evaluate("img => img.complete && img.naturalWidth > 0"):
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError("觀戰影像沒有顯示：" + await page.locator("#frame-status").inner_text())
            game = next(p for p in context.pages if p.url == "https://kiomet.com/")
            await game.evaluate("() => { window.__kiometTestFrames={count:0,run:true}; function tick(){if(window.__kiometTestFrames.run){window.__kiometTestFrames.count++;requestAnimationFrame(tick)}}requestAnimationFrame(tick) }")
            low_start = await game.evaluate("window.__kiometTestFrames.count")
            await asyncio.sleep(3)
            low_end = await game.evaluate("window.__kiometTestFrames.count")
            await page.get_by_role("button", name="開啟高頻觀戰").click()
            await asyncio.sleep(1)
            _, high_before = request("/api/status")
            frame_before = await game.evaluate("window.__kiometTestFrames.count")
            await asyncio.sleep(5)
            _, high_after = request("/api/status")
            frame_after = await game.evaluate("window.__kiometTestFrames.count")
            assert high_after["live"]["sequence"]-high_before["live"]["sequence"] >= 15, (high_before["live"], high_after["live"])
            assert frame_after-frame_before > 20
            checks["high_frequency_fps"] = (high_after["live"]["sequence"]-high_before["live"]["sequence"])/5
            checks["game_raf_low_fps"] = (low_end-low_start)/3
            checks["game_raf_high_fps"] = (frame_after-frame_before)/5
            checks["high_view_keeps_game_frames_progressing"] = True
            await page.get_by_role("button", name="關閉高頻觀戰").click()
            await asyncio.sleep(1)
            _, low_again = request("/api/status")
            assert low_again["live"]["target_fps"] == 1
            await game.evaluate("window.__kiometTestFrames.run = false")
            checks["high_frequency_toggle"] = True
            await page.screenshot(path=str(ROOT/"runtime/screenshots/dashboard-desktop.png"), full_page=True)
            await page.set_viewport_size({"width":390,"height":844})
            await page.screenshot(path=str(ROOT/"runtime/screenshots/dashboard-mobile.png"), full_page=True)
            assert not console_errors, console_errors
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            checks["dashboard_render"] = True
            await page.get_by_role("button", name="繼續 AI").first.click()
            await expect_state(page, "RUNNING（執行中）")
            await asyncio.sleep(2)
            _, resumed = request("/api/status")
            assert resumed["plan_count"] > after["plan_count"]
            assert resumed["browser"]["probe_inputs"] > after["browser"]["probe_inputs"]
            checks["dashboard_resume"] = True
            assert request("/api/stop", "POST", token)[1]["state"] == "STOPPED"
            checks["authenticated_stop"] = True
        code = await asyncio.to_thread(process.wait, timeout=20)
        assert code == 0, code
        final = json.loads((ROOT/"runtime/state/final-status.json").read_text(encoding="utf-8"))
        assert final["state"] == "STOPPED" and not final["errors"]
        assert final["browser"]["focus_violations"] == 0
        checks["focus_guard"] = True
        checks["clean_shutdown"] = True
        (ROOT/"runtime/state/smoke-report.json").write_text(json.dumps({"checks":checks,"final":final},ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(checks, ensure_ascii=False))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)

asyncio.run(main())
