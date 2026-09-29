"""正式即時控制器以短週期重規劃，但仍允許安全的明確覆寫。"""
import asyncio
from types import SimpleNamespace

import pytest

from kiomet_ai import live_controller as live_controller_module
from kiomet_ai.live_controller import LiveController


@pytest.mark.parametrize(("override", "expected"), [(None, 2.0), (5, 5)])
def test_run_loop_sleeps_for_default_or_explicit_interval(monkeypatch,
                                                          override,
                                                          expected):
    async def scenario():
        stop_event = asyncio.Event()
        controller = LiveController.__new__(LiveController)
        controller.app = SimpleNamespace(
            gate=SimpleNamespace(stop_event=stop_event))
        controller.running = False
        controller.cycle_count = 0
        controller.cycle_seq = 0
        controller.last_cycle_at = None
        controller.phase = "STARTING"
        controller.journal = {
            "consecutive_failures": 0,
            "cycles": 0,
            "no_safe_proposals": 0,
        }
        controller._save = lambda: None
        controller._record_cycle = lambda *_args: None

        async def cycle_once():
            return "NO_SAFE_PROPOSAL", {"reason": "STALE_WORLD"}

        controller.cycle_once = cycle_once
        observed = []

        async def stop_after_sleep(seconds):
            observed.append(seconds)
            stop_event.set()

        monkeypatch.setattr(live_controller_module.asyncio, "sleep",
                            stop_after_sleep)
        if override is None:
            await controller.run_loop()
        else:
            await controller.run_loop(interval=override)

        assert observed == [expected]
        assert controller.cycle_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", [0, 0.5, -1, float("inf"), True, "2"])
def test_run_loop_rejects_invalid_or_too_fast_interval(invalid):
    controller = LiveController.__new__(LiveController)
    with pytest.raises(ValueError, match="至少 1 秒"):
        asyncio.run(controller.run_loop(interval=invalid))
