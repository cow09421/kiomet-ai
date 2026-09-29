"""Live SELF→ENEMY dispatch requires match-bound battle and server proof."""
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


def make_states(now=None, *, enemy_neighbor=True):
    now = time.time() if now is None else now

    def units(soldier):
        return TowerUnitCounts(
            units_kind="MANY", shield=0, fighter=0, chopper=0,
            bomber=0, tank=0, soldier=soldier, observed_at=now)

    edges = [ObservedEdge(1, 3)]
    if enemy_neighbor:
        edges.append(ObservedEdge(1, 2))
    observation = MatchObservation(
        match_id="m1", timestamp=now,
        towers=(
            ObservedTower(tower_id=1, tower_ref=11, world_x=0, world_y=0,
                          owner="SELF", owner_confidence="HIGH",
                          tower_type="Town", owner_ruler=False,
                          units_detail=units(24)),
            ObservedTower(tower_id=2, tower_ref=22, world_x=5, world_y=0,
                          owner="ENEMY", owner_confidence="HIGH",
                          tower_type="Town", owner_ruler=False,
                          units_detail=units(3)),
            ObservedTower(tower_id=3, tower_ref=33, world_x=0, world_y=5,
                          owner="NEUTRAL", owner_confidence="HIGH",
                          tower_type="Town", owner_ruler=False,
                          units_detail=units(2)),
        ), edges=tuple(edges))
    return {state.tower_id: state
            for state in build_real_tower_states(observation)}


def safe_attack_candidate(states, *, match_id="m1", cycle_id=8):
    force = dict(states[1].deployable_force.counts)
    binding = {
        "match_id": match_id, "cycle_id": cycle_id,
        "source_tower_id": 1, "target_tower_id": 2,
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
        "match_id": match_id, "cycle_id": cycle_id,
        "source_tower_id": 1, "target_tower_id": 2,
        "target_relation": "ENEMY", "target_owner_confidence": "HIGH",
        "attacker_owner_id": 7, "defender_owner_id": 22,
        "source_safety": "SAFE",
        "source_safety_evidence": {
            "result": "SAFE", "match_id": match_id,
            "source_tower_id": 1, "proposed_units": force},
        "proposed_units": force,
        "action_validity_token": "OK",
        "validity_token_match_id": match_id,
        "validity_token_cycle_id": cycle_id,
        "reservation": "AVAILABLE_NOT_HELD",
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


def static_dispatch_candidate(states, *, match_id="m1", cycle_id=8):
    """只含派前靜態預測；派後 proof 必須等待真實執行觀察。"""
    candidate = safe_attack_candidate(
        states, match_id=match_id, cycle_id=cycle_id)
    for key in (
            "battle_differential_evidence_id",
            "server_acceptance_evidence_id",
            "battle_differential_evidence",
            "server_acceptance_evidence"):
        candidate.pop(key, None)
    candidate.update({
        "safe_attack_candidate": False,
        "dispatch_safe_candidate": True,
        "static_support_status": "SUPPORTED",
        "evaluation_status": "UNKNOWN",
        "battle_differential_validated": False,
        "server_acceptance_validated": False,
        "runtime_validation_required": True,
    })
    return candidate


def test_attack_proof_ids_require_matching_evidence_envelopes():
    from kiomet_ai.live_controller import _attack_proof_provenance_matches

    candidate = safe_attack_candidate(make_states())
    assert _attack_proof_provenance_matches(candidate, "m1", 8)

    placeholder = dict(candidate)
    placeholder.pop("battle_differential_evidence")
    placeholder.pop("server_acceptance_evidence")
    assert not _attack_proof_provenance_matches(placeholder, "m1", 8)

    placeholder_ids = dict(candidate)
    placeholder_ids["battle_differential_evidence_id"] = "battle-proof-1"
    assert not _attack_proof_provenance_matches(placeholder_ids, "m1", 8)

    altered = dict(candidate)
    altered["battle_differential_evidence"] = {
        **candidate["battle_differential_evidence"],
        "result": "ATTACK_LOSS"}
    assert not _attack_proof_provenance_matches(altered, "m1", 8)

    cross_match = dict(candidate)
    cross_match["battle_differential_evidence"] = {
        **candidate["battle_differential_evidence"], "match_id": "m2"}
    assert not _attack_proof_provenance_matches(cross_match, "m1", 8)

    wrong_target = dict(candidate)
    wrong_target["server_acceptance_evidence"] = {
        **candidate["server_acceptance_evidence"], "target_tower_id": 99}
    assert not _attack_proof_provenance_matches(wrong_target, "m1", 8)

    self_reinforcement = dict(candidate)
    self_reinforcement["server_acceptance_evidence"] = {
        **candidate["server_acceptance_evidence"],
        "target_relation": "SELF", "action_kind": "REINFORCE_SELF"}
    assert not _attack_proof_provenance_matches(self_reinforcement, "m1", 8)


def prepared_attack(live, candidate, *, preflight="READY"):
    action_id = "m1:8:1->2"
    assert live._reservations.reserve(action_id, 1, 2) is None
    return {
        "action_kind": "ATTACK_ENEMY",
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 1, "target_tower_id": 2,
        "source_owner": "SELF", "target_owner": "ENEMY",
        "defender_owner_id": candidate["defender_owner_id"],
        "proposed_units": candidate["proposed_units"],
        "preflight": preflight, "source_safety": "SAFE",
        "source_safety_evidence": candidate["source_safety_evidence"],
        "action_validity_token": "OK",
        "validity_token_match_id": "m1",
        "validity_token_cycle_id": 8,
        "reservation": "HELD", "reservation_action_id": action_id,
    }


def test_final_attack_dispatch_requires_complete_prepared_evidence():
    live = LiveController(SimpleNamespace(
        root=Path("."), browser=SimpleNamespace(game={
            "state": "IN_MATCH", "match": {"id": "m1"}})))
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    live._select_reservation_match("m1")
    live.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 8, "status": "CLEAR",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": [], "observed_at": time.time()}
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 8, "status": "SAFE",
        "evaluations": []}
    live.journal["defense_assessment"] = {
        "match_id": "m1", "cycle_id": 8, "status": "SUPPORTED",
        "defense_evaluations": []}
    candidate = static_dispatch_candidate(make_states())
    live.journal["attack_assessment"] = {
        "match_id": "m1", "cycle_id": 8,
        "evaluations": [candidate]}

    incomplete = live._arbitrate_prepared_action(
        "m1", 8, None, prepared_attack=prepared_attack(
            live, candidate, preflight="UNKNOWN"),
        require_execution_evidence=True)
    assert incomplete["action"] == "ATTACK_ENEMY"
    assert incomplete["execution_ready"] is False
    assert incomplete["execution_rejection_reason"] == (
        "attack-execution-evidence-incomplete")

    live._select_reservation_match(None)
    live._select_reservation_match("m1")
    selected = live._arbitrate_prepared_action(
        "m1", 8, None,
        prepared_attack=prepared_attack(live, candidate),
        require_execution_evidence=True)
    assert selected["action"] == "ATTACK_ENEMY"
    assert selected["selected_action_executed"] is False


