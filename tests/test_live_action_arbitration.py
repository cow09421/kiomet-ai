"""LiveController 最終派送邊界的 PVP 仲裁優先序。"""
import asyncio
import hashlib
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
    UNIT_NAMES,
    build_real_tower_states,
)
from kiomet_ai.proposal import PREFLIGHT_READY


def controller():
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})
    live = LiveController(SimpleNamespace(root=Path("."), browser=browser))
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    live._select_reservation_match("m1")
    live.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 8,
        "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
        "coverage": {"complete": True}, "threats": [],
        "observed_at": time.time()}
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 8,
        "status": "SAFE", "evaluations": []}
    live.journal["defense_assessment"] = {
        "match_id": "m1", "cycle_id": 8, "status": "SUPPORTED",
        "action": "ABSTAIN", "defense_evaluations": []}
    live.journal["attack_assessment"] = {
        "match_id": "m1", "cycle_id": 8,
        "status": "NO_CONFIDENT_ENEMY_TARGETS", "evaluations": []}
    return live


def neutral_candidate(live, *, token="OK", reservation="HELD"):
    action_id = "m1:8:10->20"
    if reservation == "HELD":
        assert live._reservations.reserve(action_id, 10, 20) is None
    return {"validated": True, "match_id": "m1", "cycle_id": 8,
            "source_tower_id": 10, "target_tower_id": 20,
            "preflight": "READY", "source_safety": "SAFE",
            "action_validity_token": token, "reservation": reservation,
            "reservation_action_id": action_id}


