"""Kiomet AI Control Center（控制中心）v0.1。

唯讀狀態客戶端（read-only status client），跑在使用者的正常 Windows 桌面。
只做兩件事：看平台狀態、幫忙打開既有監控頁。

刻意不做的事（硬限制）：
- 不送出任何控制命令（沒有 pause／resume／stop 按鈕，不讀取控制憑證）。
- 不操作 Kiomet 遊戲、不操作隔離 Chromium（瀏覽器）。
- 不移動滑鼠、不發送鍵盤、不搶焦點、不呼叫 SwitchDesktop（切換桌面函式）。
- 不修改世界狀態、規劃器（規劃器）、行動閘門（行動閘門）。
- 只用 GET /api/status（狀態端點）讀取，不發明另一套狀態。

技術選擇：只用 Python（程式語言）標準庫 Tkinter（內建桌面介面），
無新增依賴，低資源，每 3 秒輪詢一次。
"""

import json
import os
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT
FALLBACK_URL = "http://127.0.0.1:8765/"
POLL_SECONDS = 3
LIVE_FRESH_SECONDS = 10


def load_dashboard_url():
    """從執行狀態（control.json）或設定（default.json）找出真實監控頁位址，不用猜的。"""
    control_file = ROOT / "runtime" / "state" / "control.json"
    try:
        url = json.loads(control_file.read_text(encoding="utf-8")).get("url")
        if url and url.startswith("http"):
            return url.rstrip("/") + "/"
    except (OSError, ValueError):
        pass
    config_file = ROOT / "config" / "default.json"
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
        return f"http://{config.get('host', '127.0.0.1')}:{config.get('port', 8765)}/"
    except (OSError, ValueError):
        pass
    return FALLBACK_URL


def fetch_status(dashboard_url, timeout=5):
    """唯讀抓取平台狀態。失敗時回傳 None，由呼叫方顯示 OFFLINE，不拋出崩潰。"""
    try:
        request = urllib.request.Request(dashboard_url.rstrip("/") + "/api/status")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            return json.load(response)
    except Exception:
        return None


def format_runtime(uptime_seconds):
    try:
        total = int(uptime_seconds)
    except (TypeError, ValueError):
        return "--:--:--"
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def summarize(status):
    """把原始狀態 JSON（資料格式）濃縮成顯示用摘要。缺欄位時一律降級為 UNKNOWN，不崩潰。"""
    if not isinstance(status, dict):
        return {
            "platform": "UNKNOWN", "dashboard": "OFFLINE",
            "live": "OFFLINE", "runtime": "--:--:--",
            "errors": "-", "live_age": None, "live_seq": 0,
            "kiomet": "UNKNOWN", "audio": "UNKNOWN", "mode": "UNKNOWN",
        }
    live = status.get("live") or {}
    captured = live.get("captured_at")
    age = time.time() - captured if isinstance(captured, (int, float)) else None
    live_online = isinstance(live.get("sequence"), int) and live.get("sequence", 0) > 0
    if live_online and age is not None and age <= LIVE_FRESH_SECONDS:
        live_state = "ACTIVE"
    elif live_online:
        live_state = "STALE"
    else:
        live_state = "OFFLINE"
    errors = status.get("errors")
    game = status.get("game") or {}
    audio = status.get("audio") or {}
    return {
        "platform": status.get("state", "UNKNOWN"),
        "dashboard": "ONLINE",
        "mode": str(status.get("mode", "UNKNOWN")).upper(),
        "kiomet": game.get("state", "UNKNOWN"),
        "audio": audio.get("state", "UNKNOWN"),
        "live": live_state,
        "runtime": format_runtime(status.get("uptime_seconds")),
        "errors": len(errors) if isinstance(errors, list) else "-",
        "live_age": age,
        "live_seq": live.get("sequence", 0),
    }


def _color(name):
    table = {"RUNNING": "#2da544", "PAUSED": "#b8860b", "STOPPED": "#808080",
             "ERROR": "#d43d2a", "UNKNOWN": "#808080", "OFFLINE": "#808080",
             "ONLINE": "#2da544", "ACTIVE": "#2da544", "STALE": "#b8860b",
             "MENU": "#b8860b", "JOINING": "#b8860b", "IN_MATCH": "#2da544",
             "RESULT_SCREEN": "#7a4fd0",
             "DISCONNECTED": "#d43d2a", "NO_BROWSER": "#808080",
             "MUTED": "#2da544", "ON": "#b8860b", "VIOLATION": "#d43d2a",
             "LIVE": "#2da544", "MOCK": "#b8860b"}
    return table.get(name, "#808080")


