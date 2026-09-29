import asyncio
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest
from kiomet_ai.app import Application
from kiomet_ai.live import LiveView
from kiomet_ai.observer import MockGame, MockObserver


def make_app(tmp_path):
    (tmp_path / "runtime/logs").mkdir(parents=True)
    (tmp_path / "runtime/state").mkdir(parents=True)
    config = {"host":"127.0.0.1","port":0,"interval_seconds":.01,"max_consecutive_errors":3,
              "log_max_bytes":100000,"log_backups":2,"browser_url":"https://kiomet.com/"}
    return Application(tmp_path, config, no_browser=True)


def test_latest_frame_is_bounded_and_not_written(tmp_path):
    live = LiveView(tmp_path)
    for n in range(1000):
        live.put(b"\xff\xd8" + bytes([n%255])*100, 10)
    image, sequence, _ = live.frame()
    assert sequence == 1000 and len(image) == 102
    assert len(live.times) <= 240
    assert not list(tmp_path.iterdir())


def test_high_mode_expires_without_restart(tmp_path):
    live = LiveView(tmp_path)
    assert live.target_fps == 1
    live.set_high(True)
    assert live.target_fps == 4
    live.high_until = 0
    assert live.target_fps == 1
    live.set_high(True)
    live.set_high(False)
    assert live.target_fps == 1


def test_only_diagnostics_use_bounded_disk_slots(tmp_path):
    live = LiveView(tmp_path)
    assert live.save_diagnostic("沒有畫面") is None
    live.put(b"\xff\xd8test", 1)
    for _ in range(25):
        live.save_diagnostic("測試錯誤")
    directory = tmp_path / "runtime/screenshots/diagnostics"
    assert len(list(directory.glob("*.jpg"))) == 10
    assert len(list(directory.glob("*.json"))) == 10


def test_paused_observer_progresses_without_actions(tmp_path):
    async def case():
        app = make_app(tmp_path)
        try:
            await app.command("resume")
            await app.cycle()
            await app.command("pause")
            plans, sent, observations = app.plan_count, app.executor.sent, app.observer.count
            for _ in range(10):
                await app.observe_while_paused()
            assert app.plan_count == plans and app.executor.sent == sent
            assert app.observer.count == observations+10
            assert app.world.current.tick == 11
        finally:
            app.logger.close(); app.error_logger.close()
    asyncio.run(case())


def test_error_retains_latest_game_frame(tmp_path):
    app = make_app(tmp_path)
    try:
        app.live.put(b"\xff\xd8test", 1)
        app.record_error(RuntimeError("測試驗證失敗"))
        assert app.errors[-1]["diagnostic"].endswith(".jpg")
        assert app.live.diagnostics_written == 1
    finally:
        app.logger.close(); app.error_logger.close()


def test_observation_is_immutable():
    state = asyncio.run(MockObserver(MockGame()).observe())
    with pytest.raises(FrozenInstanceError):
        state.towers[0].units = 9000
