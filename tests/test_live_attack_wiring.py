"""LiveController 敵方攻擊候選的同局證據與仲裁接線。"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import kiomet_ai.pvp as pvp_module
from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import UNIT_NAMES, TowerUnitCounts


def counts(soldier):
    result = {name: 0 for name in UNIT_NAMES}
    result["Soldier"] = soldier
    return result


def make_tower(tower_id, owner, *, neighbors=(), owner_confidence="HIGH",
               soldiers=12, deployable=0, now=None):
    now = time.time() if now is None else now
    return SimpleNamespace(
        tower_id=tower_id, tower_ref=tower_id + 1000, match_id="m1",
        owner=owner, owner_confidence=owner_confidence,
        tower_type="Town", owner_ruler=False,
        world_x=float(tower_id), world_y=0.0,
        neighbors=tuple(neighbors), timestamp=now,
        freshness=lambda match_id, _now: (
            "FRESH" if match_id == "m1" else "STALE"),
        unit_counts=TowerUnitCounts(
            units_kind="MANY", shield=0, fighter=0, chopper=0,
            bomber=0, tank=0, soldier=soldiers, observed_at=now),
        deployable_force=SimpleNamespace(
            counts=counts(deployable), status="CANDIDATE"),
        deployable_force_confidence="DERIVED")


def controller():
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})
    app = SimpleNamespace(root=Path("."), browser=browser)
    live = LiveController(app)
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    live.journal["threat_state"] = {
        "match_id": "m1", "cycle_id": 4, "status": "CLEAR",
        "freshness": "FRESH", "coverage": {"complete": True},
        "threats": [], "observed_at": time.time()}
    live.journal["multi_threat_evaluation"] = {
        "match_id": "m1", "cycle_id": 4, "status": "CLEAR",
        "evaluations": []}
    live.journal["defense_assessment"] = {
        "match_id": "m1", "cycle_id": 4, "status": "SUPPORTED",
        "action": "ABSTAIN", "defense_evaluations": []}
    return live


def empty_snapshot(tower_ref, now):
    return {"tower_ref": tower_ref, "match_id": "m1",
            "captured_at": now,
            "collections": {
                "inbound": {"length": 0, "entries": []},
                "outbound": {"length": 0, "entries": []},
            }}


def test_cycle_attack_adapter_exposes_static_candidate_without_faking_runtime_proof(
        monkeypatch):
    live = controller()
    now = time.time()
    source = make_tower(10, "SELF", neighbors=(20,), soldiers=20,
                        deployable=20, now=now)
    target = make_tower(20, "ENEMY", neighbors=(10,), soldiers=3,
                        now=now)
    target_snapshot = empty_snapshot(target.tower_ref, now)
    target_snapshot["collections"]["outbound"] = {
            "length": 1,
            "entries": [{"ref": 9001, "path": (99, 20), "owner_id": 22,
                         "units": counts(1), "speed_flag": 0,
                     "progress": 4, "endurance": 10}],
    }
    reads = []

    async def snapshot(tower_ref):
        reads.append(tower_ref)
        return (target_snapshot if tower_ref == target.tower_ref else
                empty_snapshot(tower_ref, now))

    live.snapshot_collections = snapshot
    live.evaluate_live_source_safety = lambda match, source, _snapshot, proposed_units, **_kwargs: {
        "result": "SAFE", "reason": "source-safe", "match_id": match,
        "source_tower_id": source.tower_id,
        "proposed_units": dict(proposed_units)}
    live.fresh_screen_map = lambda _towers: asyncio.sleep(0, result=(
        {10: (1.0, 1.0), 20: (2.0, 2.0)},
        {"camera": (0, 1, 2), "w": 800, "h": 600}))
    live._build_dispatch_token = lambda *_args, **_kwargs: (
        object(), "OK")
    battle_cases = []

    def battle(case):
        battle_cases.append(case)
        return {"supported": True,
                "support_status": "RUNTIME_VALIDATION_NEEDED",
                "static_support_status": "SUPPORTED",
                "evaluation_status": "UNKNOWN",
                "winner": "attacker",
                "attacker_survivors": dict(case["attacker_units"]),
                "defender_survivors": {},
                "runtime_validation_required": True}

    monkeypatch.setattr(pvp_module, "evaluate_battle", battle)
    result = asyncio.run(live._evaluate_cycle_attack_candidates(
        "m1", 4, [source, target], {10: source, 20: target},
        {"towers": [{"packed_id": 10}, {"packed_id": 20}]}, now))

    assert len(battle_cases) == 1
    assert battle_cases[0]["attacker_owner_id"] == 7
    assert battle_cases[0]["defender_owner_id"] == 22
    assert battle_cases[0]["battle_differential_validated"] is False
    assert result["evaluations"][0]["server_acceptance_validated"] is False
    assert result["evaluations"][0]["action_validity_token"] == "OK"
    assert result["evaluations"][0]["reservation"] == "AVAILABLE_NOT_HELD"
    assert result["evaluations"][0]["safe_attack_candidate"] is False
    assert result["evaluations"][0]["dispatch_safe_candidate"] is True
    assert result["evaluations"][0]["static_support_status"] == "SUPPORTED"
    assert result["evaluations"][0]["runtime_validation_required"] is True
    assert result["arbitration"]["action"] == "ATTACK_ENEMY"
    assert result["arbitration"]["evaluation_status"] == "SUPPORTED_STATIC"
    assert result["execution"] == "NOT_ATTEMPTED_P0D_ASSESSMENT_ONLY"
    assert reads == [target.tower_ref, source.tower_ref]


def test_unknown_enemy_owner_confidence_does_not_read_target_or_dispatch():
    live = controller()
    now = time.time()
    source = make_tower(10, "SELF", neighbors=(20,), now=now)
    target = make_tower(20, "ENEMY", neighbors=(10,),
                        owner_confidence="UNKNOWN", now=now)
    reads = []

    async def snapshot(tower_ref):
        reads.append(tower_ref)
        return empty_snapshot(tower_ref, now)

    live.snapshot_collections = snapshot
    result = asyncio.run(live._evaluate_cycle_attack_candidates(
        "m1", 4, [source, target], {10: source, 20: target},
        {"towers": []}, now))

    assert result["evaluations"][0]["reason"] == (
        "enemy-owner-confidence-not-high")
    assert result["evaluations"][0]["safe_attack_candidate"] is False
    assert result["arbitration"]["action"] == "ABSTAIN"
    assert reads == []


def test_low_confidence_source_owner_fails_closed_without_force_snapshot():
    live = controller()
    now = time.time()
    source = make_tower(10, "SELF", neighbors=(20,),
                        owner_confidence="MEDIUM", soldiers=20,
                        deployable=20, now=now)
    target = make_tower(20, "ENEMY", neighbors=(10,), soldiers=3, now=now)
    reads = []

    async def snapshot(tower_ref):
        reads.append(tower_ref)
        result = empty_snapshot(tower_ref, now)
        if tower_ref == target.tower_ref:
            result["collections"]["outbound"] = {
                "length": 1,
                "entries": [{"path": (99, 20), "owner_id": 22,
                             "units": counts(1), "speed_flag": 0,
                             "progress": 2, "endurance": 5}],
            }
        return result

    live.snapshot_collections = snapshot
    result = asyncio.run(live._evaluate_cycle_attack_candidates(
        "m1", 4, [source, target], {10: source, 20: target},
        {"towers": []}, now))

    assert result["unclassified_adjacent_targets"][0]["reason"] == (
        "source-owner-confidence-not-high")
    assert result["evaluations"] == []
    assert reads == []
    assert result["arbitration"]["action"] == "ABSTAIN"


def test_cross_match_or_unresolved_threat_state_blocks_attack_scan():
    live = controller()
    now = time.time()
    source = make_tower(10, "SELF", neighbors=(20,), now=now)
    target = make_tower(20, "ENEMY", neighbors=(10,), now=now)
    live.journal["multi_threat_evaluation"]["status"] = "UNKNOWN"
    reads = []

    async def snapshot(tower_ref):
        reads.append(tower_ref)
        return empty_snapshot(tower_ref, now)

    live.snapshot_collections = snapshot
    result = asyncio.run(live._evaluate_cycle_attack_candidates(
        "m1", 4, [source, target], {10: source, 20: target},
        {"towers": []}, now))

    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "current-threat-and-defense-evidence-required"
    assert reads == []
