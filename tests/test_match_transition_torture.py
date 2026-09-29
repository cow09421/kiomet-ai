"""離線壓測完整對局轉換，確認舊局狀態不會授權新局行動。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from kiomet_ai.live_controller import LiveController


def _game(state: str, match_id: str | None, *, join_clicks: int = 0) -> dict:
    return {
        "state": state,
        "match": {"id": match_id},
        "join_clicks": join_clicks,
    }


def _old_decision_inputs(controller: LiveController, match_id: str,
                         cycle_id: int, source_id: int, target_id: int,
                         scenario: int) -> str:
    """注入不同識別碼的舊局狀態，讓真實轉換路徑負責隔離。"""
    action_id = f"{match_id}:{source_id}->{target_id}:{cycle_id}"
    self_id = 20_000 + scenario

    controller._select_player_id_match(match_id)
    controller._player_ids.observe("SELF", self_id)
    controller.journal["self_owner_id"] = self_id
    controller.journal["self_owner_id_match_id"] = match_id

    controller._select_reservation_match(match_id)
    assert controller._reservations.reserve(
        action_id, source_id=source_id, target_id=target_id) is None

    controller.journal.update({
        "current_proposal": {
            "source": source_id, "target": target_id,
            "match_id": match_id, "cycle_id": cycle_id,
            "action_kind": "ATTACK_ENEMY", "status": "READY",
        },
        "threat_state": {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
            "coverage": {"complete": True},
            "threats": [{"threat_id": f"enemy-{scenario}",
                         "match_id": match_id}],
        },
        "multi_threat_evaluation": {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SAFE", "evaluations": [],
        },
        "defense_assessment": {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "defense_evaluations": [],
        },
        "pvp_arbitration": {
            "match_id": match_id, "cycle_id": cycle_id,
            "action": "ATTACK_ENEMY", "evaluation_status": "SUPPORTED",
        },
        "attack_assessment": {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "SUPPORTED", "evaluations": [],
        },
        "last_action_validity": {
            "action_id": action_id, "match_id": match_id,
            "cycle_id": cycle_id, "status": "OK",
        },
        "last_source_safety": {
            "action_id": action_id, "match_id": match_id,
            "observed_at": time.time(),
            "threat_observation_status": "OBSERVED_CANDIDATE",
            "threat_observation_reason": "old-match fixture",
            "incoming_threats": [{"match_id": match_id,
                                  "source_tower_id": source_id,
                                  "target_tower_id": target_id}],
        },
        "last_verification": {
            "action_id": action_id, "match_id": match_id,
            "verdict": "TARGET_CAPTURED",
        },
    })
    return action_id


def _pending_dispatch(match_id: str, action_id: str, source_id: int,
                      target_id: int, status: str) -> dict:
    record = {
        "schema_version": 1,
        "action_id": action_id,
        "match_id": match_id,
        "source_tower_id": source_id,
        "target_tower_id": target_id,
        "action_kind": "ATTACK_ENEMY",
        "cycle_id": 7,
        "status": status,
        "created_at": 1_000.0,
        "join_clicks": 0,
        "browser_session_id": "same-isolated-session",
        "attack_validation_status": "VALIDATION_PENDING",
        "attack_proof_bundle": {
            "match_id": match_id,
            "action_id": action_id,
            "battle_differential_evidence_id": f"battle-{match_id}",
        },
        "before": {
            "match_id": match_id,
            "source": {"owner": "SELF", "units": {"Soldier": 20}},
            "target": {"owner": "ENEMY", "units": {"Soldier": 5}},
        },
    }
    if status in ("SENT", "VERIFICATION_UNKNOWN"):
        record["sent_at"] = 1_001.0
    if status == "VERIFICATION_UNKNOWN":
        record["last_verdict"] = "UNKNOWN"
    return record


@pytest.mark.parametrize("scenario", range(64))
def test_old_match_evidence_stays_stale_through_full_match_transition(
        tmp_path, scenario):
    """64 組不同身分／驗證狀態，走過結果、選單、加入與新對局。"""
    old_match = f"old-{scenario}"
    new_match = f"new-{scenario}"
    source_id = 1_000 + scenario * 2
    target_id = source_id + 1
    old_cycle = scenario + 10
    explicit_join = scenario % 2 == 0
    pending_status = ("PREPARED", "SENT", "VERIFICATION_UNKNOWN")[scenario % 3]

    browser = SimpleNamespace(
        game=_game("IN_MATCH", old_match),
        session_id="same-isolated-session",
    )
    app = SimpleNamespace(root=Path(tmp_path), browser=browser,
                          autonomy_paused=False)
    controller = LiveController(app)

    async def no_anchor(_match_id):
        return None

    controller.ensure_anchor = no_anchor
    old_action_id = f"{old_match}:{source_id}->{target_id}:{old_cycle}"
    if scenario % 4 != 0:
        controller._set_pending_dispatch(_pending_dispatch(
            old_match, old_action_id, source_id, target_id, pending_status))

    now = time.time()
    fresh_new_capture = {
        "action_id": f"{new_match}:{source_id}->{target_id}:new",
        "match_id": new_match, "target": target_id + 10_000,
        "since": now, "action_kind": "ATTACK_ENEMY",
    }
    controller.journal["pending_captures"] = [
        {"action_id": old_action_id, "match_id": old_match,
         "target": target_id, "since": now,
         "action_kind": "ATTACK_ENEMY"},
        fresh_new_capture,
    ]

    inactive_stages = (
        ("RESULT_SCREEN", old_match, 0),
        ("MENU", old_match if scenario % 3 else None, 0),
        ("JOINING", None, 1 if explicit_join else 0),
    )
    for step, (state, stage_match, join_clicks) in enumerate(inactive_stages):
        # Re-inject late old-cycle results at every boundary. They must not
        # survive the controller's normal out-of-match cycle handling.
        _old_decision_inputs(
            controller, old_match, old_cycle + step,
            source_id, target_id, scenario)
        browser.game = _game(state, stage_match, join_clicks=join_clicks)
        controller.cycle_seq = old_cycle + step
        phase, info = asyncio.run(controller.cycle_once())

        assert (phase, info["reason"]) == ("NO_SAFE_PROPOSAL", "not_in_match")
        assert controller._player_ids.self_id() is None
        assert controller._player_ids_match_id is None
        assert controller._reservations.holder(source_id) is None
        assert controller._reservations.holder(target_id) is None
        assert controller._reservation_match_id is None
        assert controller.journal["threat_state"]["status"] == "STALE"
        assert controller.journal["threat_state"]["match_id"] is None
        for key in ("multi_threat_evaluation", "defense_assessment",
                    "attack_assessment"):
            assert controller.journal[key]["status"] == "STALE"
            assert controller.journal[key]["match_id"] is None
        assert controller.journal["pvp_arbitration"]["action"] == "ABSTAIN"

    # A new match starts with new-cycle decision inputs, never the old READY
    # assessments. The missing visible anchor keeps the test fully offline.
    new_cycle = old_cycle + 100
    browser.game = _game(
        "IN_MATCH", new_match, join_clicks=1 if explicit_join else 0)
    controller.cycle_seq = new_cycle
    phase, info = asyncio.run(controller.cycle_once())
    assert (phase, info["reason"]) == ("NO_SAFE_PROPOSAL", "anchor_unavailable")
    assert info["match_id"] == new_match
    assert controller._player_ids.self_id() is None
    assert controller._player_ids_match_id == new_match
    assert controller._reservation_match_id == new_match
    assert controller._reservations.holder(source_id) is None
    assert controller.journal["threat_state"]["match_id"] == new_match
    assert controller.journal["threat_state"]["status"] == "UNKNOWN"
    for key in ("multi_threat_evaluation", "defense_assessment",
                "attack_assessment"):
        assert controller.journal[key]["match_id"] == new_match
        assert controller.journal[key]["status"] == "UNKNOWN"
    assert controller.journal["pvp_arbitration"]["action"] == "ABSTAIN"

    # Old action/proposal/evidence remain explicitly tagged with the old match;
    # they cannot satisfy this new cycle's threat gate or become an action.
    assert controller.journal["current_proposal"]["match_id"] == old_match
    assert controller.journal["last_action_validity"]["match_id"] == old_match
    assert controller.journal["last_verification"]["match_id"] == old_match
    assert controller._dashboard_inbound_observation()["status"] == "UNKNOWN"
    stale_candidate = {
        "validated": True, "match_id": old_match, "cycle_id": old_cycle,
        "source_tower_id": source_id, "target_tower_id": target_id,
        "preflight": "READY", "source_safety": "SAFE",
        "action_validity_token": "OK", "reservation": "HELD",
        "reservation_action_id": old_action_id,
    }
    decision = controller._arbitrate_prepared_action(
        new_match, new_cycle, stale_candidate)
    assert decision["action"] == "ABSTAIN"
    assert decision["evaluation_status"] == "UNKNOWN"

    # Even if fresh new-match assessments later become available, a caller
    # cannot promote the retained old proposal after its reservation vanished.
    controller.journal["threat_state"] = {
        "match_id": new_match, "cycle_id": new_cycle,
        "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
        "coverage": {"complete": True}, "threats": [],
    }
    controller.journal["multi_threat_evaluation"] = {
        "match_id": new_match, "cycle_id": new_cycle,
        "status": "SAFE", "evaluations": [],
    }
    controller.journal["defense_assessment"] = {
        "match_id": new_match, "cycle_id": new_cycle,
        "status": "SUPPORTED", "defense_evaluations": [],
    }
    controller.journal["attack_assessment"] = {
        "match_id": new_match, "cycle_id": new_cycle,
        "status": "NO_CONFIDENT_ENEMY_TARGETS", "evaluations": [],
    }
    decision = controller._arbitrate_prepared_action(
        new_match, new_cycle, stale_candidate)
    assert decision["action"] == "ABSTAIN"

    controller._check_pending_captures({}, new_match, time.time())
    assert controller.journal["pending_captures"] == [fresh_new_capture]

    pending = controller.journal.get("pending_dispatch")
    if scenario % 4 != 0:
        assert pending["match_id"] == old_match
        assert pending["action_id"] == old_action_id
        if not explicit_join:
            assert controller._reconcile_pending_dispatch({}, new_match) is True
            assert controller.journal["pending_dispatch"] == pending
            assert pending["before"]["match_id"] == old_match
            assert pending["attack_proof_bundle"]["match_id"] == old_match
        else:
            assert controller._reconcile_pending_dispatch({}, new_match) is False
            assert "pending_dispatch" not in controller.journal
    else:
        assert pending is None

    assert controller.journal.get("sent_actions", 0) == 0
    assert controller.journal.get("last_action") is None
