"""修復梯在 gate=ERROR（渲染崩潰後）必須真的能復原。

三個連鎖缺陷的回歸：
1. app.command 復原命令曾要求 gate==RUNNING → 崩潰（ERROR）時是空操作；
2. ActionGate 無 ERROR 出口（resume 拒絕 ERROR）→ ERROR 卡死只能 stop；
3. supervisor.repair 認 "ok" 欄但 dashboard 回 {"state": ...}
   → LEVEL1/2 成功被忽略、一律誤升級 LEVEL3 全重啟。

成功證據：ERROR + recover 成功 → gate 轉 PAUSED（不自動派送）；
L1/L2 以 {"state": "RECOVERED"} 被正確認定；失敗維持 ERROR 到下一階。
失敗證據：ERROR 時復原仍無效，或 L1 成功卻呼叫 restart。
"""
import asyncio
from pathlib import Path

from kiomet_ai.control import ActionGate
from kiomet_ai.supervisor import RECOVERY_LIMIT_COUNT, Supervisor


def run(coro):
    return asyncio.run(coro)


def gate_in(state: str) -> ActionGate:
    gate = ActionGate()

    async def _set():
        if state == "ERROR":
            await gate.command("error")
        elif state == "RUNNING":
            await gate.command("resume")
        elif state == "STOPPED":
            await gate.command("stop")
        return gate.state

    assert run(_set()) == state
    return gate


class FakeBrowser:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def recover_page(self):
        self.calls += 1
        return self.result

    async def recover_chromium(self):
        self.calls += 1
        return self.result


def make_app(gate: ActionGate, browser) -> "object":
    from kiomet_ai.app import Application

    app = Application.__new__(Application)
    app.gate = gate
    app.browser = browser
    app.publish = lambda: None
    app.no_capture = True
    app.live_controller = None
    return app


def test_recovered_command_leaves_error_to_paused():
    gate = gate_in("ERROR")
    assert run(gate.command("recovered")) == "PAUSED"
    assert gate.state == "PAUSED"


def test_recovered_never_leaves_stopped():
    gate = gate_in("STOPPED")
    assert run(gate.command("recovered")) == "STOPPED"
    assert gate.state == "STOPPED"


def test_resume_still_refuses_error_until_explicit_recover():
    gate = gate_in("ERROR")
    assert run(gate.command("resume")) == "ERROR"
    assert run(gate.command("recovered")) == "PAUSED"
    assert run(gate.command("resume")) == "RUNNING"


def test_recover_page_in_error_transitions_to_paused():
    gate = gate_in("ERROR")
    browser = FakeBrowser({"ok": True, "result": "RECOVERED"})
    app = make_app(gate, browser)
    state = run(app.command("recover-page"))
    # 回傳值維持 RECOVERED（supervisor 以 state==RECOVERED 判定成功），
    # gate 則停在 PAUSED：不自動恢復派送。
    assert state == "RECOVERED"
    assert gate.state == "PAUSED"
    assert browser.calls == 1


def test_recover_page_failure_keeps_gate_error():
    gate = gate_in("ERROR")
    browser = FakeBrowser({"ok": False, "result": "RECOVERY_FAILED",
                           "message": "boom"})
    app = make_app(gate, browser)
    state = run(app.command("recover-page"))
    assert state == "RECOVERY_FAILED"
    assert gate.state == "ERROR"


def test_recover_in_running_does_not_forcibly_pause():
    gate = gate_in("RUNNING")
    browser = FakeBrowser({"ok": True, "result": "RECOVERED"})
    app = make_app(gate, browser)
    state = run(app.command("recover-chromium"))
    assert state == "RECOVERED"
    assert gate.state == "RUNNING"


def test_recover_is_noop_when_stopped():
    gate = gate_in("STOPPED")

    class Exploding(FakeBrowser):
        async def recover_page(self):
            raise AssertionError("STOPPED 下不得呼叫瀏覽器復原")

    app = make_app(gate, Exploding(None))
    assert run(app.command("recover-page")) == "STOPPED"


def test_repair_ladder_accepts_state_recovered_at_level_1(tmp_path, monkeypatch):
    sup = Supervisor(root=Path(tmp_path))
    monkeypatch.setattr(sup, "health",
                        lambda url: {"backend": "ERROR", "dashboard": "ONLINE"})
    monkeypatch.setattr(
        "kiomet_ai.supervisor._api_command",
        lambda url, token, command, **kw: {"state": "RECOVERED"})
    monkeypatch.setattr(
        sup, "restart",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("LEVEL1 成功不得升級 LEVEL3")))
    result = sup.repair("http://127.0.0.1:8765", "t")
    assert result == {"ok": True, "result": "RECOVERED",
                      "level": "LEVEL_1_PAGE"}


