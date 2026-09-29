"""Live SELF→SELF reinforcement stays behind every dispatch safety gate."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import kiomet_ai.live_controller as live_controller_module
from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)


def make_states(now=None):
    now = time.time() if now is None else now
    units = lambda soldier: TowerUnitCounts(
        units_kind="MANY", shield=0, fighter=0, chopper=0,
        bomber=0, tank=0, soldier=soldier)
    observation = MatchObservation(
        match_id="m1", timestamp=now,
        towers=(
            ObservedTower(tower_id=1, tower_ref=11, world_x=0, world_y=0,
                          owner="SELF", tower_type="Town",
                          owner_ruler=False, units_detail=units(12)),
            ObservedTower(tower_id=2, tower_ref=22, world_x=5, world_y=0,
                          owner="SELF", tower_type="Town",
                          owner_ruler=False, units_detail=units(3)),
        ), edges=(ObservedEdge(1, 2),))
    return {state.tower_id: state
            for state in build_real_tower_states(observation)}


def arbitration_controller():
    browser = SimpleNamespace(game={
        "state": "IN_MATCH", "match": {"id": "m1"}})
    live = LiveController(SimpleNamespace(root=Path("."), browser=browser))
    live._select_player_id_match("m1")
    live._select_reservation_match("m1")
    live.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 8, "status": "CLEAR",
        "freshness": "FRESH", "coverage": {"complete": True}}
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 8, "status": "CLEAR",
        "evaluations": []}
    live.journal["defense_assessment"] = {
        "match_id": "m1", "cycle_id": 8, "status": "SUPPORTED",
        "defense_evaluations": []}
    live.journal["attack_assessment"] = {
        "match_id": "m1", "cycle_id": 8, "evaluations": []}
    return live


def test_final_dispatch_requires_fresh_token_safety_and_held_reservation():
    live = arbitration_controller()
    states = make_states()
    force = dict(states[1].deployable_force.counts)
    defense_candidate = {
        "source_tower_id": 1,
        "full_deployable_force": force,
        "unit_count": sum(force.values()),
        "command_validated": True,
    }
    live.journal["defense_assessment"]["defense_evaluations"] = [{
        "support_status": "SUPPORTED", "tower_lost": True,
        "enemy_eta": 4, "target_tower_id": 2,
        "minimum_sufficient_reinforcement": defense_candidate,
        "reinforcement_command_validated": True,
    }]

    missing = live._arbitrate_prepared_action(
        "m1", 8, None, require_execution_evidence=True)
    assert missing["action"] == "ABSTAIN"
    assert missing["reason"] == "defense-execution-evidence-incomplete"

    action_id = "m1:1->2:8"
    assert live._reservations.reserve(action_id, 1, 2) is None
    prepared = {
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 1, "target_tower_id": 2,
        "source_owner": "SELF", "target_owner": "SELF",
        "full_deployable_force": force,
        "unit_count": sum(force.values()), "command_validated": True,
        "preflight": "READY", "source_safety": "SAFE",
        "source_safety_evidence": {
            "result": "SAFE", "match_id": "m1",
            "source_tower_id": 1, "proposed_units": force},
        "action_validity_token": "OK",
        "validity_token_match_id": "m1",
        "validity_token_cycle_id": 8,
        "reservation": "HELD", "reservation_action_id": action_id,
    }
    selected = live._arbitrate_prepared_action(
        "m1", 8, None, prepared_reinforcement=prepared,
        require_execution_evidence=True)
    assert selected["action"] == "REINFORCE_SELF"
    assert selected["selected_action_executed"] is False


def test_selected_defense_does_not_fall_back_to_neutral_without_proof(
        tmp_path, monkeypatch):
    now = time.time()
    browser = SimpleNamespace(game={
        "state": "IN_MATCH", "match": {"id": "m1"}})

    class App:
        def __init__(self):
            self.root = tmp_path
            self.browser = browser
            self.autonomy_paused = False
            self.execute_calls = []

        async def execute_move(self, payload):
            self.execute_calls.append(payload)
            return {"sent": True}

    app = App()
    live = LiveController(app)
    live._select_player_id_match("m1")
    live._select_reservation_match("m1")
    states = make_states(now)
    anchor = {"match_id": "m1", "towers": [
        {"packed_id": 1, "tower_ref": 11, "position": [0, 0]},
        {"packed_id": 2, "tower_ref": 22, "position": [5, 0]},
    ], "edges": [[1, 2]]}
    probe = tmp_path / "runtime/research/units/unit-struct-probe-m1.json"
    probe.parent.mkdir(parents=True)
    probe.write_text(json.dumps({"match_id": "m1", "rows": []}),
                     encoding="utf-8")

    async def ready(value):
        return value

    live.ensure_anchor = lambda _match: ready(anchor)
    live.build_states = lambda *_args: list(states.values())
    live._check_pending_captures = lambda *_args: None
    live._reconcile_pending_dispatch = lambda *_args: False

    async def observe(match_id, cycle_id, *_args):
        live.journal["threat_state"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "CLEAR", "freshness": "FRESH",
            "coverage": {"complete": True}, "threats": []}

    live._observe_cycle_threat_state = observe
    live._evaluate_cycle_multi_threat = lambda match_id, cycle_id, *_args: (
        live.journal.__setitem__("multi_threat_evaluation", {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "CLEAR", "evaluations": []}))

    async def defense(match_id, cycle_id, *_args):
        force = dict(states[1].deployable_force.counts)
        candidate = {
            "source_tower_id": 1,
            "full_deployable_force": force,
            "unit_count": sum(force.values()),
            "command_validated": False,
        }
        live.journal["defense_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "action": "REINFORCE_SELF",
            "arbitration": {
                "action": "REINFORCE_SELF",
                "evaluation_status": "SUPPORTED",
                "match_id": match_id, "cycle_id": cycle_id,
                "candidate": candidate, "target_tower_id": 2,
            },
            "defense_evaluations": [],
        }

    async def attack(match_id, cycle_id, *_args):
        live.journal["attack_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "NO_CONFIDENT_ENEMY_TARGETS", "evaluations": []}

    live._evaluate_cycle_defense = defense
    live._evaluate_cycle_attack_candidates = attack
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [])

    phase, info = asyncio.run(live.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == (
        "PVP_REINFORCEMENT_PROPOSAL_reinforcement_command_validated")
    assert app.execute_calls == []


def test_restart_reconciliation_keeps_reinforcement_action_kind(monkeypatch):
    live = arbitration_controller()
    states = make_states()
    live.journal["pending_dispatch"] = {
        "match_id": "m1", "source_tower_id": 1,
        "target_tower_id": 2, "action_kind": "REINFORCE_SELF",
        "before": {"match_id": "m1", "source": {"units": 12},
                   "target": {"owner": "SELF"}},
    }
    live.snapshot_tower = lambda state: {"owner": state.owner,
                                        "units": {"soldier": 3}}
    observed = {}

    def verify(before, after, proposal):
        observed["action_kind"] = proposal.action_kind
        return "UNKNOWN"

    monkeypatch.setattr(live_controller_module, "verify_post_action", verify)

    assert live._reconcile_pending_dispatch(states, "m1") is True
    assert observed["action_kind"] == "REINFORCE_SELF"


def test_validated_reinforcement_uses_existing_dispatch_and_verification_loop(
        tmp_path, monkeypatch):
    from kiomet_ai.pvp import arbitrate_pvp_action

    now = time.time()
    browser = SimpleNamespace(game={
        "state": "IN_MATCH", "match": {"id": "m1"},
        "join_clicks": 1}, session_id="test-session")

    class App:
        def __init__(self):
            self.root = tmp_path
            self.browser = browser
            self.autonomy_paused = False
            self.execute_calls = []
            self.verifications = []
            self.actions = []

        async def execute_move(self, payload):
            self.execute_calls.append(payload)
            return {"sent": True, "result": "sent"}

        def record_verification(self, verdict, match_id):
            self.verifications.append((verdict, match_id))

        def append_live_action(self, record):
            self.actions.append(record)

    app = App()
    live = LiveController(app)
    live._select_player_id_match("m1")
    live._select_reservation_match("m1")
    states = make_states(now)
    force = dict(states[1].deployable_force.counts)
    candidate = {
        "source_tower_id": 1, "full_deployable_force": force,
        "unit_count": sum(force.values()), "command_validated": True,
    }
    defense_row = {
        "support_status": "SUPPORTED", "tower_lost": True,
        "enemy_eta": 4, "target_tower_id": 2,
        "minimum_sufficient_reinforcement": candidate,
        "reinforcement_command_validated": True,
    }
    arbitration = arbitrate_pvp_action(
        defense_evaluations=[defense_row], attack_evaluations=[],
        neutral_expansion_candidate=None)
    anchor = {"match_id": "m1", "towers": [
        {"packed_id": 1, "tower_ref": 11, "position": [0, 0]},
        {"packed_id": 2, "tower_ref": 22, "position": [5, 0]},
    ], "edges": [[1, 2]]}
    probe = tmp_path / "runtime/research/units/unit-struct-probe-m1.json"
    probe.parent.mkdir(parents=True)
    probe.write_text(json.dumps({"match_id": "m1", "rows": []}),
                     encoding="utf-8")

    async def ready(value):
        return value

    live.ensure_anchor = lambda _match: ready(anchor)
    live.build_states = lambda *_args: list(states.values())
    live._check_pending_captures = lambda *_args: None

    async def observe(match_id, cycle_id, *_args):
        live.journal["threat_state"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
            "coverage": {"complete": True}, "threats": []}

    live._observe_cycle_threat_state = observe
    live._evaluate_cycle_multi_threat = lambda match_id, cycle_id, *_args: (
        live.journal.__setitem__("multi_threat_evaluation", {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SAFE", "evaluations": []}))

    async def defense(match_id, cycle_id, *_args):
        bound_candidate = {**candidate, "match_id": match_id,
                           "cycle_id": cycle_id}
        live.journal["defense_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "action": "REINFORCE_SELF",
            "arbitration": {**arbitration,
                            "candidate": bound_candidate,
                            "target_tower_id": 2,
                            "match_id": match_id,
                            "cycle_id": cycle_id},
            "defense_evaluations": [defense_row],
        }

    async def attack(match_id, cycle_id, *_args):
        live.journal["attack_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "NO_CONFIDENT_ENEMY_TARGETS", "evaluations": []}

    live._evaluate_cycle_defense = defense
    live._evaluate_cycle_attack_candidates = attack
    live._run_tool = lambda *_args: ready((0, ""))
    live.snapshot_collections = lambda tower_ref: ready({
        "tower_ref": tower_ref, "match_id": "m1",
        "captured_at": time.time(), "collections": {
            "inbound": {"length": 0, "entries": []},
            "outbound": {"length": 0, "entries": []}}})
    live.fresh_screen_map = lambda _towers: ready((
        {1: (100, 100), 2: (150, 100)},
        {"w": 800, "h": 600, "camera": (0, 1, 2),
         "viewport": (800, 600), "dpr": 1,
         "canvas_rect": (0, 0, 800, 600)}))
    live._build_dispatch_token = lambda *_args: (object(), "OK")
    live.evaluate_live_source_safety = lambda *_args, **_kwargs: {
        "result": "SAFE", "reason": "verified-test-snapshot"}
    live.snapshot_tower = lambda state: {
        "owner": state.owner,
        "units": dict(state.deployable_force.counts)}
    correlate_calls = []

    def correlate_force(*args, dispatched_at=None):
        correlate_calls.append((args, dispatched_at))
        return "FORCE_MATCH_VERIFIED"

    live.correlate_force = correlate_force
    live._record_dispatch_observation = lambda *_args: "FORCE_OBSERVED"
    live._save_force_bundle = lambda *_args, **_kwargs: None
    live._record_battle_differential = lambda *_args: None

    async def no_sleep(_duration):
        return None

    monkeypatch.setattr(live_controller_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [])

    phase, info = asyncio.run(live.cycle_once())

    assert phase == "VERIFYING", info
    assert len(app.execute_calls) == 1
    assert app.execute_calls[0]["match_id"] == "m1"
    assert app.execute_calls[0]["source"] == [100, 100]
    assert app.execute_calls[0]["target"] == [150, 100]
    assert live.journal["pvp_arbitration"]["selected_action_executed"] is True
    assert live.journal["pvp_arbitration"]["dispatched_action"] == "REINFORCE_SELF"
    assert live.journal["last_action"]["action_kind"] == "REINFORCE_SELF"
    sent_at = live.journal["last_action"]["sent_at"]
    assert len(correlate_calls) == 2
    assert all(call[1] == sent_at for call in correlate_calls)
    assert live.journal["last_verification"] == "FORCE_OBSERVED"
    assert live.journal["verified_expansions"] == 0
    assert live.journal.get("pending_captures", []) == []
    assert app.verifications == [("FORCE_OBSERVED", "m1")]
