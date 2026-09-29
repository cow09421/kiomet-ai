import asyncio
from dataclasses import replace
import json
from kiomet_ai.observer import MockGame, MockObserver
from kiomet_ai.planner import MockPlanner
from kiomet_ai.executor import MockExecutor
from kiomet_ai.verifier import MockVerifier
from kiomet_ai.control import ActionGate
from kiomet_ai.actions import Action
from kiomet_ai.logging import DecisionLogger
from kiomet_ai.world import WorldModel


def run(coro):
    return asyncio.run(coro)


def test_closed_loop():
    async def case():
        game, gate = MockGame(), ActionGate()
        observer, planner = MockObserver(game), MockPlanner()
        executor, verifier = MockExecutor(game, gate), MockVerifier()
        await gate.command("resume")
        kinds = set()
        for _ in range(50):
            game.advance()
            before = await observer.observe()
            action = planner.plan(before)
            result = await executor.execute(action)
            after = await observer.observe()
            assert result.accepted
            assert verifier.verify(before, action, after).status == "SUCCESS"
            kinds.add(action.kind)
        assert kinds == {"MoveForce", "UpgradeTower", "Wait"}
        assert observer.count == 100
    run(case())


def test_visibility_filters_nodes_edges_forces():
    async def case():
        from kiomet_ai.world import Force
        game = MockGame()
        game.raw.forces.append(Force("secret", "hidden_enemy", 99, 1, 200))
        game.raw.supply_lines.append((99, 1))
        observation = await MockObserver(game).observe()
        serialized = json.dumps(observation.to_dict())
        assert "hidden_enemy" not in serialized
        assert observation.tower(99) is None
        assert 99 not in observation.tower(1).neighbors
        assert not observation.forces and not observation.supply_lines
        try:
            MockPlanner().plan(game.raw)
            assert False
        except TypeError:
            pass
    run(case())


def test_pause_stop_and_no_resurrection():
    async def case():
        game, gate = MockGame(), ActionGate()
        executor = MockExecutor(game, gate)
        action = Action("MoveForce", 1, 2, 10)
        assert not (await executor.execute(action)).accepted
        await gate.command("resume")
        assert (await executor.execute(action)).accepted
        await gate.command("pause")
        assert not (await executor.execute(action)).accepted
        await gate.command("stop")
        await gate.command("resume")
        assert gate.state == "STOPPED"
        for _ in range(100):
            assert not (await executor.execute(action)).accepted
        assert executor.sent == 1
    run(case())


def test_stop_race_orders_input_before_ack():
    async def case():
        gate = ActionGate()
        await gate.command("resume")
        events = []
        async def input_operation():
            events.append("input_begin")
            await asyncio.sleep(0.01)
            events.append("input_end")
        task = asyncio.create_task(gate.dispatch(input_operation))
        await asyncio.sleep(0)
        await gate.command("stop")
        events.append("stop_ack")
        await task
        assert await gate.dispatch(input_operation) is None
        assert events == ["input_begin", "input_end", "stop_ack"]
    run(case())


def test_click_is_not_success():
    async def case():
        game = MockGame()
        observer = MockObserver(game)
        before, after = await observer.observe(), await observer.observe()
        verifier = MockVerifier()
        assert verifier.verify(before, Action("UpgradeTower", source=1, upgrade="Radar"), after).status == "FAILED"
        assert verifier.verify(before, Action("Wait"), before).status == "FAILED"
        assert verifier.verify(before, Action("MoveForce", 1, 2, 10), after).status == "FAILED"
    run(case())


def test_invalid_and_hidden_actions_do_not_mutate():
    async def case():
        game, gate = MockGame(), ActionGate()
        await gate.command("resume")
        executor = MockExecutor(game, gate)
        for action in [Action("MoveForce", 1, 99, 20), Action("MoveForce", 1, 2, -1),
                       Action("MoveForce", 1, 2, 40), Action("MoveForce", 1, 2, True),
                       Action("UpgradeTower", source=99, upgrade="Radar"),
                       Action("MoveKing", 1, 3), Action("SetSupplyLine", 1, 99)]:
            assert not (await executor.execute(action)).accepted
        assert game.raw.towers[1].units == 40
        assert executor.sent == 0
    run(case())


def test_world_discards_hidden_information():
    async def case():
        game, world = MockGame(), WorldModel()
        observer = MockObserver(game)
        world.update(await observer.observe())
        game.raw.visible_ids.remove(3)
        world.update(await observer.observe())
        assert world.current.tower(3) is None
    run(case())


def test_bounded_logs(tmp_path):
    logger = DecisionLogger(tmp_path / "decisions.jsonl", max_bytes=300, backups=2)
    for n in range(100):
        logger.write({"n": n, "reason": "測試"})
    assert len(logger.recent) == 20
    logger.close()
    assert len(list(tmp_path.iterdir())) <= 3
    for path in tmp_path.iterdir():
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
