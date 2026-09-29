"""LiveController PvP 防守分析與仲裁的接線回歸。"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import kiomet_ai.live_controller as live_controller_module
import kiomet_ai.pvp as pvp_module
from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import UNIT_NAMES, TowerUnitCounts


def unit_vector(soldier=0):
    result = {name: 0 for name in UNIT_NAMES}
    result["Soldier"] = soldier
    return result


def tower(tower_id, owner, *, xy=(0.0, 0.0), neighbors=(), now=None,
          soldiers=10, deployable=0):
    now = time.time() if now is None else now
    state = SimpleNamespace(
        tower_id=tower_id, match_id="m1", owner=owner,
        tower_type="Town", world_x=xy[0], world_y=xy[1],
        neighbors=tuple(neighbors), tower_ref=tower_id + 100,
        owner_ruler=False, timestamp=now,
        freshness=lambda match_id, _now: (
            "FRESH" if match_id == "m1" else "STALE"),
        unit_counts=TowerUnitCounts(
            units_kind="MANY", shield=0, fighter=0, chopper=0,
            bomber=0, tank=0, soldier=soldiers, observed_at=now),
        deployable_force=SimpleNamespace(
            counts=unit_vector(deployable), status="CANDIDATE"),
        deployable_force_confidence="VERIFIED")
    return state


def controller():
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})
    result = LiveController(SimpleNamespace(root=Path("."), browser=browser))
    result._select_player_id_match("m1")
    result._player_ids.observe("SELF", 7)
    return result


def current_threat_state(cycle_id=3):
    return {"match_id": "m1", "cycle_id": cycle_id,
            "freshness": "FRESH", "status": "OBSERVED_CANDIDATE",
            "coverage": {"complete": True}, "threats": [{
                "match_id": "m1", "cycle_id": cycle_id,
                "owner_id": 42, "relation": "ENEMY",
                "source_force_id": 501, "source_tower": 1,
                "target_tower": 10, "units": unit_vector(20),
                "eta_ticks": 100, "eta_status": "CANDIDATE",
                "freshness": "FRESH"}],
            "observed_at": time.time()}


def test_multi_threat_controller_binds_each_enemy_id_and_carries_survivors(
        monkeypatch):
    live = controller()
    now = time.time()
    target = tower(10, "SELF", now=now, soldiers=10)
    rows = []
    for force_id, owner_id, eta in ((501, 42, 5), (502, 21, 10)):
        rows.append({"match_id": "m1", "cycle_id": 3,
                     "source_force_id": force_id, "owner_id": owner_id,
                     "relation": "ENEMY", "source_tower": 1,
                     "target_tower": 10, "units": unit_vector(1),
                     "eta_ticks": eta, "eta_status": "CANDIDATE",
                     "freshness": "FRESH"})
    live.journal["threat_state"] = {
        **current_threat_state(), "threats": rows}
    cases = []

    def battle(case):
        cases.append(case)
        survivors = dict(case["defender_units"])
        survivors["Soldier"] -= 1
        return {"supported": True, "winner": "defender",
                "defender_survivors": survivors,
                "runtime_validation_required": False}

    monkeypatch.setattr(pvp_module, "evaluate_battle", battle)
    result = live._evaluate_cycle_multi_threat(
        "m1", 3, (target,), {10: target}, now)

    assert result["status"] == "SAFE"
    assert [case["attacker_owner_id"] for case in cases] == [42, 21]
    assert [case["defender_units"]["Soldier"] for case in cases] == [10, 9]


def test_first_loss_runs_source_safety_eta_defense_then_abstains_without_merge(
        monkeypatch):
    live = controller()
    now = time.time()
    enemy = tower(1, "ENEMY", xy=(-10.0, 0.0), neighbors=(10,), now=now)
    target = tower(10, "SELF", xy=(0.0, 0.0), neighbors=(1, 20), now=now)
    source = tower(20, "SELF", xy=(0.0, 1.0), neighbors=(10,), now=now,
                   deployable=12)
    live.journal["threat_state"] = current_threat_state()
    threat = {"eta_ticks": 100, "source_tower_id": 1,
              "target_tower_id": 10, "owner_id": 42,
              "owner_relation": "ENEMY", "units": unit_vector(20)}
    battle_case = {"attacker_owner_relation": "ENEMY",
                   "defender_owner_relation": "SELF"}
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 3, "status": "UNKNOWN",
        "evaluations": [{"target_tower_id": 10,
                         "status": "UNKNOWN",
                         "result": {"result": "UNSAFE",
                                    "runtime_validation_required": True,
                                    "first_loss": {
                                        "threat": threat,
                                        "battle_case": battle_case}}}]}
    snapshots = []
    async def snapshot(ref):
        snapshots.append(ref)
        return {"match_id": "m1"}

    live.snapshot_collections = snapshot
    safety_calls = []
    live.evaluate_live_source_safety = lambda *args, **kwargs: (
        safety_calls.append(args) or {"result": "SAFE", "reason": "test-safe"})
    defense_inputs = []

    def evaluate_defense(data):
        defense_inputs.append(data)
        return {"support_status": "RUNTIME_VALIDATION_NEEDED",
                "tower_lost": True, "enemy_eta": data["enemy_eta"],
                "reinforcement_command_validated": False,
                "rescue_requirement_status": "EXACT_POST_MERGE_REQUIRED"}

    monkeypatch.setattr(pvp_module, "evaluate_defense", evaluate_defense)
    result = asyncio.run(live._evaluate_cycle_defense(
        "m1", 3, (enemy, target, source),
        {1: enemy, 10: target, 20: source}, now))

    assert len(snapshots) == 1
    assert len(safety_calls) == 1
    assert len(defense_inputs) == 1
    assert defense_inputs[0]["incoming_path_valid"] is True
    assert len(defense_inputs[0]["reinforcement_candidates"]) == 1
    assert defense_inputs[0]["reinforcement_candidates"][0][
        "post_merge_snapshot_exact"] is False
    assert result["action"] == "ABSTAIN"
    assert result["arbitration"]["evaluation_status"] == "UNKNOWN"
    assert result["execution_gates"]["ui_dispatch"] == "NOT_ATTEMPTED"
    assert live.heartbeat()["defense_assessment"]["action"] == "ABSTAIN"


def test_unknown_multi_threat_and_stale_match_never_read_reinforcement_sources(
        monkeypatch):
    live = controller()
    now = time.time()
    target = tower(10, "SELF", now=now)
    live.journal["threat_state"] = current_threat_state()
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 3, "status": "UNKNOWN",
        "evaluations": [{"target_tower_id": 10, "status": "UNKNOWN",
                         "reason": "UNSUPPORTED_TEMPORAL_CASE",
                         "result": {"result": "UNKNOWN"}}]}
    reads = []
    live.snapshot_collections = lambda ref: reads.append(ref)
    same_tick = asyncio.run(live._evaluate_cycle_defense(
        "m1", 3, [target], {10: target}, now))
    assert same_tick["action"] == "ABSTAIN"
    assert reads == []

    live.journal["multi_threat_evaluation"]["match_id"] = "old-match"
    stale = asyncio.run(live._evaluate_cycle_defense(
        "m1", 3, [target], {10: target}, now))
    assert stale["action"] == "ABSTAIN"
    assert stale["reason"] == "current-match-cycle-threat-evidence-required"
    assert reads == []


def test_unknown_enemy_eta_abstains_without_source_snapshot():
    live = controller()
    now = time.time()
    enemy = tower(1, "ENEMY", xy=(-10.0, 0.0), neighbors=(10,), now=now)
    target = tower(10, "SELF", xy=(0.0, 0.0), neighbors=(1, 20), now=now)
    source = tower(20, "SELF", xy=(0.0, 1.0), neighbors=(10,), now=now,
                   deployable=12)
    live.journal["threat_state"] = current_threat_state()
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 3, "status": "UNKNOWN",
        "evaluations": [{"target_tower_id": 10, "status": "UNKNOWN",
                         "result": {"result": "UNSAFE", "first_loss": {
                             "threat": {"eta_ticks": None,
                                        "source_tower_id": 1,
                                        "target_tower_id": 10,
                                        "owner_id": 42,
                                        "owner_relation": "ENEMY"},
                             "battle_case": {
                                 "attacker_owner_relation": "ENEMY",
                                 "defender_owner_relation": "SELF"}}}}]}
    reads = []

    async def snapshot(ref):
        reads.append(ref)
        return {"match_id": "m1"}

    live.snapshot_collections = snapshot
    result = asyncio.run(live._evaluate_cycle_defense(
        "m1", 3, (enemy, target, source),
        {1: enemy, 10: target, 20: source}, now))

    assert result["action"] == "ABSTAIN"
    assert result["arbitration"]["evaluation_status"] == "UNSUPPORTED"
    assert reads == []
    assert result["source_gates"][0]["status"] == "ABSTAIN_ETA_UNKNOWN"


def test_unsafe_reinforcement_source_is_not_passed_to_defense_evaluator(
        monkeypatch):
    live = controller()
    now = time.time()
    enemy = tower(1, "ENEMY", xy=(-10.0, 0.0), neighbors=(10,), now=now)
    target = tower(10, "SELF", xy=(0.0, 0.0), neighbors=(1, 20), now=now)
    source = tower(20, "SELF", xy=(0.0, 1.0), neighbors=(10,), now=now,
                   deployable=12)
    live.journal["threat_state"] = current_threat_state()
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 3, "status": "UNKNOWN",
        "evaluations": [{"target_tower_id": 10, "status": "UNKNOWN",
                         "result": {"result": "UNSAFE",
                                    "runtime_validation_required": True,
                                    "first_loss": {
                                        "threat": {
                                            "eta_ticks": 100,
                                            "source_tower_id": 1,
                                            "target_tower_id": 10,
                                            "owner_id": 42,
                                            "owner_relation": "ENEMY"},
                                        "battle_case": {
                                            "attacker_owner_relation": "ENEMY",
                                            "defender_owner_relation": "SELF"}}}}]}
    live.snapshot_collections = lambda _ref: asyncio.sleep(0, result={
        "match_id": "m1"})
    live.evaluate_live_source_safety = lambda *_args, **_kwargs: {
        "result": "UNSAFE", "reason": "SOURCE_WOULD_BECOME_UNSAFE"}
    defense_inputs = []

    def evaluate_defense(data):
        defense_inputs.append(data)
        return {"support_status": "RUNTIME_VALIDATION_NEEDED",
                "tower_lost": True, "enemy_eta": data["enemy_eta"],
                "reinforcement_command_validated": False}

    monkeypatch.setattr(pvp_module, "evaluate_defense", evaluate_defense)
    result = asyncio.run(live._evaluate_cycle_defense(
        "m1", 3, (enemy, target, source),
        {1: enemy, 10: target, 20: source}, now))

    assert result["action"] == "ABSTAIN"
    assert result["source_gates"][0]["status"] == "ABSTAIN_SOURCE_SAFETY"
    assert defense_inputs[0]["reinforcement_candidates"] == []


def test_cycle_publishes_defense_assessment_to_heartbeat(tmp_path, monkeypatch):
    live = controller()
    live.root = tmp_path
    live.app.root = tmp_path
    live.cycle_seq = 3
    now = time.time()
    target = tower(10, "SELF", now=now)
    enemy = tower(1, "ENEMY", now=now)

    async def ensure_anchor(_match_id):
        return {"match_id": "m1", "towers": []}

    async def observe(match_id, cycle_id, _states, _by_id, _observed_at):
        live.journal["threat_state"] = current_threat_state(cycle_id)

    live.ensure_anchor = ensure_anchor
    live.build_states = lambda *_args: [target, enemy]
    live._observe_cycle_threat_state = observe
    live._evaluate_cycle_multi_threat = lambda *args: {
        "match_id": "m1", "cycle_id": 3, "status": "CLEAR",
        "evaluations": []}
    defense_calls = []

    async def assess(*args):
        defense_calls.append(args)
        value = {"match_id": "m1", "cycle_id": 3,
                 "status": "SUPPORTED", "action": "ABSTAIN",
                 "reason": "no-validated-candidate"}
        live.journal["defense_assessment"] = value
        live.journal["pvp_arbitration"] = {
            "action": "ABSTAIN", "evaluation_status": "SUPPORTED"}
        return value

    live._evaluate_cycle_defense = assess
    probe = tmp_path / "runtime/research/units/unit-struct-probe-m1.json"
    probe.parent.mkdir(parents=True)
    probe.write_text('{"rows": []}', encoding="utf-8")
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [])
    monkeypatch.setattr(live_controller_module,
                        "rejection_reasons", lambda *_args: [])

    phase, _info = asyncio.run(live.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert len(defense_calls) == 1
    assert live.heartbeat()["defense_assessment"]["action"] == "ABSTAIN"
    assert live.heartbeat()["pvp_arbitration"]["action"] == "ABSTAIN"
