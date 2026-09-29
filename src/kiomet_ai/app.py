import argparse
import asyncio
from collections import deque
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
import threading
import time
import traceback
import psutil
from kiomet_ai.actions import VerificationResult
from kiomet_ai.browser import BrowserHost
from kiomet_ai.control import ActionGate
from kiomet_ai.dashboard import Dashboard
from kiomet_ai.executor import MockExecutor
from kiomet_ai.logging import DecisionLogger
from kiomet_ai.live import LiveView
from kiomet_ai.observer import MockGame, MockObserver
from kiomet_ai.planner import MockPlanner
from kiomet_ai.verifier import MockVerifier
from kiomet_ai.world import WorldModel

ROOT = Path(__file__).resolve().parents[2]
JOIN_NON_ERROR_CODES = frozenset((
    "ALREADY_IN_MATCH", "JOIN_IN_PROGRESS", "RETRY_AFTER_RECOVERY"))

class Application:
    def __init__(self, root: Path, config: dict, no_browser=False,
                 no_capture=False):
        self.root, self.config = root, config
        self.gate = ActionGate()
        self.autonomy_paused = False
        self.live_mode = config.get("mode") == "live"
        if self.live_mode:
            # Live 模式不構造 Mock 遊玩棧（測試仍可用 mock 模式）。
            self.game = self.world = None
            self.observer = self.planner = None
            self.executor = self.verifier = None
            from kiomet_ai.live_controller import LiveController
            self.live_controller = LiveController(self)
        else:
            self.game, self.world = MockGame(), WorldModel()
            self.observer, self.planner = MockObserver(self.game), MockPlanner()
            self.executor, self.verifier = MockExecutor(self.game, self.gate), MockVerifier()
            self.live_controller = None
        self.logger = DecisionLogger(root / "runtime/logs/decisions.jsonl", config["log_max_bytes"], config["log_backups"])
        self.error_logger = DecisionLogger(root / "runtime/logs/errors.jsonl", config["log_max_bytes"], config["log_backups"])
        (root / "runtime/audio").mkdir(parents=True, exist_ok=True)
        self.audio_logger = DecisionLogger(root / "runtime/audio/audio_events.jsonl", 65536, 2)
        self.last_audio_actual = None
        self.browser = None if no_browser else BrowserHost(root, self.gate)
        self.no_capture = no_capture
        self.live = LiveView(root)
        self.user_paused = False
        self.token = secrets.token_urlsafe(32)
        try:
            self.build_commit = json.loads(
                (root / "runtime/state/build.json").read_text(encoding="utf-8-sig")).get("commit", "UNKNOWN")
        except (OSError, ValueError):
            self.build_commit = "UNKNOWN"
        self.started = time.monotonic()
        self.started_wall = time.time()
        self.errors = deque(maxlen=20)
        self.observation_times, self.plan_times = deque(maxlen=1000), deque(maxlen=1000)
        self.plan_count = self.verification_failures = 0
        self.memory_mb = 0.0
        self.lock = threading.Lock()
        self.cached = {}
        self.loop = None
        self.dashboard = None
        self.last_action = self.last_verification = None
        self.consecutive_errors = 0
        self.ended = None
        self.publish()

    def publish(self):
        now = time.monotonic()
        for queue in (self.observation_times, self.plan_times):
            while queue and queue[0] < now-10:
                queue.popleft()
        elapsed = max(1, min(10, now-self.started))
        browser_status = dict(self.browser.status) if self.browser else {"connected": False, "mode": "disabled"}
        game_status = dict(self.browser.game) if self.browser else {"state": "NO_BROWSER", "evidence": "未啟用瀏覽器"}
        audio_status = dict(getattr(self.browser, "audio", {"state": "UNKNOWN", "mode": "FALLBACK_MUTE"})) if self.browser else {"state": "UNKNOWN", "mode": "FALLBACK_MUTE"}
        state = {"schema_version": 1, "state": self.gate.state,
                 "mode": self.config.get("mode", "mock"),
                 "process": {"pid": os.getpid(), "ppid": os.getppid(),
                             "started_at": self.started_wall},
                 "uptime_seconds": (self.ended or now)-self.started,
                 "observation": (self.world.current.summary() if self.world and self.world.current else None),
                 "intent": self.last_action.reason if self.last_action else "等待啟動",
                 "last_action": asdict(self.last_action) if self.last_action else None,
                 "last_verification": asdict(self.last_verification) if self.last_verification else None,
                 "observation_count": (self.observer.count if self.observer else 0), "plan_count": self.plan_count,
                 "sent_actions": (self.executor.sent if self.executor else 0), "verification_failures": self.verification_failures,
                  "controller": (self.live_controller.heartbeat() if self.live_controller else {"running": False}),
                  "build": {"commit": getattr(self, "build_commit", "UNKNOWN"),
                            "pid": os.getpid(),
                            "started_at": self.started_wall},
                  "anchor_summary": self._read_anchor_summary(),
                 "observations_per_second": len(self.observation_times)/elapsed,
                 "plans_per_second": len(self.plan_times)/elapsed,
                  "memory_mb": self.memory_mb, "browser": browser_status, "live": self.live.stats(),
                  "game": game_status,
                  "audio": audio_status,
                  "real_action": dict(self.browser.move_probe["last"])
                  if self.browser and self.browser.move_probe["last"] else None,
                  "errors": list(self.errors), "recent_decisions": list(self.logger.recent),
                  "live_gameplay": self._read_live_journal(),
                  "live_sent_actions": len(getattr(self.browser, "directed_moves", []) or []),
                  "autonomous_sent_actions": sum(1 for m in (getattr(self.browser, "directed_moves", []) or []) if m.get("origin") == "LIVE_CONTROLLER"),
                  "manual_probe_sent_actions": sum(1 for m in (getattr(self.browser, "directed_moves", []) or []) if m.get("origin") != "LIVE_CONTROLLER"),
                  "live_controller": self._read_live_controller(),
                  "live_authorization": {"enabled": self.gate.authorized,
                      "provenance": self.gate.authorization_provenance,
                      "granted_at": self.gate.authorization_granted_at,
                      "mode": "LIVE_NEUTRAL_EXPANSION" if self.gate.authorized else None},}
        try:
            journal = (self.live_controller.journal
                       if self.live_controller else None)
            live_match = ((self.browser.game.get("match") or {})
                          if self.browser else {})
            if self.live_mode and journal is not None:
                current = journal.get("current_proposal") or {}
                if current.get("match_id") and current.get("match_id") != live_match.get("id"):
                    current = {}
                phase = journal.get("current_phase")
                last = journal.get("last_action") or {}
                state["next_action"] = {
                    "mode": ("LIVE / AUTONOMOUS" if self.gate.authorized
                             else "LIVE / DISABLED"),
                    "match_id": live_match.get("id"),
                    "phase": phase,
                    "source": current.get("source", last.get("source")),
                    "target": current.get("target", last.get("target")),
                    "rank": current.get("rank_score"),
                    "preflight": None,
                    "authorization": ("ENABLED" if self.gate.authorized
                                      else "DISABLED"),
                    "proposal_status": current.get("status"),
                }
            candidate_path = self.root / "runtime/state/first_move_candidate.json"
            if not self.live_mode and candidate_path.exists():
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                proposal = candidate.get("proposal") or {}
                cycle = candidate.get("cycle") or {}
                state["next_action"] = {
                    "mode": "DRY / LOCKED",
                    "match_id": candidate.get("match_id"),
                    "source": proposal.get("source_tower_id"),
                    "source_type": proposal.get("source_type"),
                    "target": proposal.get("target_tower_id"),
                    "target_type": proposal.get("target_type"),
                    "deployable": proposal.get("source_deployable_force"),
                    "rank": proposal.get("rank_score"),
                    "preflight": (cycle.get("preflight") or [None])[0],
                    "authorization": "WAITING FOR EXECUTE",
                    "proposal_status": proposal.get("status"),
                }
            elif not self.live_mode:
                state["next_action"] = {"mode": "NO_SAFE_PROPOSAL"}
        except Exception:
            state["next_action"] = {"mode": "UNKNOWN"}
        with self.lock:
            self.cached = json.loads(json.dumps(state, ensure_ascii=False))

    def tactical_view(self):
        """戰術全圖資料：錨點塔＋邊＋控制器高亮（唯讀文件）。"""
        try:
            anchor = json.loads((self.root / "runtime/research/source-map/verified-anchor-current.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            anchor = {}
        highlight = {}
        try:
            journal = (self.live_controller.journal
                       if self.live_controller else {})
            current = journal.get("current_proposal") or {}
            last = journal.get("last_action") or {}
            if current.get("source") is not None:
                highlight = {"source": current.get("source"),
                             "target": current.get("target"),
                             "match_id": current.get("match_id")}
            elif last.get("source") is not None:
                highlight = {"source": last.get("source"),
                             "target": last.get("target"),
                             "match_id": last.get("match_id")}
        except Exception:
            pass
        towers = [{"id": t.get("packed_id"), "x": (t.get("position") or [None, None])[0],
                   "y": (t.get("position") or [None, None])[1],
                   "owner": t.get("owner", "UNKNOWN"),
                   "tower_type": t.get("tower_type")} for t in anchor.get("towers", [])]
        return {"match_id": anchor.get("match_id"), "towers": towers,
                "edges": anchor.get("edges", []), "highlight": highlight}

    def recent_live_actions(self, limit: int = 20):
        """最近真實行動（日誌檔倒序，控制器與平台共寫）。"""
        path = self.root / "runtime/logs/live_actions.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            lines = []
        rows = []
        for line in lines[-limit:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        rows.reverse()
        return {"actions": rows, "count": len(rows)}

    def append_live_action(self, row: dict):
        """真實行動日誌附加（控制器每動作呼叫）。"""
        try:
            path = self.root / "runtime/logs/live_actions.jsonl"
            row = dict(row)
            row.setdefault("logged_at", time.time())
            with path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.cached, ensure_ascii=False))

    def _live_journal_path(self):
        return self.root / "runtime/state/live_gameplay.json"

    def _read_live_journal(self):
        try:
            return json.loads(self._live_journal_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"mode": "LIVE_NEUTRAL_EXPANSION", "match_id": None,
                    "sent_actions": 0, "verified_moves": 0,
                    "verified_expansions": 0, "failed_actions": 0,
                    "last_action": None, "last_verification": None,
                    "current_proposal": None, "current_phase": "OBSERVING"}

    def _read_anchor_summary(self):
        """錨點摘要（外部錨點工具寫入；對局不符即視為缺席）。"""
        try:
            data = json.loads((self.root / "runtime/research/source-map/verified-anchor-current.json").read_text(encoding="utf-8"))
            towers = data.get("towers") or []
            counts = {}
            for tower in towers:
                owner = tower.get("owner", "UNKNOWN")
                counts[owner] = counts.get(owner, 0) + 1
            return {"match_id": data.get("match_id"), "tower_count": len(towers),
                    "owners": counts,
                    "edges": data.get("undirected_edges")}
        except (OSError, ValueError):
            return {"match_id": None}

    def _read_live_controller(self):
        """控制器狀態（外部 LiveController 進程寫入；缺席即未知）。"""
        try:
            data = json.loads((self.root / "runtime/state/live_controller.json").read_text(encoding="utf-8"))
            return {"phase": data.get("phase"), "cycles": (data.get("journal") or {}).get("cycles"),
                    "sent_actions": (data.get("journal") or {}).get("sent_actions"),
                    "updated_at": data.get("updated_at")}
        except (OSError, ValueError):
            return {"phase": "UNKNOWN"}

    def record_verification(self, verdict: str, match_id=None):
        """控制器回寫驗證結果（平台日誌口徑：VERIFIED_MOVE／EXPANSION 計數）。"""
        journal = self._read_live_journal()
        journal["last_verification"] = verdict
        if verdict in ("TARGET_CAPTURED", "TARGET_CONTESTED",
                       "FORCE_OBSERVED", "SOURCE_CHANGED"):
            journal["verified_moves"] = journal.get("verified_moves", 0) + 1
            if verdict == "TARGET_CAPTURED":
                journal["verified_expansions"] = journal.get("verified_expansions", 0) + 1
        self._write_live_journal(journal)
        try:
            self.publish()
        except Exception:
            pass
        return journal

    def record_expansion(self, item: dict):
        """待確認佔領回寫平台日誌。"""
        journal = self._read_live_journal()
        journal["verified_expansions"] = journal.get("verified_expansions", 0) + 1
        journal["last_expansion"] = dict(item)
        self._write_live_journal(journal)
        try:
            self.publish()
        except Exception:
            pass
        return journal

    def _write_live_journal(self, journal):
        journal["updated_at"] = time.time()
        self._live_journal_path().write_text(
            json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")

    async def execute_move(self, payload):
        """定向真實調兵（需呼叫方持有明確使用者授權；本方法只管執行一次）。

        payload: {source:[x,y], target:[x,y], proposal_id, match_id}。
        單次語意：一次呼叫最多一次拖曳；記日誌；回 outcome。
        """
        journal = self._read_live_journal()
        if not self.gate.authorized:
            return {"ok": False, "result": "NOT_AUTHORIZED",
                    "message": "無執行授權，不執行"}
        if self.browser is None or self.gate.state != "RUNNING":
            return {"ok": False, "result": "GATE_CLOSED",
                    "message": "閘門未開，不執行"}
        try:
            sx, sy = payload["source"]
            tx, ty = payload["target"]
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "result": "BAD_PAYLOAD",
                    "message": "缺少 source/target 座標"}
        live_match = (self.browser.game.get("match") or {}).get("id")
        if payload.get("match_id") and payload["match_id"] != live_match:
            return {"ok": False, "result": "MATCH_MISMATCH",
                    "message": "提案對局與現行對局不符，拒絕"}
        outcome = await self.browser.execute_directed_move(
            sx, sy, tx, ty, {"proposal_id": payload.get("proposal_id"),
                             "match_id": live_match,
                             "origin": payload.get("origin", "API_MANUAL")})
        if outcome is None:
            return {"ok": False, "result": "GATE_CLOSED",
                    "message": "派送時閘門關閉或授權撤銷"}
        journal["match_id"] = live_match
        journal["current_phase"] = "VERIFYING"
        if outcome.get("sent"):
            journal["sent_actions"] = journal.get("sent_actions", 0) + 1
            journal["last_action"] = {
                "source": [sx, sy], "target": [tx, ty],
                "proposal_id": payload.get("proposal_id"),
                "match_id": live_match, "sent_at": time.time(),
                "result": outcome.get("result")}
        else:
            journal["failed_actions"] = journal.get("failed_actions", 0) + 1
        journal["current_proposal"] = payload.get("proposal_id")
        self._write_live_journal(journal)
        try:
            self.logger.write({"time": time.time(), "kind": "LiveMove",
                               "action": journal.get("last_action"),
                               "result": outcome.get("result")})
        except OSError:
            pass
        self.publish()
        return outcome

    def _restart_background_tasks(self):
        """復原後重啟已死亡的背景迴圈（擷取／控制器）。

        capture_loop 在連續失敗>=3 時會自行 command(error) 並退出；
        live_controller.run_loop 同樣可能因頁面崩潰退出。gate 離開
        ERROR 後這兩個 task 不會自己回來——必須在此重建，否則復原
        後平台看似 RUNNING 但擷取/觀察永久為零。
        """
        if (self.browser and not self.no_capture
                and (getattr(self, "_capture_task", None) is None
                     or self._capture_task.done())):
            self._capture_task = asyncio.create_task(self.capture_loop())
        if (self.live_controller is not None
                and (getattr(self, "_controller_task", None) is None
                     or self._controller_task.done())):
            self._controller_task = asyncio.create_task(
                self.live_controller.run_loop())

    async def command(self, command):
        if command in ("watch-high", "watch-low"):
            if self.gate.state in ("RUNNING", "PAUSED"):
                self.live.set_high(command == "watch-high")
            state = self.gate.state
        elif command == "enter-match":
            # 統一進入對局：MENU 點 Play，RESULT 點 Play Again；
            # 只佈署旗標，由主迴圈執行單次交易（可重進下一局，不自動重連）。
            if self.browser and self.gate.state == "RUNNING" \
                    and not self.browser.game["join_busy"]:
                self.browser.game["join_armed"] = True
            state = self.gate.state
        elif command in ("mute", "unmute"):
            # 管理控制：PAUSED 照樣可以靜音；絕不為靜音而 resume。
            # 偏好持久化：只有使用者明確按「開啟聲音」才記 true。
            if self.browser and self.gate.state in ("RUNNING", "PAUSED"):
                from kiomet_ai import prefs as _prefs
                enabled = (command == "unmute")
                self.browser.audio_want_muted = not enabled
                _prefs.save({"game_audio_enabled": enabled})
                result = await self.browser.set_audio_muted(command == "mute")
                if not result["ok"]:
                    self.record_error(RuntimeError(f"音訊控制失敗：{result['message']}"))
            state = self.gate.state
        elif command == "probe-move":
            # 受控單次派兵探針：只佈署旗標，由主迴圈執行；執行中拒絕重複請求。
            if self.browser and self.gate.state == "RUNNING" \
                    and not self.browser.move_probe["running"]:
                self.browser.move_probe["armed"] = True
            state = self.gate.state
        elif command == "pause-autonomy":
            self.autonomy_paused = True
            state = self.gate.state
        elif command == "resume-autonomy":
            self.autonomy_paused = False
            state = self.gate.state
        elif command == "recover-page":
            # 崩潰時 gate 會轉 ERROR（failures>=3）；復原命令必須能在
            # ERROR 下執行，否則復原梯在最需要時是空操作。
            if self.browser and self.gate.state in ("RUNNING", "ERROR"):
                was_error = self.gate.state == "ERROR"
                state = (await self.browser.recover_page()).get("result", "UNKNOWN")
                if state == "RECOVERED":
                    if was_error:
                        # 復原只回到 PAUSED：不自動恢復派送，需顯式 resume。
                        await self.gate.command("recovered")
                    self._restart_background_tasks()
            else:
                state = self.gate.state
        elif command == "recover-chromium":
            if self.browser and self.gate.state in ("RUNNING", "ERROR"):
                was_error = self.gate.state == "ERROR"
                state = (await self.browser.recover_chromium()).get("result", "UNKNOWN")
                if state == "RECOVERED":
                    if was_error:
                        await self.gate.command("recovered")
                    self._restart_background_tasks()
            else:
                state = self.gate.state
        else:
            if command == "pause":
                self.user_paused = True
            elif command == "resume":
                self.user_paused = False
            state = await self.gate.command(command)
        self.publish()
        return state

    def record_error(self, exc):
        error = {"time": time.time(), "message": str(exc), "type": type(exc).__name__}
        self.errors.append(error)
        try:
            error["diagnostic"] = self.live.save_diagnostic(exc)
        except OSError as diagnostic_error:
            error["diagnostic_error"] = str(diagnostic_error)
        self.error_logger.write(error)
        self.publish()

    async def cycle(self):
        start = time.perf_counter()
        self.game.advance()
        before = await self.observer.observe()
        self.observation_times.append(time.monotonic())
        self.world.update(before)
        action = self.planner.plan(before)
        self.plan_count += 1
        self.plan_times.append(time.monotonic())
        result = await self.executor.execute(action)
        after = await self.observer.observe()
        self.observation_times.append(time.monotonic())
        self.world.update(after)
        verification = self.verifier.verify(before, action, after) if result.accepted else VerificationResult("CANCELLED" if self.gate.state != "RUNNING" else "FAILED", result.message)
        self.last_action, self.last_verification = action, verification
        if verification.status == "FAILED":
            self.verification_failures += 1
        record = {"schema_version": 1, "time": time.time(), "observation": before.summary(),
                  "after_observation": after.summary(), "action": asdict(action),
                  "planner": "MockPlanner", "reason": action.reason, "execution": asdict(result),
                  "verification": asdict(verification), "latency_ms": (time.perf_counter()-start)*1000,
                  "error": None if verification.status == "SUCCESS" else verification.message}
        self.logger.write(record)
        if verification.status == "FAILED":
            raise RuntimeError(verification.message)
        self.publish()

    def sample_memory(self):
        parent = psutil.Process()
        total = 0
        for proc in [parent, *parent.children(recursive=True)]:
            try:
                total += proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self.memory_mb = total / 1024**2

    async def monitor(self):
        metrics = DecisionLogger(self.root / "runtime/logs/metrics.jsonl", self.config["log_max_bytes"], self.config["log_backups"])
        ticks = 0
        try:
            while not self.gate.stop_event.is_set():
                try:
                    if self.browser and self.browser.process:
                        self.browser.guard()
                        if self.browser.process.poll() is not None:
                            raise RuntimeError("專用瀏覽器程序已退出")
                        # 對局狀態唯讀感測（約每 5 秒一次），失敗只記 DISCONNECTED 不拋出。
                        ticks += 1
                        if ticks % 5 == 0:
                            await self.browser.sense_game_state()
                        # 音訊守衛（約每 4 秒）：先讀新鮮狀態（含期望／實際）；
                        # 偏好靜音時若實際違規，自動補靜音；違規轉換記事件（有界）。
                        # 涵蓋：啟動／換頁／進局／回選單／reload／重連／新分頁。
                        if ticks % 4 == 0:
                            try:
                                self.browser.audio = await self.browser.audio_state()
                                actual = self.browser.audio.get("actual")
                                if actual != self.last_audio_actual:
                                    self.audio_logger.write({
                                        "time": time.time(), "event": "AUDIO_STATE",
                                        "actual": actual,
                                        "evidence": self.browser.audio.get("evidence"),
                                        "game": self.browser.game.get("state")})
                                    self.last_audio_actual = actual
                                if self.browser.audio_want_muted and actual == "VIOLATION":
                                    await self.browser.set_audio_muted(True)
                                    self.audio_logger.write({
                                        "time": time.time(), "event": "AUDIO_POLICY_REAPPLIED",
                                        "game": self.browser.game.get("state")})
                            except Exception:
                                pass
                    self.sample_memory()
                    self.publish()
                    record = {"time": time.time(), "elapsed": time.monotonic()-self.started,
                              "memory_mb": self.memory_mb, "state": self.gate.state,
                              "plans": self.plan_count, "browser": self.browser.status if self.browser else None, "live": self.live.stats()}
                    metrics.write(record)
                except Exception as exc:
                    try:
                        self.record_error(exc)
                    finally:
                        await self.command("error")
                    break
                await asyncio.sleep(1)
        finally:
            metrics.close()

    async def observe_while_paused(self):
        self.game.advance()
        observation = await self.observer.observe()
        self.observation_times.append(time.monotonic())
        self.world.update(observation)
        if self.browser:
            # 同一輸入閘門會拒絕所有輸入，只更新本機頁面讀取與背景渲染量測。
            await self.browser.probe()
        self.publish()

    async def capture_loop(self):
        failures = 0
        while self.gate.state not in ("STOPPED", "ERROR"):
            started = time.perf_counter()
            try:
                image = await self.browser.capture_frame()
                self.live.put(image, (time.perf_counter()-started)*1000)
                failures = 0
            except Exception as exc:
                if self.gate.state == "STOPPED":
                    break
                failures += 1
                self.live.error = str(exc)
                if failures >= 3:
                    self.record_error(exc)
                    await self.command("error")
                    break
            self.publish()
            delay = max(0.01, 1/self.live.target_fps-(time.perf_counter()-started))
            try:
                await asyncio.wait_for(self.gate.stop_event.wait(), delay)
            except TimeoutError:
                pass

    async def run(self, duration=0, exit_after_stop=False):
        self.loop = asyncio.get_running_loop()
        tasks = []
        try:
            self.dashboard = Dashboard(self, self.config["host"], self.config["port"])
            self.dashboard.start()
            port = self.dashboard.server.server_port
            control = {"url": f"http://127.0.0.1:{port}", "token": self.token, "pid": os.getpid()}
            (self.root / "runtime/state/control.json").write_text(json.dumps(control), encoding="utf-8")
            print(f"監控頁：http://127.0.0.1:{port}；模式：{'真實觀察' if self.config.get('mode') == 'live' else '本機模擬'}", flush=True)
            tasks.append(asyncio.create_task(self.monitor()))
            if self.browser:
                startup = asyncio.create_task(self.browser.start(self.config["browser_url"], f"http://127.0.0.1:{port}/probe"))
                stopped = asyncio.create_task(self.gate.stop_event.wait())
                try:
                    done, _ = await asyncio.wait({startup, stopped}, return_when=asyncio.FIRST_COMPLETED)
                    if stopped in done:
                        startup.cancel()
                        await asyncio.gather(startup, return_exceptions=True)
                    else:
                        await startup
                finally:
                    stopped.cancel()
                    await asyncio.gather(stopped, return_exceptions=True)
                if self.gate.state not in ("STOPPED", "ERROR"):
                    try:
                        marked = await self.browser.mark_live_page(self.token)
                    except Exception:
                        marked = False
                    if not marked:
                        self.record_error(RuntimeError("存活標記寫入失敗"))
                if self.gate.state not in ("STOPPED", "ERROR") and not self.no_capture:
                    self._capture_task = asyncio.create_task(self.capture_loop())
                    tasks.append(self._capture_task)
            if self.live_controller is not None and self.gate.state not in ("STOPPED", "ERROR"):
                self._controller_task = asyncio.create_task(self.live_controller.run_loop())
                tasks.append(self._controller_task)
            if self.gate.state == "PAUSED" and not self.user_paused:
                await self.command("resume")
            if self.browser:
                # 背景長時間運行預設靜音；使用者可從監控頁開啟。
                try:
                    await self.browser.set_audio_muted(True)
                except Exception as exc:
                    self.record_error(exc)
                self.publish()
            ready = time.monotonic()
            (self.root / "runtime/state/ready.json").write_text(json.dumps({"time": time.time(), "pid": os.getpid()}), encoding="utf-8")
            while not self.gate.stop_event.is_set():
                if duration and time.monotonic()-ready >= duration:
                    await self.command("stop")
                    break
                if self.browser and self.browser.game.get("join_armed") \
                        and self.gate.state == "RUNNING":
                    result = await self.browser.enter_match()
                    if (not result["ok"]
                            and result.get("code") not in JOIN_NON_ERROR_CODES):
                        self.record_error(RuntimeError(f"進入對局失敗：{result['message']}"))
                    elif self.browser.audio_want_muted:
                        # 進局事件後重申靜音（新對局頁可能自帶聲音）。
                        try:
                            await self.browser.set_audio_muted(True)
                        except Exception as exc:
                            self.record_error(exc)
                    self.publish()
                if self.browser and self.browser.move_probe.get("armed") \
                        and self.gate.state == "RUNNING":
                    self.browser.move_probe["armed"] = False
                    probe = await self.browser.probe_move()
                    # 探針陰性結果（FAILED_*／UNKNOWN）是研究資料，已存 runtime/probe，
                    # 不計為平台錯誤；只有基礎設施異常才記錯誤。
                    if probe["result"] in ("ABORTED_GATE", "ERROR"):
                        self.record_error(RuntimeError(f"派兵探針異常：{probe['result']}：{probe['message']}"))
                    self.publish()
                if self.gate.state == "RUNNING":
                    if self.config.get("mode") == "live":
                        # live 模式：禁止 Mock 閉環（不 advance／不規劃／不寫假決策）。
                        # 真實觀察由 monitor（感測／守衛）負責；此處只送心跳。
                        self.publish()
                    else:
                        try:
                            await self.cycle()
                            if self.browser:
                                await self.browser.probe()
                            self.consecutive_errors = 0
                        except Exception as exc:
                            self.consecutive_errors += 1
                            self.record_error(exc)
                            # 瀏覽器安全／連線錯誤立即停機；一般模擬錯誤最多三次。
                            if self.browser or self.consecutive_errors >= self.config["max_consecutive_errors"]:
                                await self.command("error")
                elif self.gate.state == "PAUSED":
                    if self.config.get("mode") == "live":
                        self.publish()
                    else:
                        try:
                            await self.observe_while_paused()
                        except Exception as exc:
                            self.record_error(exc)
                            await self.command("error")
                if self.gate.state == "ERROR":
                    break
                try:
                    await asyncio.wait_for(self.gate.stop_event.wait(), self.config["interval_seconds"])
                except TimeoutError:
                    pass
        except Exception as exc:
            self.record_error(exc)
            await self.command("error")
            traceback.print_exc()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # ERROR 也封鎖操作；關閉專用瀏覽器後監控頁保留錯誤。
            if self.gate.state != "ERROR":
                await self.command("stop")
            if self.browser:
                await self.browser.close()
            self.ended = time.monotonic()
            self.publish()
            (self.root / "runtime/state/final-status.json").write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
            self.logger.close()
            self.error_logger.close()
            try:
                self.audio_logger.close()
            except Exception:
                pass
        if not exit_after_stop and self.dashboard:
            print("操作已封鎖；監控頁保留最終狀態。關閉命令視窗或 Ctrl+C 可結束服務。", flush=True)
            await asyncio.Event().wait()
        if self.dashboard:
            await self.dashboard.close()
        return 1 if self.errors or self.verification_failures else 0


def build_parser():
    parser = argparse.ArgumentParser(description="Kiomet 人工智慧控制平台")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--exit-after-stop", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--no-capture", action="store_true",
                        help="停用週期截圖（Renderer Crash A/B 實驗 B 組用）")
    parser.add_argument("--live-authorize", action="store_true",
                        help="本次進程持有使用者明確真實遊玩授權（無旗標＝無授權）")
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def main():
    parser = build_parser()
    args = parser.parse_args()
    for name in ("logs", "tmp", "state", "browser-profile", "browsers", "screenshots", "cache"):
        (ROOT / "runtime" / name).mkdir(parents=True, exist_ok=True)
    os.environ.update(PLAYWRIGHT_BROWSERS_PATH=str(ROOT/"runtime/browsers"),
                      TEMP=str(ROOT/"runtime/tmp"), TMP=str(ROOT/"runtime/tmp"))
    import tempfile
    tempfile.tempdir = str(ROOT/"runtime/tmp")
    config = json.loads((ROOT/"config/default.json").read_text(encoding="utf-8"))
    if args.live and args.mock:
        parser.error("不可同時指定 --live 與 --mock")
    if args.live:
        config["mode"] = "live"
    elif args.mock:
        config["mode"] = "mock"
    if config.get("mode", "mock") not in ("mock", "live"):
        parser.error("mode 僅支援 mock／live")
    if config["browser_url"] != "https://kiomet.com/":
        parser.error("僅支援指定 Kiomet 網址")
    if args.port is not None:
        config["port"] = args.port
    if config["interval_seconds"] < 0.1 or args.duration < 0:
        parser.error("執行間隔至少 0.1 秒，運行時長不得為負數")
    # 檔案鎖防止同一瀏覽器設定檔被多個平台實例同時使用。
    import msvcrt
    instance = (ROOT/"runtime/state/platform.lock").open("a+b")
    instance.seek(0)
    if instance.read(1) == b"":
        instance.write(b"0")
        instance.flush()
    instance.seek(0)
    try:
        msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        parser.exit(2, "已有平台實例正在執行；請先停止並關閉原服務。\n")
    try:
        app = Application(ROOT, config, args.no_browser,
                          no_capture=args.no_capture)
        if args.live_authorize:
            app.gate.set_authorized(
                True, "explicit_user_authorization:process-start-flag")
        raise SystemExit(asyncio.run(app.run(args.duration, args.exit_after_stop)))
    except KeyboardInterrupt:
        print("已結束平台。")
    finally:
        instance.close()

if __name__ == "__main__":
    main()
