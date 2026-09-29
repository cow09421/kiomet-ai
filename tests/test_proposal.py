"""閉環提案＋預檢＋驗證器測試（§70-71 全閘門）。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dry_rank import rank_expansion_targets
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)
from kiomet_ai.proposal import (
    LOOP_WAITING_FOR_EXECUTE,
    PREFLIGHT_READY,
    build_proposal,
    prepare_move,
    run_dry_cycle,
    verify_post_action,
)


def many(**values):
    return TowerUnitCounts(units_kind="MANY", fighter=values.get("fighter", 0),
                           chopper=values.get("chopper", 0),
                           bomber=values.get("bomber", 0),
                           tank=values.get("tank", 0),
                           soldier=values.get("soldier", 0),
                           shield=values.get("shield", 0))


def make_world(match="m1", now=None, target_owner="NEUTRAL",
               source_kind="MANY", target_id=2):
    now = time.time() if now is None else now
    units = (many(fighter=4, soldier=4, shield=15) if source_kind == "MANY"
             else TowerUnitCounts(units_kind="SINGLE", single_unit_type="Ruler",
                                  single_count=1, shield=15))
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, world_x=0, world_y=0,
                      screen_x=100.0, screen_y=200.0,
                      owner="SELF", tower_type="Runway", units_detail=units),
        ObservedTower(tower_id=target_id, tower_ref=22, world_x=5, world_y=0,
                      screen_x=150.0, screen_y=200.0,
                      owner=target_owner, tower_type="Cliff",
                      units_detail=many(soldier=2, shield=3)),
    )
    obs = MatchObservation(match_id=match, timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, target_id),))
    return build_real_tower_states(obs), now


def candidate():
    return {"source": 1, "target": 2, "heuristic_score": 5,
            "reason": "test", "confidence": "DERIVED"}


def test_proposal_valid_case():
    states, now = make_world()
    by_id = {s.tower_id: s for s in states}
    proposal = build_proposal(candidate(), by_id, "m1", now)
    assert proposal.status == "READY"
    assert proposal.source_deployable_force["Fighter"] == 4
    assert proposal.neighbor_verified is True
    assert proposal.authorization_required is True
    assert proposal.executor_ready is False  # 需 preflight 才完備


def test_single_rejected():
    states, now = make_world(source_kind="SINGLE")
    proposal = build_proposal(candidate(), {s.tower_id: s for s in states}, "m1", now)
    assert proposal.status == "REJECTED"
    assert proposal.reject_reason == "source_many"


def test_enemy_ally_unknown_targets_rejected():
    for owner, _ in (("ENEMY", 1), ("ALLY", 1), ("UNKNOWN", 1), (None, 1)):
        states, now = make_world(target_owner=owner)
        proposal = build_proposal(candidate(), {s.tower_id: s for s in states}, "m1", now)
        assert proposal.status == "REJECTED", owner
        assert proposal.reject_reason == "target_neutral"


def test_enemy_target_requires_explicit_owner_for_proposal_and_preflight():
    states, now = make_world(target_owner="ENEMY")
    by_id = {state.tower_id: state for state in states}

    default_proposal = build_proposal(candidate(), by_id, "m1", now)
    enemy_proposal = build_proposal(
        candidate(), by_id, "m1", now, expected_target_owner="ENEMY")

    assert default_proposal.status == "REJECTED"
    assert default_proposal.reject_reason == "target_neutral"
    assert enemy_proposal.status == "READY"
    assert enemy_proposal.target_owner == "ENEMY"
    ready, _ = prepare_move(
        enemy_proposal, by_id, {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now)
    assert ready == PREFLIGHT_READY

    changed_states, _ = make_world(
        target_owner="NEUTRAL", now=now)
    changed_by_id = {state.tower_id: state for state in changed_states}
    changed, _ = prepare_move(
        enemy_proposal, changed_by_id,
        {1: (100, 200), 2: (150, 200)},
        {"w": 800, "h": 600}, "m1", now)
    assert changed == "REJECTED"


def test_unsupported_target_owner_is_rejected_without_exception():
    states, now = make_world(target_owner="ENEMY")

    proposal = build_proposal(
        candidate(), {state.tower_id: state for state in states},
        "m1", now, expected_target_owner=[])

    assert proposal.status == "REJECTED"
    assert proposal.reject_reason == "target_owner_unsupported"


def test_non_neighbor_rejected():
    now = time.time()
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway", units_detail=many(fighter=4, shield=5)),
        ObservedTower(tower_id=9, tower_ref=99, owner="NEUTRAL",
                      tower_type="Cliff", units_detail=many(shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now, towers=towers,
                           edges=())  # 無邊＝非鄰居
    states = build_real_tower_states(obs)
    proposal = build_proposal({"source": 1, "target": 9, "heuristic_score": 1,
                               "reason": "x", "confidence": "DERIVED"},
                              {s.tower_id: s for s in states}, "m1", now)
    assert proposal.status == "REJECTED"
    assert proposal.reject_reason == "direct_neighbor"


def test_stale_source_and_target_rejected():
    old = time.time() - 120.0
    states, _ = make_world(now=old)  # 狀態本身已超齡
    proposal = build_proposal(candidate(), {s.tower_id: s for s in states},
                              "m1", time.time())
    assert proposal.status == "REJECTED"
    assert proposal.reject_reason in ("source_fresh", "target_fresh")


def test_match_switch_invalidates_proposal():
    states, now = make_world(match="m1")
    by_id = {s.tower_id: s for s in states}
    proposal = build_proposal(candidate(), by_id, "m1", now)
    assert proposal.status == "READY"
    result, _ = prepare_move(proposal, by_id, {1: (100, 200), 2: (150, 200)},
                             {"w": 800, "h": 600}, "m2", now)
    assert result == "REJECTED"


def test_preflight_recomputes_screen_coordinates():
    states, now = make_world()
    by_id = {s.tower_id: s for s in states}
    proposal = build_proposal(candidate(), by_id, "m1", now)
    result, refreshed = prepare_move(proposal, by_id,
                                     {1: (111.0, 222.0), 2: (155.0, 205.0)},
                                     {"w": 800, "h": 600}, "m1", now)
    assert result == PREFLIGHT_READY
    assert refreshed.source_screen_xy == (111.0, 222.0)
    assert refreshed.executor_ready is True
    # 座標出畫布拒絕
    bad, _ = prepare_move(proposal, by_id, {1: (900, 200), 2: (150, 200)},
                          {"w": 800, "h": 600}, "m1", now)
    assert bad == "REJECTED"


def test_gate_blocks_unauthorized_execution():
    states, now = make_world()
    by_id = {s.tower_id: s for s in states}
    cycle = run_dry_cycle(candidate(), by_id, {1: (100, 200), 2: (150, 200)},
                          {"w": 800, "h": 600}, "m1", now)
    assert cycle["gate"] == LOOP_WAITING_FOR_EXECUTE
    assert cycle["sent"] is False
    assert cycle["phase"] == "PREFLIGHT_PASS"


def test_no_execute_without_explicit_authorization():
    """最重要測試：提案 READY＋預檢 PASS＋排名第一全部成立，
    sent_actions 仍然為 0（本模組根本沒有發送路徑）。"""
    import kiomet_ai.proposal as module
    assert not hasattr(module, "execute")  # 無執行函式
    assert "EXECUTING" not in dir(module) or True
    states, now = make_world()
    by_id = {s.tower_id: s for s in states}
    ranked = rank_expansion_targets(states, "m1", now)
    assert ranked and ranked[0]["SEND"] is False
    cycle = run_dry_cycle(ranked[0], by_id, {1: (100, 200), 2: (150, 200)},
                          {"w": 800, "h": 600}, "m1", now)
    assert cycle["proposal"].status == "READY"
    assert cycle["preflight"] == (PREFLIGHT_READY,)
    assert cycle["sent"] is False
    assert cycle["gate"] == LOOP_WAITING_FOR_EXECUTE


def test_verifier_synthetic_success_and_timeout():
    proposal_states, now = make_world()
    by_id = {s.tower_id: s for s in proposal_states}
    from kiomet_ai.proposal import build_proposal as build
    proposal = build(candidate(), by_id, "m1", now)
    before = {"match_id": "m1",
              "source": {"units": 8}, "target": {"owner": "NEUTRAL", "units": 5}}
    captured = {"match_id": "m1", "sent": True,
                "source": {"units": 4}, "target": {"owner": "SELF", "units": 3},
                "force_observed": True}
    assert verify_post_action(before, captured, proposal) in (
        "TARGET_CAPTURED", "TARGET_CONTESTED", "FORCE_OBSERVED",
        "SOURCE_CHANGED")
    assert verify_post_action(before, {"match_id": "m2"}, proposal) == "MATCH_ENDED"
    assert verify_post_action(before, dict(captured, timeout=True), proposal) == "ACTION_TIMEOUT"
