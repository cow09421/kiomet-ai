"""專用有畫面 Chromium；所有輸入僅經 Playwright 送到測試分頁。"""
import asyncio
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4
import psutil
from playwright.async_api import async_playwright
from kiomet_ai.windows_process import IsolatedProcess


def extract_visible_result_summary(text: str) -> dict | None:
    """從結果頁可見文字擷取明確標記的數值與階級；不猜排行榜身分。"""
    if not isinstance(text, str) or not text.strip():
        return None
    lines = [re.sub(r"\s+", " ", line).strip()
             for line in text[:8192].splitlines()]
    summary = {
        "captured_towers": None,
        "defeated_rulers": None,
        "duration_minutes": None,
        "high_score": None,
        "current_rank": None,
        "next_rank": None,
        "rank_progress_percent": None,
    }

    def labeled_number(labels):
        for index, line in enumerate(lines):
            for label in labels:
                match = re.search(re.escape(label), line, re.IGNORECASE)
                if not match:
                    continue
                tail = line[match.end():].strip(" \t:：")
                number = re.fullmatch(r"\d{1,7}", tail)
                if number:
                    return int(number.group())
                for following in lines[index + 1:index + 3]:
                    if not following:
                        continue
                    number = re.fullmatch(r"\d{1,7}", following)
                    return int(number.group()) if number else None
        return None

    def heading_value(labels):
        def known(value):
            value = value[:80].strip()
            return None if value.casefold() in {
                "unknown", "--", "—", "n/a", "無"} else value

        for index, line in enumerate(lines):
            for label in labels:
                match = re.match(re.escape(label) + r"\b\s*[:：]?\s*(.*)$",
                                 line, re.IGNORECASE)
                if not match:
                    continue
                tail = match.group(1).strip()
                if tail:
                    return known(tail)
                for following in lines[index + 1:index + 3]:
                    if not following:
                        continue
                    if re.fullmatch(r"\d+(?:\.\d+)?%?", following):
                        return None
                    return known(following)
        return None

    summary.update(
        captured_towers=labeled_number(("Conquered towers", "佔領的塔")),
        defeated_rulers=labeled_number(("Kings defeated", "Defeated kings", "擊敗的國王")),
        duration_minutes=labeled_number(("Playtime (minutes)", "遊戲時長（分鐘）")),
        high_score=labeled_number(("High score", "最高分")),
        current_rank=heading_value(("Current Rank", "目前階級", "目前軍階")),
        next_rank=heading_value(("Next Rank", "下一階級", "下一軍階")),
    )
    for line in lines:
        progress = re.search(
            r"(?:Progress\s+towards?|進度)[^\n]{0,100}?(\d{1,3})\s*%",
            line, re.IGNORECASE)
        if progress:
            summary["rank_progress_percent"] = int(progress.group(1))
            break
    return summary if any(value is not None for value in summary.values()) else None


def is_our_browser_cmdline(cmdline, profile) -> bool:
    """只有命令列明帶專用 profile 目錄的程序才算我們的瀏覽器。

    使用者自己的 Chrome（系統 User Data）永不相符——避免誤殺。
    無法驗證（空命令列）一律不算。
    """
    if not cmdline or not profile:
        return False
    text = " ".join(cmdline) if isinstance(cmdline, (list, tuple)) else str(cmdline)
    if not text:
        return False
    return str(profile).lower() in text.lower()


def find_orphan_browser_pids(profile, processes=None) -> list[int]:
    """找出殘留（孤兒）專用瀏覽器程序 PID。

    背景：app 被強制終止時其 Chromium 子程序不隨之死亡；下次 start()
    用同一 profile 目錄再啟一個實例 → 舊 singleton／同名隔離桌殘窗
    干擾新實例（match 開場即 Target crashed，事件 13/14）。
    processes 可注入 (pid, name, cmdline) 序列供測試。
    """
    if processes is None:
        try:
            processes = [
                (info.get("pid"), info.get("name") or "",
                 info.get("cmdline") or [])
                for info in psutil.process_iter(["pid", "name", "cmdline"])
            ]
        except Exception:
            return []
    pids = []
    for pid, name, cmdline in processes:
        if not str(name).lower().endswith(("chrome.exe", "chromium.exe")):
            continue
        if is_our_browser_cmdline(cmdline, profile):
            pids.append(pid)
    return pids


def reap_orphan_browser(profile) -> list[int]:
    """終止孤兒專用瀏覽器（只認 profile 目錄完全相符者）。"""
    pids = find_orphan_browser_pids(profile)
    if not pids:
        return []
    procs = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    if procs:
        try:
            _, alive = psutil.wait_procs(procs, timeout=5)
            for proc in alive:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    pass
        except Exception:
            pass
    return pids

# 音訊政策注入腳本（document_start）：出生即靜音＋resume 攔截＋媒體靜音。
# window.__kiometAudioOn 由平台經 CDP 讀寫（預設 false＝靜音）。
AUDIO_POLICY_JS = r"""(() => {
  if (window.__kiometAudioInstalled) return;
  window.__kiometAudioInstalled = true;
  window.__kiometAudioOn = false;
  window.__kiometAudioEvents = [];
  const note = (t) => {
    try {
      const log = window.__kiometAudioEvents;
      log.push([Date.now(), t]);
      if (log.length > 50) log.splice(0, log.length - 50);
    } catch (e) {}
  };
  const muteCtx = (ctx) => {
    try {
      if (!window.__kiometAudioOn && ctx && ctx.state === 'running') {
        ctx.suspend();
        note('auto-suspend');
      }
    } catch (e) {}
  };
  const wrapCtx = (ctx) => {
    try {
      if (ctx.__kiometWrapped) return ctx;
      ctx.__kiometWrapped = true;
      const origResume = ctx.resume.bind(ctx);
      ctx.resume = () => {
        if (!window.__kiometAudioOn) {
          note('resume-blocked');
          return Promise.resolve();
        }
        return origResume();
      };
    } catch (e) {}
    return ctx;
  };
  for (const name of ['AudioContext', 'webkitAudioContext']) {
    try {
      const Orig = window[name];
      if (!Orig || Orig.__kiometPatched) continue;
      const Patched = function(...args) {
        const ctx = new Orig(...args);
        note('created');
        wrapCtx(ctx);
        muteCtx(ctx);
        return ctx;
      };
      Patched.prototype = Orig.prototype;
      Object.defineProperty(Patched, 'name', {value: name});
      Patched.__kiometPatched = true;
      window[name] = Patched;
    } catch (e) {}
  }
  const muteMedia = (m) => {
    try {
      m.muted = true;
      if ('volume' in m) m.volume = 0;
    } catch (e) {}
  };
  const sweepMedia = (root) => {
    try {
      for (const m of root.querySelectorAll('audio,video')) muteMedia(m);
    } catch (e) {}
  };
  sweepMedia(document);
  const startObserver = () => {
    try {
      const target = document.documentElement || document;
      new MutationObserver((muts) => {
        for (const mu of muts) {
          for (const n of mu.addedNodes) {
            if (!n || !n.querySelectorAll) continue;
            if (/^(AUDIO|VIDEO)$/.test(n.tagName)) { muteMedia(n); note('media-created'); }
            sweepMedia(n);
          }
        }
      }).observe(target, {childList: true, subtree: true});
    } catch (e) {}
  };
  startObserver();
  try {
    new MutationObserver((muts, obs) => {
      if (document.documentElement) { obs.disconnect(); startObserver(); }
    }).observe(document, {childList: true});
  } catch (e) {}
  window.__kiometAudioAudit = () => {
    return {flag: !!window.__kiometAudioOn, events: window.__kiometAudioEvents.slice(-10)};
  };
})();"""


def classify_game_state(page_ok: bool, menu_visible: bool) -> str:
    """舊版單證據分類（保留相容）；新流程請用 classify_game。"""
    if not page_ok:
        return "DISCONNECTED"
    if menu_visible:
        return "MENU"
    return "IN_MATCH"


# 對局特徵文字（與主選單互斥的對局頁訊號；大小寫敏感，與客戶端語系一致）。
MATCH_MARKERS = ("佔領", "滿員", "@")

# 結算畫面特徵（優先於主選單判斷；結算 overlay 蓋在首頁 DOM 上）。
RESULT_MARKERS = ("Play Again", "Back to menu", "Session Statistics")
GAME_STATE_SENSE_TIMEOUT_S = 5.0


