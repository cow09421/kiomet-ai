"""恢復重播框架（P1-A）。

不研究 Chromium root cause。把 crash→恢復→重取→續跑編成可重播劇本，
GPT 改 main-loop 後本框架可立刻驗證。

劇本（全 fake，不碰正式 Production 邏輯）：
crash → PAUSED → recovery → page reacquire → anchor reacquire →
match state reacquire → stale data cleared → controller 再經顯式
resume 才可繼續。

覆蓋與 test_repair_ladder.py 不重疊：後者測閘門躍遷與修復梯分級，
此處測整段 episode 的順序契約與過期清除。
"""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.control import ActionGate


def run(coro):
    return asyncio.run(coro)


class FakeBrowser:
    """崩潰頁→恢復換頁；generation 計數證明換過頁。"""

    def __init__(self):
        self.crashed = False
        self.page_generation = 1
        self.game = {"state": "IN_MATCH",
                     "match": {"id": "m1", "state": "IN_MATCH"}}

    async def capture_frame(self):
        if self.crashed:
            raise RuntimeError("Page.screenshot: Target crashed")
        return b"frame"

    async def recover_page(self):
        if not self.crashed:
            return {"ok": False, "result": "NO_CRASH"}
        self.crashed = False
        self.page_generation += 1
        self.game = {"state": "MENU",
                     "match": {"id": None, "state": None}}
        return {"ok": True, "result": "RECOVERED"}

    async def recover_chromium(self):
        self.crashed = False
        self.page_generation += 1
        self.game = {"state": "MENU",
                     "match": {"id": None, "state": None}}
        return {"ok": True, "result": "RECOVERED"}


class FakeController:
    """按局綁定的控制器狀態（self id／保留／待確認／錨點）。"""

    def __init__(self, gate):
        self.gate = gate
        self.match_id = None
        self.self_owner_id = None
        self.reservations = set()
        self.pending = []
        self.anchor = None
        self.capture_task_alive = False
        self.dispatched = []

    def on_match(self, match_id, anchor):
        if match_id != self.match_id:
            self.self_owner_id = None
            self.reservations = set()
            self.pending = []
        self.match_id = match_id
        self.anchor = anchor

    async def cycle(self, browser):
        if self.gate.state != "RUNNING":
            return "NO_SAFE_PROPOSAL"
        frame = await browser.capture_frame()
        assert frame == b"frame"
        self.capture_task_alive = True
        return "CYCLE_OK"

    async def dispatch(self, action_id):
        if self.gate.state != "RUNNING":
            return None
        if action_id in self.dispatched:
            return None
        self.dispatched.append(action_id)
        return action_id


def replay_episode(browser, controller, gate):
    """回放一次 crash→恢復→重取→續跑，回傳各階段快照。"""
    snap = {}
    snap["crashed_gate"] = gate.state
    browser.crashed = True
    try:
        run(controller.cycle(browser))
        snap["capture_after_crash"] = "RUNNING"
    except RuntimeError:
        snap["capture_after_crash"] = "STOPPED"
        run(gate.command("error"))
    snap["gate_after_crash"] = gate.state
    snap["dispatch_during_error"] = run(controller.dispatch("a1"))
    return snap


def test_crash_freezes_gate_and_stops_capture():
    gate = ActionGate()
    run(gate.command("resume"))
    browser, controller = FakeBrowser(), FakeController(gate)
    assert run(controller.cycle(browser)) == "CYCLE_OK"
    snap = replay_episode(browser, controller, gate)
    assert snap["gate_after_crash"] == "ERROR"
    assert snap["capture_after_crash"] == "STOPPED"
    assert snap["dispatch_during_error"] is None


def test_recovery_reacquires_page_and_pauses_gate():
    gate = ActionGate()
    run(gate.command("resume"))
    browser, controller = FakeBrowser(), FakeController(gate)
    replay_episode(browser, controller, gate)
    assert gate.state == "ERROR"
    gen_before = browser.page_generation
    assert run(browser.recover_page())["result"] == "RECOVERED"
    assert browser.page_generation == gen_before + 1
    run(gate.command("recovered"))
    assert gate.state == "PAUSED"
    assert run(controller.dispatch("a1")) is None


