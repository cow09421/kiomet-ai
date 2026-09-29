"""SELF→SELF PvP reinforcement proposal and verification contract."""
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)
from kiomet_ai.proposal import (
    PREFLIGHT_READY,
    PROPOSAL_REJECTED,
    PROPOSAL_READY,
    build_reinforcement_proposal,
    prepare_move,
    verify_post_action,
)


def many(**values):
    return TowerUnitCounts(
        units_kind="MANY",
        fighter=values.get("fighter", 0),
        chopper=values.get("chopper", 0),
        bomber=values.get("bomber", 0),
        tank=values.get("tank", 0),
        soldier=values.get("soldier", 0),
        shield=values.get("shield", 0),
    )


def make_states(now=None, target_owner="SELF", adjacent=True):
    now = time.time() if now is None else now
    towers = (
        ObservedTower(
            tower_id=1, tower_ref=11, world_x=0, world_y=0,
            screen_x=100, screen_y=200, owner="SELF", tower_type="Runway",
            units_detail=many(fighter=8, soldier=3, shield=12)),
        ObservedTower(
            tower_id=2, tower_ref=22, world_x=5, world_y=0,
            screen_x=150, screen_y=200, owner=target_owner,
            tower_type="Cliff", units_detail=many(soldier=2, shield=5)),
    )
    edges = (ObservedEdge(1, 2),) if adjacent else ()
    observation = MatchObservation(
        match_id="m1", timestamp=now, towers=towers, edges=edges)
    states = build_real_tower_states(observation)
    return {state.tower_id: state for state in states}, now


def candidate_for(states, *, match_id="m1", cycle_id=7,
                  command_validated=True, force=None, unit_count=None):
    deployable = states[1].deployable_force.counts
    force = dict(deployable) if force is None else force
    return {
        "source_tower_id": 1,
        "match_id": match_id,
        "cycle_id": cycle_id,
        "full_deployable_force": force,
        "unit_count": (sum(force.values()) if unit_count is None
                       else unit_count),
        "command_validated": command_validated,
    }


def build(states, now, candidate=None, *, target=2, match_id="m1",
          cycle_id=7):
    candidate = candidate or candidate_for(states, cycle_id=cycle_id)
    return build_reinforcement_proposal(
        candidate, target, states, match_id, cycle_id, now)


def test_validated_reinforcement_builds_self_target_proposal_and_preflights():
    states, now = make_states()
    proposal = build(states, now)

    assert proposal.status == PROPOSAL_READY
    assert proposal.action_kind == "REINFORCE_SELF"
    assert proposal.cycle_id == 7
    assert proposal.source_owner == proposal.target_owner == "SELF"
    assert proposal.neighbor_verified is True
    assert proposal.source_deployable_force == states[1].deployable_force.counts

    ready, refreshed = prepare_move(
        proposal, states, {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now, cycle_id=7)
    assert ready == PREFLIGHT_READY
    assert refreshed.executor_ready is True


def test_reinforcement_rejects_missing_command_validation():
    states, now = make_states()
    proposal = build(
        states, now, candidate_for(states, command_validated=False))

    assert proposal.status == PROPOSAL_REJECTED
    assert proposal.reject_reason == "reinforcement_command_validated"


def test_reinforcement_rejects_non_exact_or_partial_force():
    states, now = make_states()
    force = dict(states[1].deployable_force.counts)
    force["Fighter"] -= 1
    proposal = build(states, now, candidate_for(states, force=force))
    assert proposal.status == PROPOSAL_REJECTED
    assert proposal.reject_reason == "reinforcement_full_force_exact"

    exact_force = dict(states[1].deployable_force.counts)
    proposal = build(
        states, now,
        candidate_for(states, force=exact_force,
                      unit_count=sum(exact_force.values()) - 1))
    assert proposal.status == PROPOSAL_REJECTED
    assert proposal.reject_reason == "reinforcement_unit_count_exact"


def test_reinforcement_rejects_stale_match_or_cycle_evidence():
    states, now = make_states()
    stale_match = build(
        states, now, candidate_for(states, match_id="m0"))
    stale_cycle = build(
        states, now, candidate_for(states, cycle_id=6))

    assert stale_match.status == PROPOSAL_REJECTED
    assert stale_match.reject_reason == "reinforcement_match_cycle"
    assert stale_cycle.status == PROPOSAL_REJECTED
    assert stale_cycle.reject_reason == "reinforcement_match_cycle"

    fresh = build(states, now)
    result, _ = prepare_move(
        fresh, states, {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now, cycle_id=8)
    assert result == "REJECTED"


def test_reinforcement_requires_fresh_self_neighbor_target():
    states, now = make_states(target_owner="ENEMY")
    enemy_target = build(states, now)
    assert enemy_target.status == PROPOSAL_REJECTED
    assert enemy_target.reject_reason == "target_self"

    states, now = make_states(adjacent=False)
    non_neighbor = build(states, now)
    assert non_neighbor.status == PROPOSAL_REJECTED
    assert non_neighbor.reject_reason == "reinforcement_bidirectional_neighbor"

    states, now = make_states()
    states[2] = replace(states[2], neighbors=())
    one_way = build(states, now)
    assert one_way.status == PROPOSAL_REJECTED
    assert one_way.reject_reason == "reinforcement_bidirectional_neighbor"


def test_reinforcement_preflight_rechecks_owner_kind_and_cycle():
    from dataclasses import replace

    states, now = make_states()
    proposal = build(states, now)
    changed_states, _ = make_states(now=now, target_owner="ENEMY")
    result, _ = prepare_move(
        proposal, changed_states, {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now, cycle_id=7)
    assert result == "REJECTED"

    malformed = replace(proposal, target_owner=[])
    result, _ = prepare_move(
        malformed, states, {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now, cycle_id=7)
    assert result == "REJECTED"


def test_self_reinforcement_verifier_does_not_report_capture():
    states, now = make_states()
    proposal = build(states, now)
    before = {"source": {"units": 8}, "target": {"owner": "SELF"}}
    sent = {"match_id": "m1", "source": {"units": 8},
            "target": {"owner": "SELF"}, "sent": True}
    unchanged = {"match_id": "m1", "source": {"units": 8},
                 "target": {"owner": "SELF"}}

    assert verify_post_action(before, sent, proposal) == "ACTION_SENT"
    assert verify_post_action(before, unchanged, proposal) == "UNKNOWN"


def test_reinforcement_force_observation_requires_route_correlation():
    states, now = make_states()
    proposal = build(states, now)
    before = {"source": {"units": 8}, "target": {"owner": "SELF"}}
    after = {
        "match_id": "m1", "source": {"units": 7},
        "target": {"owner": "SELF", "units": 4},
        "force_observed": True,
        "force_match": "FORCE_MATCH_VERIFIED",
        "force_path": (1, 2),
        "action_id": "m1:1->2:1790000000",
        "temporal_status": "TEMPORAL_OK",
        "action_origin": "LIVE_CONTROLLER",
    }
    assert verify_post_action(before, after, proposal) == "FORCE_OBSERVED"

    after["force_path"] = (1, 3)
    assert verify_post_action(before, after, proposal) == "SOURCE_CHANGED"


def test_reinforcement_target_losing_self_ownership_is_contested():
    states, now = make_states()
    proposal = build(states, now)
    before = {"source": {"units": 8}, "target": {"owner": "SELF"}}
    after = {"match_id": "m1", "source": {"units": 8},
             "target": {"owner": "ENEMY"}}

    assert verify_post_action(before, after, proposal) == "TARGET_CONTESTED"
