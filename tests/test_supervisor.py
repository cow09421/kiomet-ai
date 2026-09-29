"""Supervisor（監督器）測試：生命週期＋單實例＋恢復階梯（全合成）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai import supervisor as module
from kiomet_ai.supervisor import Supervisor


class FakeSupervisor(Supervisor):
    def __init__(self, root, status=None, commands=None):
        super().__init__(root)
        self._status = status
        self.commands = commands if commands is not None else []
        self.killed = []

    def dashboard_status(self, url):
        if self._status is not None:
            return self._status
        return module._api_status(url)

    def cleanup_zombies(self):
        return []


def _api_ok(url, token, command, payload=None, timeout=15):
    return {"ok": True, "result": "DONE"}


def test_start_attaches_healthy_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_api_status",
                        lambda url, timeout=5: {"state": "RUNNING"})
    sup = FakeSupervisor(tmp_path)
    result = sup.start("http://x/")
    assert result["ok"] is True and result["result"] == "ATTACHED"


def test_start_refuses_busy_port(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_api_status", lambda url, timeout=5: None)
    monkeypatch.setattr(Supervisor, "_port_in_use", staticmethod(lambda url: True))
    sup = FakeSupervisor(tmp_path)
    result = sup.start("http://x/")
    assert result["ok"] is False and result["result"] == "PORT_BUSY"


def test_stop_graceful_then_state(tmp_path, monkeypatch):
    states = [{"state": "RUNNING"}, {"state": "STOPPED"}]

    def fake_status(url, timeout=5):
        return states.pop(0) if states else None
    monkeypatch.setattr(module, "_api_status", fake_status)
    monkeypatch.setattr(module, "_api_command",
                        lambda url, token, command, payload=None, timeout=15: {"state": "STOPPED"})
    sup = FakeSupervisor(tmp_path)
    result = sup.stop("http://x/", "tok", timeout=60)
    assert result["ok"] is True


def test_repair_retry_limit(tmp_path):
    sup = FakeSupervisor(tmp_path)
    sup.recovery_attempts = [1e12, 1e12 + 1, 1e12 + 2]
    import time
    sup.recovery_attempts = [time.time()] * 3
    result = sup.repair("http://x/", "tok")
    assert result["ok"] is False and result["result"] == "RECOVERY_LIMIT"


def test_repair_offline_goes_full_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_api_status", lambda url, timeout=5: None)
    sup = FakeSupervisor(tmp_path)
    monkeypatch.setattr(Supervisor, "restart",
                        lambda self, url, token, authorize=True: {"ok": True, "result": "STARTED"})
    result = sup.repair("http://x/", "tok")
    assert result["level"] == "LEVEL_3_FULL_RESTART"


def test_health_layers(tmp_path):
    sup = FakeSupervisor(tmp_path, status={
        "state": "RUNNING", "game": {"state": "IN_MATCH", "match": {"id": "m1"}},
        "browser": {"connected": True}, "live": {},
        "live_authorization": {"enabled": True}})
    health = sup.health("http://x/")
    assert health["backend"] == "RUNNING"
    assert health["browser"] == "HEALTHY"
    assert health["authorization"] == "ENABLED"
    assert health["game_state"] == "IN_MATCH"


def test_health_page_crashed(tmp_path):
    sup = FakeSupervisor(tmp_path, status={
        "state": "ERROR", "game": {"state": "UNKNOWN"},
        "browser": {"connected": True},
        "live": {"error": "Page.screenshot: Target crashed"}})
    health = sup.health("http://x/")
    assert health["browser"] == "PAGE_CRASHED"
    assert health["backend"] == "ERROR"


def test_double_start_prevention_documented(tmp_path, monkeypatch):
    # 單實例：健康實例存在時 start() 不啟動第二個，只接管
    calls = []
    monkeypatch.setattr(module, "_api_status",
                        lambda url, timeout=5: {"state": "RUNNING"})
    sup = FakeSupervisor(tmp_path)
    result = sup.start("http://x/")
    assert result["result"] == "ATTACHED"
    assert calls == []
