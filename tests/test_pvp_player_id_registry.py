"""Player ID lookup must abstain when evidence is missing or ambiguous."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.pvp_live import PlayerIdRegistry


def test_unique_relation_id_returns_only_one_observed_positive_id():
    registry = PlayerIdRegistry()
    registry.observe("SELF", 5)
    registry.observe("ENEMY", 12)
    registry.observe("ENEMY", 12)
    registry.observe("ALLY", 20)

    assert registry.unique_id("SELF") == 5
    assert registry.self_id() == 5
    assert registry.unique_id("ENEMY") == 12
    assert registry.unique_id("ALLY") == 20
    assert registry.unique_id("NEUTRAL") is None


def test_missing_unknown_and_ambiguous_relations_return_none():
    registry = PlayerIdRegistry()
    assert registry.unique_id("ENEMY") is None
    assert registry.unique_id("UNCLASSIFIED") is None
    assert registry.unique_id([]) is None

    registry.observe("ENEMY", 12)
    registry.observe("ENEMY", 26)

    assert registry.unique_id("ENEMY") is None


def test_invalid_owner_ids_never_create_or_confuse_registry_entries():
    registry = PlayerIdRegistry()
    for owner_id in (True, False, 0, -1, None, "12"):
        registry.observe("ENEMY", owner_id)

    assert registry.unique_id("ENEMY") is None

    registry.observe("ENEMY", 12)
    assert registry.unique_id("ENEMY") == 12
