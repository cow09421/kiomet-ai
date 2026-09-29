"""Dashboard threat telemetry stays fresh, bounded, and match scoped."""
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController


def controller_with_observation(*, active_match="m1", observed_at=None,
                                threats=None, status="OBSERVED_CANDIDATE"):
    controller = LiveController(SimpleNamespace(
        root=Path("."),
        browser=SimpleNamespace(game={"match": {"id": active_match}})))
    controller.journal["last_source_safety"] = {
        "match_id": "m1", "result": "UNKNOWN",
        "reason": "inbound-force-owner-unresolved",
        "observed_at": time.time() if observed_at is None else observed_at,
        "threat_observation_status": status,
        "threat_observation_reason": "complete-readonly-inbound-snapshot",
        "incoming_threats": threats if threats is not None else [{
            "match_id": "m1", "source_tower_id": 10,
            "target_tower_id": 20, "owner_relation": "ENEMY",
            "eta_ticks": 24, "eta_seconds": 6.0,
            "eta_status": "CANDIDATE", "confidence": "CANDIDATE",
        }],
    }
    return controller


def test_heartbeat_exposes_bounded_candidate_eta_with_explicit_confidence():
    heartbeat = controller_with_observation().heartbeat()

    observation = heartbeat["inbound_threat_observation"]
    assert observation["match_id"] == "m1"
    assert observation["status"] == "OBSERVED_CANDIDATE"
    assert observation["threats"] == [{
        "source_tower_id": 10, "target_tower_id": 20,
        "owner_relation": "ENEMY", "eta_ticks": 24,
        "eta_seconds": 6.0, "eta_status": "CANDIDATE",
    }]
    assert 0 <= observation["age_seconds"] < 30


def test_heartbeat_hides_observation_from_another_match():
    observation = controller_with_observation(active_match="m2").heartbeat()[
        "inbound_threat_observation"]

    assert observation["match_id"] is None
    assert observation["status"] == "UNKNOWN"
    assert observation["threats"] == []


def test_heartbeat_hides_candidate_rows_after_thirty_seconds():
    observation = controller_with_observation(
        observed_at=time.time() - 31).heartbeat()["inbound_threat_observation"]

    assert observation["match_id"] == "m1"
    assert observation["status"] == "STALE"
    assert observation["threats"] == []


def test_heartbeat_downgrades_malformed_eta_without_turning_it_into_zero():
    row = {
        "match_id": "m1", "source_tower_id": 10,
        "target_tower_id": 20, "owner_relation": "ENEMY",
        "eta_ticks": 24, "eta_seconds": True,
        "eta_status": "CANDIDATE", "confidence": "CANDIDATE",
    }
    observation = controller_with_observation(threats=[row]).heartbeat()[
        "inbound_threat_observation"]

    assert observation["status"] == "OBSERVED_CANDIDATE"
    assert observation["threats"][0]["eta_ticks"] == 24
    assert observation["threats"][0]["eta_seconds"] is None
    assert observation["threats"][0]["eta_status"] == "UNKNOWN"
