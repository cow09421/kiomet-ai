import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (MatchObservation, build_snapshot, gate_check)


def make_obs(match="m1", age_s=5.0):
    return build_snapshot(
        match, {"cx": 1.0}, {"w": 2}, 1.0,
        [{"packed_id": 7, "tower_ref": 99, "position": [10, 20],
          "owner": "SELF"}],
        [(7, 8)], {7: (100.0, 200.0)}, timestamp=time.time() - age_s)


def test_match_change_invalidates():
    obs = make_obs("m1")
    assert obs.freshness("m1") == "FRESH"
    assert obs.freshness("m2") == "STALE"
    ok, _ = gate_check(obs, "m2")
    assert not ok


def test_age_invalidates_screen_mapping():
    fresh = make_obs("m1", age_s=5.0)
    old = make_obs("m1", age_s=120.0)
    assert fresh.freshness("m1") == "FRESH"
    assert old.freshness("m1") == "STALE"
    ok, _ = gate_check(old, "m1")
    assert not ok


def test_unknown_owner_never_becomes_self():
    obs = build_snapshot("m1", {}, {}, 1.0,
                         [{"packed_id": 1, "position": [0, 0], "owner": "UNKNOWN"},
                          {"packed_id": 2, "position": [1, 1]}],
                         [], {})
    by_id = {t.tower_id: t for t in obs.towers}
    assert by_id[1].owner is None
    assert by_id[2].owner is None
    assert all(t.owner_confidence == "UNKNOWN" for t in obs.towers)


def test_stale_units_rejected_and_unknown_default():
    obs = make_obs("m1", age_s=60.0)
    assert obs.towers[0].units is None
    ok, reason = gate_check(obs, "m1")
    assert not ok and "STALE" in reason


def test_snapshot_carries_identity_and_screen():
    obs = make_obs("m9")
    assert obs.match_id == "m9"
    tower = obs.tower(7)
    assert tower is not None
    assert (tower.world_x, tower.world_y) == (10, 20)
    assert (tower.screen_x, tower.screen_y) == (100.0, 200.0)
    assert tower.owner == "SELF"
