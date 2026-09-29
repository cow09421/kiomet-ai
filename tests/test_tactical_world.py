"""戰術世界資料回歸（P1 §7）。

所有權/部隊/ETA/受威脅塔/路徑皆來自真實後端；缺資料 UNKNOWN，不補 0。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.tactical_world import build_tactical, classify_route


def test_classify_route():
    assert classify_route("SELF", "ENEMY") == "ATTACK"
    assert classify_route("SELF", "ALLY") == "REINFORCE"
    assert classify_route("ALLY", "SELF") == "REINFORCE"
    assert classify_route("SELF", "NEUTRAL") == "EXPAND"
    assert classify_route("SELF", "UNKNOWN") == "UNKNOWN"
    assert classify_route("NEUTRAL", "NEUTRAL") == "UNKNOWN"
    assert classify_route(None, None) == "UNKNOWN"


def _payload(**over):
    base = {
        "match_id": "m1",
        "towers_complete": True,
        "towers": [
            {"id": 1, "position": [0, 0], "owner": "SELF", "tower_type": "SHIELD"},
            {"id": 2, "position": [10, 10], "owner": "NEUTRAL"},
            {"id": 3, "x": 20, "y": 20, "owner": "ENEMY"},
            {"id": 4, "x": 30, "y": 30},  # owner 缺 → UNKNOWN
        ],
        "edges": [[1, 2], [2, 3]],
        "threat_state": {
            "match_id": "m1",
            "freshness": "FRESH",
            "status": "OBSERVED_CANDIDATE",
            "threats": [
                {"source_tower_id": 3, "target_tower_id": 1,
                 "owner_relation": "ENEMY", "eta_status": "CANDIDATE",
                 "eta_seconds": 12.5},
            ],
        },
        "current_proposal": {"source": 1, "target": 2},
        "last_action": {"source": 1, "target": 3},
    }
    base.update(over)
    return base


def test_build_basic_fields():
    result = build_tactical(_payload())
    assert result["match_id"] == "m1"
    assert len(result["towers"]) == 4
    assert result["towers"][3]["owner"] == "UNKNOWN"
    assert result["fidelity"] == "REAL_BACKEND_DATA"


def test_owner_counts():
    result = build_tactical(_payload())
    assert result["owner_count_status"] == "KNOWN"
    assert result["owners"] == {"SELF": 1, "NEUTRAL": 1, "ENEMY": 1,
                                "ALLY": 0, "UNKNOWN": 1}


def test_moving_forces_and_threatened():
    result = build_tactical(_payload())
    assert result["moving_status"] == "KNOWN"
    assert result["moving_forces"][0]["owner_relation"] == "ENEMY"
    assert result["moving_forces"][0]["eta_seconds"] == 12.5
    assert result["threatened"][0]["tower"] == 1
    assert result["threatened"][0]["eta_seconds"] == 12.5


def test_unknown_threat_state_is_unknown():
    result = build_tactical(_payload(threat_state={"status": "UNKNOWN"}))
    assert result["moving_status"] == "UNKNOWN"
    assert result["moving_forces"] == []
    assert result["threatened"] == []


def test_eta_missing_stays_none_not_zero():
    payload = _payload(threat_state={
        "match_id": "m1",
        "freshness": "FRESH",
        "status": "OBSERVED_CANDIDATE",
        "threats": [{"source_tower_id": 3, "target_tower_id": 1,
                     "owner_relation": "ENEMY", "eta_status": "UNKNOWN"}]})
    result = build_tactical(payload)
    assert result["moving_forces"][0]["eta_seconds"] is None


def test_old_match_threat_snapshot_is_stale_and_not_rendered():
    result = build_tactical(_payload(threat_state={
        "match_id": "m0",
        "freshness": "FRESH",
        "status": "OBSERVED_CANDIDATE",
        "threats": [{"source_tower_id": 3, "target_tower_id": 1,
                     "owner_relation": "ENEMY", "eta_status": "CANDIDATE",
                     "eta_seconds": 5}],
    }))
    assert result["moving_status"] == "STALE"
    assert result["moving_forces"] == []
    assert result["threatened"] == []


def test_stale_same_match_threat_snapshot_is_not_rendered():
    result = build_tactical(_payload(threat_state={
        "match_id": "m1",
        "freshness": "STALE",
        "status": "OBSERVED_CANDIDATE",
        "threats": [{"source_tower_id": 3, "target_tower_id": 1,
                     "owner_relation": "ENEMY", "eta_status": "CANDIDATE",
                     "eta_seconds": 5}],
    }))
    assert result["moving_status"] == "STALE"
    assert result["moving_forces"] == []
    assert result["threatened"] == []


def test_threat_without_match_or_freshness_is_unknown():
    for threat_state in (
        {"freshness": "FRESH", "status": "OBSERVED_CANDIDATE",
         "threats": []},
        {"match_id": "m1", "status": "OBSERVED_CANDIDATE",
         "threats": []},
    ):
        result = build_tactical(_payload(threat_state=threat_state))
        assert result["moving_status"] == "UNKNOWN"
        assert result["moving_forces"] == []


def test_observed_candidate_without_a_threat_list_is_unknown():
    result = build_tactical(_payload(threat_state={
        "match_id": "m1", "freshness": "FRESH",
        "status": "OBSERVED_CANDIDATE",
    }))
    assert result["moving_status"] == "UNKNOWN"
    assert result["moving_forces"] == []


def test_fresh_same_match_clear_threat_state_is_known():
    result = build_tactical(_payload(threat_state={
        "match_id": "m1", "freshness": "FRESH",
        "status": "CLEAR", "threats": [],
    }))
    assert result["moving_status"] == "KNOWN"
    assert result["moving_forces"] == []


def test_routes_classified():
    result = build_tactical(_payload())
    assert {"origin": "last", "source": 1, "target": 3} in \
        result["routes"]["ATTACK"]
    assert {"origin": "planned", "source": 1, "target": 2} in \
        result["routes"]["EXPAND"]
    assert result["routes"]["REINFORCE"] == []


def test_reinforcement_route():
    payload = _payload(current_proposal={"source": 1, "target": 1})
    result = build_tactical(payload)
    assert result["routes"]["REINFORCE"][0]["source"] == 1


def test_empty_payload_all_unknown():
    result = build_tactical(None)
    assert result["match_id"] is None
    assert result["towers"] == []
    assert result["moving_status"] == "UNKNOWN"
    assert result["owner_count_status"] == "UNKNOWN"
    assert all(value is None for value in result["owners"].values())


def test_partial_tower_snapshot_does_not_turn_missing_owners_into_zero():
    result = build_tactical({
        "match_id": "m1",
        "towers": [{"id": 1, "owner": "SELF"}],
    })
    assert result["owner_count_status"] == "UNKNOWN"
    assert all(value is None for value in result["owners"].values())


def test_explicit_complete_empty_tower_snapshot_has_known_zero_counts():
    result = build_tactical({
        "match_id": "m1",
        "towers": [],
        "towers_complete": True,
    })
    assert result["owner_count_status"] == "KNOWN"
    assert result["owners"] == {owner: 0 for owner in
                                 ("SELF", "NEUTRAL", "ENEMY", "ALLY", "UNKNOWN")}


def test_malformed_row_prevents_complete_zero_count_claim():
    result = build_tactical({
        "towers": [None],
        "towers_complete": True,
    })
    assert result["owner_count_status"] == "UNKNOWN"
    assert all(value is None for value in result["owners"].values())


def test_edges_filtered_to_lists():
    result = build_tactical(_payload(edges=[[1, 2], "bad", [2, 3]]))
    assert result["edges"] == [[1, 2], [2, 3]]
