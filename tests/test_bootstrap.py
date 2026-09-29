import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.browser import (BrowserHost, advance_match, classify_game,
                                 classify_game_state)
import control_center


def test_classify_menu_match_disconnected():
    assert classify_game_state(True, True) == "MENU"
    assert classify_game_state(True, False) == "IN_MATCH"
    assert classify_game_state(False, True) == "DISCONNECTED"
    assert classify_game_state(False, False) == "DISCONNECTED"


def test_classify_game_result_screen_first():
    # 結算 overlay 蓋在首頁上：按鈕可見＋結算文字 → RESULT_SCREEN（不是 MENU）。
    state, evidences = classify_game(
        True, "Session Statistics Back to menu Play Again")
    assert state == "RESULT_SCREEN"
    assert any("result_markers" in e for e in evidences)
    # 純首頁仍是 MENU。
    assert classify_game(True, "Play Play with friends")[0] == "MENU"


def test_advance_match_identity():
    base = {"index": 0, "id": None, "state": None,
            "started_at": None, "ended_at": None}
    m1 = advance_match(base, "IN_MATCH", 100.0)
    assert m1["index"] == 1 and m1["state"] == "IN_MATCH"
    assert m1["started_at"] == 100.0 and m1["ended_at"] is None
    # 同局持續不建新號。
    m1b = advance_match(m1, "IN_MATCH", 200.0)
    assert m1b["index"] == 1 and m1b["id"] == m1["id"]
    # 終局記錄結束。
    m2 = advance_match(m1b, "RESULT_SCREEN", 300.0)
    assert m2["state"] == "RESULT_SCREEN" and m2["ended_at"] == 300.0
    assert m2["index"] == 1
    # 下一局建新號。
    m3 = advance_match(m2, "IN_MATCH", 400.0)
    assert m3["index"] == 2 and m3["id"] != m1["id"]


def test_classify_game_needs_two_evidences():
    assert classify_game(True, "Play with friends")[0] == "MENU"
    state, evidences = classify_game(False, "佔領更多塔 Botkiller @xxx")
    assert state == "IN_MATCH"
    assert "menu_absent" in evidences and any("match_markers" in e for e in evidences)
    # 主選單消失但無對局特徵 → UNKNOWN，不亂判。
    assert classify_game(False, "載入中…")[0] == "UNKNOWN"


def test_audio_prefs_default_muted_and_roundtrip(tmp_path, monkeypatch):
    from kiomet_ai import prefs
    monkeypatch.setattr(prefs, "PREFS_FILE", tmp_path / "runtime-preferences.json")
    assert prefs.load() == {"game_audio_enabled": False}
    prefs.save({"game_audio_enabled": True})
    assert prefs.load() == {"game_audio_enabled": True}


def test_fresh_host_starts_unknown_never_inherits():
    from kiomet_ai.control import ActionGate
    from pathlib import Path
    host = BrowserHost(Path("."), ActionGate())
    assert host.game["state"] == "UNKNOWN"
    assert host.game["source"] == "init"
    assert host.game["join_busy"] is False
    assert host.game["join_clicks"] == 0
    assert host.audio_want_muted is True


def test_kiomet_pages_lists_all_game_tabs():
    from kiomet_ai.control import ActionGate
    from pathlib import Path

    class FakePage:
        def __init__(self, url):
            self.url = url

    class FakeContext:
        pages = [FakePage("https://kiomet.com/"), FakePage("https://kiomet.com/"),
                 FakePage("http://127.0.0.1:8765/probe")]

    host = BrowserHost(Path("."), ActionGate())
    host.context = FakeContext()
    assert len(host.kiomet_pages()) == 2


def test_management_ready_without_gate_running():
    import asyncio
    from kiomet_ai.control import ActionGate
    from pathlib import Path
    gate = ActionGate()  # 初始 PAUSED
    host = BrowserHost(Path("."), gate)

    async def check():
        ok, _ = host.management_ready()
        assert not ok  # 無瀏覽器 → 拒絕（但不是因為閘門）
        await gate.command("stop")  # 關閉中 → 拒絕
        ok, reason = host.management_ready()
        assert not ok and "關閉" in reason
    asyncio.run(check())


def test_summarize_shows_game_state():
    status = {"state": "RUNNING", "uptime_seconds": 61.0, "errors": [],
              "live": {"sequence": 5, "captured_at": __import__("time").time()},
              "game": {"state": "IN_MATCH"}}
    summary = control_center.summarize(status)
    assert summary["platform"] == "RUNNING"
    assert summary["kiomet"] == "IN_MATCH"


def test_summarize_offline_has_kiomet_unknown():
    summary = control_center.summarize(None)
    assert summary["dashboard"] == "OFFLINE"
    assert summary["kiomet"] == "UNKNOWN"


def test_summarize_missing_game_field():
    summary = control_center.summarize({"state": "PAUSED"})
    assert summary["kiomet"] == "UNKNOWN"


def test_summarize_audio_field():
    status = {"state": "RUNNING", "uptime_seconds": 10.0, "errors": [],
              "live": {"sequence": 1, "captured_at": __import__("time").time()},
              "game": {"state": "IN_MATCH"},
              "audio": {"state": "MUTED", "mode": "FALLBACK_MUTE"}}
    assert control_center.summarize(status)["audio"] == "MUTED"
    assert control_center.summarize(None)["audio"] == "UNKNOWN"
    assert control_center._color("MUTED") == "#2da544"


def test_publish_mode_and_control_center_mode(tmp_path):
    from kiomet_ai.app import Application
    (tmp_path / "runtime/logs").mkdir(parents=True)
    (tmp_path / "runtime/state").mkdir(parents=True)
    base = {"host": "127.0.0.1", "port": 0, "interval_seconds": .01,
            "max_consecutive_errors": 3, "log_max_bytes": 100000,
            "log_backups": 2, "browser_url": "https://kiomet.com/"}
    mock_app = Application(tmp_path, dict(base, mode="mock"), no_browser=True)
    live_app = Application(tmp_path, dict(base, mode="live"), no_browser=True)
    try:
        assert mock_app.snapshot()["mode"] == "mock"
        assert live_app.snapshot()["mode"] == "live"
        assert control_center.summarize({"state": "RUNNING"})["mode"] == "UNKNOWN"
        assert control_center.summarize(
            {"state": "RUNNING", "mode": "live"})["mode"] == "LIVE"
    finally:
        mock_app.logger.close()
        mock_app.error_logger.close()
        live_app.logger.close()
        live_app.error_logger.close()