def _cycle_harness(tmp_path, monkeypatch, *, candidate, enemy_neighbor=True):
    now = time.time()
    browser = SimpleNamespace(game={
        "state": "IN_MATCH", "match": {"id": "m1"},
        "join_clicks": 1}, session_id="offline-test")

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
    live.cycle_seq = 8
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    live._select_reservation_match("m1")
    states = make_states(now, enemy_neighbor=enemy_neighbor)
    anchor = {"match_id": "m1", "towers": [
        {"packed_id": 1, "tower_ref": 11, "position": [0, 0]},
        {"packed_id": 2, "tower_ref": 22, "position": [5, 0]},
        {"packed_id": 3, "tower_ref": 33, "position": [0, 5]},
    ], "edges": [[1, 2], [1, 3]]}
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
            "status": "SAFE", "evaluations": []}))
    async def defense(match_id, cycle_id, *_args):
        live.journal["defense_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "action": "ABSTAIN",
            "defense_evaluations": []}

    live._evaluate_cycle_defense = defense

    async def attack(match_id, cycle_id, *_args):
        bound = {**candidate, "match_id": match_id, "cycle_id": cycle_id}
        live.journal["attack_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "OBSERVED_CANDIDATE", "evaluations": [bound],
            "arbitration": {
                "action": "ATTACK_ENEMY",
                "evaluation_status": (
                    "SUPPORTED_STATIC"
                    if bound.get("dispatch_safe_candidate") is True
                    else "SUPPORTED"),
                "match_id": match_id, "cycle_id": cycle_id,
                "candidate": bound, "target_tower_id": 2,
            }}

    live._evaluate_cycle_attack_candidates = attack
    live._run_tool = lambda *_args: ready((0, ""))
    live.snapshot_collections = lambda tower_ref: ready({
        "tower_ref": tower_ref, "match_id": "m1",
        "captured_at": time.time(), "collections": {
            "inbound": {"length": 0, "entries": []},
            "outbound": {"length": 0, "entries": []}}})
    live.fresh_screen_map = lambda _towers: ready((
        {1: (100, 100), 2: (150, 100), 3: (200, 100)},
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
    force_bundle_dispatch_times = []

    def save_force_bundle(*_args, dispatch_sent_at=None):
        force_bundle_dispatch_times.append(dispatch_sent_at)

    live._save_force_bundle = save_force_bundle
    live._record_battle_differential = lambda *_args: None

    async def no_sleep(_duration):
        return None

    monkeypatch.setattr(live_controller_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [{
                            "source": 1, "target": 3,
                            "heuristic_score": 10,
                            "reason": "neutral-fallback"}])
    live.test_correlate_calls = correlate_calls
    live.test_force_bundle_dispatch_times = force_bundle_dispatch_times
    return live, app


def test_invalid_selected_attack_proof_or_proposal_never_falls_back_to_neutral(
        tmp_path, monkeypatch):
    states = make_states()
    invalid_proof = static_dispatch_candidate(states)
    invalid_proof["server_acceptance_evidence"] = {
        "status": "ACCEPTED", "server_accepted": True,
        "action_kind": "ATTACK_ENEMY"}
    live, app = _cycle_harness(
        tmp_path / "bad-proof", monkeypatch, candidate=invalid_proof)

    phase, info = asyncio.run(live.cycle_once())
    assert phase == "NO_SAFE_PROPOSAL", info
    assert info["reason"] == "PVP_ATTACK_EVIDENCE_INCOMPLETE"
    assert app.execute_calls == []
    assert live.journal.get("current_proposal") is None

    states = make_states()
    no_neighbor = static_dispatch_candidate(states)
    live, app = _cycle_harness(
        tmp_path / "bad-proposal", monkeypatch,
        candidate=no_neighbor, enemy_neighbor=False)
    phase, info = asyncio.run(live.cycle_once())
    assert phase == "NO_SAFE_PROPOSAL", info
    assert info["reason"].startswith("PVP_ATTACK_PROPOSAL_")
    assert app.execute_calls == []


def test_static_enemy_attack_dispatches_and_leaves_runtime_proof_pending(
        tmp_path, monkeypatch):
    candidate = static_dispatch_candidate(make_states())
    live, app = _cycle_harness(tmp_path, monkeypatch, candidate=candidate)
    pending_records = []
    set_pending = live._set_pending_dispatch

    def capture_pending(record):
        pending_records.append(json.loads(json.dumps(record)))
        set_pending(record)

    live._set_pending_dispatch = capture_pending

    phase, info = asyncio.run(live.cycle_once())

    assert phase == "VERIFYING", info
    assert len(app.execute_calls) == 1
    assert app.execute_calls[0]["match_id"] == "m1"
    assert app.execute_calls[0]["source"] == [100, 100]
    assert app.execute_calls[0]["target"] == [150, 100]
    assert live.journal["pvp_arbitration"]["selected_action_executed"] is True
    assert live.journal["pvp_arbitration"]["dispatched_action"] == "ATTACK_ENEMY"
    assert live.journal["last_action"]["action_kind"] == "ATTACK_ENEMY"
    assert live.journal["last_action"]["cycle_id"] == 8
    assert live.journal["last_action"]["attack_proof_bundle"] is None
    assert live.journal["last_action"]["attack_validation_status"] == (
        "VALIDATION_PENDING")
    dispatch_sent_at = live.journal["last_action"]["sent_at"]
    assert dispatch_sent_at > 0
    assert app.actions[0]["dispatch"]["sent_at"] == dispatch_sent_at
    assert live.journal["pending_captures"][-1]["since"] == dispatch_sent_at
    assert len(live.test_correlate_calls) == 2
    assert all(call[1] == dispatch_sent_at
               for call in live.test_correlate_calls)
    assert live.test_force_bundle_dispatch_times == [dispatch_sent_at]
    assert pending_records[0]["attack_validation_status"] == (
        "VALIDATION_PENDING")
    assert app.actions[0]["attack_proof_bundle"] is None
    assert app.actions[0]["attack_validation_status"] == (
        "VALIDATION_PENDING")
    assert app.actions[0]["cycle_id"] == 8
    assert live.journal["last_verification"] == "FORCE_OBSERVED"
    assert live.journal["pending_captures"][-1]["target"] == 2
    assert live.journal["pending_captures"][-1]["action_kind"] == (
        "ATTACK_ENEMY")
    assert live.journal["pending_captures"][-1][
        "dispatch_observation"] == "FORCE_OBSERVED"
    assert live.journal["pending_captures"][-1][
        "target_owner_before"] == "ENEMY"
    assert app.verifications == [("FORCE_OBSERVED", "m1")]