def classify_game(menu_visible: bool, text: str) -> tuple[str, list[str]]:
    """三態分類。回 (狀態, 證據清單)。

    RESULT_SCREEN：結算特徵文字存在（overlay 蓋在首頁上，优先判定）。
    MENU：Play 主選單可見且無結算特徵（決定性）。
    IN_MATCH：主選單消失 AND 對局特徵文字存在（兩項獨立證據）。
    UNKNOWN：主選單消失但無對局特徵（不亂判 IN_MATCH）。
    """
    markers = [m for m in RESULT_MARKERS if m in (text or "")]
    if markers:
        return "RESULT_SCREEN", ["result_markers:" + ",".join(markers)]
    if menu_visible:
        return "MENU", ["menu_visible"]
    markers = [m for m in MATCH_MARKERS if m in (text or "")]
    if markers:
        return "IN_MATCH", ["menu_absent", "match_markers:" + ",".join(markers)]
    return "UNKNOWN", ["menu_absent", "no_match_markers"]


def advance_match(prev: dict, sensed: str, now: float) -> dict:
    """純函式：對局身份狀態機。回傳更新後的 match 摘要。

    - 首次或 RESULT 後進入 IN_MATCH → 新 match（index+1）。
    - IN_MATCH → RESULT_SCREEN → 記錄 MATCH_END（保留 match 供查詢）。
    - 其餘保持。
    """
    match = dict(prev)
    if sensed == "IN_MATCH" and match.get("state") != "IN_MATCH":
        match["index"] = int(match.get("index") or 0) + 1
        match["id"] = f"m{match['index']}-{int(now)}"
        match["started_at"] = now
        match["ended_at"] = None
        match["state"] = "IN_MATCH"
    elif sensed == "RESULT_SCREEN" and match.get("state") == "IN_MATCH":
        match["ended_at"] = now
        match["state"] = "RESULT_SCREEN"
    elif sensed == "RESULT_SCREEN" and match.get("state") != "RESULT_SCREEN":
        match["state"] = "RESULT_SCREEN"
    return match