class ControlCenter:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import messagebox
        self.tk = tk
        self.messagebox = messagebox
        self.root = root
        self.dashboard_url = load_dashboard_url()
        self.live_url = self.dashboard_url.rstrip("/") + "/#live-view"
        self.supervisor = None
        try:
            sys.path.insert(0, str(PROJECT_DIR / "src"))
            from kiomet_ai.supervisor import Supervisor
            self.supervisor = Supervisor(PROJECT_DIR)
        except Exception:
            self.supervisor = None
        self.busy = False
        root.title("Kiomet AI Control Center（控制中心）")
        root.resizable(False, False)
        root.attributes("-topmost", False)

        self.rows = {}
        frame = tk.Frame(root, padx=18, pady=14)
        frame.pack()
        tk.Label(frame, text="Kiomet AI", font=("Microsoft JhengHei", 16, "bold")).pack(anchor="w")
        tk.Label(frame, text="監督器 · 可啟停修復（操作平台，不操作遊戲）",
                 font=("Microsoft JhengHei", 9),
                 fg="#666666").pack(anchor="w", pady=(0, 8))

        for key, label in [("platform", "Platform（平台）"), ("dashboard", "Dashboard（監控頁）"),
                           ("mode", "Mode（模式）"),
                           ("kiomet", "Kiomet（對局）"), ("audio", "Game Audio（遊戲音訊）"),
                           ("live", "LIVE VIEW（即時觀戰）"), ("runtime", "Runtime（運行時間）"),
                           ("browser", "Browser（瀏覽器）"),
                           ("controller", "Controller（控制器）"),
                           ("authorization", "Authorization（授權）"),
                           ("version", "Version（版本）"),
                           ("update", "Last update（最後更新）"), ("errors", "Errors（錯誤數）")]:
            row = tk.Frame(frame)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, width=22, anchor="w",
                     font=("Microsoft JhengHei", 10)).pack(side="left")
            value = tk.Label(row, text="…", anchor="w", font=("Microsoft JhengHei", 11, "bold"))
            value.pack(side="left")
            self.rows[key] = value

        self.live_detail = tk.Label(frame, text="", anchor="w",
                                    font=("Microsoft JhengHei", 9), fg="#666666")
        self.live_detail.pack(anchor="w")
        self.url_label = tk.Label(frame, text=self.dashboard_url, anchor="w",
                                  font=("Microsoft JhengHei", 8), fg="#666666")
        self.url_label.pack(anchor="w", pady=(6, 0))

        buttons = tk.Frame(frame, pady=10)
        buttons.pack()
        tk.Button(buttons, text="開啟監控", width=14,
                  command=self.open_dashboard).pack(side="left", padx=3)
        tk.Button(buttons, text="開啟即時觀戰", width=14,
                  command=self.open_live).pack(side="left", padx=3)
        tk.Button(buttons, text="重新整理狀態", width=14,
                  command=self.refresh_once).pack(side="left", padx=3)
        tk.Button(buttons, text="開啟專案資料夾", width=14,
                  command=self.open_project).pack(side="left", padx=3)

        row1 = tk.Frame(frame)
        row1.pack(pady=(2, 0))
        self.btn_start = tk.Button(row1, text="啟動 AI", width=14,
                                   command=self.on_start)
        self.btn_start.pack(side="left", padx=3)
        self.btn_stop = tk.Button(row1, text="停止 AI", width=14,
                                  command=self.on_stop)
        self.btn_stop.pack(side="left", padx=3)
        self.btn_restart = tk.Button(row1, text="重新啟動 AI", width=14,
                                     command=self.on_restart)
        self.btn_restart.pack(side="left", padx=3)

        row2 = tk.Frame(frame)
        row2.pack(pady=(4, 0))
        self.btn_pause = tk.Button(row2, text="暫停自主", width=14,
                                   command=self.on_pause_autonomy)
        self.btn_pause.pack(side="left", padx=3)
        self.btn_resume = tk.Button(row2, text="恢復自主", width=14,
                                    command=self.on_resume_autonomy)
        self.btn_resume.pack(side="left", padx=3)
        self.btn_repair = tk.Button(row2, text="修復遊戲頁", width=14,
                                    command=self.on_repair)
        self.btn_repair.pack(side="left", padx=3)

        self.status_line = tk.Label(frame, text="", anchor="w",
                                    font=("Microsoft JhengHei", 9), fg="#666666")
        self.status_line.pack(anchor="w", pady=(6, 0))

        self.refresh_once()

    def open_dashboard(self):
        webbrowser.open(self.dashboard_url)

    def open_live(self):
        webbrowser.open(self.live_url)

    def open_project(self):
        try:
            os.startfile(str(PROJECT_DIR))  # noqa: S606 -- 只開啟專案固定資料夾
        except OSError:
            pass

    def refresh_once(self):
        summary = summarize(fetch_status(self.dashboard_url))
        stated = datetime.now().strftime("%H:%M:%S")
        self._set("platform", "● " + summary["platform"], _color(summary["platform"]))
        self._set("dashboard", "● " + summary["dashboard"], _color(summary["dashboard"]))
        self._set("mode", "● " + summary["mode"], _color(summary["mode"]))
        self._set("kiomet", "● " + summary["kiomet"], _color(summary["kiomet"]))
        self._set("audio", "● " + summary["audio"], _color(summary["audio"]))
        self._set("live", "● " + summary["live"], _color(summary["live"]))
        self._set("runtime", summary["runtime"], "#000000")
        self._set("update", stated, "#000000")
        self._set("errors", str(summary["errors"]),
                  "#d43d2a" if summary["errors"] not in ("-", 0) else "#000000")
        if self.supervisor is not None:
            try:
                health = self.supervisor.health(self.dashboard_url)
            except Exception:
                health = {}
            self._set("browser", "● " + health.get("browser", "UNKNOWN"),
                      _color(health.get("browser", "UNKNOWN")))
            controller = str(health.get("controller", "UNKNOWN"))
            cycles = health.get("controller_cycles")
            if cycles is not None:
                controller += f" · {cycles} cycles"
            self._set("controller", "● " + controller, _color("RUNNING" if controller == "RUNNING" else "UNKNOWN"))
            self._set("authorization", "● " + str(health.get("authorization", "UNKNOWN")),
                      _color("UNKNOWN"))
            version = self._read_version()
            self._set("version", version, "#000000")
            self._update_buttons(summary, health)
        if summary["live_age"] is None:
            self.live_detail.config(text=f"seq {summary['live_seq']} · 尚無畫面時間")
        else:
            self.live_detail.config(
                text=f"seq {summary['live_seq']} · Last frame（最後畫面）：{summary['live_age']:.0f} 秒前")
        self.root.after(POLL_SECONDS * 1000, self.refresh_once)

    def _read_version(self):
        try:
            build = json.loads((PROJECT_DIR / "runtime/state/build.json").read_text(encoding="utf-8-sig"))
            return str(build.get("commit", "?"))
        except (OSError, ValueError):
            return "?"

    def _update_buttons(self, summary, health):
        offline = summary["dashboard"] == "OFFLINE"
        crashed = health.get("browser") in ("PAGE_CRASHED", "DISCONNECTED")
        state = "normal" if not self.busy else "disabled"
        self.btn_start.config(state="normal" if (offline and not self.busy) else "disabled")
        self.btn_stop.config(state="normal" if (not offline and not self.busy) else "disabled")
        self.btn_restart.config(state=state)
        self.btn_pause.config(state=state)
        self.btn_resume.config(state=state)
        self.btn_repair.config(state="normal" if (crashed and not self.busy) else state)

    def _set(self, key, text, color):
        self.rows[key].config(text=text, fg=color)


    def _control_token(self):
        try:
            control = json.loads((PROJECT_DIR / "runtime/state/control.json").read_text(encoding="utf-8"))
            return control.get("token", "")
        except (OSError, ValueError):
            return ""

    def _run_async(self, label, func):
        """背景執行監督操作，避免凍結 UI。"""
        if self.busy:
            return
        if self.supervisor is None:
            self.status_line.config(text="監督器未載入")
            return
        self.busy = True
        self.status_line.config(text=label + "執行中…")
        import threading

        def work():
            try:
                result = func()
                text = label + "：" + str(result.get("result", result))
            except Exception as exc:
                text = label + "失敗：" + str(exc)[:100]
            self.root.after(0, lambda: self._done(text))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, text):
        self.busy = False
        self.status_line.config(text=text)
        self.refresh_once()

    def on_start(self):
        self._run_async("啟動 AI", lambda: self.supervisor.start(
            self.dashboard_url, authorize=True))

    def on_stop(self):
        self._run_async("停止 AI", lambda: self.supervisor.stop(
            self.dashboard_url, self._control_token()))

    def on_restart(self):
        if not self.messagebox.askyesno("重新啟動 AI", "確定重新啟動 AI？\n授權將延續（CONTROL_CENTER_RESTART）。"):
            return
        self._run_async("重新啟動 AI", lambda: self.supervisor.restart(
            self.dashboard_url, self._control_token(), authorize=True))

    def on_pause_autonomy(self):
        self._run_async("暫停自主", lambda: self.supervisor.pause_autonomy(
            self.dashboard_url, self._control_token()))

    def on_resume_autonomy(self):
        self._run_async("恢復自主", lambda: self.supervisor.resume_autonomy(
            self.dashboard_url, self._control_token()))

    def on_repair(self):
        self._run_async("修復遊戲頁", lambda: self.supervisor.repair(
            self.dashboard_url, self._control_token()))


def main():
    import tkinter as tk
    root = tk.Tk()
    ControlCenter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
