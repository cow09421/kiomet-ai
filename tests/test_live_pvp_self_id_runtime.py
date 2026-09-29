import json
from types import SimpleNamespace

from kiomet_ai.live_controller import LiveController
from kiomet_ai.pvp_live import PlayerIdRegistry


def controller_for_test():
    controller = object.__new__(LiveController)
    controller._player_ids = PlayerIdRegistry()
    controller._player_ids_match_id = None
    controller.journal = {}
    return controller


def verified_source_snapshot(owner_id=5, path=(20, 10)):
    return {"collections": {"outbound": {"entries": [
        {"owner_id": owner_id, "path": list(path)},
    ]}}}


def test_live_controller_learns_self_id_only_from_two_verified_sides():
    controller = controller_for_test()
    candidate = {"source_owner": "SELF"}
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)

    learned = controller._learn_self_id_from_verified_dispatch(
        "match-a", candidate, action, verified_source_snapshot(),
        "FORCE_MATCH_VERIFIED", "FORCE_MATCH_VERIFIED")

    assert learned == 5
    assert controller._player_ids.self_id() == 5
    assert controller.journal["self_owner_id"] == 5
    assert controller.journal["self_owner_id_match_id"] == "match-a"


def test_live_controller_rejects_derived_target_match_and_wrong_path():
    controller = controller_for_test()
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)

    assert controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "SELF"}, action,
        verified_source_snapshot(), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_DERIVED") is None
    assert controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "SELF"}, action,
        verified_source_snapshot(path=(10, 20)),
        "FORCE_MATCH_VERIFIED", "FORCE_MATCH_VERIFIED") is None
    assert controller._player_ids.self_id() is None
    assert "self_owner_id" not in controller.journal


def test_live_controller_rejects_non_self_source():
    controller = controller_for_test()
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)

    assert controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "ENEMY"}, action,
        verified_source_snapshot(), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_VERIFIED") is None
    assert controller._player_ids.self_id() is None


def test_player_id_evidence_is_cleared_between_matches_and_menu():
    controller = controller_for_test()
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)
    assert controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "SELF"}, action,
        verified_source_snapshot(), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_VERIFIED") == 5

    controller._select_player_id_match("match-b")
    assert controller._player_ids_match_id == "match-b"
    assert controller._player_ids.self_id() is None
    assert "self_owner_id" not in controller.journal


def test_verified_self_id_is_added_to_differential_when_candidate_omits_it(
        tmp_path):
    controller = controller_for_test()
    controller.root = tmp_path
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)
    controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "SELF"}, action,
        verified_source_snapshot(), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_VERIFIED")

    controller._record_battle_differential(
        "match-a", "match-a:10->20:1000", action,
        {"source": {"units": {"Soldier": 4}},
         "target": {"units": {"Soldier": 2}}},
        {"source": {"units": {"Soldier": 0}},
         "target": {"owner": "ENEMY", "units": {"Soldier": 2}}},
        {"source_owner": "SELF", "target_owner": "ENEMY"})

    path = (tmp_path / "runtime/research/pvp_validation"
            / "match-a_10-_20_1000" / "battle-differential.json")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["source_owner_id"] == 5
    assert row["target_owner_id"] is None
    assert row["evaluation_status"] == "NOT_EVALUATED_UNKNOWN_IDS"


def test_differential_does_not_reuse_self_id_from_previous_match(tmp_path):
    controller = controller_for_test()
    controller.root = tmp_path
    action = SimpleNamespace(source_tower_id=10, target_tower_id=20)
    controller._learn_self_id_from_verified_dispatch(
        "match-a", {"source_owner": "SELF"}, action,
        verified_source_snapshot(), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_VERIFIED")

    controller._record_battle_differential(
        "match-b", "match-b:10->20:2000", action,
        {"source": {"units": {"Soldier": 4}},
         "target": {"units": {"Soldier": 2}}},
        {"source": {"units": {"Soldier": 0}},
         "target": {"owner": "ENEMY", "units": {"Soldier": 2}}},
        {"source_owner": "SELF", "target_owner": "ENEMY"})

    path = (tmp_path / "runtime/research/pvp_validation"
            / "match-b_10-_20_2000" / "battle-differential.json")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["source_owner_id"] is None
    assert row["target_owner_id"] is None
    assert row["evaluation_status"] == "NOT_EVALUATED_UNKNOWN_IDS"
    assert "self_owner_id" not in controller.journal
    assert "self_owner_id_match_id" not in controller.journal

    assert controller._learn_self_id_from_verified_dispatch(
        "match-b", {"source_owner": "SELF"}, action,
        verified_source_snapshot(owner_id=6), "FORCE_MATCH_VERIFIED",
        "FORCE_MATCH_VERIFIED") == 6
    controller._select_player_id_match(None)
    assert controller._player_ids.self_id() is None
    assert "self_owner_id" not in controller.journal