def safe_attack(live):
    action_id = "m1:8:11->31"
    assert live._reservations.reserve(action_id, 11, 31) is None
    force = {name: 0 for name in UNIT_NAMES}
    force["Soldier"] = 20
    binding = {
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 11, "target_tower_id": 31,
        "attacker_owner_id": 7, "defender_owner_id": 22,
        "target_relation": "ENEMY", "proposed_units": force,
    }
    def with_digest(evidence):
        encoded = json.dumps(
            evidence, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        return {**evidence,
                "evidence_id": "sha256:" + hashlib.sha256(encoded).hexdigest()}

    battle_evidence = with_digest({
        **binding,
        "status": "VALIDATED", "support_status": "MATCH",
        "result": "ATTACK_WIN", "legality": "LEGAL_STATIC_SHAPE",
        "safety_margin": "ROBUST_WIN", "runtime_validated": True,
    })
    server_evidence = with_digest({
        **binding,
        "status": "ACCEPTED", "server_accepted": True,
        "command_kind": "DeployForce", "action_kind": "ATTACK_ENEMY",
    })
    return {
        "safe_attack_candidate": True,
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 11, "target_tower_id": 31,
        "target_relation": "ENEMY", "target_owner_confidence": "HIGH",
        "attacker_owner_id": 7, "defender_owner_id": 22,
        "source_safety": "SAFE",
        "source_safety_evidence": {
            "result": "SAFE", "match_id": "m1",
            "source_tower_id": 11, "proposed_units": force},
        "proposed_units": force,
        "action_validity_token": "OK",
        "validity_token_match_id": "m1", "validity_token_cycle_id": 8,
        "reservation": "HELD", "reservation_action_id": action_id,
        "battle_differential_validated": True,
        "battle_differential_evidence_id": battle_evidence["evidence_id"],
        "server_acceptance_validated": True,
        "server_acceptance_evidence_id": server_evidence["evidence_id"],
        "result": "ATTACK_WIN", "legality": "LEGAL_STATIC_SHAPE",
        "evaluation_status": "SUPPORTED", "battle_supported": True,
        "safety_margin": "ROBUST_WIN",
        "runtime_validation_required": False,
        "battle_differential_evidence": battle_evidence,
        "server_acceptance_evidence": server_evidence,
    }


def test_arbitration_prefers_verified_defense_over_attack_and_neutral():
    live = controller()
    live.journal["defense_assessment"]["defense_evaluations"] = [{
        "support_status": "SUPPORTED", "tower_lost": True,
        "enemy_eta": 2, "target_tower_id": 20,
        "minimum_sufficient_reinforcement": {
            "source_tower_id": 10, "unit_count": 4,
            "command_validated": True},
        "reinforcement_command_validated": True}]
    live.journal["attack_assessment"]["evaluations"] = [safe_attack(live)]

    decision = live._arbitrate_prepared_action(
        "m1", 8, neutral_candidate(live))

    assert decision["action"] == "REINFORCE_SELF"
    assert decision["selected_action_executed"] is False


def test_arbitration_prefers_safe_attack_over_validated_neutral():
    live = controller()
    live.journal["attack_assessment"]["evaluations"] = [safe_attack(live)]

    decision = live._arbitrate_prepared_action(
        "m1", 8, neutral_candidate(live))

    assert decision["action"] == "ATTACK_ENEMY"
    assert decision["selected_action_executed"] is False


def test_arbitration_uses_neutral_only_when_no_verified_pvp_candidate():
    live = controller()

    decision = live._arbitrate_prepared_action(
        "m1", 8, neutral_candidate(live))

    assert decision["action"] == "EXPAND_NEUTRAL"
    assert decision["evaluation_status"] == "SUPPORTED"


def test_safe_flag_without_all_runtime_gates_cannot_beat_neutral_fallback():
    live = controller()
    live.journal["attack_assessment"]["evaluations"] = [{
        "safe_attack_candidate": True, "source_tower_id": 11,
        "target_tower_id": 31, "result": "ATTACK_WIN"}]

    decision = live._arbitrate_prepared_action(
        "m1", 8, neutral_candidate(live))

    assert decision["action"] == "EXPAND_NEUTRAL"


def test_unknown_defense_blocks_attack_and_neutral_fallback():
    live = controller()
    live.journal["defense_assessment"]["status"] = "UNKNOWN"
    live.journal["defense_assessment"]["defense_evaluations"] = [{
        "support_status": "UNKNOWN", "tower_lost": None,
        "enemy_eta": None, "target_tower_id": 20}]
    live.journal["attack_assessment"]["evaluations"] = [{
        "safe_attack_candidate": True, "source_tower_id": 10,
        "target_tower_id": 30}]

    decision = live._arbitrate_prepared_action(
        "m1", 8, neutral_candidate(live))

    assert decision["action"] == "ABSTAIN"
    assert decision["reason"] == "defense-assessment-stale-or-unresolved"


def test_stale_threat_cycle_and_missing_token_or_reservation_abstain():
    live = controller()
    candidate = neutral_candidate(live, reservation="MISSING")
    decision = live._arbitrate_prepared_action("m1", 8, candidate)
    assert decision["action"] == "ABSTAIN"

    live.journal["threat_state"]["cycle_id"] = 7
    decision = live._arbitrate_prepared_action(
        "m1", 8, {**candidate, "reservation": "HELD"})
    assert decision["action"] == "ABSTAIN"
    assert decision["reason"] == "MULTI_THREAT_STALE_OR_INCOMPLETE"


def test_multi_threat_block_rejects_old_match_or_cycle_even_if_safe():
    live = controller()
    live.journal["multi_threat_evaluation"]["match_id"] = "old-match"

    blocked = live._multi_threat_action_block("m1", 8)

    assert blocked["reason"] == "MULTI_THREAT_STALE_OR_INCOMPLETE"


def test_final_dispatch_boundary_does_not_run_neutral_after_attack_wins(
        tmp_path, monkeypatch):
    now = time.time()
    probe = tmp_path / "runtime/research/units/unit-struct-probe-m1.json"
    probe.parent.mkdir(parents=True)
    probe.write_text('{"match_id":"m1","rows":[]}', encoding="utf-8")
    (tmp_path / "runtime/research/source-map").mkdir(parents=True)
    (tmp_path / "runtime/research/source-map/verified-anchor-current.json").write_text(
        "{}", encoding="utf-8")
    counts_by_tower = lambda soldier: TowerUnitCounts(
        units_kind="MANY", shield=0, fighter=0, chopper=0,
        bomber=0, tank=0, soldier=soldier)
    states = build_real_tower_states(MatchObservation(
        match_id="m1", timestamp=now,
        towers=(
            ObservedTower(tower_id=1, tower_ref=11, world_x=0, world_y=0,
                          owner="SELF", tower_type="Town",
                          owner_ruler=False,
                          units_detail=counts_by_tower(12)),
            ObservedTower(tower_id=2, tower_ref=22, world_x=5, world_y=0,
                          owner="NEUTRAL", tower_type="Town",
                          owner_ruler=False,
                          units_detail=counts_by_tower(2)),
        ), edges=(ObservedEdge(1, 2),)))
    anchor = {"match_id": "m1", "towers": [
        {"packed_id": 1, "tower_ref": 11, "position": [0, 0]},
        {"packed_id": 2, "tower_ref": 22, "position": [5, 0]},
    ]}
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})

    class App:
        def __init__(self):
            self.root = tmp_path
            self.browser = browser
            self.autonomy_paused = False
            self.execute_calls = []

        async def execute_move(self, payload):
            self.execute_calls.append(payload)
            return {"sent": False, "result": "should-not-run"}

    app = App()
    live = LiveController(app)
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    live._select_reservation_match("m1")
    live.ensure_anchor = lambda _match_id: asyncio.sleep(0, result=anchor)
    live.build_states = lambda *_args: states
    live._check_pending_captures = lambda *_args: None
    live._run_tool = lambda *_args: asyncio.sleep(0, result=(0, ""))

    async def snapshot(tower_ref):
        return {"tower_ref": tower_ref, "match_id": "m1",
                "captured_at": time.time(), "collections": {
                    "inbound": {"length": 0, "entries": []},
                    "outbound": {"length": 0, "entries": []}}}

    live.snapshot_collections = snapshot
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
        live.journal["defense_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "action": "ABSTAIN",
            "defense_evaluations": []}

    async def attack(match_id, cycle_id, *_args):
        row = safe_attack(live)
        row.update({"match_id": match_id, "cycle_id": cycle_id,
                    "validity_token_match_id": match_id,
                    "validity_token_cycle_id": cycle_id})
        live.journal["attack_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "OBSERVED_CANDIDATE", "evaluations": [row]}

    live._evaluate_cycle_defense = defense
    live._evaluate_cycle_attack_candidates = attack
    live.fresh_screen_map = lambda _towers: asyncio.sleep(0, result=(
        {1: (100, 100), 2: (150, 100)},
        {"w": 800, "h": 600, "camera": (0, 1, 2),
         "viewport": (800, 600), "dpr": 1,
         "canvas_rect": (0, 0, 800, 600)}))
    live._build_dispatch_token = lambda *_args: (object(), "OK")
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [{
                            "source": 1, "target": 2,
                            "heuristic_score": 1}])
    monkeypatch.setattr(live_controller_module, "build_proposal",
                        lambda *_args: SimpleNamespace(
                            status="READY", source_tower_id=1,
                            target_tower_id=2,
                            source_deployable_force=dict(
                                states[0].deployable_force.counts)))
    monkeypatch.setattr(live_controller_module, "prepare_move",
                        lambda *_args: (PREFLIGHT_READY, SimpleNamespace(
                            source_tower_id=1, target_tower_id=2,
                            source_screen_xy=(100, 100),
                            target_screen_xy=(150, 100))))
    live.evaluate_live_source_safety = lambda *_args, **_kwargs: {
        "result": "SAFE", "reason": "test-safe"}

    phase, info = asyncio.run(live.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == "PVP_ARBITRATION_ATTACK_ENEMY"
    assert info["pvp_arbitration"]["action"] == "ATTACK_ENEMY"
    assert app.execute_calls == []
