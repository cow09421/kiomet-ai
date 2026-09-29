import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.actions import Action
from kiomet_ai.katakiomet.belief import BeliefState, decay
from kiomet_ai.katakiomet.graph import ForceEdge, GameGraph, TowerNode
from kiomet_ai.katakiomet.ownership import control_probability, frontlines
from kiomet_ai.katakiomet.policy import HeuristicPolicy, safe_sendable
from kiomet_ai.katakiomet.safety import SafetyConfig, govern, king_risk
from kiomet_ai.katakiomet.value import evaluate


def arena() -> GameGraph:
    return GameGraph(
        timestamp=1000.0, player_id="me",
        towers={
            1: TowerNode(1, "me", "Outpost", None, True, 40, 1.0, None, True,
                         (2, 3), (), 1000.0, 1.0),
            2: TowerNode(2, None, "Outpost", None, True, 4, None, None, False,
                         (1, 3), (), 1000.0, 1.0),
            3: TowerNode(3, "enemy", "Outpost", None, True, 8, None, None, False,
                         (1, 2), (), 1000.0, 1.0),
            4: TowerNode(4, "me", "Outpost", None, True, 30, 1.0, None, False,
                         (1,), (), 1000.0, 1.0),
        },
        king_tower=1)


def test_unknown_units_never_dispatch():
    assert safe_sendable(None, 15) == 0
    assert safe_sendable(40, 15) == 25


def test_belief_decay_and_staleness():
    assert decay(1.0, 0.0) == 1.0
    assert abs(decay(1.0, 8.0) - 0.5) < 1e-9
    belief = BeliefState("me")
    belief.update(arena())
    assert belief.towers[1].confidence == 1.0
    aged = belief.tower(1, now=1008.0)
    assert abs(aged.confidence - 0.5) < 1e-9
    assert belief.staleness(1, now=1005.0) == 5.0
    assert belief.staleness(999, now=1005.0) is None


def test_ownership_and_frontlines():
    graph = arena()
    assert control_probability(graph, 1) < 0.9  # 鄰接敵塔，控制權打折
    assert control_probability(graph, 2) is not None
    assert control_probability(graph, 999) is None  # 未知塔回 UNKNOWN
    lines = frontlines(graph)
    assert (1, 3) in lines or (3, 1) in lines or any(
        set(p) == {1, 3} for p in lines)


def test_value_prefers_king_alive():
    good = evaluate(arena())
    bad_towers = dict(arena().towers)
    bad_towers[1] = TowerNode(1, "enemy", "Outpost", None, True, 8, None,
                              None, False, (2, 3), (), 1000.0, 1.0)
    bad = evaluate(GameGraph(1000.0, "me", bad_towers, (), None, None))
    assert good.total > bad.total
    assert "king_safety" in good.parts


def test_policy_reinforces_weak_king():
    towers = dict(arena().towers)
    towers[1] = TowerNode(1, "me", "Outpost", None, True, 8, 1.0, None, True,
                          (2, 3), (), 1000.0, 1.0)
    graph = GameGraph(1000.0, "me", towers, (), 30, 1)
    first = HeuristicPolicy().candidates(graph)[0][1]
    assert first.kind == "MoveForce" and first.destination == 1


def test_policy_emergency_blocks_expansion():
    graph = arena()
    actions = HeuristicPolicy().candidates(graph, intent="EMERGENCY_KING_DEFENSE")
    assert all(a.reason.startswith(("國王安全", "前線缺口", "保留兵力"))
               for _, a in actions)


def test_safety_vetoes_bad_attack_and_reserve():
    graph = arena()
    belief = BeliefState("me")
    belief.update(graph)
    # 兵力 40 保留 15 剩 25；打 8 兵敵塔需 8*1.5=12 → 允許且裁定 25。
    ok, amount, _ = govern(belief, graph, Action("MoveForce", 1, 3, 30))
    assert ok and amount == 25
    # 陳舊 20 秒的敵情報：邊際 1.5*(1+1.0)=3.0，需 24；來源剩 25 仍允許。
    old = GameGraph(1020.0, "me", graph.towers, (), 30, 1)
    ok, _, _ = govern(belief, old, Action("MoveForce", 1, 3, 30))
    assert ok
    # 兵力 UNKNOWN 的來源：拒絕。
    towers = dict(graph.towers)
    towers[4] = TowerNode(4, "me", "Outpost", None, True, None, None, None,
                          False, (1,), (), 1000.0, 1.0)
    graph2 = GameGraph(1000.0, "me", towers, (), 30, 1)
    ok, _, reason = govern(belief, graph2, Action("MoveForce", 4, 1, 10))
    assert not ok and "UNKNOWN" in reason


def test_king_risk():
    assert king_risk(arena()) < 0.6
    assert king_risk(GameGraph(1000.0, "me", {}, (), None, None)) == 1.0
