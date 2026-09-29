import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from kiomet_ai import spectator_api
from kiomet_ai import health as health_mod
from kiomet_ai import dashboard_truth
from kiomet_ai import manual_api

class Dashboard:
    def __init__(self, app, host, port):
        if host != "127.0.0.1":
            raise ValueError("監控頁只允許綁定本機 127.0.0.1")
        self.app = app
        directory = Path(__file__).parent
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def handle(self):
                self.connection.settimeout(10)
                try:
                    super().handle()
                except (ConnectionResetError, ConnectionAbortedError, TimeoutError):
                    pass

            def log_message(self, *_):
                pass

            def reply(self, code, body, content_type="application/json; charset=utf-8"):
                if not isinstance(body, bytes):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def host_valid(self):
                return self.headers.get("Host") in (f"127.0.0.1:{outer.server.server_port}", f"localhost:{outer.server.server_port}")

            def do_GET(self):
                if not self.host_valid():
                    return self.reply(403, {"error": "不合法的主機來源"})
                path = urlparse(self.path).path
                if path == "/":
                    html = (directory / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                    return self.reply(200, html.encode("utf-8"), "text/html; charset=utf-8")
                if path == "/probe":
                    return self.reply(200, (directory / "probe.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/api/live.jpg":
                    image, _, _ = app.live.frame()
                    if image:
                        return self.reply(200, image, "image/jpeg")
                    return self.reply(503, {"error": "等候第一張遊戲畫面"})
                if path == "/api/status":
                    return self.reply(200, app.snapshot())
                if path == "/api/tactical":
                    return self.reply(200, app.tactical_view())
                if path == "/api/actions":
                    return self.reply(200, app.recent_live_actions())
                if path == "/api/spectator/status":
                    return self.reply(200, spectator_api.spectator_status(app))
                if path == "/api/health":
                    return self.reply(200, health_mod.health_from_snapshot(
                        app.snapshot(), time.time()))
                if path == "/api/truth":
                    return self.reply(200, dashboard_truth.truth_from_snapshot(
                        app.snapshot(), time.time()))
                if path == "/api/control/status":
                    get_kpi = getattr(app, "autonomy_kpi", None)
                    get_idle = getattr(app, "idle_diagnostics", None)
                    return self.reply(200, manual_api.control_status(
                        app,
                        kpi=get_kpi() if callable(get_kpi) else None,
                        idle=get_idle() if callable(get_idle) else None))
                if path == "/spectator.js":
                    return self.reply(200, (directory / "spectator.js").read_bytes(),
                                      "application/javascript; charset=utf-8")
                if path == "/manual_control.js":
                    return self.reply(200, (directory / "manual_control.js").read_bytes(),
                                      "application/javascript; charset=utf-8")
                return self.reply(404, {"error": "找不到頁面"})

            def do_POST(self):
                if not self.host_valid() or not hmac.compare_digest(self.headers.get("X-Control-Token", ""), app.token):
                    return self.reply(403, {"error": "控制憑證不正確"})
                origin = self.headers.get("Origin")
                if origin and origin not in (f"http://127.0.0.1:{outer.server.server_port}", f"http://localhost:{outer.server.server_port}"):
                    return self.reply(403, {"error": "拒絕跨站控制"})
                command = self.path.removeprefix("/api/")
                if self.path in spectator_api.POST_ROUTES:
                    try:
                        length = int(self.headers.get("Content-Length", 0) or 0)
                        payload = json.loads(self.rfile.read(length) or b"{}")
                    except (ValueError, OSError):
                        return self.reply(400, {"error": "請求內容非 JSON"})
                    spectator_command = command.removeprefix("spectator/")
                    return self.reply(200, spectator_api.spectator_command(
                        app, spectator_command, payload))
                if self.path in manual_api.POST_ROUTES:
                    try:
                        length = int(self.headers.get("Content-Length", 0) or 0)
                        payload = json.loads(self.rfile.read(length) or b"{}")
                    except (ValueError, OSError):
                        return self.reply(400, {"error": "請求內容非 JSON"})
                    control_command = command.removeprefix("control/")
                    return self.reply(200, manual_api.control_command(
                        app, control_command, payload))
                if self.path != f"/api/{command}" or command not in ("pause", "resume", "stop", "watch-high", "watch-low", "enter-match", "mute", "unmute", "probe-move", "execute-move", "pause-autonomy", "resume-autonomy", "recover-page", "recover-chromium"):
                    return self.reply(404, {"error": "未知命令"})
                if command == "execute-move":
                    try:
                        length = int(self.headers.get("Content-Length", 0) or 0)
                        payload = json.loads(self.rfile.read(length) or b"{}")
                    except (ValueError, OSError):
                        return self.reply(400, {"error": "請求內容非 JSON"})
                    future = asyncio.run_coroutine_threadsafe(app.execute_move(payload), app.loop)
                    try:
                        return self.reply(200, future.result(timeout=120))
                    except TimeoutError:
                        return self.reply(200, {"ok": False, "result": "ACCEPTED",
                                                "note": "執行已受理，結果稍後顯示於狀態"})
                    except Exception as exc:
                        return self.reply(503, {"error": str(exc)})
                future = asyncio.run_coroutine_threadsafe(app.command(command), app.loop)
                # 慢速管理命令（多分頁靜音、進入對局）給較長等待；探針需數分鐘，
                # 逾時只代表「已受理、結果稍後顯示」，不代表失敗。
                timeout = 120 if command in ("mute", "unmute", "enter-match") else 8
                try:
                    return self.reply(200, {"state": future.result(timeout=timeout)})
                except TimeoutError:
                    if command == "probe-move":
                        return self.reply(200, {"state": "ACCEPTED",
                                                "note": "探針執行中，結果稍後顯示於狀態"})
                    return self.reply(503, {"error": "平台回應逾時（命令可能仍在執行）"})
                except Exception as exc:
                    return self.reply(503, {"error": str(exc)})
        self.server = ThreadingHTTPServer((host, port), Handler)
        self.server.daemon_threads = True

    def start(self):
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, name="dashboard", daemon=True)
        self.thread.start()

    async def close(self):
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
