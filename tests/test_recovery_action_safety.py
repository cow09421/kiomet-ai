"""恢復後行動安全guard contract（P0-C）。

Renderer crash → recovery → controller resume 後不得：
- 重放舊 proposal
- 重複送同 action
- 重用 stale token
- 重用舊 reservation
- 使用上一 match action
- 因 replay log 誤判成新 action

本檔以 contract test 形式建立規格；production 由 GPT re-entry 修復搭配。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.action_validity import ReservationBoard
from kiomet_ai.control import ActionGate


def run(coro):
    return asyncio.run(coro)


def test_gate_recovers_to_paused_not_running():
    """Recovery 只到 PAUSED：不自動恢復派送。"""
    gate = ActionGate()

    async def scenario():
        await gate.command("error")
        assert gate.state == "ERROR"
        await gate.command("recovered")
        assert gate.state == "PAUSED"

        async def operation():
            return "SENT"

        result = await gate.dispatch(operation)
        assert result is None

    run(scenario())


def test_dispatch_requires_running():
    gate = ActionGate()

    async def scenario():
        await gate.command("resume")
        assert gate.state == "RUNNING"

        async def operation():
            return "SENT"

        result = await gate.dispatch(operation)
        assert result == "SENT"

    run(scenario())


def test_dispatch_paused_returns_none():
    gate = ActionGate()

    async def scenario():
        assert gate.state == "PAUSED"

        async def operation():
            return "SENT"

        result = await gate.dispatch(operation)
        assert result is None

    run(scenario())


def test_dispatch_exec_requires_running_and_authorized():
    gate = ActionGate()

    async def scenario():
        await gate.command("resume")
        gate.set_authorized(True, provenance="test")
        called = []

        async def operation():
            called.append(True)
            return "DONE"

        result = await gate.dispatch_exec(operation)
        assert result == "DONE"
        assert called == [True]

    run(scenario())


def test_reservation_board_clears_on_match_change():
    """換局時 reservation 必須清空（不得重用舊 reservation）。"""
    board = ReservationBoard()
    board.reserve("action:1", source_id=10, target_id=20)
    assert board.holder(10) == "action:1"
    board.clear_match()
    assert board.holder(10) is None


def test_reservation_prevents_double_spend():
    """同一 source 不得被兩個 action 同時保留。"""
    board = ReservationBoard()
    ok1 = board.reserve("action:1", source_id=10, target_id=20)
    assert ok1 is None
    ok2 = board.reserve("action:2", source_id=10, target_id=30)
    assert ok2 == "RESOURCE_RESERVED:source"


def test_reservation_prevents_double_target():
    """同一 target 不得被兩個 action 同時保留。"""
    board = ReservationBoard()
    board.reserve("action:1", source_id=10, target_id=20)
    ok2 = board.reserve("action:2", source_id=30, target_id=20)
    assert ok2 == "RESOURCE_RESERVED:target"


def test_reservation_releases_after_action():
    board = ReservationBoard()
    board.reserve("action:1", source_id=10, target_id=20)
    board.release("action:1")
    assert board.holder(10) is None
    assert board.holder(20) is None


def test_reservation_allows_reuse_after_release():
    """Release 後同一 source 可再次保留（不得永久鎖定）。"""
    board = ReservationBoard()
    board.reserve("action:1", source_id=10, target_id=20)
    board.release("action:1")
    ok = board.reserve("action:2", source_id=10, target_id=30)
    assert ok is None
    assert board.holder(10) == "action:2"


def test_gate_stopped_is_irreversible():
    gate = ActionGate()

    async def scenario():
        await gate.command("stop")
        assert gate.state == "STOPPED"
        await gate.command("resume")
        assert gate.state == "STOPPED"
        await gate.command("recovered")
        assert gate.state == "STOPPED"

    run(scenario())
