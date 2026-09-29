from tools.combat_runtime_readiness import build_readiness


def _running_status(now=1000.0):
    return {
        "state": "RUNNING",
        "process": {"pid": 99, "started_at": now - 1},
        "uptime_seconds": 1,
        "browser": {"connected": True},
        "live": {"sequence": 3, "captured_at": now - 1},
        "game": {"state": "IN_MATCH", "match": {"id": "m-current"}},
        "live_authorization": {"enabled": True, "provenance": "explicit-test"},
        "controller": {
            "running": True, "cycle_id": 7,
            "last_cycle": {"match_id": "m-current", "cycle_id": 7,
                           "gate_state": "RUNNING", "authorization": True},
            "threat_state": {"match_id": "m-current", "cycle_id": 7,
                             "status": "CLEAR", "freshness": "FRESH",
                             "observed_at": now - 1,
                             "coverage": {"complete": True}, "threats": []},
            "attack_assessment": {"match_id": "m-current", "cycle_id": 7,
                                  "status": "NO_CANDIDATES", "evaluations": []},
        },
    }


def test_missing_runtime_is_unknown_and_does_not_invent_values():
    report = build_readiness(None, now=1000)
    assert report["status"] == "UNKNOWN"
    assert report["match_id"] is None
    assert report["checks"]["runtime"]["status"] == "UNKNOWN"


def test_disconnected_error_runtime_is_blocked_and_old_match_is_not_reused():
    status = _running_status()
    status.update(state="ERROR", browser={"connected": False})
    status["game"] = {"state": "UNKNOWN", "match": {"id": None}}
    status["controller"]["threat_state"] = {
        "match_id": "m-old", "cycle_id": 42, "status": "FRESH",
        "freshness": "FRESH", "observed_at": 999,
        "coverage": {"complete": True}, "threats": []}

    report = build_readiness(status, now=1000, process_alive=False)

    assert report["status"] == "BLOCKED"
    assert report["checks"]["runtime"]["status"] == "BLOCKED"
    assert report["checks"]["browser"]["status"] == "BLOCKED"
    assert report["match_id"] is None
    assert report["checks"]["world_freshness"]["status"] == "UNKNOWN"


def test_fresh_observation_without_enemy_target_keeps_identity_unknown():
    report = build_readiness(_running_status(), now=1000,
                             process_alive=True, max_cycle_age=15)

    assert report["status"] == "UNKNOWN"
    assert report["checks"]["world_freshness"]["status"] == "READY"
    assert report["checks"]["threat_eta"]["status"] == "READY"
    assert report["checks"]["attack_candidate"]["status"] == "PARTIAL"
    assert report["checks"]["enemy_evidence"]["status"] == "PARTIAL"
    assert report["checks"]["self_identity"]["status"] == "UNKNOWN"


def test_cross_cycle_candidate_cannot_satisfy_attack_gates():
    status = _running_status()
    status["controller"]["attack_assessment"] = {
        "match_id": "m-current", "cycle_id": 6,
        "evaluations": [{"match_id": "m-current", "cycle_id": 6,
                         "target_relation": "ENEMY", "attacker_owner_id": 5,
                         "source_safety": "SAFE", "action_validity_token": "OK",
                         "reservation": "AVAILABLE_NOT_HELD", "battle_supported": True}],
    }

    report = build_readiness(status, now=1000, process_alive=True)

    assert report["checks"]["attack_candidate"]["status"] == "BLOCKED"
    assert report["checks"]["source_safety"]["status"] == "BLOCKED"
    assert report["checks"]["action_validity"]["status"] == "BLOCKED"
    assert report["status"] == "BLOCKED"


def test_current_target_gate_needs_explicit_same_cycle_results():
    status = _running_status()
    status["controller"]["attack_assessment"] = {
        "match_id": "m-current", "cycle_id": 7,
        "evaluations": [{"match_id": "m-current", "cycle_id": 7,
                         "target_relation": "ENEMY", "attacker_owner_id": 5,
                         "source_safety": "SAFE", "action_validity_token": "OK",
                         "reservation": "AVAILABLE_NOT_HELD", "battle_supported": True}],
    }

    report = build_readiness(status, now=1000, process_alive=True)

    assert report["checks"]["self_identity"]["status"] == "READY"
    assert report["checks"]["battle"]["status"] == "READY"
    assert report["checks"]["source_safety"]["status"] == "READY"
    assert report["checks"]["action_validity"]["status"] == "READY"
    assert report["checks"]["reservation"]["status"] == "READY"
    assert report["status"] == "PARTIAL"


def test_only_same_action_enemy_evidence_can_validate_proof_and_replay():
    status = _running_status()
    status["controller"]["last_action"] = {
        "action_id": "a-1", "match_id": "m-current", "cycle_id": 7,
        "action_kind": "ATTACK_ENEMY", "force_observation_status": "FORCE_OBSERVED",
        "verdict": "ATTACK_WIN",
    }
    evidence = {"actions": [{"action_id": "a-1", "match_id": "m-current",
                             "action_kind": "ATTACK_ENEMY",
                             "attack_proof_status": "VALIDATED"}]}
    replay = {"replay": {"cases": [{"action_id": "a-1", "match_id": "m-current",
                                    "target_owner": "ENEMY", "status": "REPLAYED"}]}}

    report = build_readiness(status, now=1000, process_alive=True,
                             evidence_index=evidence, replay_index=replay)

    assert report["checks"]["moving_force"]["status"] == "READY"
    assert report["checks"]["verification"]["status"] == "READY"
    assert report["checks"]["enemy_evidence"]["status"] == "READY"
    assert report["checks"]["replay"]["status"] == "READY"


def test_non_attack_verdict_cannot_validate_enemy_attack():
    status = _running_status()
    status["controller"]["last_action"] = {
        "action_id": "a-2", "match_id": "m-current", "cycle_id": 7,
        "action_kind": "ATTACK_ENEMY", "force_observation_status": "FORCE_OBSERVED",
        "verdict": "TARGET_CAPTURED",
    }

    report = build_readiness(status, now=1000, process_alive=True)

    assert report["checks"]["verification"]["status"] == "UNKNOWN"


def test_stale_or_future_observations_do_not_become_fresh():
    status = _running_status()
    status["controller"]["threat_state"]["observed_at"] = 1010

    report = build_readiness(status, now=1000, process_alive=True)

    assert report["checks"]["world_freshness"]["status"] == "UNKNOWN"
    assert report["checks"]["observer"]["status"] == "UNKNOWN"


def test_stale_runtime_snapshot_is_blocked():
    status = _running_status(now=900)

    report = build_readiness(status, now=1000, process_alive=True,
                             max_state_age=30)

    assert report["checks"]["runtime"]["status"] == "BLOCKED"
    assert report["checks"]["browser"]["status"] == "UNKNOWN"
