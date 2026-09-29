"""Live inbound threat diagnostics are match-bound and never action authority."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import UNIT_NAMES
from kiomet_ai.live_controller import LiveController
from kiomet_ai.pvp_live import PlayerIdRegistry, candidate_inbound_threats


def state(tower_id, owner, x, y=0.0, match_id="m1"):
    return SimpleNamespace(
        tower_id=tower_id, match_id=match_id, owner=owner,
        world_x=x, world_y=y,
        freshness=lambda current, _now: (
            "FRESH" if current == match_id else "STALE"),
    )


def snapshot(*entries, match_id="m1", length=None):
    if length is None:
        length = len(entries)
    return {"match_id": match_id, "captured_at": time.time(),
            "collections": {
                "inbound": {"length": length, "entries": list(entries)},
                "outbound": {"length": 0, "entries": []},
            }}


def force_entry(*, owner_id=42, path=(2, 1), progress=37):
    units = {name: 0 for name in UNIT_NAMES}
    units["Soldier"] = 4
    return {"ref": 99, "owner_id": owner_id, "path": list(path),
            "units": units, "speed_flag": 0, "progress": progress,
            "endurance": 20}


def test_candidate_inbound_fact_has_eta_and_unverified_relation_confidence():
    result = candidate_inbound_threats(
        snapshot(force_entry()), state(2, "SELF", 100.0),
        {1: state(1, "ENEMY", 0.0), 2: state(2, "SELF", 100.0)},
        "m1", self_id=7, player_ids=PlayerIdRegistry())

    assert result["status"] == "OBSERVED_CANDIDATE"
    assert result["threats"] == [{
        "force_identity": None, "target_tower_id": 2,
        "source_tower_id": 1, "source_player": 42, "owner_id": 42,
        "owner_relation": "ENEMY", "units": force_entry()["units"],
        "progress": 37, "eta_ticks": 109, "eta_seconds": 27.25,
        "freshness": "FRESH", "confidence": "CANDIDATE",
        "match_id": "m1", "relation_confidence": "CANDIDATE",
        "eta_status": "CANDIDATE",
    }]


def test_empty_complete_inbound_snapshot_is_clear():
    result = candidate_inbound_threats(
        snapshot(), state(2, "SELF", 100.0), {2: state(2, "SELF", 100.0)},
        "m1")

    assert result == {"status": "CLEAR",
                      "reason": "complete-empty-inbound", "threats": []}


def test_missing_source_position_keeps_force_but_eta_unknown():
    result = candidate_inbound_threats(
        snapshot(force_entry()), state(2, "SELF", 100.0),
        {2: state(2, "SELF", 100.0)}, "m1")

    assert result["status"] == "OBSERVED_CANDIDATE"
    assert result["threats"][0]["eta_ticks"] is None
    assert result["threats"][0]["eta_status"] == "UNKNOWN"
    assert result["threats"][0]["owner_relation"] == "UNKNOWN"


def test_incomplete_or_cross_match_snapshots_are_unknown():
    target = state(2, "SELF", 100.0)
    states = {1: state(1, "ENEMY", 0.0), 2: target}

    incomplete = candidate_inbound_threats(
        snapshot(force_entry(), length=2), target, states, "m1")
    stale = candidate_inbound_threats(
        snapshot(force_entry(), match_id="m2"), target, states, "m1")

    assert incomplete["status"] == "UNKNOWN"
    assert incomplete["threats"] == []
    assert stale["status"] == "UNKNOWN"
    assert stale["threats"] == []


def test_live_source_gate_exposes_enemy_eta_but_still_abstains():
    live = LiveController(SimpleNamespace(root=Path("."), browser=None))
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    target = state(2, "SELF", 100.0)
    enemy = state(1, "ENEMY", 0.0)
    target.unit_counts = SimpleNamespace(
        units_kind="MANY", shield=20, fighter=0, chopper=0,
        bomber=0, tank=0, soldier=20)
    target.owner_ruler = False
    target.tower_type = "Cliff"
    proposed = {name: 0 for name in UNIT_NAMES}

    result = live.evaluate_live_source_safety(
        "m1", target, snapshot(force_entry()), proposed,
        tower_states_by_id={1: enemy, 2: target})

    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "inbound-force-owner-unresolved"
    assert result["threat_observation_status"] == "OBSERVED_CANDIDATE"
    assert result["incoming_threats"][0]["owner_relation"] == "ENEMY"
    assert result["incoming_threats"][0]["eta_ticks"] == 109


def test_malformed_foreign_force_keeps_owner_gate_reason_and_unknown_eta():
    live = LiveController(SimpleNamespace(root=Path("."), browser=None))
    live._select_player_id_match("m1")
    live._player_ids.observe("SELF", 7)
    target = state(2, "SELF", 100.0)
    target.unit_counts = SimpleNamespace(
        units_kind="MANY", shield=20, fighter=0, chopper=0,
        bomber=0, tank=0, soldier=20)
    target.owner_ruler = False
    target.tower_type = "Cliff"
    proposed = {name: 0 for name in UNIT_NAMES}

    result = live.evaluate_live_source_safety(
        "m1", target, snapshot({"owner_id": 42}), proposed,
        tower_states_by_id={2: target})

    assert result["result"] == "UNKNOWN"
    assert result["reason"] == "inbound-force-owner-unresolved"
    assert result["threat_observation_status"] == "UNKNOWN"
    assert result["incoming_threats"] == []
