"""Runtime Supervisor（執行期監督器）：平台生命週期唯一權威。

Control Center 經此管理 Runtime，不經 Dashboard。
職責：啟動／停止／重啟／修復／健康分層／恢復階梯／單實例保護。
絕不 taskkill 無關進程；只處理確認屬於 Kiomet 且失能的進程。
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "runtime/state/supervisor.json"
RECOVERY_LIMIT_WINDOW_S = 600
RECOVERY_LIMIT_COUNT = 3


def _api_status(url: str, timeout=5) -> dict | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/status", timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.load(resp)
    except Exception:
        return None


def _api_command(url: str, token: str, command: str, payload: dict | None = None,
                 timeout=15) -> dict | None:
    try:
        data = json.dumps(payload or {}).encode() if payload is not None or command == "execute-move" else None
        req = urllib.request.Request(
            url.rstrip("/") + "/api/" + command, data=data,
            headers={"X-Control-Token": token,
                     "Content-Type": "application/json"} if data else {"X-Control-Token": token},
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception:
        return None


class Supervisor:
    """本機進程管理器。state 持久化於 supervisor.json。"""

    def __init__(self, root: Path | None = None):
        self.root = root or ROOT
        self.state_path = self.root / "runtime/state/supervisor.json"
        self.recovery_attempts: list = []

    # ---- 狀態存取 ----
    def load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_state(self, patch: dict) -> dict:
        state = self.load_state()
        state.update(patch)
        state["updated_at"] = time.time()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        return state

    # ---- 進程識別（只認 Kiomet） ----
    @staticmethod
    def kiomet_pids() -> list:
        """回傳命令列含 kiomet_ai.app 的 python PID。"""
        try:
            import psutil
        except ImportError:
            return []
        found = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if "kiomet_ai.app" in cmdline:
                found.append(proc.info["pid"])
        return found

    def dashboard_status(self, url: str) -> dict | None:
        return _api_status(url)

    # ---- 健康分層（§29） ----
    def health(self, url: str) -> dict:
        """Backend／Dashboard／Browser／Page／Game／Observer／Planner／
        Executor／Verifier／Controller／Authorization 分層。"""
        status = self.dashboard_status(url) or {}
        game = status.get("game") or {}
        browser = status.get("browser") or {}
        live = status.get("live") or {}
        controller = status.get("controller") or {}
        auth = status.get("live_authorization") or {}
        gameplay = status.get("live_gameplay") or {}
        backend = "RUNNING" if status else "STOPPED"
        if status.get("state") == "ERROR":
            backend = "ERROR"
        browser_health = "HEALTHY" if browser.get("connected") else "DISCONNECTED"
        if live.get("error") and "Target crashed" in str(live.get("error")):
            browser_health = "PAGE_CRASHED"
        report = {
            "backend": backend,
            "dashboard": "ONLINE" if status else "OFFLINE",
            "browser": browser_health,
            "game_page": "CRASHED" if browser_health == "PAGE_CRASHED" else (
                "READY" if browser.get("connected") else "UNKNOWN"),
            "game_state": game.get("state", "UNKNOWN"),
            "observer": "STALE" if game.get("state") != "IN_MATCH" else "FRESH",
            "planner": ("CONNECTED" if controller.get("running") else "STALLED"),
            "executor": ("PAUSED" if gameplay.get("phase") == "PAUSED_FAILSAFE"
                         else ("READY" if auth.get("enabled") else "PAUSED")),
            "verifier": "READY",
            "controller": ("RUNNING" if controller.get("running") else "STOPPED"),
            "controller_cycles": controller.get("cycle_count"),
            "authorization": ("ENABLED" if auth.get("enabled") else "DISABLED"),
            "match_id": (game.get("match") or {}).get("id"),
        }
        return report

    # ---- 生命週期 ----
    def start(self, url="http://127.0.0.1:8765", authorize: bool = True,
              timeout=180) -> dict:
        """啟動 AI：健康實例則接管；否則清理殭屍＋標準啟動＋健康確認。"""
        existing = self.dashboard_status(url)
        if existing and existing.get("state") == "RUNNING":
            self.save_state({"url": url, "attached": True})
            return {"ok": True, "result": "ATTACHED",
                    "message": "已有健康實例，直接接管"}
        self.cleanup_zombies()
        if self._port_in_use(url):
            return {"ok": False, "result": "PORT_BUSY",
                    "message": "埠被非 Kiomet 程序佔用，不啟動"}
        args = ["-Live", "-Duration", "7200", "-ExitAfterStop"]
        if authorize:
            args.append("-LiveAuthorize")
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(self.root / "run.ps1")] + args,
            cwd=str(self.root))
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            time.sleep(5)
            last = self.dashboard_status(url)
            if last and last.get("state") == "RUNNING":
                self.save_state({"url": url, "pid": (last.get("process") or {}).get("pid"),
                                 "authorized": authorize,
                                 "provenance": ("CONTROL_CENTER_USER" if authorize else None)})
                return {"ok": True, "result": "STARTED", "pid": (last.get("process") or {}).get("pid")}
        try:
            proc.terminate()
        except Exception:
            pass
        return {"ok": False, "result": "START_TIMEOUT",
                "message": "啟動逾時", "last": last}

    def stop(self, url: str, token: str, timeout=60) -> dict:
        """正常關閉優先；逾時才限定 PID 強制結束。"""
        result = _api_command(url, token, "stop", timeout=15)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            if self.dashboard_status(url) is None:
                self.save_state({"url": url, "stopped": True})
                return {"ok": True, "result": "STOPPED"}
            status = self.dashboard_status(url) or {}
            if status.get("state") == "STOPPED":
                return {"ok": True, "result": "STOPPED"}
        for pid in self.kiomet_pids():
            try:
                import psutil
                psutil.Process(pid).terminate()
            except Exception:
                pass
        time.sleep(5)
        if self.dashboard_status(url) is None:
            return {"ok": True, "result": "STOPPED_FORCEFUL"}
        return {"ok": False, "result": "STOP_TIMEOUT"}

    def restart(self, url: str, token: str, authorize: bool = True) -> dict:
        """受控重啟：停→清→啟→健康確認。授權延續記 CONTROL_CENTER_RESTART。"""
        stop_result = self.stop(url, token)
        if not stop_result.get("ok"):
            return {"ok": False, "result": "RESTART_STOP_FAILED",
                    "detail": stop_result}
        self.cleanup_zombies()
        start_result = self.start(url, authorize=authorize)
        if authorize and start_result.get("ok"):
            self.save_state({"provenance": "CONTROL_CENTER_RESTART"})
        start_result["restart_from_stop"] = stop_result.get("result")
        return start_result

    def cleanup_zombies(self) -> list:
        """只清理已死亡或無回應的 Kiomet 進程（有 Dashboard 回應者不动）。"""
        removed = []
        try:
            import psutil
        except ImportError:
            return removed
        for pid in self.kiomet_pids():
            try:
                proc = psutil.Process(pid)
                if proc.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    proc.kill()
                    removed.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return removed

    @staticmethod
    def _port_in_use(url: str) -> bool:
        from urllib.parse import urlparse
        import socket
        try:
            parts = urlparse(url)
            port = parts.port or 80
            sock = socket.create_connection((parts.hostname or "127.0.0.1", port), timeout=2)
            sock.close()
            return True
        except OSError:
            return False

    # ---- 自主暫停／恢復（不關平台） ----
    def pause_autonomy(self, url: str, token: str) -> dict:
        result = _api_command(url, token, "pause-autonomy")
        return {"ok": bool(result and result.get("ok", True)), "detail": result}

    def resume_autonomy(self, url: str, token: str) -> dict:
        result = _api_command(url, token, "resume-autonomy")
        return {"ok": bool(result and result.get("ok", True)), "detail": result}

    # ---- 修復階梯（§25） ----
    def repair(self, url: str, token: str) -> dict:
        """LEVEL 1 Page → LEVEL 2 Chromium → LEVEL 3 全平台重啟。
        10 分鐘內超過 3 次則停手要求人工。"""
        now = time.time()
        self.recovery_attempts = [t for t in self.recovery_attempts
                                  if now - t < RECOVERY_LIMIT_WINDOW_S]
        if len(self.recovery_attempts) >= RECOVERY_LIMIT_COUNT:
            return {"ok": False, "result": "RECOVERY_LIMIT",
                    "message": "10 分鐘內已達 3 次，要求人工處理"}
        self.recovery_attempts.append(now)
        health = self.health(url)
        if health["backend"] in ("STOPPED",) or health["dashboard"] == "OFFLINE":
            result = self.restart(url, token, authorize=True)
            result["level"] = "LEVEL_3_FULL_RESTART"
            return result
        page = _api_command(url, token, "recover-page", timeout=120)
        # dashboard 以 {"state": "RECOVERED"} 回報；舊檢查只認 "ok" 導致
        # LEVEL 1/2 成功永遠被忽略、一律誤升級到 LEVEL 3 全重啟。
        if page and (page.get("ok") or page.get("state") == "RECOVERED"):
            return {"ok": True, "result": "RECOVERED", "level": "LEVEL_1_PAGE"}
        chromium = _api_command(url, token, "recover-chromium", timeout=180)
        if chromium and (chromium.get("ok") or chromium.get("state") == "RECOVERED"):
            return {"ok": True, "result": "RECOVERED", "level": "LEVEL_2_CHROMIUM"}
        result = self.restart(url, token, authorize=True)
        result["level"] = "LEVEL_3_FULL_RESTART"
        return result
