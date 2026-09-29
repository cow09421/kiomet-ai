"""Force-poll identity inference must preserve ally/enemy color evidence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from force_poll import force_owner_relation, tower_owner_relation


def test_render_color_keeps_ally_and_enemy_separate():
    assert tower_owner_relation({"owner": "OTHER", "render_color": 2}) == "ALLY"
    assert tower_owner_relation({"owner": "OTHER", "render_color": 3}) == "ENEMY"


def test_other_without_render_color_remains_unknown():
    assert tower_owner_relation({"owner": "OTHER"}) is None
    assert tower_owner_relation({"owner": "OTHER", "render_color": 99}) is None


def test_force_relation_only_infers_from_explicit_source_relation():
    assert force_owner_relation("ENEMY", "SELF", "INBOUND") == "ENEMY"
    assert force_owner_relation("ALLY", "SELF", "INBOUND") == "ALLY"
    assert force_owner_relation("OTHER", "SELF", "INBOUND") == "UNKNOWN"
    assert force_owner_relation(None, "SELF", "INBOUND") == "UNKNOWN"


def test_only_self_outbound_proves_self_owner_relation():
    assert force_owner_relation("SELF", "NEUTRAL", "OUTBOUND") == "SELF"
    assert force_owner_relation("SELF", "SELF", "INBOUND") == "UNKNOWN"