class BrowserHost:
    def __init__(self, root: Path, gate):
        self.root, self.gate = root, gate
        self.process = None
        self.playwright = self.browser = self.context = self.game_page = self.probe_page = None
        self.output = None
        self.desktop_handle = None
        self.desktop_name = "KiometAI_" + uuid4().hex
        self.session_id = uuid4().hex
        self.status = {"connected": False, "url": None, "mode": "headed-isolated-desktop", "real_game_input": False}
        from kiomet_ai import prefs as _prefs
        self.audio_want_muted = not _prefs.load().get("game_audio_enabled", False)
        self.audio = {"state": "UNKNOWN", "mode": "FALLBACK_MUTE"}
        self.game = {"state": "UNKNOWN", "evidence": "尚未感測", "evidences": [],
                     "source": "init", "updated_at": None,
                     "join_armed": False, "join_busy": False,
                     "join_clicks": 0,
                     "match": {"index": 0, "id": None, "state": None,
                               "started_at": None, "ended_at": None},
                     "result_summary": None,
                     "match_events": []}
        self._page_generation = 0
        self.move_probe = {"state": "IDLE", "running": False, "last": None}
        self.directed_moves = []
        self.guard_samples = self.focus_violations = 0
        self.owned_pids = set()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
        if self._user32:
            self._user32.GetForegroundWindow.restype = wintypes.HWND
            self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self._user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
            self._user32.CreateDesktopW.restype = wintypes.HANDLE
            self._user32.CloseDesktop.argtypes = [wintypes.HANDLE]
            self._user32.CloseDesktop.restype = wintypes.BOOL
            self._enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            self._user32.EnumDesktopWindows.argtypes = [wintypes.HANDLE, self._enum_callback, wintypes.LPARAM]
            self._user32.EnumWindows.argtypes = [self._enum_callback, wintypes.LPARAM]

    def desktop_sample(self):
        if not self._user32:
            return {"foreground_pid": None, "cursor": None}
        handle = self._user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        return {"foreground_pid": pid.value, "cursor": [point.x, point.y]}

    def _pids(self):
        if self.process:
            self.owned_pids = {self.process.pid}
            try:
                self.owned_pids.update(p.pid for p in psutil.Process(self.process.pid).children(recursive=True))
            except psutil.NoSuchProcess:
                pass
        return self.owned_pids

    def guard(self):
        sample = self.desktop_sample()
        owned = self._pids()
        current_windows, isolated_windows = [], []
        def collect(destination):
            @self._enum_callback
            def callback(handle, _):
                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value in owned:
                    destination.append(int(handle))
                return True
            return callback
        if self.desktop_handle:
            self._user32.EnumDesktopWindows(self.desktop_handle, collect(isolated_windows), 0)
            self._user32.EnumWindows(collect(current_windows), 0)
            self.status.update(isolated_window_count=len(isolated_windows), user_desktop_window_count=len(current_windows))
            if current_windows:
                raise RuntimeError("專用瀏覽器視窗出現在使用者桌面；封鎖操作")
        self.guard_samples += 1
        if sample["foreground_pid"] in owned:
            self.focus_violations += 1
            self.status.update(focus_violations=self.focus_violations, guard_samples=self.guard_samples, violation_sample=sample)
            raise RuntimeError("專用瀏覽器進入前景；安全停機。也可能是使用者手動點開視窗。")
        return sample

    @staticmethod
    def _chromium_launch_args(executable: Path, profile: Path, root: Path,
                              *, use_warp: bool = False) -> list[str]:
        args = [str(executable), f"--user-data-dir={profile}", "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
                "--no-startup-window", "--window-size=1280,900", "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
                "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--enable-logging", "--v=0",
                f"--log-file={root / 'runtime/logs/chromium-startup.log'}",
                "--disable-features=CalculateNativeWinOcclusion"]
        if use_warp:
            # Chromium ANGLE WARP is the Windows D3D11 software rasterizer.
            # Do not opt into SwiftShader's unsafe WebGL mode.
            args.extend(("--use-gl=angle", "--use-angle=warp"))
        return args

    @staticmethod
    def _gpu_failure_allows_warp_retry(error: Exception | str,
                                       log_text: str) -> bool:
        message = str(error)
        repeated_gpu_crashes = log_text.count("GPU process exited unexpectedly") >= 2
        fatal_gpu = "GPU process isn't usable" in log_text
        transport_failed = ("ECONNRESET" in message
                            or "exited before control port ready" in message
                            or "control port wait timed out" in message
                            or ("TargetClosedError" in message
                                and "browser has been closed" in message))
        return repeated_gpu_crashes and fatal_gpu and transport_failed

    @staticmethod
    def _startup_log_since(path: Path, byte_offset: int) -> str:
        try:
            contents = path.read_bytes()
        except OSError:
            return ""
        # Chromium may truncate --log-file on launch. If it did, inspect the
        # whole new log; otherwise only consider bytes written by this attempt.
        start = byte_offset if len(contents) > byte_offset else 0
        return contents[start:].decode("utf-8", errors="replace")[-65536:]

    async def _launch_chromium_and_connect(self, args: list[str], port_file: Path,
                                           old_stamp: int | None):
        self.process = IsolatedProcess(
            args, "winsta0\\" + self.desktop_name, self.root)
        started = time.monotonic()
        port = None
        while time.monotonic() - started < 30:
            self.guard()
            if self.process.poll() is not None:
                raise RuntimeError("專用 Chromium exited before control port ready")
            if port_file.exists() and port_file.stat().st_mtime_ns != old_stamp:
                try:
                    port = int(port_file.read_text().splitlines()[0])
                    break
                except (ValueError, IndexError, OSError):
                    pass
            await asyncio.sleep(0.1)
        if port is None:
            raise TimeoutError("專用 Chromium control port wait timed out")
        return await self.playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}", timeout=15000)

    async def _stop_failed_chromium_start(self, profile: Path) -> None:
        browser = self.browser
        self.browser = None
        self.context = self.game_page = self.probe_page = None
        if browser is not None:
            try:
                await asyncio.wait_for(browser.close(), timeout=3)
            except Exception:
                pass
        process = self.process
        self.process = None
        self.owned_pids.clear()
        if process is not None:
            pid = process.pid
            # Closing its kill-on-close job reaps only this dedicated browser tree.
            process.close()
            try:
                await asyncio.to_thread(psutil.Process(pid).wait, timeout=5)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired,
                    psutil.AccessDenied, OSError):
                pass
        reaped = reap_orphan_browser(profile)
        if reaped:
            print(f"[browser] reap failed-start procs: {reaped}", flush=True)

    async def start(self, url: str, probe_url: str):
        self._start_url = url
        self._start_probe_url = probe_url
        if os.name != "nt":
            raise RuntimeError("目前只驗收 Windows 的不啟用前景啟動方式")
        self.playwright = await async_playwright().start()
        executable = Path(self.playwright.chromium.executable_path)
        if not executable.exists():
            raise RuntimeError("找不到專案專用 Chromium，請先執行 tools/setup.ps1")
        profile = self.root / "runtime/browser-profile"
        port_file = profile / "DevToolsActivePort"
        old_stamp = port_file.stat().st_mtime_ns if port_file.exists() else None
        # 先清孤兒：上一個 app 被強殺時殘留的同 profile Chromium 會與
        # 新實例互搶 singleton／同名隔離桌（match 開場即崩，事件 13/14）。
        reaped = reap_orphan_browser(profile)
        if reaped:
            print(f"[browser] reap orphan browser procs: {reaped}", flush=True)
        args = self._chromium_launch_args(executable, profile, self.root)
        startup_log = self.root / "runtime/logs/chromium-startup.log"
        try:
            startup_log_offset = startup_log.stat().st_size
        except OSError:
            startup_log_offset = 0
        # 非輸入桌面是 Windows 工作階段內的暫時隔離物件，不切換使用者桌面。
        # 不呼叫 SwitchDesktop／SetThreadDesktop，也不注入任何實體輸入。
        self.desktop_handle = self._user32.CreateDesktopW(self.desktop_name, None, None, 0, 0x000F01FF, None)
        if not self.desktop_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        initial = self.desktop_sample()

        async def connect_and_create_page(launch_args, port_stamp):
            self.browser = await self._launch_chromium_and_connect(
                launch_args, port_file, port_stamp)
            self.context = self.browser.contexts[0]
            # Apply the audio policy before creating any new game document.
            await self.context.add_init_script(AUDIO_POLICY_JS)
            self.game_page = await self.create_background_page()

        try:
            await connect_and_create_page(args, old_stamp)
        except Exception as exc:
            startup_log_text = self._startup_log_since(
                startup_log, startup_log_offset)
            if not self._gpu_failure_allows_warp_retry(exc, startup_log_text):
                raise
            await self._stop_failed_chromium_start(profile)
            old_stamp = port_file.stat().st_mtime_ns if port_file.exists() else None
            self.status["startup_fallback"] = {
                "renderer": "D3D11_WARP",
                "reason": "repeated GPU-process fatal error with CDP disconnect",
                "first_error": str(exc),
            }
            warp_args = self._chromium_launch_args(
                executable, profile, self.root, use_warp=True)
            await connect_and_create_page(warp_args, old_stamp)
            self.status["startup_fallback"]["connected"] = True
        # 專用設定檔可能恢復上次未正常關閉的測試分頁。
        # 先保留新建的空白遊戲頁，再關閉該專用實例內的舊分頁。
        restored = [p for p in self.context.pages if p != self.game_page]
        for page in restored:
            await page.close(run_before_unload=False)
        self.status["restored_pages_closed"] = len(restored)
        self.game_page.set_default_timeout(5000)
        try:
            await self.game_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            self.status["navigation_error"] = None
        except Exception as exc:
            self.status["navigation_error"] = str(exc)
            raise RuntimeError(f"Kiomet 網頁載入失敗：{exc}") from exc
        self.guard()
        # 本機測試頁用於確認頁面輸入隔離；不對正式遊戲送出點擊或按鍵。
        self.probe_page = await self.create_background_page()
        await self.probe_page.goto(probe_url, wait_until="domcontentloaded")
        self.probe_page.set_default_timeout(3000)
        self.status.update(isolated_desktop=True, connected=True, url=self.game_page.url, title=await self.game_page.title(),
                           version=self.browser.version, desktop_name=self.desktop_name, startup_before=initial,
                           startup_after=self.guard(), probe_inputs=0)

    async def create_background_page(self):
        session = await self.browser.new_browser_cdp_session()
        existing = set(self.context.pages)
        await session.send("Target.createTarget", {"url": "about:blank", "newWindow": True,
                           "background": True, "windowState": "normal"})
        try:
            for _ in range(100):
                self.guard()
                pages = [p for p in self.context.pages if p not in existing]
                if pages:
                    return pages[0]
                await asyncio.sleep(0.05)
            raise TimeoutError("背景分頁建立逾時")
        finally:
            await session.detach()

    async def recover_page(self):
        """LEVEL 1：關閉崩潰頁＋建新頁＋重載 Kiomet＋重標記。

        成功後呼叫方必須重取錨點／相機（舊 refs 全 STALE）。
        """
        url = getattr(self, "_start_url", None)
        if not url:
            return {"ok": False, "result": "NO_START_URL",
                    "message": "無啟動網址紀錄"}
        join_pending = bool(self.game.get("join_armed")
                            or self.game.get("join_busy"))
        try:
            try:
                await self.game_page.close(run_before_unload=False)
            except Exception:
                pass
            self.game_page = await self.create_background_page()
            self.game_page.set_default_timeout(5000)
            await self.game_page.goto(url, wait_until="domcontentloaded",
                                      timeout=45000)
            await self._apply_live_token()
            self._page_generation = getattr(self, "_page_generation", 0) + 1
            self.game.update(
                state="UNKNOWN", join_armed=join_pending, join_busy=False,
                match={"index": 0, "id": None, "state": None,
                       "started_at": None, "ended_at": None})
            return {"ok": True, "result": "RECOVERED",
                    "message": "遊戲頁已重建；需重取錨點"}
        except Exception as exc:
            return {"ok": False, "result": "RECOVERY_FAILED",
                    "message": str(exc)[:200]}

    async def recover_chromium(self):
        """LEVEL 2：安全關閉瀏覽器＋完整重啟（同 start 參數）。"""
        url = getattr(self, "_start_url", None)
        probe_url = getattr(self, "_start_probe_url", None)
        if not url:
            return {"ok": False, "result": "NO_START_URL",
                    "message": "無啟動網址紀錄"}
        join_pending = bool(self.game.get("join_armed")
                            or self.game.get("join_busy"))
        try:
            await self.close()
        except Exception:
            pass
        try:
            await self.start(url, probe_url or "")
            await self._apply_live_token()
            self._page_generation = getattr(self, "_page_generation", 0) + 1
            self.game.update(state="UNKNOWN", join_armed=join_pending,
                             join_busy=False,
                             match={"index": 0, "id": None, "state": None,
                                    "started_at": None, "ended_at": None})
            return {"ok": True, "result": "RECOVERED",
                    "message": "瀏覽器已重啟；需重取錨點並重進對局"}
        except Exception as exc:
            return {"ok": False, "result": "RECOVERY_FAILED",
                    "message": str(exc)[:200]}

    async def _apply_live_token(self):
        token = getattr(self, "_live_token", None)
        page = getattr(self, "game_page", None)
        if not token or page is None:
            return False
        try:
            script = "window.__kiometLiveToken = " + json.dumps(token)
            await page.add_init_script(script)
            await page.evaluate(script)
            return await page.evaluate(
                "() => window.__kiometLiveToken ?? null") == token
        except Exception:
            return False

    async def _ensure_live_token(self):
        """讓真頁標記跨越重新載入，供唯讀工具安全配對目標分頁。"""
        token = getattr(self, "_live_token", None)
        page = getattr(self, "game_page", None)
        if not token or page is None:
            return False
        try:
            if await page.evaluate(
                    "() => window.__kiometLiveToken ?? null") == token:
                return True
        except Exception:
            return False
        return await self._apply_live_token()

    async def mark_live_page(self, token: str) -> bool:
        """在遊戲頁標記本進程存活 token，供研究工具識別真頁。

        多個 kiomet.com 分頁並存時（崩潰殘留），工具以 token 配對，
        不再取第一個命中（曾導致錨點讀到細胞渲染的 stale 頁）。
        """
        self._live_token = token
        return await self._apply_live_token()

    async def read_wasm_bytes(self, address: int, length: int, timeout=10):
        """停用遊戲記憶體讀取；正式觀察必須來自玩家可見 UI。"""
        del address, length, timeout
        raise RuntimeError(
            "停用遊戲記憶體讀取；請使用玩家可見 UI 觀察，未知狀態必須棄權")

    async def probe(self):
        if not self.probe_page or not self.browser.is_connected() or self.game_page.is_closed():
            raise RuntimeError("專用瀏覽器或遊戲分頁已關閉")
        self.status["owned_page_count"] = len(self.context.pages)
        before = self.guard()
        async def operation():
            # Playwright 頁面事件，不呼叫 OS 鍵鼠注入，也不 bring_to_front。
            await self.probe_page.mouse.click(60, 35)
            await self.probe_page.mouse.click(100, 85)
            await self.probe_page.keyboard.press("Control+A")
            await self.probe_page.keyboard.insert_text("隔離輸入測試")
            return True
        sent = await self.gate.dispatch(operation)
        probe = await self.probe_page.evaluate("() => ({...window.probeStats, text:document.querySelector('input').value, visibility:document.visibilityState})")
        after = self.guard()
        self.status.update(probe=probe, last_desktop_sample=after, guard_samples=self.guard_samples,
                           focus_violations=self.focus_violations)
        if sent:
            self.status["probe_inputs"] += 1
            if probe["text"] != "隔離輸入測試" or probe["clicks"] != self.status["probe_inputs"]:
                raise RuntimeError("瀏覽器隔離輸入未通過重新讀取驗證")
        self.status["last_input_cursor_unchanged"] = before["cursor"] == after["cursor"]
        self.status["last_input_foreground_unchanged"] = before["foreground_pid"] == after["foreground_pid"]
        # 游標不同可能來自使用者正常操作，不視為失控；只記錄當次觀測。
        return self.status

    async def sense_game_state(self):
        """唯讀感測對局狀態：只讀 DOM（文件結構），不點擊、不輸入、不導航，永不拋出。

        規則：新程序一律從 UNKNOWN 開始，只接受瀏覽器即時證據；
        IN_MATCH 需雙證據（主選單消失＋對局特徵）；來源固定標
        browser_live_detection，附更新時間供 STALE 判斷。
        """
        import time as _time
        page_generation = getattr(self, "_page_generation", 0)
        try:
            if not self.game_page or self.game_page.is_closed() \
                    or not self.browser.is_connected():
                self.game.update(state="DISCONNECTED", evidence="遊戲分頁已關閉或瀏覽器斷線",
                                 source="sense_error", updated_at=_time.time())
                return self.game
            self.guard()
            await self._ensure_live_token()
            probe = await asyncio.wait_for(self.game_page.evaluate("""() => ({
                play: !!document.querySelector('#play_button') &&
                      document.querySelector('#play_button').offsetParent !== null,
                friends: !!document.querySelector('#play_with_friends_button') &&
                      document.querySelector('#play_with_friends_button').offsetParent !== null,
                url: location.href, title: document.title,
                canvas: document.querySelectorAll('canvas').length,
                text_len: document.body ? document.body.innerText.length : 0,
                text_head: (document.body ? document.body.innerText.slice(0, 400) : ''),
                visible_text: (document.body ? document.body.innerText.slice(0, 8192) : '')
            })"""), timeout=GAME_STATE_SENSE_TIMEOUT_S)
            if page_generation != getattr(self, "_page_generation", 0):
                return self.game
            menu_visible = bool(probe.get("play") or probe.get("friends"))
            text_head = probe.get("text_head") or ""
            sensed, evidences = classify_game(menu_visible, text_head)
            result_summary = (
                extract_visible_result_summary(probe.get("visible_text"))
                if sensed == "RESULT_SCREEN" else None)
            if result_summary is not None:
                match = self.game.get("match") or {}
                result_summary.update(
                    match_id=match.get("id"),
                    captured_at=_time.time(),
                    source="VISIBLE_UI_DOM_TEXT")
            if self.game["state"] == "JOINING" and sensed in ("MENU", "UNKNOWN"):
                pass  # 過渡期：已點 Play 但頁面尚未轉換，保持 JOINING 等待驗證。
            else:
                # 對局身份推進：IN_MATCH 新局建號；IN_MATCH→RESULT 記 MATCH_END。
                # 其餘只記錄，不自動重進。
                before_match = dict(self.game["match"])
                self.game["match"] = advance_match(
                    self.game["match"], sensed, _time.time())
                if before_match.get("state") == "IN_MATCH" and sensed == "RESULT_SCREEN":
                    self.game["match_events"].append(
                        {"event": "MATCH_END", "match_id": before_match.get("id"),
                         "time": _time.time()})
                    self.game["match_events"] = self.game["match_events"][-10:]
                if self.game["match"].get("index") != before_match.get("index"):
                    self.game["match_events"].append(
                        {"event": "MATCH_START",
                         "match_id": self.game["match"].get("id"),
                         "time": _time.time()})
                    self.game["match_events"] = self.game["match_events"][-10:]
                self.game["state"] = sensed
            self.game.update(evidences=evidences, result_summary=result_summary,
                             source="browser_live_detection",
                             evidence=f"url={probe.get('url')} title={probe.get('title')} "
                             f"menu_visible={menu_visible} canvas={probe.get('canvas')} "
                             f"text_len={probe.get('text_len')}",
                             updated_at=_time.time())
        except Exception as exc:
            if page_generation != getattr(self, "_page_generation", 0):
                # A late failure from the replaced page must not overwrite the
                # fresh UNKNOWN state installed by recovery.
                return self.game
            import time as _time2
            self.game.update(state="DISCONNECTED", evidence=f"感測失敗：{exc}",
                             source="sense_error", updated_at=_time2.time())
        return self.game

    async def enter_match(self):
        """統一進入對局（ENTER_MATCH）：經行動閘門點 Play／Play Again。

        MENU → 點 Play；RESULT_SCREEN → 點 Play Again（同 #play_button）。
        IN_MATCH → no-op；JOINING → 等待不重複點；
        UNKNOWN → 拒絕盲點；DISCONNECTED → 回報。
        忙碌鎖只屬於單次交易（join_busy），不鎖整個程序生命週期：
        上一局結束（RESULT）後可再進下一局，但絕不自動重連。
        成功後只觀察，不做任何戰術輸入。
        回傳 {"ok", "code", "message", "evidence"}。
        """
        import time as _time
        page_generation = getattr(self, "_page_generation", 0)

        def recovered_result():
            self.game.update(join_armed=True,
                             evidence="頁面已復原；保留原進局要求並重新感測",
                             updated_at=_time.time())
            return {"ok": False, "code": "RETRY_AFTER_RECOVERY",
                    "message": "頁面已復原，等待主迴圈重新感測後重試",
                    "evidence": dict(self.game)}

        if self.game["join_busy"]:
            return {"ok": False, "code": "JOIN_IN_PROGRESS",
                    "message": "進入對局進行中，不重複點擊",
                    "evidence": dict(self.game)}
        await self.sense_game_state()
        if page_generation != getattr(self, "_page_generation", 0):
            return recovered_result()
        state = self.game["state"]
        if state == "IN_MATCH":
            self.game["join_armed"] = False
            return {"ok": True, "code": "ALREADY_IN_MATCH",
                    "message": "已在對局中，不操作", "evidence": dict(self.game)}
        if state == "JOINING":
            return {"ok": False, "code": "JOIN_IN_PROGRESS",
                    "message": "進入對局進行中，不重複點擊",
                    "evidence": dict(self.game)}
        if state == "UNKNOWN":
            return {"ok": False, "code": "REFUSED_UNKNOWN",
                    "message": "狀態未知，拒絕盲點擊", "evidence": dict(self.game)}
        if state == "DISCONNECTED":
            return {"ok": False, "code": "REFUSED_DISCONNECTED",
                    "message": "瀏覽器斷線，不可進局", "evidence": dict(self.game)}
        if state not in ("MENU", "RESULT_SCREEN"):
            return {"ok": False, "code": "REFUSED_STATE",
                    "message": f"目前狀態 {state} 不可進局",
                    "evidence": dict(self.game)}
        via = "Play Again" if state == "RESULT_SCREEN" else "Play"
        self.game["join_busy"] = True
        self.game["join_armed"] = False
        try:
            self.game.update(state="JOINING", evidence=f"已點{via}，等待進入對局",
                             updated_at=_time.time())
            self.guard()

            async def click_play():
                # Play 與 Play Again 共用 #play_button；頁面級點擊，不經實體滑鼠。
                await self.game_page.wait_for_selector("#play_button", state="visible",
                                                       timeout=15000)
                await self.game_page.click("#play_button", timeout=10000)
                return True
            sent = await self.gate.dispatch(click_play)
            if not sent:
                self.game.update(state=state, evidence="行動閘門拒絕點擊（已暫停／停止／錯誤）",
                                 updated_at=_time.time())
                return {"ok": False, "code": "GATE_REFUSED",
                        "message": "行動閘門拒絕點擊", "evidence": dict(self.game)}
            self.game["join_clicks"] += 1
            if page_generation != getattr(self, "_page_generation", 0):
                return recovered_result()
            self.guard()
            # 驗證：出現 IN_MATCH 才算進入，需獨立於「點過按鈕」的證據。
            for _ in range(30):
                await asyncio.sleep(2)
                await self.sense_game_state()
                if page_generation != getattr(self, "_page_generation", 0):
                    return recovered_result()
                if self.game["state"] == "IN_MATCH":
                    self.game["join_armed"] = False
                    self.game.update(evidence=f"經{via}進入對局；轉為只觀察",
                                     updated_at=_time.time())
                    return {"ok": True, "code": "ENTERED",
                            "message": f"經{via}已進入對局，轉為只觀察",
                            "evidence": dict(self.game)}
            self.game.update(state="ERROR", evidence="60 秒後仍未進入對局，超時",
                             updated_at=_time.time())
            return {"ok": False, "code": "TIMEOUT",
                    "message": "進入對局超時", "evidence": dict(self.game)}
        except Exception as exc:
            self.game.update(state="ERROR", evidence=f"進入對局異常：{exc}",
                             updated_at=_time.time())
            return {"ok": False, "code": "EXCEPTION",
                    "message": str(exc), "evidence": dict(self.game)}
        finally:
            self.game["join_busy"] = False

    def management_ready(self) -> tuple[bool, str]:
        """管理控制（Management Control）就緒檢查：靜音／解除靜音／感測用。

        只拒絕：Chromium 不存在、未連接、Kiomet 頁面不存在、平台關閉中、
        控制目標失效。不看 ActionGate（行動閘門）：PAUSED 照樣可以靜音。
        """
        if self.gate.stop_event.is_set():
            return False, "平台正在關閉"
        if not self.browser or not self.browser.is_connected():
            return False, "專用瀏覽器未連接"
        if not self.game_page or self.game_page.is_closed():
            return False, "Kiomet 頁面不存在"
        return True, "就緒"

    def kiomet_pages(self):
        """隔離瀏覽器內所有 Kiomet 分頁（對局頁＋廣告彈出的重複分頁）。"""
        try:
            return [p for p in self.context.pages
                    if "kiomet.com" in (p.url or "")]
        except Exception:
            return []

    async def _audio_contexts(self, page, session=None):
        """經 CDP 列舉頁面內 AudioContext 實例（唯讀列舉，不改變狀態）。

        session 可由呼叫方傳入（同一 session 內列舉＋操作；CDP 物件 ID
        只在同一 session 有效，不可跨 session 混用）。
        """
        own = session is None
        if own:
            session = await page.context.new_cdp_session(page)
        try:
            found = []
            for ctor in ("AudioContext", "webkitAudioContext"):
                try:
                    proto = await session.send("Runtime.evaluate", {
                        "expression": f"typeof {ctor} !== 'undefined' ? {ctor}.prototype : null",
                        "returnByValue": False})
                    result = proto.get("result", {})
                    if result.get("subtype") == "null" or "objectId" not in result:
                        continue
                    objs = await session.send("Runtime.queryObjects", {
                        "prototypeObjectId": result["objectId"]})
                    arr = objs.get("objects", {})
                    if "objectId" not in arr:
                        continue
                    props = await session.send("Runtime.getProperties", {
                        "objectId": arr["objectId"], "ownProperties": True})
                    for prop in props.get("result", []):
                        value = prop.get("value") or {}
                        if value.get("objectId"):
                            found.append(value["objectId"])
                except Exception:
                    continue
            states = []
            for object_id in found:
                try:
                    called = await session.send("Runtime.callFunctionOn", {
                        "objectId": object_id,
                        "functionDeclaration": "function(){return {state:this.state,t:this.currentTime}}",
                        "returnByValue": True})
                    states.append(called.get("result", {}).get("value"))
                except Exception:
                    continue
            return found, states
        finally:
            if own:
                await session.detach()

    async def audio_state(self):
        """唯讀音訊狀態：MUTED（全部 suspended）／ON（任一 running）／UNKNOWN。

        掃描所有 Kiomet 分頁（廣告彈窗會開重複分頁各自放音），任一 running
        即視為 ON，避免「主頁靜了、彈窗還在響」的誤報。
        """
        import time as _time
        try:
            if not self.browser or not self.browser.is_connected():
                return {"state": "UNKNOWN", "mode": "FALLBACK_MUTE",
                        "contexts": 0, "pages": 0,
                        "evidence": "專用瀏覽器未連接", "updated_at": _time.time()}
            pages = self.kiomet_pages()
            if not pages:
                return {"state": "UNKNOWN", "mode": "FALLBACK_MUTE",
                        "contexts": 0, "pages": 0,
                        "evidence": "無 Kiomet 分頁", "updated_at": _time.time()}
            total = running = 0
            js_events = []
            for page in pages:
                try:
                    if page.is_closed():
                        continue
                    _, states = await self._audio_contexts(page)
                    total += len(states)
                    running += sum(1 for s in states if s and s.get("state") == "running")
                    try:
                        audit = await page.evaluate(
                            "() => (window.__kiometAudioAudit ? window.__kiometAudioAudit() : null)")
                        if audit and audit.get("events"):
                            js_events.extend(audit["events"][-4:])
                    except Exception:
                        pass
                except Exception:
                    continue
            desired = "MUTED" if self.audio_want_muted else "ON"
            if total == 0:
                return {"state": "UNKNOWN", "desired": desired, "actual": "UNKNOWN",
                        "mode": "POLICY_INJECT",
                        "contexts": 0, "pages": len(pages),
                        "evidence": "找不到 AudioContext", "updated_at": _time.time()}
            actual = "MUTED" if running == 0 else "ON"
            if desired == "MUTED" and running > 0:
                actual = "VIOLATION"
            return {"state": actual, "desired": desired, "actual": actual,
                    "mode": "POLICY_INJECT",
                    "contexts": total, "pages": len(pages),
                    "evidence": f"running={running}/{total} pages={len(pages)}",
                    "policy_events": js_events[-6:],
                    "updated_at": _time.time()}
        except Exception as exc:
            return {"state": "UNKNOWN",
                    "desired": "MUTED" if self.audio_want_muted else "ON",
                    "actual": "UNKNOWN", "mode": "POLICY_INJECT",
                    "contexts": 0, "pages": 0,
                    "evidence": f"探測失敗：{exc}", "updated_at": _time.time()}

    async def set_audio_muted(self, muted: bool):
        """多層靜音開關（管理控制，不經 ActionGate；PAUSED 照樣可用）。

        1. 同步各頁注入旗標（新 ctx 出生即靜音／resume 攔截）。
        2. 現存 AudioContext suspend／resume。
        只動隔離 Chromium，不碰系統音量。
        """
        import time as _time
        self.audio = getattr(self, "audio", {"state": "UNKNOWN", "mode": "POLICY_INJECT"})
        verb = "suspend" if muted else "resume"
        ready, reason = self.management_ready()
        if not ready:
            self.audio = await self.audio_state()
            return {"ok": False, "message": f"管理控制拒絕：{reason}",
                    "audio": dict(self.audio)}
        try:
            pages = self.kiomet_pages() or [self.game_page]
            ok = True
            flag = "false" if muted else "true"
            for page in pages:
                try:
                    if page is None or page.is_closed():
                        continue
                    try:
                        await page.evaluate(
                            f"() => {{ window.__kiometAudioOn = {flag}; }}")
                    except Exception:
                        ok = False
                    session = await page.context.new_cdp_session(page)
                    try:
                        found, _ = await self._audio_contexts(page, session)
                        if not found:
                            ok = False
                            continue
                        for object_id in found:
                            try:
                                await session.send("Runtime.callFunctionOn", {
                                    "objectId": object_id,
                                    "functionDeclaration": f"function(){{return this.{verb}()}}",
                                    "awaitPromise": True, "returnByValue": True})
                            except Exception:
                                ok = False
                    finally:
                        await session.detach()
                except Exception:
                    ok = False
        except Exception as exc:
            self.audio = await self.audio_state()
            return {"ok": False, "message": f"音訊控制異常：{exc}",
                    "audio": dict(self.audio)}
        self.audio = await self.audio_state()
        want = "MUTED" if muted else "ON"
        # suspend／resume 生效有非同步延遲：輪詢確認，不以第一次讀數判死刑。
        for _ in range(6):
            self.audio = await self.audio_state()
            if self.audio["state"] == want:
                break
            await asyncio.sleep(0.5)
        ok = ok and self.audio["state"] == want
        self.audio["updated_at"] = _time.time()
        return {"ok": ok, "message": f"音訊：{self.audio['state']}（期望 {want}）",
                "audio": dict(self.audio)}

    async def probe_move(self):
        """RealMoveProbe（真實調兵探針）：一次性受控拖曳測試。

        Phase 1（安全掃描）：網格起點，小幅拖曳後回到原點放開
          → 只產生選擇（select），不派兵；用路徑渲染的拉長變化找我方塔。
        Phase 2（驗證拖曳）：起點→終點完整拖曳，截圖比對判定
          SUCCESS／FAILED_CAMERA_PAN／FAILED_NO_FORCE_CREATED／UNKNOWN。
        全程經行動閘門；任一時刻 STOP／ERROR 即中止。PNG＋JSON 存
        runtime/probe/（只留最近 2 輪）。永不拋出。
        """
        from kiomet_ai import imgutil
        import time as _time
        if self.move_probe["running"]:
            return {"ok": False, "result": "ALREADY_RUNNING",
                    "message": "探針已在執行中"}
        self.move_probe["running"] = True
        outcome = {"ok": False, "result": "UNKNOWN", "message": "",
                   "evidence": {}, "shots": []}
        ws_log: list = []
        ws_session = None
        try:
            await self.sense_game_state()
            if self.game["state"] != "IN_MATCH":
                outcome.update(result="NOT_IN_MATCH",
                               message=f"非對局中（{self.game['state']}），拒絕探針")
                return outcome
            run_dir = self.root / "runtime" / "probe" / str(int(_time.time()))
            run_dir.mkdir(parents=True, exist_ok=True)
            self._prune_probe_runs(keep=2)
            # WebSocket 封包時序：放開瞬間有無對伺服器送訊，
            # 是「客戶端接受拖曳」獨立於像素的證據（viewport 更新平時極少）。
            try:
                ws_session = await self.game_page.context.new_cdp_session(self.game_page)
                await ws_session.send("Network.enable", {})

                def _ws(direction):
                    def handler(params):
                        payload = (params.get("response") or {}).get("payloadData", "")
                        ws_log.append((direction, _time.time(), len(payload)))
                    return handler

                ws_session.on("webSocketFrameSent", _ws("sent"))
                ws_session.on("webSocketFrameReceived", _ws("recv"))
            except Exception:
                ws_session = None

            async def shot(name):
                data = await self.game_page.screenshot(type="png", timeout=10000)
                (run_dir / f"{name}.png").write_bytes(data)
                outcome["shots"].append(name)
                width, height, rgb = imgutil.decode_png(data)
                return name, imgutil.luminance_grid(rgb, width, height, 160, 90), width, height

            async def alive():
                await self.sense_game_state()
                return self.game["state"] == "IN_MATCH"

            async def gated(fn):
                return await self.gate.dispatch(fn)

            # -- Phase 1：掃描起點 --
            _, grid0, W, H = await shot("sweep-base")
            spots = [(0.30, 0.35), (0.50, 0.35), (0.70, 0.35),
                     (0.30, 0.55), (0.50, 0.55), (0.70, 0.55),
                     (0.40, 0.75), (0.60, 0.75)]
            dirs = [(0.10, 0.0), (0.0, 0.10)]
            best = None  # (score, x, y)
            n = 0
            for fx, fy in spots:
                x, y = fx * W, fy * H
                for dxf, dyf in dirs:
                    n += 1
                    qx, qy = x + dxf * W, y + dyf * H

                    async def sweep():
                        await self.game_page.mouse.move(x, y)
                        await self.game_page.mouse.down()
                        for i in range(1, 6):
                            await self.game_page.mouse.move(
                                x + (qx - x) * i / 5, y + (qy - y) * i / 5)
                            await asyncio.sleep(0.03)
                        return True
                    if not await gated(sweep):
                        outcome.update(result="ABORTED_GATE",
                                       message="閘門關閉，中止掃描")
                        return outcome
                    _, grid_mid, _, _ = await shot(f"sweep-{n:02d}")
                    score = self._elongation(grid0, grid_mid, 160, 90, W, H,
                                             x, y, qx - x, qy - y)

                    async def clear():
                        await self.game_page.mouse.move(x, y)
                        await self.game_page.mouse.up()
                        await self.game_page.mouse.down(button="right")
                        await self.game_page.mouse.up(button="right")
                        return True
                    if not await gated(clear):
                        outcome.update(result="ABORTED_GATE",
                                       message="閘門關閉，中止掃描")
                        return outcome
                    if best is None or score > best[0]:
                        best = (score, x, y)
                    if not await alive():
                        outcome.update(result="MATCH_ENDED",
                                       message="對局在掃描中結束")
                        return outcome
            outcome["evidence"]["sweep_best"] = best
            # 取前三名起點逐一嘗試（活局中塔狀態會變，單一起點可能失效）。
            starts = []
            # 重建排序：掃描時只留了最佳；此處以最佳為主，容差內不再重掃。
            # （v0.2 簡化：先試最佳；若 hunt 全滅，回報並由操作員決定重掃。）
            if best is None or best[0] < 8.0:
                outcome.update(result="FAILED_NO_TOWER_FOUND", ok=False,
                               message=f"掃描無反應起點（最佳 {best}）")
                return outcome
            _, sx, sy = best

            async def clear_sel():
                async def op():
                    await self.game_page.mouse.down(button="right")
                    await self.game_page.mouse.up(button="right")
                    return True
                await gated(op)
            await clear_sel()

            # -- Phase 2：survey-then-nearest-release --
            # 先按住掃完 8 方向（全程不放開＝不送命令），收集所有路徑渲染點，
            # 再選離起點最近者（最可能是道路鄰居）移過去、按住、放開。
            # 起點經路徑渲染已證明是我方有單位塔（參考源 draw 早退規則）。
            import math as _math
            hits = []
            _, grid_base, _, _ = await shot("hunt-base")
            survey_ok = True
            for angle_i in range(8):
                ang = _math.pi * 2 * angle_i / 8
                ux, uy = _math.cos(ang), _math.sin(ang)

                async def press():
                    await self.game_page.mouse.move(sx, sy)
                    await self.game_page.mouse.down()
                    return True
                if not await gated(press):
                    outcome.update(result="ABORTED_GATE", message="閘門關閉")
                    return outcome
                async def safe_up():
                    async def op():
                        try:
                            await self.game_page.mouse.up()
                        except Exception:
                            pass
                        return True
                    try:
                        await gated(op)
                    except Exception:
                        pass
                try:
                    for hop in (70, 130, 190):
                        qx, qy = sx + ux * hop, sy + uy * hop

                        async def hop_move():
                            await self.game_page.mouse.move(qx, qy, steps=4)
                            await asyncio.sleep(0.4)
                            return True
                        if not await gated(hop_move):
                            await safe_up()
                            outcome.update(result="ABORTED_GATE", message="閘門關閉")
                            return outcome
                        _, grid_mid, _, _ = await shot(f"hunt-a{angle_i}h{hop}")
                        corr = imgutil.corridor_change(
                            grid_base, grid_mid, (sx, sy), (qx, qy), W, H)
                        inside, outside = corr["inside_frac"], corr["outside_frac"]
                        if inside >= 0.04 and inside > 1.5 * max(outside, 1e-6):
                            hits.append((hop, angle_i, qx, qy,
                                         round(inside, 4), round(outside, 4)))
                    async def back_release():
                        await self.game_page.mouse.move(sx, sy, steps=3)
                        await self.game_page.mouse.up()
                        return True
                    await gated(back_release)
                    await clear_sel()
                except Exception:
                    try:
                        async def emergency_up():
                            await self.game_page.mouse.up()
                            return True
                        await gated(emergency_up)
                    except Exception:
                        pass
                if not await alive():
                    outcome.update(result="MATCH_ENDED", message="對局在掃描中結束")
                    return outcome
            outcome["evidence"]["survey_hits"] = [
                {"hop": h, "angle": a, "x": round(x), "y": round(y),
                 "inside": i, "outside": o} for h, a, x, y, i, o in hits]
            if not hits:
                outcome.update(result="FAILED_NO_FORCE_CREATED", ok=False,
                               message="環掃無路徑渲染：起點可能已無可動單位")
                return outcome
            hits.sort(key=lambda h: h[0])
            hop, angle_i, qx, qy, inf, outf = hits[0]
            outcome["evidence"]["chosen"] = {
                "hop": hop, "angle": angle_i, "x": round(qx), "y": round(qy)}
            # 移到最近渲染點（按住），確認、按住 2.5 秒、質心吸附、放開。
            async def go():
                await self.game_page.mouse.move(sx, sy)
                await self.game_page.mouse.down()
                await self.game_page.mouse.move(qx, qy, steps=6)
                await asyncio.sleep(0.6)
                return True
            if not await gated(go):
                outcome.update(result="ABORTED_GATE", message="閘門關閉")
                return outcome
            try:
                _, grid_hold, _, _ = await shot("move-hold")
                corr2 = imgutil.corridor_change(
                    grid_base, grid_hold, (sx, sy), (qx, qy), W, H)
                if not (corr2["inside_frac"] >= 0.04 and corr2["inside_frac"] > 1.5 * max(corr2["outside_frac"], 1e-6)):
                    async def abort_up():
                        await self.game_page.mouse.move(sx, sy, steps=3)
                        await self.game_page.mouse.up()
                        return True
                    await gated(abort_up)
                    await clear_sel()
                    outcome.update(result="FAILED_NO_FORCE_CREATED", ok=False,
                                   message="最近點渲染未重現，放棄放開")
                    return outcome
                await asyncio.sleep(2.5)
                centroid = self._render_centroid(
                    grid_base, grid_hold, 160, 90, W, H)
                if centroid is not None:
                    qx, qy = centroid
                    async def snap_go():
                        await self.game_page.mouse.move(qx, qy, steps=3)
                        await asyncio.sleep(0.8)
                        return True
                    if not await gated(snap_go):
                        outcome.update(result="ABORTED_GATE", message="閘門關閉")
                        return outcome
                found_release = (qx, qy, angle_i, hop, inf, outf)
            except Exception:
                try:
                    async def emergency_up2():
                        await self.game_page.mouse.up()
                        return True
                    await gated(emergency_up2)
                except Exception:
                    pass
                outcome.update(result="ERROR", message="移動至釋放點異常")
                return outcome
            qx, qy, angle_i, hop, inf, outf = found_release
            # 吸附後先移到精確點（仍按住），確認渲染仍在，再放開。
            async def snap_move():
                await self.game_page.mouse.move(qx, qy, steps=3)
                await asyncio.sleep(1.0)
                return True
            if not await gated(snap_move):
                outcome.update(result="ABORTED_GATE", message="閘門關閉")
                return outcome
            _, grid_snap, _, _ = await shot("move-snap-verify")
            corr_snap = imgutil.corridor_change(
                grid_base, grid_snap, (sx, sy), (qx, qy), W, H)
            outcome["evidence"]["snap"] = {
                "inside": round(corr_snap["inside_frac"], 4),
                "outside": round(corr_snap["outside_frac"], 4)}
            # 放開（路徑已渲染處）→ 觀察。
            async def release():
                await self.game_page.mouse.up()
                return True
            if not await gated(release):
                outcome.update(result="ABORTED_GATE", message="閘門關閉，中止放開")
                return outcome
            t_release = _time.time()
            _, grid_before_rel, _, _ = await shot("move-final-before")
            await asyncio.sleep(1.5)
            _, grid_after1, _, _ = await shot("move-final-after1")
            await asyncio.sleep(1.5)
            _, grid_after2, _, _ = await shot("move-final-after2")
            await clear_sel()
            try:
                if ws_session is not None:
                    await ws_session.detach()
                    ws_session = None
            except Exception:
                pass
            pre = [e for e in ws_log if e[0] == "sent" and e[1] < t_release - 0.5]
            spike = [e for e in ws_log if e[0] == "sent" and t_release - 0.5 <= e[1] <= t_release + 3.0]
            outcome["evidence"]["ws"] = {
                "sent_before_release": len(pre),
                "sent_at_release_window": len(spike),
                "release_bytes": sum(e[2] for e in spike),
                "recv_total": sum(1 for e in ws_log if e[0] == "recv"),
            }
            verdict = self._classify_drag(grid_base, grid_after1, grid_after2,
                                          grid_after2, (sx, sy), (qx, qy), W, H)
            # 放開前已確認路徑渲染：把 mid 證據併入。
            verdict["path_rendered"] = {"angle": angle_i, "hop": hop,
                                        "inside": inf, "outside": outf}
            verdict["src"] = [round(sx), round(sy)]
            verdict["dst"] = [round(qx), round(qy)]
            outcome["evidence"]["final"] = verdict
            if verdict["result"] == "SUCCESS":
                outcome.update(ok=True, result="SUCCESS", message="路徑渲染後放開，部隊移動確認")
            else:
                outcome.update(result=verdict["result"],
                               message=f"有路徑渲染但放開後：{verdict['message']}")
            if not await alive():
                outcome["evidence"]["match_note"] = "探針後對局狀態變化"
            return outcome
        except Exception as exc:
            outcome.update(result="ERROR", message=f"探針異常：{exc}")
            return outcome
        finally:
            try:
                if ws_session is not None:
                    await ws_session.detach()
            except Exception:
                pass
            self.move_probe["running"] = False
            self.move_probe["last"] = {"result": outcome["result"],
                                       "message": outcome["message"],
                                       "time": _time.time(),
                                       "evidence": outcome["evidence"]}

    async def execute_directed_move(self, sx, sy, tx, ty, meta):
        """定向真實拖曳（需外部明確授權＋閘門 RUNNING）：一次 exactly-one drag。

        只用 Page 層 Playwright 滑鼠輸入。前截圖→移動→按下→分步拖曳→
        放開→結算截圖。全程受 gate.dispatch 門控；任一環節閘門關閉即中止。
        返回 outcome（含 sent 布林與證據路徑）。
        """
        from kiomet_ai import imgutil
        import time as _time
        outcome = {"ok": False, "result": "UNKNOWN", "message": "",
                   "sent": False, "evidence": {},
                   "proposal_id": (meta or {}).get("proposal_id"),
                   "match_id": (meta or {}).get("match_id")}
        try:
            await self.sense_game_state()
            if self.game["state"] != "IN_MATCH":
                outcome.update(result="NOT_IN_MATCH",
                               message="非對局中，不執行")
                return outcome
            for name, value in (("sx", sx), ("sy", sy), ("tx", ty), ("ty", ty)):
                if not isinstance(value, (int, float)) or not (0 <= value < 10000):
                    outcome.update(result="BAD_COORDS",
                                   message=f"座標非法：{name}={value}")
                    return outcome
            run_dir = self.root / "runtime" / "moves" / str(int(_time.time()))
            run_dir.mkdir(parents=True, exist_ok=True)
            outcome["evidence"]["run_dir"] = str(run_dir.relative_to(self.root))

            async def shot(name):
                data = await self.game_page.screenshot(type="png", timeout=10000)
                (run_dir / f"{name}.png").write_bytes(data)
                return name

            async def gated(fn):
                return await self.gate.dispatch_exec(fn)

            await shot("before")
            t_down = t_up = None

            async def press():
                await self.game_page.mouse.move(sx, sy)
                await self.game_page.mouse.down()
                return True
            if not await gated(press):
                outcome.update(result="ABORTED_GATE", message="按下前閘門關閉")
                return outcome
            t_down = _time.time()

            async def drag():
                steps = 10
                for i in range(1, steps + 1):
                    await self.game_page.mouse.move(
                        sx + (tx - sx) * i / steps, sy + (ty - sy) * i / steps)
                    await asyncio.sleep(0.03)
                return True
            if not await gated(drag):
                async def release():
                    await self.game_page.mouse.up()
                    return True
                await gated(release)
                outcome.update(result="ABORTED_GATE", message="拖曳中閘門關閉")
                return outcome

            async def release():
                await self.game_page.mouse.up()
                return True
            if not await gated(release):
                outcome.update(result="ABORTED_GATE", message="放開前閘門關閉")
                return outcome
            t_up = _time.time()
            outcome["sent"] = True
            await asyncio.sleep(1.0)
            await shot("after_settle")
            outcome["evidence"].update(
                {"source": [sx, sy], "target": [tx, ty],
                 "t_down": t_down, "t_up": t_up})
            outcome.update(ok=True, result="ACTION_SENT",
                           message="定向拖曳已送出；待驗證器確認遊戲狀態變化")
            self.directed_moves.append({
                "time": t_up, "match_id": outcome["match_id"],
                "proposal_id": outcome["proposal_id"],
                "origin": (meta or {}).get("origin", "UNKNOWN"),
                "source": [sx, sy], "target": [tx, ty],
                "result": outcome["result"]})
            return outcome
        except Exception as exc:
            outcome.update(result="ERROR", message=f"執行異常：{exc}")
            return outcome

    @staticmethod
    def _render_centroid(base, mid, cols, rows, W, H):
        """渲染質心：變化像素的最大連通簇中心（像素座標），無則 None。"""
        mask = [[abs(mid[y][x] - base[y][x]) > 40 for x in range(cols)]
                for y in range(rows)]
        seen = [[False] * cols for _ in range(rows)]
        best = (0, 0.0, 0.0)
        for y in range(rows):
            for x in range(cols):
                if mask[y][x] and not seen[y][x]:
                    stack, sx, sy, n = [(x, y)], 0.0, 0.0, 0
                    seen[y][x] = True
                    while stack:
                        cx, cy = stack.pop()
                        sx += cx
                        sy += cy
                        n += 1
                        for nx in (cx - 1, cx, cx + 1):
                            for ny in (cy - 1, cy, cy + 1):
                                if 0 <= nx < cols and 0 <= ny < rows \
                                        and mask[ny][nx] and not seen[ny][nx]:
                                    seen[ny][nx] = True
                                    stack.append((nx, ny))
                    if n >= 3 and n > best[0]:
                        best = (n, sx / n * W / cols, sy / n * H / rows)
        return (best[1], best[2]) if best[0] >= 5 else None

    @staticmethod
    def _elongation(before, mid, cols, rows, W, H, x, y, dx, dy):
        """路徑拉長分數：變化質心沿拖曳方向的投影（像素）。圓形選擇環≈0，路徑≫0。"""
        mag = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / mag, dy / mag
        proj_sum = hit = 0.0
        n = 0
        for gy in range(rows):
            for gx in range(cols):
                if abs(before[gy][gx] - mid[gy][gx]) < 30:
                    continue
                px = (gx + 0.5) * W / cols - x
                py = (gy + 0.5) * H / rows - y
                if px * px + py * py > 150 * 150:
                    continue
                proj_sum += px * ux + py * uy
                n += 1
        return proj_sum / max(1, n) if n > 3 else 0.0

    @staticmethod
    def _classify_drag(grid_before, grid_mid, grid_after1, grid_after2,
                       p0, p1, W, H):
        from kiomet_ai import imgutil
        dx, dy, zero_sad, best_sad = imgutil.estimate_shift(grid_before, grid_after2)
        pan = (dx != 0 or dy != 0) and best_sad < 0.6 * zero_sad \
            and (abs(dx) + abs(dy)) >= 2
        corr = imgutil.corridor_change(grid_before, grid_after2, p0, p1, W, H)
        localized = corr["inside_frac"] > 3 * corr["outside_frac"] \
            and corr["inside_frac"] > 0.02
        motion = imgutil.corridor_change(grid_after1, grid_after2, p0, p1, W, H)
        moving = motion["inside_frac"] > 0.005
        # 終點加權：部隊在目標端生成；取後 25% 路段＋80px 半徑的變化。
        mx, my = p0[0] * 0.25 + p1[0] * 0.75, p0[1] * 0.25 + p1[1] * 0.75
        dst = imgutil.corridor_change(grid_after1, grid_after2, (mx, my), p1,
                                      W, H, radius_px=80.0)
        dst_motion = dst["inside_frac"]
        dst_last = imgutil.corridor_change(grid_before, grid_after2, (mx, my), p1,
                                           W, H, radius_px=80.0)
        ev = {"shift": [dx, dy], "zero_sad": round(zero_sad, 2),
              "best_sad": round(best_sad, 2),
              "inside_frac": round(corr["inside_frac"], 4),
              "outside_frac": round(corr["outside_frac"], 4),
              "motion_frac": round(motion["inside_frac"], 4),
              "dst_motion": round(dst_motion, 4),
              "dst_change": round(dst_last["inside_frac"], 4)}
        if pan:
            return {"result": "FAILED_CAMERA_PAN",
                    "message": "整圖平移，未見局部派兵", "evidence": ev}
        if (localized and moving) or (dst_motion > 0.02 and not pan):
            return {"result": "SUCCESS",
                    "message": "走廊／終點變化＋放開後持續移動", "evidence": ev}
        if localized or dst_last["inside_frac"] > 0.05:
            return {"result": "UNKNOWN",
                    "message": "有局部變化但放開後無持續移動", "evidence": ev}
        return {"result": "FAILED_NO_FORCE_CREATED",
                "message": "無平移也無局部派兵跡象", "evidence": ev}

    def _prune_probe_runs(self, keep=2):
        try:
            base = self.root / "runtime" / "probe"
            runs = sorted([d for d in base.iterdir() if d.is_dir()])
            for old in runs[:-keep]:
                for child in sorted(old.iterdir()):
                    child.unlink()
                old.rmdir()
        except OSError:
            pass

    async def capture_frame(self):
        if not self.game_page or self.game_page.is_closed():
            raise RuntimeError("遊戲分頁已關閉，無法擷取觀戰畫面")
        self.guard()
        # screenshot 不帶檔案路徑：結果直接以位元組留在記憶體。
        image = await self.game_page.screenshot(type="jpeg", quality=72, timeout=5000)
        self.guard()
        return image

    async def capture_visible_canvas_png(self):
        """只截取遊戲分頁唯一可見 canvas，PNG 位元組只留在記憶體。"""
        if not self.game_page or self.game_page.is_closed():
            raise RuntimeError("遊戲分頁已關閉，無法擷取可見畫布")
        self.guard()
        canvases = self.game_page.locator("canvas")
        count = await canvases.count()
        if count != 1:
            raise RuntimeError(f"可見畫布數量未知：{count}")
        canvas = canvases.first
        if not await canvas.is_visible():
            raise RuntimeError("Kiomet 可見畫布目前不可見")
        image = await canvas.screenshot(type="png", timeout=5000)
        self.guard()
        return image

    async def close(self):
        self.status["connected"] = False
        if self.browser:
            try:
                session = await self.browser.new_browser_cdp_session()
                await asyncio.wait_for(session.send("Browser.close"), timeout=5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.browser.close(), timeout=5)
            except Exception:
                pass
        if self.playwright:
            try:
                await asyncio.wait_for(self.playwright.stop(), timeout=5)
            except Exception:
                pass
        if self.process:
            for _ in range(100):
                if self.process.poll() is not None:
                    break
                await asyncio.sleep(0.05)
        if self.process and self.process.poll() is None:
            parent = psutil.Process(self.process.pid)
            try:
                children = parent.children(recursive=True)
                parent.terminate()
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                await asyncio.to_thread(psutil.wait_procs, [parent, *children], timeout=5)
            except psutil.NoSuchProcess:
                pass
        if self.process:
            self.process.close()
        if self.output:
            self.output.close()
        if self.desktop_handle:
            self._user32.CloseDesktop(self.desktop_handle)
            self.desktop_handle = None