def test_repair_ladder_falls_from_failed_level_1_to_level_2(tmp_path, monkeypatch):
    sup = Supervisor(root=Path(tmp_path))
    monkeypatch.setattr(sup, "health",
                        lambda url: {"backend": "ERROR", "dashboard": "ONLINE"})
    replies = {"recover-page": {"state": "ERROR"},
               "recover-chromium": {"state": "RECOVERED"}}
    monkeypatch.setattr(
        "kiomet_ai.supervisor._api_command",
        lambda url, token, command, **kw: replies[command])
    monkeypatch.setattr(
        sup, "restart",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("LEVEL2 成功不得升級 LEVEL3")))
    result = sup.repair("http://127.0.0.1:8765", "t")
    assert result["level"] == "LEVEL_2_CHROMIUM"


def test_repair_ladder_escalates_to_level_3_when_all_fail(tmp_path, monkeypatch):
    sup = Supervisor(root=Path(tmp_path))
    monkeypatch.setattr(sup, "health",
                        lambda url: {"backend": "ERROR", "dashboard": "ONLINE"})
    monkeypatch.setattr(
        "kiomet_ai.supervisor._api_command",
        lambda url, token, command, **kw: {"state": "ERROR"})
    monkeypatch.setattr(
        sup, "restart", lambda *a, **kw: {"ok": True, "result": "RESTARTED"})
    result = sup.repair("http://127.0.0.1:8765", "t")
    assert result["level"] == "LEVEL_3_FULL_RESTART"


def test_repair_rate_limit_stops_after_three_attempts(tmp_path, monkeypatch):
    sup = Supervisor(root=Path(tmp_path))
    monkeypatch.setattr(sup, "health",
                        lambda url: {"backend": "ERROR", "dashboard": "ONLINE"})
    monkeypatch.setattr(
        "kiomet_ai.supervisor._api_command",
        lambda url, token, command, **kw: {"state": "ERROR"})
    monkeypatch.setattr(
        sup, "restart", lambda *a, **kw: {"ok": True, "result": "RESTARTED"})
    for _ in range(RECOVERY_LIMIT_COUNT):
        assert sup.repair("http://127.0.0.1:8765", "t")["level"] == \
            "LEVEL_3_FULL_RESTART"
    limited = sup.repair("http://127.0.0.1:8765", "t")
    assert limited == {"ok": False, "result": "RECOVERY_LIMIT",
                       "message": "10 分鐘內已達 3 次，要求人工處理"}


def test_recover_restarts_dead_capture_and_controller_tasks():
    from kiomet_ai.app import Application

    async def scenario():
        gate = ActionGate()
        assert await gate.command("error") == "ERROR"
        browser = FakeBrowser({"ok": True, "result": "RECOVERED"})
        app = Application.__new__(Application)
        app.gate = gate
        app.browser = browser
        app.publish = lambda: None
        app.no_capture = False
        calls = {"capture": 0, "controller": 0}

        async def capture_loop():
            calls["capture"] += 1
            await asyncio.sleep(3600)

        async def controller_loop():
            calls["controller"] += 1
            await asyncio.sleep(3600)

        class FakeController:
            async def run_loop(self):
                await controller_loop()

        app.capture_loop = capture_loop
        app.live_controller = FakeController()
        # 崩潰時已退出（完成）的舊任務
        app._capture_task = asyncio.create_task(asyncio.sleep(0))
        app._controller_task = asyncio.create_task(asyncio.sleep(0))
        await asyncio.gather(app._capture_task, app._controller_task)
        assert app._capture_task.done() and app._controller_task.done()

        state = await app.command("recover-page")
        assert state == "RECOVERED"
        assert gate.state == "PAUSED"
        assert app._capture_task is not None and not app._capture_task.done()
        assert app._controller_task is not None and not app._controller_task.done()
        await asyncio.sleep(0)  # 讓新任務跑第一輪
        assert calls == {"capture": 1, "controller": 1}

        # 活著的任務不得重複建立（再次復原時 gate 必須在可復原狀態）
        assert await gate.command("error") == "ERROR"
        await app.command("recover-page")
        assert calls == {"capture": 1, "controller": 1}

        app._capture_task.cancel()
        app._controller_task.cancel()
        await asyncio.gather(app._capture_task, app._controller_task,
                             return_exceptions=True)

    run(scenario())
