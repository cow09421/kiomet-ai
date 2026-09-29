"""Production-path tests for per-cycle sequential threat evaluation."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import kiomet_ai.live_controller as live_controller_module
import kiomet_ai.pvp_live as pvp_live_module
from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import UNIT_NAMES, TowerUnitCounts
from kiomet_ai.pvp_live import evaluate_multi_threat
from kiomet_ai.battle_mirror import CAPACITIES


def units(soldier=5):
    result = {name: 0 for name in UNIT_NAMES}
    result["Soldier"] = soldier
    return result


def threat(force_id, owner_id, eta_ticks, *, target=10, relation="ENEMY"):
    return {
        "match_id": "m1", "cycle_id": 3,
        "source_force_id": force_id, "owner_id": owner_id,
        "relation": relation, "source_tower": force_id + 1000,
        "target_tower": target, "units": units(2),
        "eta_ticks": eta_ticks,
        "eta_status": "CANDIDATE" if type(eta_ticks) is int else "UNKNOWN",
        "confidence": "CANDIDATE", "freshness": "FRESH",
    }


def self_tower(tower_id=10, now=None):
    now = time.time() if now is None else now
    return SimpleNamespace(
        tower_id=tower_id, match_id="m1", owner="SELF", tower_type="Town",
        owner_ruler=False, timestamp=now,
        freshness=lambda match, _now: "FRESH" if match == "m1" else "STALE",
        unit_counts=TowerUnitCounts(
            units_kind="MANY", shield=0, fighter=0, chopper=0,
            bomber=0, tank=0, soldier=5, observed_at=now))


def make_controller():
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})
    controller = LiveController(SimpleNamespace(root=Path("."),
                                                browser=browser))
    controller._select_player_id_match("m1")
    controller._player_ids.observe("SELF", 7)
    return controller


def test_multi_threat_carries_survivors_between_different_enemy_owners(
        monkeypatch):
    import kiomet_ai.pvp as pvp_module

    cases = []

    def resolve(case):
        cases.append(case)
        survivors = dict(case["defender_units"])
        survivors["Soldier"] -= 1
        return {"supported": True, "winner": "defender",
                "defender_survivors": survivors}

    monkeypatch.setattr(pvp_module, "evaluate_battle", resolve)
    rows = [dict(row, owner_relation=row["relation"])
            for row in (threat(101, 42, 2), threat(202, 21, 8))]
    result = evaluate_multi_threat(
        units(), rows, CAPACITIES, "Town",
        self_id=7, enemy_id=None)

    assert result["result"] == "SAFE"
    assert [case["attacker_owner_id"] for case in cases] == [42, 21]
    assert [case["defender_units"]["Soldier"] for case in cases] == [5, 4]
    assert result["final_defenders"]["Soldier"] == 3


def test_controller_groups_all_current_threats_by_target_and_calls_evaluator(
        monkeypatch):
    controller = make_controller()
    now = time.time()
    target_a, target_b = self_tower(10, now), self_tower(20, now)
    rows = [threat(101, 42, 2, target=10),
            threat(102, 21, 8, target=10),
            threat(201, 52, 4, target=20)]
    controller.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 3, "status": "OBSERVED_CANDIDATE",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": rows,
    }
    calls = []

    def evaluate(defenders, threats, capacities, tower_type,
                 *, self_id=None, enemy_id=None):
        calls.append((defenders, threats, tower_type, self_id, enemy_id))
        return {"result": "SAFE", "reason": "test-supported",
                "final_defenders": defenders}

    monkeypatch.setattr(pvp_live_module, "evaluate_multi_threat",
                        evaluate, raising=False)

    result = controller._evaluate_cycle_multi_threat(
        "m1", 3, [target_a, target_b], {10: target_a, 20: target_b}, now)

    assert result["status"] == "SAFE"
    assert [row["target_tower_id"] for row in result["evaluations"]] == [10, 20]
    assert [[row["force_identity"] for row in call[1]] for call in calls] == [
        [101, 102], [201]]
    assert [call[4] for call in calls] == [None, None]
    assert controller.journal["multi_threat_evaluation"] == result


def test_controller_same_tick_threats_abstain_without_battle_evaluation():
    controller = make_controller()
    now = time.time()
    target = self_tower(now=now)
    controller.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 3, "status": "OBSERVED_CANDIDATE",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": [threat(101, 42, 2), threat(102, 21, 2)],
    }

    result = controller._evaluate_cycle_multi_threat(
        "m1", 3, [target], {10: target}, now)

    assert result["status"] == "UNKNOWN"
    assert result["evaluations"][0]["reason"] == "UNSUPPORTED_TEMPORAL_CASE"


def test_controller_unknown_eta_is_not_replaced_with_zero():
    controller = make_controller()
    now = time.time()
    target = self_tower(now=now)
    row = threat(101, 42, 99)
    row["eta_status"] = "UNKNOWN"
    controller.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 3, "status": "OBSERVED_CANDIDATE",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": [row],
    }

    result = controller._evaluate_cycle_multi_threat(
        "m1", 3, [target], {10: target}, now)

    assert result["status"] == "UNKNOWN"
    assert result["evaluations"][0]["reason"] == "threat-eta-unknown"


def test_stale_or_cross_match_threat_state_never_reaches_evaluator(monkeypatch):
    controller = make_controller()
    now = time.time()
    target = self_tower(now=now)
    controller.journal["threat_state"] = {
        "match_id": "old-match", "cycle_id": 3,
        "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
        "coverage": {"complete": True}, "threats": [threat(101, 42, 2)],
    }
    calls = []
    monkeypatch.setattr(pvp_live_module, "evaluate_multi_threat",
                        lambda *args, **kwargs: calls.append(args),
                        raising=False)

    result = controller._evaluate_cycle_multi_threat(
        "m1", 3, [target], {10: target}, now)

    assert result["status"] == "UNKNOWN"
    assert result["evaluations"] == []
    assert calls == []


def test_cycle_once_invokes_current_cycle_multi_threat_evaluation(
        tmp_path, monkeypatch):
    controller = make_controller()
    controller.root = tmp_path
    controller.app.root = tmp_path
    controller.cycle_seq = 3
    now = time.time()
    target = self_tower(now=now)
    enemy = SimpleNamespace(tower_id=1, match_id="m1", owner="ENEMY")

    async def ensure_anchor(_match_id):
        return {"match_id": "m1", "towers": []}

    async def observe(match_id, cycle_id, states, by_id, observed_at):
        controller.journal["threat_state"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
            "coverage": {"complete": True},
            "threats": [threat(101, 42, 2)],
        }

    controller.ensure_anchor = ensure_anchor
    controller.build_states = lambda *_args: [target, enemy]
    controller._observe_cycle_threat_state = observe
    probe = tmp_path / "runtime/research/units/unit-struct-probe-m1.json"
    probe.parent.mkdir(parents=True)
    probe.write_text(json.dumps({"rows": []}), encoding="utf-8")
    calls = []

    def evaluate(*args, **kwargs):
        calls.append((args, kwargs))
        return {"result": "SAFE", "reason": "supported"}

    monkeypatch.setattr(pvp_live_module, "evaluate_multi_threat", evaluate)
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [])
    monkeypatch.setattr(live_controller_module,
                        "rejection_reasons", lambda *_args: [])

    phase, _info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert len(calls) == 1
    assert controller.heartbeat()["multi_threat_evaluation"]["status"] == "SAFE"


def test_unknown_multi_threat_result_blocks_new_action():
    controller = make_controller()
    now = time.time()
    target = self_tower(now=now)
    controller.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 3, "status": "OBSERVED_CANDIDATE",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": [threat(101, 42, 2), threat(102, 21, 2)],
    }

    evaluation = controller._evaluate_cycle_multi_threat(
        "m1", 3, [target], {10: target}, now)
    blocked = controller._multi_threat_action_block()

    assert evaluation["status"] == "UNKNOWN"
    assert evaluation["evaluations"][0]["reason"] == "UNSUPPORTED_TEMPORAL_CASE"
    assert blocked["reason"] == "MULTI_THREAT_UNKNOWN"
