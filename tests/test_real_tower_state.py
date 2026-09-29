"""RealTowerState（真實塔狀態）資料契約測試。

覆蓋：完整契約欄位、deployable_units（可派兵量）永遠 UNKNOWN、
鄰居雙向、跨局 STALE（陳舊）、超齡 STALE。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.observe import (
    UNITS_KIND_UNKNOWN,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
    build_snapshot,
    decode_tower_units,
)


def make_obs(age_s=5.0, match="m1"):
    units_raw = [0] * 48
    units_raw[38:45] = [0, 4, 0, 0, 0, 12, 20]
    counts = decode_tower_units(units_raw, tower_ref=99, observed_at=1.0)
    obs = build_snapshot(
        match, {"cx": 1.0}, {"w": 2}, 1.0,
        [{"packed_id": 7, "tower_ref": 99, "position": [10, 20],
          "owner": "SELF", "tower_type": "Runway"}],
        [(7, 8), (7, 9)], {7: (100.0, 200.0)},
        timestamp=time.time() - age_s)
    # 塞入解碼後的兵力（模擬正式 Observer 流程）
    tower = obs.towers[0]
    tower = ObservedTower(
        tower_id=tower.tower_id, tower_ref=tower.tower_ref,
        world_x=tower.world_x, world_y=tower.world_y,
        screen_x=tower.screen_x, screen_y=tower.screen_y,
        owner=tower.owner, owner_confidence="HIGH",
        tower_type=tower.tower_type, units_detail=counts)
    object.__setattr__(obs, "towers", (tower,))
    return obs, counts


def test_contract_fields_complete():
    obs, counts = make_obs()
    states = build_real_tower_states(obs)
    assert len(states) == 1
    s = states[0]
    assert s.tower_id == 7
    assert s.match_id == "m1"
    assert s.tower_ref == 99
    assert (s.world_x, s.world_y) == (10, 20)
    assert (s.screen_x, s.screen_y) == (100.0, 200.0)
    assert s.owner == "SELF"
    assert s.owner_confidence == "HIGH"
    assert s.tower_type == "Runway"
    assert s.units_kind == "MANY"
    assert s.unit_counts is counts


def test_deployable_units_always_unknown():
    obs, _ = make_obs()
    s = build_real_tower_states(obs)[0]
    assert s.deployable_units is None  # force_units 未驗證
    assert s.upgrade_state is None


def test_neighbors_bidirectional():
    obs, _ = make_obs()
    states = {s.tower_id: s for s in build_real_tower_states(obs)}
    assert states[7].neighbors == (8, 9)
    # 8、9 不在錨點塔清單，不應出現狀態
    assert 8 not in states and 9 not in states


def test_tower_state_stale_on_match_change():
    obs, _ = make_obs(match="m1")
    s = build_real_tower_states(obs)[0]
    assert s.freshness("m1") == "FRESH"
    assert s.freshness("m2") == "STALE"  # 換局立即 STALE


def test_tower_state_stale_on_age():
    obs, _ = make_obs(age_s=120.0)
    s = build_real_tower_states(obs)[0]
    assert s.freshness("m1") == "STALE"  # 超齡 STALE


def test_no_units_detail_is_unknown_kind():
    obs = build_snapshot("m1", {}, {}, 1.0,
                         [{"packed_id": 1, "position": [0, 0]}], [], {})
    s = build_real_tower_states(obs)[0]
    assert s.units_kind == UNITS_KIND_UNKNOWN
    assert s.unit_counts is None
    assert s.neighbors == ()
