"""The pure live attack adapter separates prediction from runtime proof."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)
from kiomet_ai.pvp_live import evaluate_attack_candidate


def many(*, soldier=0, shield=0):
    return TowerUnitCounts(
        units_kind="MANY", fighter=0, chopper=0, bomber=0, tank=0,
        soldier=soldier, shield=shield)


def states(*, match_id="m1", timestamp=995.0, target_owner="ENEMY",
           neighbor=True, source_type="Runway", source_shield=0):
    towers = (
        ObservedTower(
            tower_id=1, tower_ref=11, world_x=0, world_y=0,
            owner="SELF", owner_ruler=False, tower_type=source_type,
            units_detail=many(soldier=20, shield=source_shield)),
        ObservedTower(
            tower_id=2, tower_ref=22, world_x=5, world_y=0,
            owner=target_owner, owner_ruler=False, tower_type="Cliff",
            units_detail=many(soldier=1)),
    )
    edges = (ObservedEdge(1, 2),) if neighbor else ()
    return build_real_tower_states(MatchObservation(
        match_id=match_id, timestamp=timestamp, towers=towers, edges=edges))


def evaluate(source, target, **overrides):
    options = {
        "current_match_id": "m1",
        "self_owner_id": 7,
        "attacker_owner_id": 7,
        "defender_owner_id": 12,
        "attacker_aura": False,
        "defender_aura": False,
        "battle_differential_validated": True,
        "server_acceptance_validated": True,
        "now": 1000.0,
    }
    options["source_safety_evidence"] = {
        "result": "SAFE", "match_id": "m1", "source_tower_id": 1,
        "proposed_units": dict(source.deployable_force.counts),
    }
    options.update(overrides)
    return evaluate_attack_candidate(source, target, **options)


def test_known_fresh_attack_separates_dispatch_prediction_from_runtime_proof():
    source, target = states()

    result = evaluate(source, target)
    no_battle_proof = evaluate(
        source, target, battle_differential_validated=False)
    no_command_proof = evaluate(
        source, target, server_acceptance_validated=False)

    assert result["result"] == "ATTACK_WIN"
    assert result["safe_attack_candidate"] is True
    assert result["dispatch_safe_candidate"] is False
    assert no_battle_proof["safe_attack_candidate"] is False
    assert no_battle_proof["evaluation_status"] == "UNKNOWN"
    assert no_battle_proof["static_support_status"] == "SUPPORTED"
    assert no_battle_proof["dispatch_safe_candidate"] is True
    assert no_battle_proof["runtime_validation_required"] is True
    assert no_command_proof["safe_attack_candidate"] is False
    assert no_command_proof["dispatch_safe_candidate"] is True


def test_unknown_player_identity_abstains():
    source, target = states()

    result = evaluate(source, target, self_owner_id=None)

    assert result["safe_attack_candidate"] is False
    assert "identity" in result["unsupported_reason"]


def test_attack_requires_same_match_freshness_and_enemy_neighbor():
    fresh_source, fresh_target = states()
    stale_source, stale_target = states(timestamp=900.0)
    cross_match_source, cross_match_target = states(match_id="m2")
    ally_source, ally_target = states(target_owner="ALLY")
    non_neighbor_source, non_neighbor_target = states(neighbor=False)

    assert evaluate(stale_source, stale_target)["unsupported_reason"] == (
        "attack state is stale or freshness is unknown")
    assert evaluate(cross_match_source, cross_match_target)["unsupported_reason"] == (
        "attack states are missing or from another match")
    assert evaluate(ally_source, ally_target)["unsupported_reason"] == (
        "attack requires observed SELF-to-ENEMY ownership")
    assert evaluate(non_neighbor_source, non_neighbor_target)["unsupported_reason"] == (
        "enemy target is not a verified direct neighbor")
    assert evaluate(fresh_source, fresh_target)["safe_attack_candidate"] is True


def test_projector_shield_cannot_be_added_to_mobile_attack_force():
    source, target = states(source_type="Projector", source_shield=1)

    result = evaluate(source, target)

    assert result["safe_attack_candidate"] is False
    assert result["unsupported_reason"] == (
        "battle input does not match the exact full deployable force")


def test_attack_requires_source_safety_for_this_match_tower_and_force():
    source, target = states()
    safety = {
        "result": "SAFE", "match_id": "m1", "source_tower_id": 1,
        "proposed_units": dict(source.deployable_force.counts),
    }

    assert evaluate(source, target, source_safety_evidence=None)[
        "safe_attack_candidate"] is False
    assert evaluate(source, target, source_safety_evidence={
        **safety, "result": "UNKNOWN"})["safe_attack_candidate"] is False
    assert evaluate(source, target, source_safety_evidence={
        **safety, "match_id": "m2"})["safe_attack_candidate"] is False
    assert evaluate(source, target, source_safety_evidence={
        **safety, "source_tower_id": 2})["safe_attack_candidate"] is False
    bad_force = dict(safety["proposed_units"])
    bad_force["Soldier"] -= 1
    assert evaluate(source, target, source_safety_evidence={
        **safety, "proposed_units": bad_force})["safe_attack_candidate"] is False


def test_attack_source_safety_unit_counts_reject_boolean_coercion():
    source, target = states()
    bad_force = dict(source.deployable_force.counts)
    bad_force["Soldier"] = True

    result = evaluate(source, target, source_safety_evidence={
        "result": "SAFE", "match_id": "m1", "source_tower_id": 1,
        "proposed_units": bad_force,
    })

    assert result["safe_attack_candidate"] is False