def test_stale_anchor_rejected_after_recovery():
    gate = ActionGate()
    browser, controller = FakeBrowser(), FakeController(gate)
    controller.on_match("m1", anchor={"match_id": "m1", "towers": [1]})
    replay_episode(browser, controller, gate)
    run(browser.recover_page())
    # 恢復後頁面回到選單：舊錨點屬舊局，不得沿用
    assert browser.game["match"]["id"] is None
    controller.on_match(browser.game["match"]["id"],
                        anchor={"match_id": None, "towers": []})
    assert controller.anchor["match_id"] is None
    assert controller.self_owner_id is None


def test_stale_match_state_cleared_on_new_match():
    gate = ActionGate()
    controller = FakeController(gate)
    controller.on_match("m1", anchor={"match_id": "m1"})
    controller.self_owner_id = 5
    controller.reservations.add(("s", "t"))
    controller.pending.append({"action_id": "m1:1->2:1"})
    controller.on_match("m2", anchor={"match_id": "m2"})
    assert controller.self_owner_id is None
    assert controller.reservations == set()
    assert controller.pending == []


def test_controller_continues_only_after_explicit_resume():
    gate = ActionGate()
    run(gate.command("resume"))
    browser, controller = FakeBrowser(), FakeController(gate)
    replay_episode(browser, controller, gate)
    run(browser.recover_page())
    run(gate.command("recovered"))
    browser.game = {"state": "IN_MATCH",
                    "match": {"id": "m2", "state": "IN_MATCH"}}
    controller.on_match("m2", anchor={"match_id": "m2"})
    assert run(controller.cycle(browser)) == "NO_SAFE_PROPOSAL"
    run(gate.command("resume"))
    assert run(controller.cycle(browser)) == "CYCLE_OK"
    assert run(controller.dispatch("a2")) == "a2"
    assert run(controller.dispatch("a2")) is None


def test_chromium_fallback_after_page_failure():
    gate = ActionGate()
    run(gate.command("resume"))
    browser, controller = FakeBrowser(), FakeController(gate)
    replay_episode(browser, controller, gate)

    async def failing_page():
        return {"ok": False, "result": "RECOVERY_FAILED"}
    browser.recover_page = failing_page
    assert run(browser.recover_page())["result"] == "RECOVERY_FAILED"
    assert run(browser.recover_chromium())["result"] == "RECOVERED"
    run(gate.command("recovered"))
    assert gate.state == "PAUSED"


def test_repeated_episodes_do_not_accumulate_reservations():
    gate = ActionGate()
    run(gate.command("resume"))
    browser, controller = FakeBrowser(), FakeController(gate)
    for match in ("m1", "m2", "m3"):
        controller.on_match(match, anchor={"match_id": match})
        controller.reservations.add(("s", "t"))
        replay_episode(browser, controller, gate)
        run(browser.recover_chromium())
        run(gate.command("recovered"))
        run(gate.command("resume"))
    controller.on_match("m4", anchor={"match_id": "m4"})
    assert controller.reservations == set()
    assert controller.pending == []
    assert controller.self_owner_id is None


def test_supervisor_repair_drives_levels(monkeypatch):
    """修復梯分級由 supervisor.repair 驅動（打樁 API）。"""
    from kiomet_ai import supervisor as sup

    calls = []

    def fake_api(url, token, command, timeout=5):
        calls.append(command)
        if command == "recover-page":
            return {"state": "RECOVERED"}
        return None

    monkeypatch.setattr(sup, "_api_command", fake_api)
    monkeypatch.setattr(sup.Supervisor, "health",
                        lambda self, url: {"backend": "RUNNING",
                                           "dashboard": "ONLINE"})
    monkeypatch.setattr(sup.Supervisor, "restart",
                        lambda self, url, token, authorize=True: {
                            "ok": True, "result": "RESTARTED"})
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path as _P
        sv = sup.Supervisor(root=_P(tmp))
        result = sv.repair("http://127.0.0.1:8765", "token")
    assert result["ok"] is True
    assert result["level"] == "LEVEL_1_PAGE"
    assert calls == ["recover-page"]
