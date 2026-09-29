"""SELF ID 僅能由精確驗證的己方派兵路徑學習。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.pvp_live import PlayerIdRegistry


def test_verified_self_dispatch_learns_owner_id():
    registry = PlayerIdRegistry()
    outgoing = [{"owner_id": 5, "path": [16843032, 16843031]}]

    result = registry.observe_verified_self_dispatch(
        "SELF", 16843031, 16843032, "FORCE_MATCH_VERIFIED", outgoing)

    assert result == 5
    assert registry.self_id() == 5


def test_unverified_or_ambiguous_force_never_teaches_self_id():
    registry = PlayerIdRegistry()
    exact = {"owner_id": 5, "path": [16843032, 16843031]}
    cases = (
        ("OTHER", "FORCE_MATCH_VERIFIED", [exact]),
        ("SELF", "FORCE_MATCH_DERIVED", [exact]),
        ("SELF", "FORCE_MATCH_VERIFIED",
         [{"owner_id": 5, "path": [16843031, 16843032]}]),
        ("SELF", "FORCE_MATCH_VERIFIED", [exact, dict(exact)]),
        ("SELF", "FORCE_MATCH_VERIFIED",
         [{"owner_id": True, "path": [16843032, 16843031]}]),
    )

    for source_relation, status, forces in cases:
        assert registry.observe_verified_self_dispatch(
            source_relation, 16843031, 16843032, status, forces) is None

    assert registry.self_id() is None


def test_invalid_tower_ids_and_unknown_force_list_are_rejected():
    registry = PlayerIdRegistry()
    exact = [{"owner_id": 5, "path": [20, 10]}]

    assert registry.observe_verified_self_dispatch(
        "SELF", True, 20, "FORCE_MATCH_VERIFIED", exact) is None
    assert registry.observe_verified_self_dispatch(
        "SELF", 10, 20, "FORCE_MATCH_VERIFIED", None) is None
    assert registry.self_id() is None


def test_conflicting_verified_self_id_is_rejected_without_replacing_known_id():
    registry = PlayerIdRegistry()
    first = [{"owner_id": 5, "path": [20, 10]}]
    conflicting = [{"owner_id": 6, "path": [20, 10]}]

    assert registry.observe_verified_self_dispatch(
        "SELF", 10, 20, "FORCE_MATCH_VERIFIED", first) == 5
    assert registry.observe_verified_self_dispatch(
        "SELF", 10, 20, "FORCE_MATCH_VERIFIED", conflicting) is None
    assert registry.self_id() == 5


def test_conflicting_relation_evidence_makes_self_id_unknown():
    registry = PlayerIdRegistry()
    registry.observe("SELF", 5)
    registry.observe("SELF", 6)

    assert registry.self_id() is None


def test_boolean_owner_id_is_not_a_player_id():
    registry = PlayerIdRegistry()

    registry.observe("SELF", True)
    assert registry.self_id() is None
    assert not registry.known_id("SELF", True)
